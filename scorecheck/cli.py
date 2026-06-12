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
from .adjudicate import adjudicate, exit_code, rate_x10000, proof_command, source_sha256
from .seal import seal, verify_receipt, canonical


def _pct(x10000: int) -> str:
    return f"{x10000 // 100}.{x10000 % 100:02d}%"


def _cmd_adjudicate(args) -> int:
    claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
    source = ADAPTERS[args.harness](args.logs)
    card = adjudicate(claim, source)
    positive = claim.get("positive", "resolved")
    card["proof"] = proof_command(args.logs, args.harness, positive)
    card["proof_logs"], card["proof_harness"], card["proof_positive"] = args.logs, args.harness, positive
    root = seal(card, source, claim, args.receipt, args.ledger)
    rc = card["reconcile"]
    print(f"[{card['verdict']}] {card['name']} — claimed {_pct(card['claimed_x10000'])} vs raw "
          f"{_pct(card['recomputed_from_source_x10000'])}  "
          f"(reconcile: {rc['missing']} MISSING · {rc['flipped']} FLIPPED · {rc['extra']} EXTRA)  "
          f"receipt={root[:12]}")
    return exit_code(card["verdict"])


def _cmd_verify(args) -> int:
    ok, msg = verify_receipt(args.receipt)
    if not ok:
        print(msg)
        return 1
    # The self-hash holds — but that ONLY catches corruption: the root is unkeyed, so a determined forger
    # who controls the receipt can recompute it (G4). REAL verification RE-DERIVES from the committed inputs:
    if args.claim and args.logs:
        import hashlib
        sealed = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
        source = ADAPTERS[args.harness](args.logs)
        card = adjudicate(claim, source)
        inputs = hashlib.sha256((canonical(claim) + "\n" + canonical(source)).encode("utf-8")).hexdigest()
        verdict_ok = card["verdict"] == sealed["scorecard"]["verdict"]
        number_ok = card["recomputed_from_source_x10000"] == sealed["scorecard"]["recomputed_from_source_x10000"]
        inputs_ok = inputs == sealed["inputs_sha256"]
        if verdict_ok and number_ok and inputs_ok:
            print(f"RE-DERIVED ✓ — {card['verdict']} reproduces from the committed claim+logs (inputs match the seal)")
            return 0
        print(f"RE-DERIVE MISMATCH ✗ — verdict_ok={verdict_ok} number_ok={number_ok} inputs_ok={inputs_ok}")
        return 1
    print(msg + "  — corruption check only (root is unkeyed; pass --claim/--logs to RE-DERIVE from inputs)")
    return 0


def _cmd_recompute(args) -> int:
    """Re-derive the honest rate AND the source hash from the raw logs — the bound, re-runnable proof recipe."""
    source = ADAPTERS[args.harness](args.logs)
    print(f"recomputed_x10000: {rate_x10000(source, args.positive)}")
    print(f"source_sha256: {source_sha256(source)}")
    return 0


def _cmd_prove(args) -> int:
    """Re-run the sealed proof and PASS only if BOTH the number re-derives (via `verity prove`) AND it came
    from the SEALED source (the logs are bound by hash — G4: a swapped logs file with the same rate is caught)."""
    from verity import prove as verity_prove
    sc = json.loads(Path(args.receipt).read_text(encoding="utf-8"))["scorecard"]
    if "proof" not in sc:
        print("REFUSE: receipt carries no proof command (re-run adjudicate to seal one)")
        return 2
    claim = {"name": sc.get("name", "?"), "metric": "recomputed_x10000",
             "value": int(sc["recomputed_from_source_x10000"]), "proof": sc["proof"], "tolerance": 0}
    res = verity_prove(claim)                                   # re-runs the proof; checks the NUMBER
    num_ok = res["verdict"] == "PASS"
    src_ok, src_detail = False, ""                              # bind the logs to the sealed source
    try:
        src = ADAPTERS[sc["proof_harness"]](sc["proof_logs"])
        src_ok = source_sha256(src) == sc.get("source_sha256")
    except Exception as e:                                      # old/unbound receipt → fail closed
        src_detail = f"; source-binding error: {e}"
    ok = num_ok and src_ok
    print(f"[{'PASS' if ok else 'REFUSE'}] number {'✓' if num_ok else '✗'} "
          f"(sealed {claim['value']} / reproduced {res.get('reproduced')}) · "
          f"source-binding {'✓' if src_ok else '✗'} — {res.get('detail', '')}{src_detail}")
    return 0 if ok else 2


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

    v = sub.add_parser("verify", help="check a receipt; with --claim/--logs, RE-DERIVE the verdict from inputs")
    v.add_argument("--receipt", default="receipt.json")
    v.add_argument("--claim", help="(real verification) re-derive the verdict from this claim + --logs")
    v.add_argument("--logs", help="(real verification) the raw logs to re-derive from")
    v.add_argument("--harness", default="jsonl", choices=list(ADAPTERS), help="adapter for --logs")
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
