"""Thread-local IB connection pool.

``ib_async`` requires one socket per thread (no cross-thread sharing), and
TWS pacing limits reward connection reuse over reconnecting per call. This
pool hands out one connection per thread, reference-counted so nested calls
within the same thread share it, and only disconnects when the refcount
drops to zero.

Ported from the pattern validated (and bug-fixed — see the reqAllOpenOrders
note in orders.py) against a real Vibe-Trading IBKR integration this session.
"""

from __future__ import annotations

import itertools
import os
import socket
import threading
from dataclasses import dataclass
from typing import Any


class IBKRConnectionError(RuntimeError):
    """Raised when a local TWS / IB Gateway connection cannot be established."""


class IBKRDependencyError(RuntimeError):
    """Raised when the optional ``ib_async`` package is not installed."""


@dataclass(frozen=True)
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 17
    account: str | None = None
    timeout: float = 8.0
    readonly: bool = True

    @classmethod
    def from_env(cls) -> "IBKRConfig":
        return cls(
            host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(os.environ.get("IBKR_PORT", "7497")),
            client_id=int(os.environ.get("IBKR_CLIENT_ID", "17")),
        )


def tcp_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _require_ib_async():
    try:
        import ib_async  # type: ignore
    except ModuleNotFoundError as exc:
        raise IBKRDependencyError("ib_async is not installed; run `pip install ib_async>=2.0`.") from exc
    return ib_async


class _TwsPool:
    _counter = itertools.count(1)

    def __init__(self) -> None:
        self._local = threading.local()

    @staticmethod
    def _new_client_id(base: int) -> int:
        return base + next(_TwsPool._counter)

    def acquire(self, config: IBKRConfig) -> Any:
        refcount = getattr(self._local, "refcount", 0)
        if refcount > 0:
            self._local.refcount = refcount + 1
            return self._local.ib

        if not tcp_port_open(config.host, config.port):
            raise IBKRConnectionError(
                f"No TWS / IB Gateway socket listening at {config.host}:{config.port}. "
                "Open TWS or IB Gateway, log in, and enable API socket clients "
                "(Configure -> API -> Settings -> Enable ActiveX and Socket Clients)."
            )
        module = _require_ib_async()
        ib = module.IB()
        client_id = self._new_client_id(config.client_id)
        try:
            ib.connect(config.host, config.port, clientId=client_id, timeout=config.timeout)
        except Exception as exc:
            raise IBKRConnectionError(
                f"Could not connect to TWS / IB Gateway at {config.host}:{config.port}: {exc}"
            ) from exc

        self._local.ib = ib
        self._local.refcount = 1
        return ib

    def release(self) -> None:
        refcount = getattr(self._local, "refcount", 0)
        if refcount <= 0:
            return
        refcount -= 1
        if refcount > 0:
            self._local.refcount = refcount
            return
        self._local.refcount = 0
        ib = getattr(self._local, "ib", None)
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:  # noqa: BLE001 - best-effort disconnect
                pass
            self._local.ib = None


pool = _TwsPool()
