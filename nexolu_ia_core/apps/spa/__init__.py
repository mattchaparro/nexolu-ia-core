from __future__ import annotations

from nexolu_ia_core.apps.registry import AppBundle
from nexolu_ia_core.apps.spa.agents import build_agent_registry
from nexolu_ia_core.apps.spa.tools import build_tool_registry


def build_bundle() -> AppBundle:
    return AppBundle(
        app_id="spa",
        display_name="Nexolu Spa",
        tools=build_tool_registry(),
        agents=build_agent_registry(),
    )
