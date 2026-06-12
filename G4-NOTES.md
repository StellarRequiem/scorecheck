# G4 Prove-It — the adversarial pass (2026-06-11)

The anti-vapor wall: three independent fresh-context adversaries tried to **break** scorecheck, each required
to *reproduce a wrong result*, not theorize. They found **4 real, reproduced break-classes** — all now fixed,
regression-tested, and re-attacked-closed. This is the honest record (Measurable Work Standard: audited + honest-gaps).

## What broke, and the fix

| # | Break (reproduced) | Root cause | Fix |
|---|---|---|---|
| 1 | **False negative — low-rate fabrication.** Claim `0.40%` when raw is `0.00%` → `REPRODUCED`. | Fixed absolute tolerance (0.5pp) is huge relative to a near-zero base; floor-truncation discarded fractions. | Relative tolerance `max(0.10pp, 1% of true)`; rate is **round-half-up**, float-free. |
| 2 | **False negative — 2% inflation.** `25.49%` vs `25.00%` → `REPRODUCED`. | Same fixed-tolerance coarseness. | Same relative-tolerance fix (0.49pp > 1%·25% = 0.25pp → now `DID-NOT-REPRODUCE`). Honest rounding (25.00 vs 25.04) still passes. |
| 3 | **False positive — cosmetic label diff.** Honest claim with `Resolved`/`resolved `/`\tUNRESOLVED` → `CHERRY-PICKED`. | `reconcile` did exact string equality on outcome labels. | Normalise outcomes (`strip().casefold()`) on both sides before `reconcile`/rate. |
| 4 | **Seal forgery + proof-swap.** (a) Flip a sealed verdict, recompute the unkeyed root → `verify` still passes. (b) Point `prove` at a *different* logs file with the same rate → `prove` passes. | (a) Unkeyed root is attacker-recomputable — corruption-detection, not tamper-evidence. (b) The proof command didn't bind the logs to the sealed inputs. | (a) `verify --claim --logs` **re-derives** the verdict from the committed inputs (a forger can't fake it without inputs that produce it; doctored inputs are caught by reconcile) + the docstrings/README now state the honest threat model. (b) The receipt seals `source_sha256`; `prove` re-loads the logs and **REFUSEs** if the source hash doesn't match. |

What HELD (adversaries confirmed): `reconcile` correctly catches MISSING/FLIPPED/EXTRA; adapter id/outcome
`str()`-coercion creates no false matches; the append-only ledger; corruption detection.

## Residual honest limitations (not closed — documented, not hidden)
- **The seal is a commitment, not a signature.** A forger who controls the receipt *and* re-supplies matching
  inputs cannot be stopped by hashing alone — that's inherent to an unkeyed scheme. Standing integrity needs the
  root **published/anchored** (or HMAC/signed). `scorecheck` deliberately does not roll its own keyed crypto;
  it provides the re-derive-from-inputs path and is honest that integrity rests on anchoring.
- **Tolerance is a policy choice.** The relative default (0.10pp floor / 1% relative) is defensible but not
  universal; for high-stakes or sub-0.1pp-precision benchmarks, set `--tolerance` explicitly. `reconcile`
  (selective reporting) remains the primary anti-cherry-pick guard; the number check is secondary.

## Verification
20 tests / 95% coverage; re-attack with the exact original break inputs confirms each is closed
(`test_g4_*` in `tests/test_scorecheck.py`). Adversarial pass run as workflow `wf_01a75f8f-a51` (3 lenses).
