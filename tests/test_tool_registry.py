from __future__ import annotations

import pytest

from nexolu_ia_core.core.schemas import TenantContext
from nexolu_ia_core.core.tools.base import Tool, WriteTool
from nexolu_ia_core.core.tools.exceptions import ToolNotAllowedException
from nexolu_ia_core.core.tools.registry import ToolRegistry


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(name="publico", description="d", parameters={"type": "object", "properties": {}}))
    registry.register(
        Tool(
            name="con_permiso",
            description="d",
            parameters={"type": "object", "properties": {}},
            required_permission="reports.sales",
        )
    )
    registry.register(
        Tool(
            name="con_feature",
            description="d",
            parameters={"type": "object", "properties": {}},
            required_feature="inventario",
        )
    )
    registry.register(
        WriteTool(
            name="crear_gasto",
            description="d",
            parameters={"type": "object", "properties": {}},
            draft_type="gasto",
            summarize=lambda v: "resumen",
        )
    )
    return registry


def test_admin_bypasses_permission_but_not_feature():
    registry = build_registry()
    context = TenantContext(business_id="b1", user_id="u1", is_admin=True, features=[])

    available = registry.available_for(context)

    assert "con_permiso" in available  # admin no necesita el permiso
    assert "con_feature" not in available  # el feature se exige siempre


def test_employee_needs_explicit_permission():
    registry = build_registry()
    context = TenantContext(business_id="b1", user_id="u1", is_admin=False, permissions=[])

    available = registry.available_for(context)

    assert "publico" in available
    assert "con_permiso" not in available


def test_employee_with_permission_and_feature_sees_both():
    registry = build_registry()
    context = TenantContext(
        business_id="b1", user_id="u1", is_admin=False, permissions=["reports.sales"], features=["inventario"]
    )

    available = registry.available_for(context)

    assert "con_permiso" in available
    assert "con_feature" in available


def test_resolve_for_unknown_tool_raises():
    registry = build_registry()
    context = TenantContext(business_id="b1", user_id="u1", is_admin=True)

    with pytest.raises(ToolNotAllowedException):
        registry.resolve_for(context, "no_existe")


def test_duplicate_registration_rejected():
    registry = build_registry()
    with pytest.raises(ValueError):
        registry.register(Tool(name="publico", description="d", parameters={"type": "object", "properties": {}}))


def test_write_tool_for_draft_type_resolves_by_type():
    registry = build_registry()
    context = TenantContext(business_id="b1", user_id="u1", is_admin=True)

    tool = registry.write_tool_for_draft_type(context, "gasto")

    assert tool.name == "crear_gasto"
