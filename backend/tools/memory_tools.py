"""
Memory management tools exposed to the agent.
Allows the agent to store and recall facts/preferences.
"""

import json

from langchain_core.tools import StructuredTool

from memory.semantic import SemanticMemory


def create_memory_tools(semantic: SemanticMemory):

    async def _remember(key: str, value: str) -> str:
        """Store a user preference or fact in persistent memory (e.g. preferred light color, wake-up time, room assignments).
        key: Short key/label for the fact
        value: The fact or preference value
        """
        await semantic.remember(key, value)
        return json.dumps({"status": "remembered", "key": key, "value": value})

    async def _recall(query: str) -> str:
        """Search your memory for stored facts and preferences matching a query.
        query: Search query (matches against keys and values)
        """
        results = await semantic.recall(query)
        return json.dumps({"results": results, "count": len(results)})

    return [
        StructuredTool.from_function(
            coroutine=_remember,
            name="remember",
            description="Store a user preference or fact in persistent memory (e.g. preferred light color, wake-up time, room assignments).",
        ),
        StructuredTool.from_function(
            coroutine=_recall,
            name="recall",
            description="Search your memory for stored facts and preferences matching a query.",
        ),
    ]
