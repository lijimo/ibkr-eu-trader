"""The gate — the one choke point every order-placing tool must call.

Mirrors the shape validated in Vibe-Trading's ``sdk_order_gate.py`` (and in
the IBKR live-trading work built on top of it this session), rebuilt fresh
for a single-currency, single-broker app: load mandate -> check expiry ->
check halt -> check account pinning -> price the order -> check caps -> only
then place it. Every branch writes exactly one audit event.

``place_order_fn`` and ``price_eur_fn`` are injected, not imported directly —
this is what makes the gate's logic unit-testable with a fake connector and
no real TWS connection, the same pattern used for Vibe-Trading's own gate
tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from safety.audit import AuditEvent, write_audit_event
from safety.daily_count import increment_daily_count, read_daily_count
from safety.halt import halt_flag_set
from safety.mandate import Mandate, is_expired, load_mandate

PriceFn = Callable[[str], float | None]
PlaceOrderFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None


def execute_live_order(
    intent: OrderIntent,
    *,
    connected_account_id: str,
    price_eur_fn: PriceFn,
    place_order_fn: PlaceOrderFn,
) -> dict[str, Any]:
    """Risk-check and, if allowed, submit a live order. Never raises for a
    caller-controlled or connector-controlled failure — always returns a
    status envelope.
    """
    mandate = load_mandate()
    if mandate is None:
        return _deny(intent, "no valid mandate on file — run `commit-mandate` first")

    if is_expired(mandate):
        return _deny(intent, "mandate expired — re-run `commit-mandate`")

    if halt_flag_set():
        return _deny(intent, "trading halted (kill switch is set)")

    if mandate.account_id != connected_account_id:
        return _deny(
            intent,
            f"connected account {connected_account_id!r} does not match the mandate's "
            f"authorized account {mandate.account_id!r} — refusing",
        )

    if intent.symbol.strip().upper() in {s.strip().upper() for s in mandate.exclude_symbols}:
        return _deny(intent, f"{intent.symbol} is on the mandate's exclude list")

    price = price_eur_fn(intent.symbol)
    if price is None or price <= 0:
        return _deny(intent, f"could not obtain a live EUR price for {intent.symbol} — fail-closed")

    notional_eur = price * intent.quantity
    if notional_eur > mandate.max_order_notional_eur:
        return _deny(
            intent,
            f"order notional EUR {notional_eur:,.2f} exceeds mandate cap "
            f"EUR {mandate.max_order_notional_eur:,.2f}",
        )

    daily_count = read_daily_count()
    if daily_count >= mandate.max_trades_per_day:
        return _deny(intent, f"daily trade count ({daily_count}) already at mandate cap")

    # TODO: check notional_eur against mandate.max_total_exposure_eur once
    # the connector exposes current position values (needs ibkr/account.py).

    try:
        result = place_order_fn(
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            order_type=intent.order_type,
            limit_price=intent.limit_price,
        )
    except Exception as exc:  # noqa: BLE001 - connector failures are reported, never propagated
        write_audit_event(
            AuditEvent(
                kind="order_placed",
                outcome="error",
                symbol=intent.symbol,
                side=intent.side,
                quantity=intent.quantity,
                notional_eur=notional_eur,
                reason=str(exc),
            )
        )
        return {"status": "error", "error": str(exc)}

    ok = isinstance(result, dict) and str(result.get("status", "")).lower() == "ok"
    if ok:
        increment_daily_count()
    write_audit_event(
        AuditEvent(
            kind="order_placed",
            outcome="allowed" if ok else "error",
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            notional_eur=notional_eur,
            reason=None if ok else str(result.get("error", "unknown connector error")),
            broker_response=result,
        )
    )
    return result


def _deny(intent: OrderIntent, reason: str) -> dict[str, Any]:
    write_audit_event(
        AuditEvent(
            kind="order_denied",
            outcome="denied",
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            notional_eur=None,
            reason=reason,
        )
    )
    return {"status": "blocked", "decision": "deny", "reason": reason}
