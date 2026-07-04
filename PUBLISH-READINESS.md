# Publish readiness — scorecheck

Publish-prep record for scorecheck (verification-layer product line, build #11). This documents
the PII/path scrub, the clean-clone proof, and the state of the publish gate. **Publish itself
remains operator-gated** — nothing here pushes or makes the repo public.

## 1. PII / absolute-path / real-identity scrub

Scanned **every tracked file** (`git ls-files`) for `/Users/…`, `/home/<user>`, the operator's
username, real name, and personal email.

| Check | Result |
|---|---|
| Absolute host paths (`/Users/…`, `/home/…`) in tracked files | **none found** |
| Operator username / real name / personal email in tracked files | **none found** |
| Commit authorship (`git log`, all commits) | `StellarRequiem <stellarrequiem@users.noreply.github.com>` — pseudonymous, noreply. Clean. |
| `LICENSE` copyright holder | `Copyright (c) 2026 StellarRequiem` — pseudonym. Clean. |
| `fixtures/`, `scorecheck-ledger.jsonl` (audit artifact) | no embedded host paths or PII. Clean. |

**Scrub diff: no changes were required.** The repo was already authored pseudonymously with a
noreply email and carried no absolute paths or personal identifiers in any tracked file. This is a
verified *clean* result, not an assumed one — the scan is re-runnable:

```sh
git ls-files -z | xargs -0 grep -nEI '(/Users/|/home/[a-z]|<username>|<realname>|<personal-email>)'
git log --format='%an | %ae'   # expect only the pseudonym + noreply
```

The git-pinned dependencies point at **public** GitHub repos under the pseudonym
(`git+https://github.com/StellarRequiem/verity-core`, `…/calibration-log`) — no local `file://`
paths leak into `pyproject.toml`.

## 2. Clean-clone proof (recipient's empty environment)

Added `.github/workflows/clean-clone.yml`: a fresh `git clone` of the pushed repo into a scratch
dir, a fresh venv, `pip install -e ".[dev]"`, `pytest`, and the full adjudicate → verify → prove →
flag demo. This is distinct from `ci.yml` (which uses `actions/checkout` on the workspace) — it
exercises the from-scratch path a would-be user takes.

**Verified locally by running that exact path** (fresh `git clone` of this repo → fresh venv →
install → tests → demo), all from an empty environment:

- Install: git-pinned `verity-core 0.1.0` + `calibration-log 0.1.0` resolved from public GitHub and
  installed cleanly into a fresh venv.
- Tests: **21 passed** (95% coverage; `adapters.py` 100%).
- Demo: honest claim → `REPRODUCED` (exit 0); `verify` (exit 0); `prove` re-derives (exit 0);
  doctored claim → `CHERRY-PICKED` (exit 2).

The CI workflow file itself will run green on push (its steps mirror the locally-verified path), but
has **not** been exercised on GitHub Actions because publish/push is operator-gated.

## 3. New adapter (optional, trivially-additive delta)

Added `json_array` to `ADAPTERS`: a top-level JSON array of `{id, outcome}` records — the
array-shaped sibling of the existing `jsonl` adapter, for the common harness that emits one JSON
array rather than line-delimited JSONL. Pure function, mirrors the existing adapter pattern; covered
by a new unit test and verified end-to-end through the CLI (adjudicate → REPRODUCED, re-derive verify
→ intact). README adapter list updated to keep its claims true. **Core adjudication/seal logic was
not touched.**

## 4. What remains operator-gated (not done here, by design)

- **`git push` / making the repo public.** Not performed. The composition-map guardrail is explicit:
  do not flip the publish gate — that is an operator go-live decision.
- **Version pinning of the family deps.** `pyproject.toml` pins `verity-core` / `calibration-log`
  to the default branch (tracks HEAD), not a frozen SHA/tag. For byte-reproducible receipts across
  time the shared seam calls for **one pinned `verity-core` version**; pinning to a released tag/SHA
  is recommended at publish time but is left to the operator (it changes the dependency contract and
  should be a deliberate, gated choice). Called out here as an honest gap, not silently changed.

## Honesty notes (Measurable Work Standard)

- No fake track record: this repo makes no live-track-record claim; `calibration-log`'s
  `predictions.jsonl` is a scaffold and scorecheck does not read it for standing.
- The seal is a **commitment, not a signature** (unkeyed root) — already stated honestly in
  `README.md` and `G4-NOTES.md`; unchanged here.
- The scrub result is a *verified absence*, re-runnable with the commands above — not an assertion.
