from __future__ import annotations

from nexolu_ia_core.config import Settings
from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.models.router import ModelRouter

APP = AppIdentity(app_id="pos", api_key="dev-pos-key", base_url="http://pos.test", name="Nexolu POS")

AGENT_NO_OVERRIDE = AgentDefinition(name="cajero", display_name="Cajero", instructions="x")
AGENT_WITH_OVERRIDE = AgentDefinition(name="analista", display_name="Analista", instructions="x", provider="anthropic", model="claude-x")


def _settings_with_app_provider(**app_fields) -> Settings:
    import json

    return Settings(
        default_provider="null",
        default_model="null",
        nexolu_apps_json=json.dumps({"pos": {"api_key": "dev-pos-key", "base_url": "http://pos.test", **app_fields}}),
    )


def test_falls_back_to_the_global_default_when_neither_agent_nor_app_declare_a_provider():
    settings = _settings_with_app_provider()
    router = ModelRouter(settings)

    selection = router.resolve(AGENT_NO_OVERRIDE, APP)

    assert selection.provider == "null"
    assert selection.model is None
    assert selection.api_key_override is None


def test_app_level_provider_and_model_win_over_the_global_default():
    settings = _settings_with_app_provider(provider="openrouter", model="deepseek/deepseek-chat", provider_api_key="sk-or-pos")
    router = ModelRouter(settings)

    selection = router.resolve(AGENT_NO_OVERRIDE, APP)

    assert selection.provider == "openrouter"
    assert selection.model == "deepseek/deepseek-chat"
    assert selection.api_key_override == "sk-or-pos"


def test_agent_level_override_wins_over_the_app_level_override():
    settings = _settings_with_app_provider(provider="openrouter", model="deepseek/deepseek-chat", provider_api_key="sk-or-pos")
    router = ModelRouter(settings)

    selection = router.resolve(AGENT_WITH_OVERRIDE, APP)

    assert selection.provider == "anthropic"
    assert selection.model == "claude-x"
    # La api key de la app es para SU proveedor (openrouter); el agente forzo
    # otro, asi que no aplica - se usaria la api key global de anthropic.
    assert selection.api_key_override is None


def test_app_api_key_does_not_leak_to_a_different_resolved_provider():
    settings = _settings_with_app_provider(provider="openrouter", provider_api_key="sk-or-pos")
    router = ModelRouter(settings)

    agent = AgentDefinition(name="x", display_name="x", instructions="x", provider="anthropic")
    selection = router.resolve(agent, APP)

    assert selection.provider == "anthropic"
    assert selection.api_key_override is None


def test_resolve_without_an_app_identity_uses_only_agent_and_global_defaults():
    settings = _settings_with_app_provider(provider="openrouter", provider_api_key="sk-or-pos")
    router = ModelRouter(settings)

    selection = router.resolve(AGENT_NO_OVERRIDE, app=None)

    assert selection.provider == "null"
    assert selection.api_key_override is None
