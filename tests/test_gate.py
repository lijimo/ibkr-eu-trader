"""Unit tests for the order gate — no real IBKR connection needed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from safety.gate import OrderIntent, execute_live_order
from safety.mandate import MANDATE_SCHEMA_VERSION, Mandate

pytestmark = pytest.mark.unit


def _mandate(**overrides) -> Mandate:
    now = datetime.now(timezone.utc)
    defaults = dict(
        schema_version=MANDATE_SCHEMA_VERSION,
        max_order_notional_eur=10_000.0,
        max_total_exposure_eur=100_000.0,
        max_trades_per_day=10,
        exclude_symbols=(),
        account_id="U1234567",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(days=30)).isoformat(),
        consent_token_sha256="deadbeef",
    )
    defaults.update(overrides)
    return Mandate(**defaults)


def _intent(**overrides) -> OrderIntent:
    defaults = dict(symbol="SAP", side="buy", quantity=10.0)
    defaults.update(overrides)
    return OrderIntent(**defaults)


@pytest.fixture(autouse=True)
def _isolated_runtime_root(tmp_path, monkeypatch):
    """Every safety.* module did `from safety.paths import get_runtime_root`,
    which binds its own local reference — patching safety.paths.get_runtime_root
    alone would not affect any of them. Patch each module's own binding so
    tests never touch the user's real ~/.ibkr-eu-trader/ (audit log, daily
    count, mandate file)."""
    for module in ("safety.paths", "safety.mandate", "safety.halt", "safety.audit", "safety.daily_count"):
        monkeypatch.setattr(f"{module}.get_runtime_root", lambda: tmp_path)


def test_denies_without_mandate(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: None)
    placed = []
    result = execute_live_order(
        _intent(),
        connected_account_id="U1234567",
        price_eur_fn=lambda s: 100.0,
        place_order_fn=lambda **kw: placed.append(kw) or {"status": "ok"},
    )
    assert result["status"] == "blocked"
    assert result["decision"] == "deny"
    assert placed == []


def test_denies_on_halt(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: _mandate())
    monkeypatch.setattr("safety.gate.halt_flag_set", lambda: True)
    placed = []
    result = execute_live_order(
        _intent(),
        connected_account_id="U1234567",
        price_eur_fn=lambda s: 100.0,
        place_order_fn=lambda **kw: placed.append(kw) or {"status": "ok"},
    )
    assert result["status"] == "blocked"
    assert placed == []


def test_denies_on_account_mismatch(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: _mandate(account_id="U1234567"))
    monkeypatch.setattr("safety.gate.halt_flag_set", lambda: False)
    placed = []
    result = execute_live_order(
        _intent(),
        connected_account_id="U9999999",  # different account than the mandate
        price_eur_fn=lambda s: 100.0,
        place_order_fn=lambda **kw: placed.append(kw) or {"status": "ok"},
    )
    assert result["status"] == "blocked"
    assert "account" in result["reason"]
    assert placed == []


def test_denies_oversized_order(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: _mandate(max_order_notional_eur=100.0))
    monkeypatch.setattr("safety.gate.halt_flag_set", lambda: False)
    placed = []
    # 10 shares * 100 EUR = 1000 EUR > 100 EUR cap
    result = execute_live_order(
        _intent(quantity=10.0),
        connected_account_id="U1234567",
        price_eur_fn=lambda s: 100.0,
        place_order_fn=lambda **kw: placed.append(kw) or {"status": "ok"},
    )
    assert result["status"] == "blocked"
    assert placed == []


def test_allows_in_bounds_order_and_places_it(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: _mandate(max_order_notional_eur=10_000.0))
    monkeypatch.setattr("safety.gate.halt_flag_set", lambda: False)
    placed = []
    result = execute_live_order(
        _intent(quantity=10.0),
        connected_account_id="U1234567",
        price_eur_fn=lambda s: 100.0,  # 10 * 100 = 1000 EUR, within cap
        place_order_fn=lambda **kw: placed.append(kw) or {"status": "ok", "order_id": "1"},
    )
    assert result["status"] == "ok"
    assert len(placed) == 1


def test_denies_excluded_symbol(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: _mandate(exclude_symbols=("SAP",)))
    monkeypatch.setattr("safety.gate.halt_flag_set", lambda: False)
    placed = []
    result = execute_live_order(
        _intent(symbol="SAP"),
        connected_account_id="U1234567",
        price_eur_fn=lambda s: 100.0,
        place_order_fn=lambda **kw: placed.append(kw) or {"status": "ok"},
    )
    assert result["status"] == "blocked"
    assert placed == []


def test_denies_unpriceable_order(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: _mandate())
    monkeypatch.setattr("safety.gate.halt_flag_set", lambda: False)
    placed = []
    result = execute_live_order(
        _intent(),
        connected_account_id="U1234567",
        price_eur_fn=lambda s: None,  # can't price -> fail closed
        place_order_fn=lambda **kw: placed.append(kw) or {"status": "ok"},
    )
    assert result["status"] == "blocked"
    assert placed == []


def test_connector_raise_is_caught_not_propagated(monkeypatch):
    monkeypatch.setattr("safety.gate.load_mandate", lambda: _mandate())
    monkeypatch.setattr("safety.gate.halt_flag_set", lambda: False)

    def _boom(**kw):
        raise RuntimeError("TWS pacing violation")

    result = execute_live_order(
        _intent(),
        connected_account_id="U1234567",
        price_eur_fn=lambda s: 100.0,
        place_order_fn=_boom,
    )
    assert result["status"] == "error"
    assert "pacing" in result["error"]
