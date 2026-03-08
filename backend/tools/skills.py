"""
Skill management tools exposed to the agent via LangChain tools.
"""

import json
import logging
import re

from langchain_core.tools import StructuredTool

from memory.procedural import ProceduralMemory

log = logging.getLogger("homebot.tools.skills")


def _make_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def create_skill_tools(procedural: ProceduralMemory, tool_map):
    """Create skill management tools. tool_map is a ToolMap instance populated at startup."""

    async def _create_skill(
        name: str,
        description: str,
        actions: str = "[]",
        trigger_type: str = "manual",
        trigger_cron: str = "",
        trigger_entity_id: str = "",
        trigger_to: str = "",
        trigger_above: str = "",
        trigger_below: str = "",
        mode: str = "static",
        ai_prompt: str = "",
        notify: bool = False,
    ) -> str:
        """Create a new reusable skill (routine/automation). For static mode, provide actions as a JSON array of {tool, params} objects. For ai mode, provide an ai_prompt instead.
        name: Human-readable skill name
        description: What the skill does
        actions: JSON array of actions, e.g. [{"tool":"ha_call_service","params":{...}}]
        trigger_type: When the skill fires (manual, schedule, state_change)
        trigger_cron: Cron expression for schedule trigger, e.g. '0 22 * * *'
        trigger_entity_id: HA entity_id for state_change trigger
        trigger_to: Target state value for state_change trigger
        trigger_above: Numeric threshold above for state_change trigger
        trigger_below: Numeric threshold below for state_change trigger
        mode: static = fixed action sequence, ai = AI reasons with a prompt
        ai_prompt: Prompt for the AI when mode=ai
        notify: Send result to Telegram when triggered
        """
        skill_id = _make_id(name)

        trigger = {"type": trigger_type}
        if trigger_type == "schedule" and trigger_cron:
            trigger["cron"] = trigger_cron
        elif trigger_type == "state_change":
            if trigger_entity_id:
                trigger["entity_id"] = trigger_entity_id
            if trigger_to:
                trigger["to"] = trigger_to
            if trigger_above:
                trigger["above"] = float(trigger_above)
            if trigger_below:
                trigger["below"] = float(trigger_below)

        try:
            parsed_actions = json.loads(actions) if isinstance(actions, str) else actions
        except json.JSONDecodeError:
            parsed_actions = []

        skill = await procedural.create_skill(
            skill_id=skill_id,
            name=name,
            description=description,
            trigger=trigger,
            mode=mode,
            ai_prompt=ai_prompt,
            actions=parsed_actions,
            notify=notify,
        )
        return json.dumps({"status": "created", "skill": skill}, default=str)

    async def _execute_skill(skill_name: str) -> str:
        """Execute a previously learned skill by name.
        skill_name: Name or ID of the skill to execute
        """
        skill = await procedural.get_skill(skill_name)
        if not skill:
            skill_id = _make_id(skill_name)
            skill = await procedural.get_skill(skill_id)
        if not skill:
            all_skills = await procedural.list_skills()
            for s in all_skills:
                if s["name"].lower() == skill_name.lower():
                    skill = s
                    break
        if not skill:
            return json.dumps({"error": f"Skill '{skill_name}' not found"})

        if skill["mode"] == "static":
            results = []
            for action in skill.get("actions", []):
                tool_name = action.get("tool")
                params = action.get("params", {})
                if tool_map.has(tool_name):
                    result = await tool_map.execute(tool_name, params)
                    results.append({"tool": tool_name, "result": result})
                else:
                    results.append({"tool": tool_name, "error": "unknown tool"})
            return json.dumps({"status": "executed", "skill": skill["name"], "results": results}, default=str)
        elif skill["mode"] == "ai":
            return json.dumps({
                "status": "ai_skill",
                "skill": skill["name"],
                "ai_prompt": skill.get("ai_prompt", ""),
                "message": "This is an AI-powered skill. The prompt has been returned for you to reason about.",
            })
        return json.dumps({"error": "Unknown skill mode"})

    async def _list_skills() -> str:
        """List all learned skills with their triggers and status."""
        skills = await procedural.list_skills()
        return json.dumps({"skills": skills}, default=str)

    async def _update_skill(skill_name: str, updates: str) -> str:
        """Update an existing skill's properties.
        skill_name: Name or ID of the skill
        updates: JSON object of fields to update, e.g. {"description":"new desc","notify":true}
        """
        skill_id = _make_id(skill_name)
        try:
            parsed = json.loads(updates) if isinstance(updates, str) else updates
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON for updates"})
        result = await procedural.update_skill(skill_id, parsed)
        if not result:
            return json.dumps({"error": f"Skill '{skill_name}' not found"})
        return json.dumps({"status": "updated", "skill": result}, default=str)

    async def _delete_skill(skill_name: str) -> str:
        """Delete a learned skill.
        skill_name: Name or ID of the skill to delete
        """
        skill_id = _make_id(skill_name)
        deleted = await procedural.delete_skill(skill_id)
        if not deleted:
            return json.dumps({"error": f"Skill '{skill_name}' not found"})
        return json.dumps({"status": "deleted", "skill_id": skill_id})

    async def _toggle_skill(skill_name: str, active: bool) -> str:
        """Enable or disable a triggered skill.
        skill_name: Name or ID of the skill
        active: True to enable, false to disable
        """
        skill_id = _make_id(skill_name)
        result = await procedural.toggle_skill(skill_id, active)
        if not result:
            return json.dumps({"error": f"Skill '{skill_name}' not found"})
        return json.dumps({"status": "toggled", "skill": result}, default=str)

    async def _get_event_log(hours: int = 24) -> str:
        """Get recent home event log entries (state changes, automations, sensor crossings). Useful for creating daily summaries.
        hours: How many hours back to look (default 24)
        """
        events = await procedural.get_event_log(hours=hours)
        return json.dumps({"events": events, "count": len(events)}, default=str)

    return [
        StructuredTool.from_function(coroutine=_create_skill, name="create_skill",
            description="Create a new reusable skill (routine/automation). For static mode, provide actions as a JSON array of {tool, params} objects. For ai mode, provide an ai_prompt instead."),
        StructuredTool.from_function(coroutine=_execute_skill, name="execute_skill",
            description="Execute a previously learned skill by name."),
        StructuredTool.from_function(coroutine=_list_skills, name="list_skills",
            description="List all learned skills with their triggers and status."),
        StructuredTool.from_function(coroutine=_update_skill, name="update_skill",
            description="Update an existing skill's properties."),
        StructuredTool.from_function(coroutine=_delete_skill, name="delete_skill",
            description="Delete a learned skill."),
        StructuredTool.from_function(coroutine=_toggle_skill, name="toggle_skill",
            description="Enable or disable a triggered skill."),
        StructuredTool.from_function(coroutine=_get_event_log, name="get_event_log",
            description="Get recent home event log entries (state changes, automations). Useful for daily summaries."),
    ]
