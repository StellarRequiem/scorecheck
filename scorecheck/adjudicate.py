"""The adjudicator: a published benchmark *claim* + the raw *run-logs* → a verdict:
**REPRODUCED · DID-NOT-REPRODUCE · CHERRY-PICKED**.

It composes two primitives we already ship:
- `calibration-log` **reconcile()** — selective-reporting detection (MISSING/FLIPPED/EXTRA). This is the
  un-owned wedge: independent leaderboards (Epoch, Martian) re-run a benchmark and publish *their own*
  number, and reproducibility badges (ACM, REPRO-Bench) certify an artifact re-runs — but **none
  adjudicate a specific published claim against that claim's raw logs**.
- a **metric recompute** — does the headline number actually fall out of the raw logs?

Float-free by construction (rates are integer ×10000) so a verdict is byte-reproducible and sealable.
"""
from __future__ import annotations

import hashlib
import json

from calibration_log.reconcile import reconcile  # the real anti-cherry-pick primitive


def source_sha256(source: dict) -> str:
    """Canonical hash of the raw {id: outcome} source — binds a proof re-run to the exact logs
    (G4: a swapped logs file that produced the same rate passed `prove`; this catches the swap)."""
    return hashlib.sha256(
        json.dumps(source, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


REPRODUCED = "REPRODUCED"
DID_NOT_REPRODUCE = "DID-NOT-REPRODUCE"
CHERRY_PICKED = "CHERRY-PICKED"

# verdict ladder, worst wins → CI exit code
_RANK = {REPRODUCED: 0, DID_NOT_REPRODUCE: 1, CHERRY_PICKED: 2}


def _norm(v) -> str:
    """Normalise an outcome label for comparison: a categorical label differing only by case or
    surrounding whitespace ("resolved" / "Resolved" / "resolved ") is the SAME outcome. G4 caught
    reconcile false-positives (honest claims flagged CHERRY-PICKED) from exact string equality."""
    return str(v).strip().casefold()


def rate_x10000(outcomes: dict, positive: str) -> int:
    """A rate metric as an integer ×10000 (no floats reach a hashed artifact). Round half up — G4 caught
    floor-truncation discarding fractional information (a fabricated low rate passing as REPRODUCED)."""
    total = len(outcomes)
    if total == 0:
        return 0
    p = _norm(positive)
    pos = sum(1 for v in outcomes.values() if _norm(v) == p)
    return (10000 * pos + total // 2) // total              # round half up, float-free


def effective_tolerance_x10000(true_x10000: int, override) -> int:
    """How close the claimed headline must be to the raw-recomputed rate. Default = max(0.10pp, 1% of the
    true rate) so a vendor's legitimate rounding passes but low-rate fabrication is caught (G4: a fixed
    0.5pp absolute tolerance let a 0.40%-vs-0.00% claim pass REPRODUCED). An explicit override wins."""
    return int(override) if override is not None else max(10, true_x10000 // 100)


def adjudicate(claim: dict, source: dict, *, tolerance_x10000=None) -> dict:
    """Adjudicate ``claim`` against ``source`` (the raw per-instance outcomes from the logs).

    ``claim`` = ``{name, metric, value_x10000, positive, published: {id: outcome}}`` — the vendor's
    *published* per-instance results + headline rate (×10000). ``source`` = the *raw* {id: outcome}.

    Verdict ladder (worst wins): any reconcile discrepancy ⇒ **CHERRY-PICKED**; else a headline number
    that doesn't match the raw-recomputed rate (within tolerance) ⇒ **DID-NOT-REPRODUCE**; else **REPRODUCED**.
    Outcomes are normalised (case/whitespace) before comparison; tolerance is relative (see above).
    """
    positive = claim.get("positive", "resolved")
    published = claim["published"]

    # normalise outcomes on BOTH sides so cosmetic label differences don't fake a discrepancy
    pub_n = {k: _norm(v) for k, v in published.items()}
    src_n = {k: _norm(v) for k, v in source.items()}
    rec = reconcile(pub_n, src_n)                           # MISSING / FLIPPED / EXTRA (normalised)
    true_x10000 = rate_x10000(source, positive)            # the honest number, from raw logs
    claimed_x10000 = int(claim["value_x10000"])
    tol = effective_tolerance_x10000(true_x10000, tolerance_x10000)
    number_reproduces = abs(true_x10000 - claimed_x10000) <= tol

    if not rec.ok:
        verdict = CHERRY_PICKED
    elif not number_reproduces:
        verdict = DID_NOT_REPRODUCE
    else:
        verdict = REPRODUCED

    return {
        "name": str(claim.get("name", "?")),
        "metric": str(claim.get("metric", "rate")),
        "verdict": verdict,
        "claimed_x10000": claimed_x10000,
        "recomputed_from_source_x10000": true_x10000,
        "tolerance_x10000": tol,
        "number_reproduces": int(number_reproduces),
        "reconcile": {"ok": int(rec.ok), "matched": rec.matched,
                      "missing": len(rec.missing), "flipped": len(rec.flipped), "extra": len(rec.extra)},
        "n_published": len(published),
        "n_source": len(source),
        "source_sha256": source_sha256(source),
    }


def exit_code(verdict: str) -> int:
    return _RANK.get(verdict, 1)


# ── proof-carrying: the recomputed-from-raw number ships a re-runnable proof ──
# A scorecheck verdict asserts ``recomputed_from_source_x10000`` (the honest number, from the raw logs).
# ``verity prove`` closes the gap between *asserting* and *proving* it: the receipt carries a ``proof``
# command (``scorecheck recompute …``) that re-derives the number; ``scorecheck prove`` RUNS it via
# verity and PASSES only if it reproduces. So a skeptic doesn't trust our number — they re-run it.

def proof_command(logs_path: str, harness: str, positive: str) -> str:
    """The committed re-runnable recipe for the honest number — a ``scorecheck recompute`` invocation."""
    return f"scorecheck recompute --logs {logs_path} --harness {harness} --positive {positive}"


def build_proof_claim(card: dict, logs_path: str, harness: str, positive: str) -> dict:
    """A ``verity.prove``-shaped claim: re-run the recompute, assert it matches the sealed number (exact)."""
    return {
        "name": card.get("name", "?"),
        "metric": "recomputed_x10000",
        "value": int(card["recomputed_from_source_x10000"]),
        "proof": proof_command(logs_path, harness, positive),
        "tolerance": 0,
    }
