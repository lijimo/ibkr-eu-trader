"""Tool Runner wiring — the chat entrypoint.

Uses ``client.beta.messages.tool_runner`` (part of the standard ``anthropic``
SDK), not the separate Claude Agent SDK. The Agent SDK ships built-in
Read/Write/Edit/Bash/Grep/WebSearch tools by default, which is the wrong
shape here: this agent should have a small, curated, domain-specific tool
surface and no general filesystem/shell access on a machine that also holds
a live IBKR connection. The Tool Runner gives a custom-tools-only agent loop
with nothing else.
"""

from __future__ import annotations

import os

from anthropic import Anthropic
from dotenv import load_dotenv

from agent.tools.account import get_account_snapshot, get_positions
from agent.tools.backtest import run_backtest
from agent.tools.market_data import get_historical_bars, get_quote
from agent.tools.place_order import cancel_order, place_order
from agent.tools.propose_mandate import propose_mandate

SYSTEM_PROMPT = """\
You are a trading research assistant for a single Interactive Brokers \
account, trading EUR-denominated equities on Xetra/Frankfurt/Stuttgart.

You have read-only tools for quotes, historical bars, positions, account \
state, and backtesting a registered strategy. You also have `place_order` \
and `cancel_order` — `place_order` is gated by a mandate the user commits \
themselves outside this conversation; most attempts will be denied until \
they've done that. Never claim an order was placed unless the tool result \
says status "ok". If a mandate proposal is warranted, use `propose_mandate` \
and clearly tell the user they still need to run `commit-mandate` \
themselves — you cannot do that step.
"""

TOOLS = [
    get_quote,
    get_historical_bars,
    get_positions,
    get_account_snapshot,
    run_backtest,
    propose_mandate,
    place_order,
    cancel_order,
]


def main() -> None:
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set (and no `ant auth login` profile assumed). See .env.example.")

    client = Anthropic()
    messages: list[dict] = []

    print("ibkr-eu-trader — type your question, or 'exit' to quit.")
    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        runner = client.beta.messages.tool_runner(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        final = None
        for message in runner:
            final = message
        if final is not None:
            messages.append({"role": "assistant", "content": final.content})
            for block in final.content:
                if block.type == "text":
                    print(block.text)


if __name__ == "__main__":
    main()
