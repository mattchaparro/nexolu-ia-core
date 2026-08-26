from __future__ import annotations

from nexolu_ia_core.config import Settings
from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.models.router import ModelRouter

AGENT_NO_OVERRIDE = AgentDefinition(name="cajero", display_name="Cajero", instructions="x")
AGENT_WITH_OVERRIDE = AgentDefinition(name="analista", display_name="Analista", instructions="x", provider="anthropic", model="claude-x")


def _app(**fields) -> AppIdentity:
    return AppIdentity(app_id="pos", api_key="dev-pos-key", base_url="http://pos.test", name="Nexolu POS", **fields)


def test_falls_back_to_the_global_default_when_neither_agent_nor_app_declare_a_provider():
    settings = Settings(default_provider="null", default_model="null")
    router = ModelRouter(settings)

    selection = router.resolve(AGENT_NO_OVERRIDE, _app())

    assert selection.provider == "null"
    assert selection.model is None
    assert selection.api_key_override is None


def test_app_level_provider_and_model_win_over_the_global_default():
    settings = Settings(default_provider="null", default_model="null")
    router = ModelRouter(settings)
    app = _app(provider="openrouter", model="deepseek/deepseek-chat", provider_api_key="sk-or-pos")

    selection = router.resolve(AGENT_NO_OVERRIDE, app)

    assert selection.provider == "openrouter"
    assert selection.model == "deepseek/deepseek-chat"
    assert selection.api_key_override == "sk-or-pos"


def test_agent_level_override_wins_over_the_app_level_override():
    settings = Settings(default_provider="null", default_model="null")
    router = ModelRouter(settings)
    app = _app(provider="openrouter", model="deepseek/deepseek-chat", provider_api_key="sk-or-pos")

    selection = router.resolve(AGENT_WITH_OVERRIDE, app)

    assert selection.provider == "anthropic"
    assert selection.model == "claude-x"
    # La api key de la app es para SU proveedor (openrouter); el agente forzo
    # otro, asi que no aplica - se usaria la api key global de anthropic.
    assert selection.api_key_override is None


def test_app_api_key_does_not_leak_to_a_different_resolved_provider():
    settings = Settings(default_provider="null", default_model="null")
    router = ModelRouter(settings)
    app = _app(provider="openrouter", provider_api_key="sk-or-pos")

    agent = AgentDefinition(name="x", display_name="x", instructions="x", provider="anthropic")
    selection = router.resolve(agent, app)

    assert selection.provider == "anthropic"
    assert selection.api_key_override is None


def test_resolve_without_an_app_identity_uses_only_agent_and_global_defaults():
    settings = Settings(default_provider="null", default_model="null")
    router = ModelRouter(settings)

    selection = router.resolve(AGENT_NO_OVERRIDE, app=None)

    assert selection.provider == "null"
    assert selection.api_key_override is None


def test_site_url_and_site_name_and_provider_preferences_come_from_the_app():
    settings = Settings(default_provider="null", default_model="null")
    router = ModelRouter(settings)
    app = _app(
        site_url="https://pos.nexolu.co",
        site_name="Nexolu POS",
        provider_preferences={"order": ["Anthropic", "OpenAI"], "allow_fallbacks": True},
    )

    selection = router.resolve(AGENT_NO_OVERRIDE, app)

    assert selection.site_url == "https://pos.nexolu.co"
    assert selection.site_name == "Nexolu POS"
    assert selection.provider_preferences == {"order": ["Anthropic", "OpenAI"], "allow_fallbacks": True}
