"""
Tool map: thin wrapper around a dict of LangChain BaseTool instances.
Used by the reactor and skills engine to execute tools by name.
"""

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool

log = logging.getLogger("homebot.tools")


class ToolMap:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def register_many(self, tools: list[BaseTool]):
        for t in tools:
            self._tools[t.name] = t

    def get_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    async def execute(self, name: str, args: dict) -> Any:
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}
        try:
            result = await tool.ainvoke(args)
            return result
        except Exception as e:
            log.exception("Tool %s failed", name)
            return json.dumps({"error": str(e)})

    def has(self, name: str) -> bool:
        return name in self._tools

    def __len__(self):
        return len(self._tools)
