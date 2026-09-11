from __future__ import annotations

from nexolu_ia_core.apps.hogar.agents import build_agent_registry
from nexolu_ia_core.apps.hogar.tools import build_tool_registry
from nexolu_ia_core.apps.registry import AppBundle


def build_bundle() -> AppBundle:
    return AppBundle(
        app_id="hogar",
        display_name="Hogar",
        tools=build_tool_registry(),
        agents=build_agent_registry(),
    )
