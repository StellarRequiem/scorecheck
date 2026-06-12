"""scorecheck CLI — adjudicate a published benchmark claim against its raw run-logs; verify a receipt.

    scorecheck adjudicate --claim claim.json --logs runs.json --harness swebench
    scorecheck verify --receipt receipt.json

Exit code = the verdict (0 REPRODUCED · 1 DID-NOT-REPRODUCE · 2 CHERRY-PICKED) — gateable in CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import ADAPTERS
from .adjudicate import adjudicate, exit_code, rate_x10000, proof_command
from .seal import seal, verify_receipt


def _pct(x10000: int) -> str:
    return f"{x10000 // 100}.{x10000 % 100:02d}%"


def _cmd_adjudicate(args) -> int:
    claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
    source = ADAPTERS[args.harness](args.logs)
    card = adjudicate(claim, source)
    card["proof"] = proof_command(args.logs, args.harness, claim.get("positive", "resolved"))
    root = seal(card, source, claim, args.receipt, args.ledger)
    rc = card["reconcile"]
    print(f"[{card['verdict']}] {card['name']} — claimed {_pct(card['claimed_x10000'])} vs raw "
          f"{_pct(card['recomputed_from_source_x10000'])}  "
          f"(reconcile: {rc['missing']} MISSING · {rc['flipped']} FLIPPED · {rc['extra']} EXTRA)  "
          f"receipt={root[:12]}")
    return exit_code(card["verdict"])


def _cmd_verify(args) -> int:
    ok, msg = verify_receipt(args.receipt)
    print(msg)
    return 0 if ok else 1


def _cmd_recompute(args) -> int:
    """Re-derive the honest rate from the raw logs — the proof recipe `verity prove` runs."""
    source = ADAPTERS[args.harness](args.logs)
    print(f"recomputed_x10000: {rate_x10000(source, args.positive)}")
    return 0


def _cmd_prove(args) -> int:
    """Re-run the receipt's sealed proof via `verity prove`: PASS only if the number re-derives."""
    from verity import prove
    sc = json.loads(Path(args.receipt).read_text(encoding="utf-8"))["scorecard"]
    if "proof" not in sc:
        print("receipt carries no proof command (re-run adjudicate to seal one)")
        return 2
    claim = {"name": sc.get("name", "?"), "metric": "recomputed_x10000",
             "value": int(sc["recomputed_from_source_x10000"]), "proof": sc["proof"], "tolerance": 0}
    res = prove(claim)
    print(f"[{res['verdict']}] recompute: claimed {claim['value']} / reproduced {res.get('reproduced')}  "
          f"— {res.get('detail', '')}")
    return 0 if res["verdict"] == "PASS" else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="scorecheck",
        description="Adjudicate a published benchmark claim against its raw run-logs "
                    "(REPRODUCED / DID-NOT-REPRODUCE / CHERRY-PICKED), sealed and re-runnable.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("adjudicate", help="claim + raw logs → a sealed verdict")
    a.add_argument("--claim", required=True, help="the published claim JSON")
    a.add_argument("--logs", required=True, help="the raw run-logs")
    a.add_argument("--harness", default="jsonl", choices=list(ADAPTERS), help="log format adapter")
    a.add_argument("--receipt", default="receipt.json")
    a.add_argument("--ledger", default="scorecheck-ledger.jsonl")
    a.set_defaults(func=_cmd_adjudicate)

    v = sub.add_parser("verify", help="re-derive a sealed receipt root (tamper-evidence)")
    v.add_argument("--receipt", default="receipt.json")
    v.set_defaults(func=_cmd_verify)

    rc = sub.add_parser("recompute", help="re-derive the honest rate from raw logs (the proof recipe)")
    rc.add_argument("--logs", required=True, help="the raw run-logs")
    rc.add_argument("--harness", default="jsonl", choices=list(ADAPTERS), help="log format adapter")
    rc.add_argument("--positive", default="resolved", help="the outcome value that counts as a win")
    rc.set_defaults(func=_cmd_recompute)

    pr = sub.add_parser("prove", help="re-run the receipt's proof via verity (PASS iff the number re-derives)")
    pr.add_argument("--receipt", default="receipt.json")
    pr.set_defaults(func=_cmd_prove)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
