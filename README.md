# ibkr-eu-trader

An LLM-agent-driven research and trading tool for **Interactive Brokers**,
scoped to **EUR-denominated markets**: Xetra, Frankfurt, Stuttgart, Euronext
Paris/Amsterdam/Brussels, and Borsa Italiana (Milan). You chat with an agent
that can research symbols, backtest strategies, and — only once you've
explicitly committed a mandate — place real orders through IBKR, gated by a
mandate + kill-switch + audit system.

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
            fundamentals (Reuters XML via reqFundamentalData), order
            mechanics. Talks to TWS/IB Gateway via ib_async.
strategy/   The SignalEngine contract: generate(data_map) -> signals.
backtest/   EUR/Western-Europe-correct cost model. run_dir in, artifacts out.
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

Core layers are implemented and unit-tested against mocked IBKR/data
inputs: the safety gate, the backtest engine (cost model, tax estimate,
market allowlist), and the agent tool wiring. None of it has been run
against a real TWS/IB Gateway session from this environment — that
verification has to happen on your end. Do not point this at a live
account until you've validated the full backtest → paper-order →
paper-cancel round trip yourself.

## Markets

```
Exchange    Venue                    Transaction tax on top of commission
IBIS        Xetra                    none
FWB         Frankfurt                none
SWB         Stuttgart                none
AEB         Euronext Amsterdam       none
ENEXT.BE    Euronext Brussels        none (Belgian TOB is residency-based, doesn't apply to a German trader)
SBF         Euronext Paris           French FTT: 0.4% on purchases of qualifying stocks (>EUR 1bn mkt cap)
BVME        Borsa Italiana (Milan)   Italian FTT: 0.2% on purchases of qualifying stocks (>EUR 500m mkt cap)
```

`get_quote`/`get_historical_bars`/`get_fundamentals` work against any of
these (or in principle any IBKR-reachable exchange, since those tools don't
enforce an allowlist). The **backtest engine does**: it refuses to run on
an unrecognized exchange or non-EUR currency, and for SBF/BVME it also
refuses to run without an explicit `transaction_tax_pct` — the qualifying-
company lists for both FTTs are republished annually by each country's tax
authority, so this project doesn't hardcode one that could silently go
stale. Pass `0.0` if your specific symbol doesn't currently qualify, or the
current rate if it does; check before you rely on it for anything real.

Fundamentals (`get_fundamentals`) come from IBKR's own Reuters-sourced
`reqFundamentalData` — no second data vendor. It returns raw XML rather
than a parsed schema, since report contents vary by report type and by
symbol. Coverage depends on your account's market data entitlements; some
report types (particularly full financial statements and analyst
estimates) may require a paid Reuters Fundamentals subscription and may
simply come back empty for accounts without it.

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

## Taxes

German capital gains tax (Abgeltungsteuer) is **not** included in the
backtest's core cost model the way commissions are — tax isn't a
deterministic per-trade cost, it's computed on net *annual* realized gains
after loss offsetting, and depends on a personal allowance. Instead, every
backtest run also writes `artifacts/tax_estimate.csv` via `backtest/tax.py`,
a clearly-separate, opt-out-able estimate:

- **Rate**: 25% Abgeltungsteuer + 5.5% Solidaritätszuschlag on that tax =
  **26.375%** combined (excludes Kirchensteuer/church tax by default —
  pass a higher `tax_rate` to `estimate_after_tax_returns` to include it).
- **Sparerpauschbetrag**: EUR 1,000/year tax-free allowance (single filer;
  2,000 EUR married/joint), applied per year after netting.
- **Annual netting + loss carryforward**: losses offset gains within the
  same year; any unused loss carries forward to reduce future years'
  taxable gains (Verlustvortrag) — not just a flat per-trade deduction.
- Cost basis is tracked with the **moving-average method**
  (`gleitender Durchschnittspreis`), matching how German Depot tax
  accounting actually works — not FIFO.

**IBKR-specific**: unlike a German bank, IBKR does not withhold this tax at
source for German tax residents. You are personally responsible for
declaring capital gains yourself via **Anlage KAP** in your annual tax
return, using IBKR's own year-end tax certificate. `tax_estimate.csv` is a
strategy-comparison aid, not a substitute for that certificate or for
advice from a Steuerberater — always verify against your own account's
actual figures before relying on it for anything real.
