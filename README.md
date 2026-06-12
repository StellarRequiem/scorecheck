# scorecheck — adjudicate a benchmark claim against its raw logs

> In 2026 self-reported benchmark scores are routinely gamed: the same weights in different harnesses
> swing 10–30 points, and a published study found *selective submission* inflated scores by up to 100.
> The industry's answers don't close the loop — independent leaderboards (Epoch, Martian) re-run a
> benchmark and publish **their own** number, and reproducibility badges (ACM, REPRO-Bench) certify an
> artifact **re-runs** — but **none adjudicate a specific published claim against that claim's raw logs.**

`scorecheck` does. Give it a published **claim** and the **raw run-logs**, and it returns one badge —
**`REPRODUCED` · `DID-NOT-REPRODUCE` · `CHERRY-PICKED`** — sealed into a tamper-evident receipt anyone
can re-derive.

## How
It composes two primitives we already ship and a thin adapter:
- **`calibration-log` `reconcile`** — the anti-cherry-pick core: which raw outcomes were **dropped**
  (MISSING — hidden losses), **doctored** (FLIPPED), or **fabricated** (EXTRA)?
- **a metric recompute** — does the headline number actually fall out of the raw logs?
- **`verity-core` `AuditChain`** — seal the verdict + a hash of the exact inputs; `verify` re-derives it.

```sh
pip install -e .

scorecheck adjudicate --claim claim.json --logs runs.json --harness swebench
#   [CHERRY-PICKED] rag_gpt4 — claimed 8.00% vs raw 2.80%  (reconcile: 40 MISSING · 1 FLIPPED · 0 EXTRA)  receipt=3f9c…
scorecheck verify  --receipt receipt.json    # re-derive the sealed root; exit 0 iff intact
scorecheck prove   --receipt receipt.json    # proof-carrying: re-runs the recompute via `verity prove` — PASS iff the honest number re-derives from the raw logs
```
Exit code = verdict (`0` REPRODUCED · `1` DID-NOT-REPRODUCE · `2` CHERRY-PICKED) — gate it in CI.

Harness adapters (raw logs → `{id: outcome}`), all deliberately thin: `swebench` · `jsonl` · `csv` · `json_map`.
**Proof-carrying:** the receipt seals a re-runnable `proof` command, so a skeptic doesn't trust our recomputed
number — `scorecheck prove` re-derives it from the raw logs via `verity prove` (PASS) or REFUSEs.

## Honest scope
- The novelty is **composition + the `reconcile` primitive applied to a claim-vs-raw-logs adjudication**
  — *not* "a hash chain" or "re-run a benchmark," both of which are owned. We lead with the adjudication.
- A claim is only as checkable as the harness's logs are mappable. The `swebench` adapter is ~3 lines
  (verified on a real `results.json`); each harness family needs its own thin adapter (`scorecheck/adapters.py`).
- Float-free by construction (rates are integers ×10000, round-half-up), so a verdict is byte-reproducible.
- **The seal is a commitment, not a signature.** The receipt root is unkeyed: `verify` (receipt-only) detects
  corruption, not a determined forger who recomputes it. Real verification re-derives from the committed
  inputs — `scorecheck verify --claim claim.json --logs runs.json` — and standing integrity needs the root
  published/anchored. (Hardened in G4; see `G4-NOTES.md`.)
- The headline-number check uses a **relative** tolerance (max of 0.10pp and 1% of the true rate) so honest
  vendor rounding passes but low-rate fabrication is caught; `reconcile` (selective-reporting) is the primary
  guard, the number check is secondary. Outcome labels are normalised (case/whitespace) before comparison.

## Status
**G4 verified** — `adjudicate`/`verify`/`recompute`/`prove` end-to-end on a **real** SWE-bench results file;
4 thin harness adapters; proof-carrying verdicts (`verity prove`); 20 tests, 95% coverage; matrix CI (ubuntu+macos).
Survived an independent 3-lens adversarial *Prove-It* pass — 4 reproduced break-classes (low-rate false-negative,
cosmetic-label false-positive, seal-forgery, proof-swap) all fixed + regression-tested (see `G4-NOTES.md`).
Part of the [StellarRequiem](https://github.com/StellarRequiem) verification cluster. Code MIT.
