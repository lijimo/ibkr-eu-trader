# ibkr-eu-trader

An LLM-agent-driven research and trading tool for **Interactive Brokers**,
scoped to **EUR-denominated markets** (Xetra / Frankfurt / Stuttgart to
start). You chat with an agent that can research symbols, backtest
strategies, and — only once you've explicitly committed a mandate — place
real orders through IBKR, gated by a mandate + kill-switch + audit system.

## Why this exists

Built after evaluating [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)
for this exact purpose: its data and backtest layers are US/China-centric
and silently misprice non-US markets, but its trading-safety architecture
(mandate, kill switch, audit ledger) is solid and broker-agnostic. This
project reuses that *shape*, rebuilt from scratch and scoped to one broker
and one currency, with an EUR-correct data and cost layer from day one.

## Architecture

```
agent/      Tool Runner wiring (client.beta.messages.tool_runner) + one
            @beta_tool function per tradeable action. No general filesystem
            or shell access — a curated, narrow tool surface only.
ibkr/       Connection pooling, contract qualification, market data,
            order mechanics. Talks to TWS/IB Gateway via ib_async.
strategy/   The SignalEngine contract: generate(data_map) -> signals.
backtest/   Xetra/EUR-correct cost model. run_dir in, artifacts out.
safety/     Mandate (immutable, human-committed-only), kill switch
            (sentinel file), audit ledger (append-only JSONL), and the
            one gate function every order must pass through.
cli/        commit_mandate.py — the ONLY way a live mandate gets written.
            Never imported by agent/, so the agent can't self-authorize.
```

See `docs/architecture.md` (once written) for the full design rationale.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # fill in ANTHROPIC_API_KEY
```

You'll also need TWS or IB Gateway running locally, logged into a **paper**
account first, with API connections enabled (Configure → API → Settings →
Enable ActiveX and Socket Clients) and, critically, **"Read Only API"
disabled** — it's on by default and silently blocks every order regardless
of what this app or your mandate allow. See `.env.example` for details.

## Status

Early scaffold — directory structure, core type definitions (`SignalEngine`
protocol, `Mandate` model), and safety-layer skeleton are in place. Connector
mechanics, the backtest engine, and the agent tool implementations are not
yet built. Do not point this at a live account.

## Safety model

1. **Mandate** — an immutable, frozen record of risk caps (max order size,
   max exposure, max leverage, max trades/day, symbol exclusions, expiry).
   Written by exactly one function (`cli/commit_mandate.py`), which the
   agent process never imports — so even a compromised or hallucinating
   model has no code path to authorize its own trading permissions.
2. **Kill switch** — a sentinel file's existence, checked fresh on every
   order attempt. `touch ~/.ibkr-eu-trader/HALT` from anywhere stops trading
   immediately, independent of the agent process's state.
3. **Audit ledger** — append-only JSONL, one record per order attempt
   (allowed, denied, or errored), written after every decision.

Every write-capable tool routes through `safety/gate.py::execute_live_order`
— there is no path that reaches IBKR without passing the gate first.
