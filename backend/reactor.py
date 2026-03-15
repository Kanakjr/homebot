"""
Reactor: autonomous auto-actions engine.

- Scheduled triggers via APScheduler (cron)
- State-change triggers from HA WebSocket events
- Event logging for daily summaries
- Proactive smart notifications (printer done, battery low, welcome home)
- Executes skills in static or AI-powered mode
- Sends notifications to Telegram
"""

import asyncio
import json
import logging
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from notifier import TelegramNotifier
from state import StateCache
from memory.procedural import ProceduralMemory
from tools.registry import ToolMap

log = logging.getLogger("homebot.reactor")

NOTIFICATION_COOLDOWN = 300  # 5 minutes per entity per rule

NOTABLE_DOMAINS = {
    "person", "device_tracker", "light", "switch", "fan", "climate",
    "media_player", "automation", "sensor", "binary_sensor", "camera", "lock",
}


class Reactor:
    def __init__(
        self,
        state_cache: StateCache,
        procedural: ProceduralMemory,
        agent,
        notifier: TelegramNotifier,
    ):
        self.state = state_cache
        self.procedural = procedural
        self.agent = agent
        self.notifier = notifier
        self.scheduler = AsyncIOScheduler(timezone=config.TZ)
        self._tool_map: ToolMap | None = None
        self._notif_cooldowns: dict[str, float] = {}

    def set_tool_map(self, tool_map: ToolMap):
        self._tool_map = tool_map

    async def start(self):
        self.state.on_state_change(self._on_state_change)

        triggered_skills = await self.procedural.get_triggered_skills()
        for skill in triggered_skills:
            self._register_trigger(skill)

        self.scheduler.add_job(
            self._prune_event_log, CronTrigger.from_crontab("0 3 * * *"),
            id="prune_event_log", replace_existing=True,
        )

        self.scheduler.start()
        log.info("Reactor started with %d triggered skills", len(triggered_skills))

    async def stop(self):
        self.scheduler.shutdown(wait=False)
        log.info("Reactor stopped")

    async def reload_triggers(self):
        for job in self.scheduler.get_jobs():
            if job.id.startswith("skill_"):
                job.remove()
        triggered_skills = await self.procedural.get_triggered_skills()
        for skill in triggered_skills:
            self._register_trigger(skill)
        log.info("Reloaded %d triggered skills", len(triggered_skills))

    def _register_trigger(self, skill: dict):
        trigger = skill.get("trigger", {})
        ttype = trigger.get("type")

        if ttype == "schedule":
            cron_expr = trigger.get("cron", "")
            if cron_expr:
                try:
                    self.scheduler.add_job(
                        self.fire_skill,
                        CronTrigger.from_crontab(cron_expr),
                        args=[skill["id"]],
                        id=f"skill_{skill['id']}",
                        replace_existing=True,
                    )
                    log.info("Scheduled skill '%s' with cron '%s'", skill["name"], cron_expr)
                except Exception:
                    log.exception("Failed to schedule skill %s", skill["id"])

    async def _on_state_change(self, entity_id: str, old_state: dict | None, new_state: dict):
        domain = entity_id.split(".")[0]

        if domain in NOTABLE_DOMAINS:
            old_val = old_state.get("state", "") if old_state else ""
            new_val = new_state.get("state", "")
            if old_val != new_val:
                await self.procedural.log_event(
                    entity_id=entity_id,
                    old_state=old_val,
                    new_state=new_val,
                    event_type="state_change",
                )

        await self._check_proactive_notifications(entity_id, old_state, new_state)

        triggered_skills = await self.procedural.get_triggered_skills()
        for skill in triggered_skills:
            trigger = skill.get("trigger", {})
            if trigger.get("type") != "state_change":
                continue
            if trigger.get("entity_id") != entity_id:
                continue
            if not self._matches_condition(trigger, old_state, new_state):
                continue
            log.info("State trigger matched for skill '%s'", skill["name"])
            asyncio.create_task(self.fire_skill(skill["id"], context={
                "entity_id": entity_id,
                "old_state": old_state.get("state", "") if old_state else "",
                "new_state": new_state.get("state", ""),
            }))

    @staticmethod
    def _matches_condition(trigger: dict, old_state: dict | None, new_state: dict) -> bool:
        new_val = new_state.get("state", "")
        old_val = old_state.get("state", "") if old_state else ""

        if "to" in trigger:
            if new_val != trigger["to"]:
                return False
            if old_val == trigger["to"]:
                return False

        if "from" in trigger:
            if old_val != trigger["from"]:
                return False

        if "above" in trigger:
            try:
                if float(new_val) <= float(trigger["above"]):
                    return False
                if old_val and float(old_val) > float(trigger["above"]):
                    return False
            except (ValueError, TypeError):
                return False

        if "below" in trigger:
            try:
                if float(new_val) >= float(trigger["below"]):
                    return False
                if old_val and float(old_val) < float(trigger["below"]):
                    return False
            except (ValueError, TypeError):
                return False

        return True

    async def fire_skill(self, skill_id: str, context: dict | None = None) -> str | None:
        """Execute a skill by ID. Returns the result text, or None if skill not found/inactive."""
        skill = await self.procedural.get_skill(skill_id)
        if not skill or not skill.get("active"):
            return None

        log.info("Firing skill: %s (mode=%s)", skill["name"], skill["mode"])

        try:
            if skill["mode"] == "static":
                result_text = await self._execute_static(skill)
            elif skill["mode"] == "ai":
                result_text = await self._execute_ai(skill, context)
            else:
                result_text = f"Unknown mode for skill {skill['name']}"

            if skill.get("notify"):
                await self.notifier.send(result_text)

            return result_text
        except Exception:
            log.exception("Failed to fire skill %s", skill_id)
            return f"Error executing skill '{skill['name']}'"

    async def fire_skill_by_name(self, query: str, context: dict | None = None) -> str:
        """Look up a skill by name or ID and execute it. Returns result text."""
        import re
        skill = await self.procedural.get_skill(query)
        if not skill:
            slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
            skill = await self.procedural.get_skill(slug)
        if not skill:
            all_skills = await self.procedural.list_skills()
            for s in all_skills:
                if s["name"].lower() == query.lower():
                    skill = s
                    break
        if not skill:
            return f"Skill '{query}' not found. Use /skills to see available skills."
        if not skill.get("active"):
            return f"Skill '{skill['name']}' is disabled."
        return await self.fire_skill(skill["id"], context) or f"Skill '{skill['name']}' returned no result."

    async def _execute_static(self, skill: dict) -> str:
        if not self._tool_map:
            return f"Skill '{skill['name']}' executed but no tool map available."
        results = []
        for action in skill.get("actions", []):
            tool_name = action.get("tool")
            params = action.get("params", {})
            if self._tool_map.has(tool_name):
                result = await self._tool_map.execute(tool_name, params)
                results.append(f"{tool_name}: {str(result)[:200]}")
            else:
                results.append(f"{tool_name}: unknown tool")
        return f"Skill '{skill['name']}' executed:\n" + "\n".join(results)

    async def _execute_ai(self, skill: dict, context: dict | None = None) -> str:
        prompt = (
            f"[SKILL EXECUTION: {skill['name']}]\n"
            "You are executing a skill RIGHT NOW. Do NOT mention that the skill "
            "already exists or suggest waiting for it. Perform the task below "
            "immediately using your tools and live state data. Produce the "
            "requested output directly.\n\n"
        )
        prompt += skill.get("ai_prompt", "")
        if context:
            prompt += f"\n\nTrigger context: {json.dumps(context, default=str)}"

        event_log = await self.procedural.get_event_log(hours=24)
        if event_log:
            log_text = "\n".join(
                f"- [{e['ts']}] {e['entity_id']}: {e['old_state']} -> {e['new_state']} ({e['event_type']})"
                for e in event_log[-50:]
            )
            prompt += f"\n\nRecent event log:\n{log_text}"

        # Use a unique negative chat_id so skill runs don't pollute user history
        import random
        ephemeral_chat_id = -random.randint(1_000_000, 9_999_999)
        result = await self.agent.run(
            chat_id=ephemeral_chat_id,
            user_message=prompt,
            system_prompt_override=await self.agent._build_system_prompt(),
        )
        return result.text

    def _can_notify(self, key: str) -> bool:
        """Cooldown check to avoid notification spam."""
        now = time.monotonic()
        last = self._notif_cooldowns.get(key, 0)
        if now - last < NOTIFICATION_COOLDOWN:
            return False
        self._notif_cooldowns[key] = now
        return True

    async def _send_notification(self, message: str):
        """Send a notification to all allowed Telegram users."""
        await self.notifier.send(message)

    async def _check_proactive_notifications(
        self, entity_id: str, old_state: dict | None, new_state: dict
    ):
        """Built-in smart notification rules backed by DB preferences."""
        old_val = old_state.get("state", "") if old_state else ""
        new_val = new_state.get("state", "")
        attrs = new_state.get("attributes", {})
        friendly = attrs.get("friendly_name", entity_id)
        domain = entity_id.split(".")[0]
        dev_class = attrs.get("device_class", "")

        rules = await self.procedural.get_notification_rules()
        rule_map = {r["id"]: r for r in rules}

        def _is_enabled(rule_id: str) -> bool:
            r = rule_map.get(rule_id)
            return r["enabled"] if r else True

        def _get_config(rule_id: str) -> dict:
            r = rule_map.get(rule_id)
            return r.get("config", {}) if r else {}

        # 3D printer finished
        if _is_enabled("printer_done"):
            if "printo" in entity_id.lower() or "print" in friendly.lower():
                if old_val in ("printing", "preparing") and new_val in ("idle", "complete", "standby", "off"):
                    if self._can_notify(f"printer_done:{entity_id}"):
                        await self._send_notification(
                            f"Your 3D printer finished! {friendly} is now {new_val}."
                        )

        # Battery critically low
        if _is_enabled("battery_low") and dev_class == "battery" and old_val != new_val:
            threshold = _get_config("battery_low").get("threshold", 15)
            try:
                new_pct = float(new_val)
                old_pct = float(old_val) if old_val else 100
                if new_pct < threshold and old_pct >= threshold:
                    if self._can_notify(f"battery_low:{entity_id}"):
                        await self._send_notification(
                            f"Low battery: {friendly} is at {new_val}%"
                        )
            except (ValueError, TypeError):
                pass

        # Network device went offline (Deco)
        if domain == "device_tracker" and attrs.get("source_type") == "router":
            device_type = attrs.get("device_type", "")
            if device_type == "deco" and _is_enabled("deco_offline"):
                if old_val == "home" and new_val == "not_home":
                    if self._can_notify(f"deco_offline:{entity_id}"):
                        await self._send_notification(
                            f"Deco mesh node '{friendly}' went offline. Check your network connectivity."
                        )
                elif old_val == "not_home" and new_val == "home":
                    if self._can_notify(f"deco_online:{entity_id}"):
                        await self._send_notification(
                            f"Deco mesh node '{friendly}' is back online."
                        )
            elif device_type == "client" and _is_enabled("device_disconnect"):
                keywords = _get_config("device_disconnect").get(
                    "important_keywords", ["mac mini", "pixel", "ipad", "printer", "server"]
                )
                is_important = any(kw in friendly.lower() for kw in keywords)
                if is_important and old_val == "home" and new_val == "not_home":
                    if self._can_notify(f"net_offline:{entity_id}"):
                        await self._send_notification(
                            f"'{friendly}' disconnected from network "
                            f"(was on {attrs.get('deco_device', 'unknown')} node)."
                        )

        # Person arriving/leaving home (HA person entities + Deco presence devices)
        is_presence_entity = False
        if domain == "person":
            is_presence_entity = True
        elif domain == "device_tracker" and attrs.get("source_type") == "router" and attrs.get("device_type") == "client":
            device_mac = attrs.get("mac", "").upper()
            if device_mac:
                presence_devs = await self.procedural.get_presence_devices()
                presence_macs = {d["mac"].upper() for d in presence_devs}
                is_presence_entity = device_mac in presence_macs

        if is_presence_entity:
            presence_name = friendly
            aliases = await self.procedural.get_device_aliases()
            device_mac = attrs.get("mac", "").upper()
            if device_mac and device_mac in aliases:
                presence_name = aliases[device_mac].get("alias", friendly)

            if old_val in ("not_home", "away") and new_val == "home" and _is_enabled("welcome_home"):
                if self._can_notify(f"welcome:{entity_id}"):
                    lights_on = []
                    for eid, st in self.state._states.items():
                        if eid.startswith("light.") and st.get("state") == "on":
                            name = st.get("attributes", {}).get("friendly_name", eid)
                            if "printo" not in name.lower():
                                lights_on.append(name)
                    status = f"Lights on: {', '.join(lights_on)}" if lights_on else "All lights off"
                    await self._send_notification(f"Welcome home, {presence_name}! {status}.")

            elif old_val == "home" and new_val in ("not_home", "away") and _is_enabled("left_home"):
                if self._can_notify(f"left:{entity_id}"):
                    left_on = []
                    for eid, st in self.state._states.items():
                        if eid.startswith(("light.", "switch.")) and st.get("state") == "on":
                            name = st.get("attributes", {}).get("friendly_name", eid)
                            skip = ("led", "buzzer", "child lock", "printo", "enable camera")
                            if not any(kw in name.lower() for kw in skip):
                                left_on.append(name)
                    if left_on:
                        await self._send_notification(
                            f"{presence_name} left home. Still on: {', '.join(left_on[:5])}"
                        )

    async def _prune_event_log(self):
        await self.procedural.prune_event_log(keep_hours=720)
        log.info("Pruned event log (kept 30 days)")
