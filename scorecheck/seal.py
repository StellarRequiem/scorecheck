"""Seal a verdict into a receipt that COMMITS to a hash of the exact (claim, source) inputs, and
record it on an append-only `AuditChain`.

Honest threat model (G4 made this precise — do not overstate it): the receipt root is an UNKEYED hash, so
`verify_receipt` detects CORRUPTION and naive edits, but is NOT forgery-proof on its own — anyone who
controls the receipt can change a field and recompute the root. Real verification therefore RE-DERIVES the
verdict from the committed inputs (`scorecheck verify --claim <f> --logs <f>`), which a forger can't fake
without supplying inputs that actually produce the verdict (and doctored inputs are caught by reconcile).
Standing integrity over time additionally requires PUBLISHING/anchoring the root (or HMAC/signing it) so a
third party has a trusted reference — the unkeyed seal alone is a commitment, not a signature.

Reuses `verity-core`'s canonical-JSON→sha256 `entry_hash` + `AuditChain` (we do NOT roll our own crypto;
the hash chain is not the novel part — the adjudication is).
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
    """Re-derive the receipt root from its own contents — catches CORRUPTION / naive edits, NOT a forger who
    recomputes the unkeyed root (see module docstring). For real verification, re-derive from the committed
    inputs: `scorecheck verify --claim --logs`."""
    r = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    recomputed = _root(r["scorecard"], r["inputs_sha256"])
    ok = recomputed == r["root"]
    return ok, (f"OK root={recomputed}" if ok else f"MISMATCH recomputed={recomputed} != receipt={r['root']}")
