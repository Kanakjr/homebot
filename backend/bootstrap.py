"""
Shared app initialization for all entry points (Telegram, CLI, API).

Light components (DB, state cache, notifier) are initialized eagerly.
Heavy components (LangChain agent, tools) are deferred via ensure_agent()
so the API server can start serving non-chat endpoints immediately.
"""

import asyncio
import logging
import time

import config
from state import StateCache
from notifier import TelegramNotifier
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.procedural import ProceduralMemory
from dashboard_config import DashboardConfig

log = logging.getLogger("homebot.bootstrap")


class App:
    """Container for all initialized homebot components."""

    __slots__ = (
        "agent", "state_cache", "tool_map",
        "episodic", "semantic", "procedural",
        "dashboard_config", "notifier",
        "_agent_lock",
    )

    def __init__(self):
        self.state_cache = StateCache()
        self.episodic = EpisodicMemory(config.DB_PATH)
        self.semantic = SemanticMemory(config.DB_PATH)
        self.procedural = ProceduralMemory(config.DB_PATH)
        self.dashboard_config = DashboardConfig(config.DB_PATH)
        self.notifier = TelegramNotifier()
        self.tool_map = None
        self.agent = None
        self._agent_lock = asyncio.Lock()

    async def ensure_agent(self):
        """Lazily import LangChain and build the agent + tools on first use.

        Thread-safe: concurrent callers block until the first build completes.
        Fast no-op after the first call.
        """
        if self.agent is not None:
            return

        async with self._agent_lock:
            if self.agent is not None:
                return

            t0 = time.monotonic()
            log.info("Building agent (importing LangChain)...")

            from agent import Agent
            from tools.registry import ToolMap
            from tools.homeassistant import create_ha_tools, create_ha_state_tools
            from tools.skills import create_skill_tools
            from tools.memory_tools import create_memory_tools
            from tools.n8n import create_n8n_tools
            from tools.sonarr import create_sonarr_tools
            from tools.transmission import create_transmission_tools
            from tools.jellyseerr import create_jellyseerr_tools
            from tools.prowlarr import create_prowlarr_tools
            from tools.jellyfin import create_jellyfin_tools
            from tools.scenes import create_scene_tools

            self.tool_map = ToolMap()
            self.tool_map.register_many(create_ha_tools())
            self.tool_map.register_many(create_ha_state_tools(self.state_cache))
            self.tool_map.register_many(create_skill_tools(self.procedural, self.tool_map))
            self.tool_map.register_many(create_memory_tools(self.semantic))
            self.tool_map.register_many(create_n8n_tools())
            self.tool_map.register_many(create_sonarr_tools())
            self.tool_map.register_many(create_transmission_tools())
            self.tool_map.register_many(create_jellyseerr_tools())
            self.tool_map.register_many(create_prowlarr_tools())
            self.tool_map.register_many(create_jellyfin_tools())
            self.tool_map.register_many(create_scene_tools(self.procedural, self.state_cache))
            log.info("Registered %d LangChain tools", len(self.tool_map))

            self.agent = Agent(
                state_cache=self.state_cache,
                episodic=self.episodic,
                semantic=self.semantic,
                procedural=self.procedural,
                tool_map=self.tool_map,
            )
            self.agent.build_agent()

            log.info("Agent ready in %.1fs", time.monotonic() - t0)


async def create_app(connect_ha: bool = True, build_agent: bool = True) -> App:
    """Create and initialize all homebot components.

    Args:
        connect_ha: Whether to connect the HA WebSocket state cache.
        build_agent: Whether to eagerly build the agent and tools.
                     Set False for fast API startup (agent built on first chat).
    """
    t0 = time.monotonic()
    app = App()

    await app.episodic.init()
    await app.semantic.init()
    await app.procedural.init()
    await app.procedural.ensure_default_skills()
    await app.procedural.ensure_default_notification_rules()
    await app.dashboard_config.init()

    if connect_ha:
        await app.state_cache.connect()

    if build_agent:
        await app.ensure_agent()

    log.info("App ready in %.1fs", time.monotonic() - t0)
    return app


async def shutdown_app(app: App):
    """Gracefully shut down all components."""
    await app.state_cache.disconnect()
    await app.episodic.close()
    await app.semantic.close()
    await app.procedural.close()
    await app.dashboard_config.close()
    log.info("App shut down cleanly")
