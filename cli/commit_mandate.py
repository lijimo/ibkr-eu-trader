"""The ONLY way a live mandate ever gets written. Run this yourself from a
terminal — it is never imported by ``agent/``, so the agent process has no
code path to reach it. That's the whole point: even a compromised or
hallucinating model cannot self-authorize trading permissions.

Usage:
    commit-mandate                     # interactive, reads mandate_proposal.json if present
    commit-mandate --max-order 500 --max-exposure 5000 --max-trades-per-day 3 \\
                   --account U1234567 --lifetime-days 30
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone

from safety.mandate import MANDATE_SCHEMA_VERSION, Mandate, write_mandate
from safety.paths import get_runtime_root


def _load_proposal() -> dict:
    path = get_runtime_root() / "mandate_proposal.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    proposal = _load_proposal()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", required=True, help="IBKR account id this mandate authorizes, e.g. U1234567")
    parser.add_argument("--max-order", type=float, default=proposal.get("max_order_notional_eur"), required=True)
    parser.add_argument("--max-exposure", type=float, default=proposal.get("max_total_exposure_eur"), required=True)
    parser.add_argument("--max-trades-per-day", type=int, default=proposal.get("max_trades_per_day"), required=True)
    parser.add_argument("--exclude", nargs="*", default=proposal.get("exclude_symbols", []))
    parser.add_argument("--lifetime-days", type=int, default=proposal.get("lifetime_days", 30))
    parser.add_argument("--yes", action="store_true", help="skip the interactive confirmation prompt")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=args.lifetime_days)

    print("About to commit a mandate authorizing REAL trading with these limits:")
    print(f"  account:              {args.account}")
    print(f"  max order notional:   EUR {args.max_order:,.2f}")
    print(f"  max total exposure:   EUR {args.max_exposure:,.2f}")
    print(f"  max trades / day:     {args.max_trades_per_day}")
    print(f"  excluded symbols:     {args.exclude or '(none)'}")
    print(f"  expires:              {expires.isoformat()} ({args.lifetime_days} days from now)")

    if not args.yes:
        confirm = input("\nType 'yes' to commit this mandate: ").strip().lower()
        if confirm != "yes":
            print("Aborted — no mandate written.")
            return 1

    consent_token = hashlib.sha256(f"{args.account}|{now.isoformat()}".encode()).hexdigest()
    mandate = Mandate(
        schema_version=MANDATE_SCHEMA_VERSION,
        max_order_notional_eur=args.max_order,
        max_total_exposure_eur=args.max_exposure,
        max_trades_per_day=args.max_trades_per_day,
        exclude_symbols=tuple(args.exclude),
        account_id=args.account,
        created_at=now.isoformat(),
        expires_at=expires.isoformat(),
        consent_token_sha256=consent_token,
    )
    path = write_mandate(mandate)
    print(f"\nMandate committed: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
