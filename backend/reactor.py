"""
Reactor: autonomous auto-actions engine.

- Scheduled triggers via APScheduler (cron)
- State-change triggers from HA WebSocket events
- Event logging for daily summaries
- Executes skills in static or AI-powered mode
- Sends notifications to Telegram
"""

import asyncio
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

import config
from state import StateCache
from memory.procedural import ProceduralMemory
from tools.registry import ToolMap

log = logging.getLogger("homebot.reactor")

NOTABLE_DOMAINS = {
    "person", "light", "switch", "fan", "climate", "media_player",
    "automation", "sensor", "binary_sensor", "camera", "lock",
}


class Reactor:
    def __init__(
        self,
        state_cache: StateCache,
        procedural: ProceduralMemory,
        agent,
        bot: Bot,
        allowed_users: list[int],
    ):
        self.state = state_cache
        self.procedural = procedural
        self.agent = agent
        self.bot = bot
        self.allowed_users = allowed_users
        self.scheduler = AsyncIOScheduler(timezone=config.TZ)
        self._tool_map: ToolMap | None = None

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
                        self._fire_skill,
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
            asyncio.create_task(self._fire_skill(skill["id"], context={
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

    async def _fire_skill(self, skill_id: str, context: dict | None = None):
        skill = await self.procedural.get_skill(skill_id)
        if not skill or not skill.get("active"):
            return

        log.info("Firing skill: %s (mode=%s)", skill["name"], skill["mode"])

        try:
            if skill["mode"] == "static":
                result_text = await self._execute_static(skill)
            elif skill["mode"] == "ai":
                result_text = await self._execute_ai(skill, context)
            else:
                result_text = f"Unknown mode for skill {skill['name']}"

            if skill.get("notify") and self.allowed_users:
                for uid in self.allowed_users:
                    try:
                        await self.bot.send_message(chat_id=uid, text=result_text)
                    except Exception:
                        log.exception("Failed to notify user %s", uid)
        except Exception:
            log.exception("Failed to fire skill %s", skill_id)

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
        prompt = skill.get("ai_prompt", "")
        if context:
            prompt += f"\n\nTrigger context: {json.dumps(context, default=str)}"

        event_log = await self.procedural.get_event_log(hours=24)
        if event_log:
            log_text = "\n".join(
                f"- [{e['ts']}] {e['entity_id']}: {e['old_state']} -> {e['new_state']} ({e['event_type']})"
                for e in event_log[-50:]
            )
            prompt += f"\n\nRecent event log:\n{log_text}"

        chat_id = self.allowed_users[0] if self.allowed_users else 0
        result = await self.agent.run(
            chat_id=chat_id,
            user_message=prompt,
            system_prompt_override=await self.agent._build_system_prompt(),
        )
        return result.text

    async def _prune_event_log(self):
        await self.procedural.prune_event_log(keep_hours=72)
        log.info("Pruned event log (kept 72h)")
