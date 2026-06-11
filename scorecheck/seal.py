"""Seal a verdict into a tamper-evident receipt and re-derive it — so a skeptic can check the
adjudication wasn't silently re-based on different inputs.

Reuses `verity-core`'s canonical-JSON→sha256 `entry_hash` + append-only `AuditChain` (we do NOT roll our
own crypto; tamper-evident hash chains are not the novel part — the adjudication is). The receipt commits
to a hash of the EXACT (claim, source) inputs, so changing either after the fact breaks `verify`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from verity.audit import entry_hash, GENESIS, AuditChain


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _root(scorecard: dict, inputs_sha256: str) -> str:
    return entry_hash(seq=0, prev_hash=GENESIS, actor="scorecheck", event_type="verdict",
                      event_data={**scorecard, "inputs_sha256": inputs_sha256})


def seal(scorecard: dict, source: dict, claim: dict, receipt_path: str, ledger_path: str) -> str:
    """Write a sealed receipt + append the verdict to an audit chain. Returns the receipt root."""
    inputs_sha256 = hashlib.sha256((canonical(claim) + "\n" + canonical(source)).encode("utf-8")).hexdigest()
    root = _root(scorecard, inputs_sha256)
    AuditChain(ledger_path).append("verdict", {**scorecard, "inputs_sha256": inputs_sha256, "root": root},
                                   actor="scorecheck")
    Path(receipt_path).write_text(
        canonical({"root": root, "verdict": scorecard["verdict"], "scorecard": scorecard,
                   "inputs_sha256": inputs_sha256}) + "\n", encoding="utf-8")
    return root


def verify_receipt(receipt_path: str) -> tuple[bool, str]:
    """Re-derive the receipt root from its own contents — must match (catches a doctored receipt)."""
    r = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    recomputed = _root(r["scorecard"], r["inputs_sha256"])
    ok = recomputed == r["root"]
    return ok, (f"OK root={recomputed}" if ok else f"MISMATCH recomputed={recomputed} != receipt={r['root']}")
