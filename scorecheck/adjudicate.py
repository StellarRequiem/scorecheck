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

from calibration_log.reconcile import reconcile  # the real anti-cherry-pick primitive

REPRODUCED = "REPRODUCED"
DID_NOT_REPRODUCE = "DID-NOT-REPRODUCE"
CHERRY_PICKED = "CHERRY-PICKED"

# verdict ladder, worst wins → CI exit code
_RANK = {REPRODUCED: 0, DID_NOT_REPRODUCE: 1, CHERRY_PICKED: 2}


def rate_x10000(outcomes: dict, positive: str) -> int:
    """A rate metric as an integer ×10000 (no floats reach a hashed artifact)."""
    total = len(outcomes)
    if total == 0:
        return 0
    pos = sum(1 for v in outcomes.values() if v == positive)
    return (10000 * pos) // total


def adjudicate(claim: dict, source: dict, *, tolerance_x10000: int = 50) -> dict:
    """Adjudicate ``claim`` against ``source`` (the raw per-instance outcomes from the logs).

    ``claim`` = ``{name, metric, value_x10000, positive, published: {id: outcome}}`` — the vendor's
    *published* per-instance results + headline rate (×10000). ``source`` = the *raw* {id: outcome}.

    Verdict ladder (worst wins): any reconcile discrepancy ⇒ **CHERRY-PICKED**; else a headline number
    that doesn't match the raw-recomputed rate ⇒ **DID-NOT-REPRODUCE**; else **REPRODUCED**.
    """
    positive = claim.get("positive", "resolved")
    published = claim["published"]

    rec = reconcile(published, source)                      # MISSING / FLIPPED / EXTRA
    true_x10000 = rate_x10000(source, positive)             # the honest number, from raw logs
    claimed_x10000 = int(claim["value_x10000"])
    number_reproduces = abs(true_x10000 - claimed_x10000) <= tolerance_x10000

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
        "number_reproduces": int(number_reproduces),
        "reconcile": {"ok": int(rec.ok), "matched": rec.matched,
                      "missing": len(rec.missing), "flipped": len(rec.flipped), "extra": len(rec.extra)},
        "n_published": len(published),
        "n_source": len(source),
    }


def exit_code(verdict: str) -> int:
    return _RANK.get(verdict, 1)
