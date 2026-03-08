"""
Shared app initialization for all entry points (Telegram, CLI, API).
Avoids duplicating setup logic across main.py, cli.py, and api.py.
"""

import logging

import config
from state import StateCache
from agent import Agent
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.procedural import ProceduralMemory
from tools.registry import ToolMap
from tools.homeassistant import create_ha_tools
from tools.skills import create_skill_tools
from tools.memory_tools import create_memory_tools
from tools.n8n import create_n8n_tools
from tools.sonarr import create_sonarr_tools
from tools.transmission import create_transmission_tools
from tools.jellyseerr import create_jellyseerr_tools
from tools.prowlarr import create_prowlarr_tools
from tools.jellyfin import create_jellyfin_tools

log = logging.getLogger("homebot.bootstrap")


class App:
    """Container for all initialized homebot components."""

    __slots__ = (
        "agent", "state_cache", "tool_map",
        "episodic", "semantic", "procedural",
    )

    def __init__(self):
        self.state_cache = StateCache()
        self.episodic = EpisodicMemory(config.DB_PATH)
        self.semantic = SemanticMemory(config.DB_PATH)
        self.procedural = ProceduralMemory(config.DB_PATH)
        self.tool_map = ToolMap()
        self.agent = Agent(
            state_cache=self.state_cache,
            episodic=self.episodic,
            semantic=self.semantic,
            procedural=self.procedural,
            tool_map=self.tool_map,
        )


async def create_app(connect_ha: bool = True) -> App:
    """Create and initialize all homebot components.

    Args:
        connect_ha: Whether to connect the HA WebSocket state cache.
                    Set False for quick testing without HA.
    """
    app = App()

    await app.episodic.init()
    await app.semantic.init()
    await app.procedural.init()

    app.tool_map.register_many(create_ha_tools())
    app.tool_map.register_many(create_skill_tools(app.procedural, app.tool_map))
    app.tool_map.register_many(create_memory_tools(app.semantic))
    app.tool_map.register_many(create_n8n_tools())
    app.tool_map.register_many(create_sonarr_tools())
    app.tool_map.register_many(create_transmission_tools())
    app.tool_map.register_many(create_jellyseerr_tools())
    app.tool_map.register_many(create_prowlarr_tools())
    app.tool_map.register_many(create_jellyfin_tools())
    log.info("Registered %d LangChain tools", len(app.tool_map))

    app.agent.build_agent()

    if connect_ha:
        await app.state_cache.connect()

    return app


async def shutdown_app(app: App):
    """Gracefully shut down all components."""
    await app.state_cache.disconnect()
    await app.episodic.close()
    await app.semantic.close()
    await app.procedural.close()
    log.info("App shut down cleanly")
