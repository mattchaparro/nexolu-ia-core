from __future__ import annotations

import pytest

from nexolu_ia_core.core.schemas import TenantContext
from nexolu_ia_core.core.tools.base import Tool
from nexolu_ia_core.core.tools.exceptions import ToolInputException
from nexolu_ia_core.core.tools.guard import ToolGuard

CONTEXT = TenantContext(business_id="b1", user_id="u1")


def make_tool() -> Tool:
    return Tool(
        name="ventas_resumen",
        description="test",
        parameters={
            "type": "object",
            "properties": {
                "desde": {"type": "string"},
                "monto": {"type": "number", "minimum": 0, "maximum": 1000},
                "estado": {"type": "string", "enum": ["abierto", "cerrado"]},
            },
            "required": ["desde"],
        },
    )


def test_discards_undeclared_arguments():
    guard = ToolGuard()
    clean = guard.sanitize(make_tool(), CONTEXT, {"desde": "2026-01-01", "inventado": "x"})
    assert clean == {"desde": "2026-01-01"}


def test_requires_declared_required_fields():
    guard = ToolGuard()
    with pytest.raises(ToolInputException):
        guard.sanitize(make_tool(), CONTEXT, {})


@pytest.mark.parametrize(
    "reserved_key",
    ["business_id", "BUSINESS_ID", "tenant_id", "sql", "table", "connection"],
)
def test_rejects_reserved_keys_regardless_of_case(reserved_key):
    guard = ToolGuard()
    with pytest.raises(ToolInputException):
        guard.sanitize(make_tool(), CONTEXT, {"desde": "2026-01-01", reserved_key: "x"})


def test_coerces_numeric_string_to_number():
    guard = ToolGuard()
    clean = guard.sanitize(make_tool(), CONTEXT, {"desde": "2026-01-01", "monto": "500"})
    assert clean["monto"] == 500.0


def test_rejects_value_outside_numeric_range():
    guard = ToolGuard()
    with pytest.raises(ToolInputException):
        guard.sanitize(make_tool(), CONTEXT, {"desde": "2026-01-01", "monto": 5000})


def test_rejects_value_outside_enum():
    guard = ToolGuard()
    with pytest.raises(ToolInputException):
        guard.sanitize(make_tool(), CONTEXT, {"desde": "2026-01-01", "estado": "no_existe"})


def test_accepts_value_within_enum():
    guard = ToolGuard()
    clean = guard.sanitize(make_tool(), CONTEXT, {"desde": "2026-01-01", "estado": "abierto"})
    assert clean["estado"] == "abierto"


def test_resolve_date_range_rejects_start_after_end():
    guard = ToolGuard()
    with pytest.raises(ToolInputException):
        guard.resolve_date_range(CONTEXT, "2026-01-10", "2026-01-01")


def test_resolve_date_range_rejects_future():
    guard = ToolGuard()
    with pytest.raises(ToolInputException):
        guard.resolve_date_range(CONTEXT, "2999-01-01", "2999-01-31")


def test_cap_rows_truncates_to_max():
    guard = ToolGuard()
    rows = list(range(500))
    capped = guard.cap_rows(rows)
    assert len(capped) == 100
