"""Tool registry for the HomeBotAI deep agent."""


def get_all_tools() -> list:
    """Return all tools: HA + media services + generative UI."""
    from .homeassistant import get_ha_tools
    from .sonarr import get_sonarr_tools
    from .radarr import get_radarr_tools
    from .jellyfin import get_jellyfin_tools
    from .transmission import get_transmission_tools
    from .jellyseerr import get_jellyseerr_tools
    from .prowlarr import get_prowlarr_tools
    from .render_ui import get_render_ui_tools
    from .obsidian import get_obsidian_tools
    from .link_processor import get_link_processor_tools

    return (
        get_ha_tools()
        + get_sonarr_tools()
        + get_radarr_tools()
        + get_jellyfin_tools()
        + get_transmission_tools()
        + get_jellyseerr_tools()
        + get_prowlarr_tools()
        + get_render_ui_tools()
        + get_obsidian_tools()
        + get_link_processor_tools()
    )
