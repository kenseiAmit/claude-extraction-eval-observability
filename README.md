# Calibrated Document Extraction, HITL Routing & Multi-Source Synthesis Evaluation Suite

Production evaluation, calibration, and observability monorepo for **Anthropic Claude (`claude-haiku-4-5-20251001`)** structured extraction and multi-agent synthesis pipelines—verified across **104 automated `pytest` tests (`0` `mypy` / `ruff` errors)** and controlled fault/perturbation experiments.

---

## Monorepo Architecture & Headline Empirical Findings

| Package | Test Suite | Core Reliability Mechanism | Key Quantitative Finding |
| :--- | :---: | :--- | :--- |
| **[`packages/policy-extractor`](packages/policy-extractor)** | `45 passed` | Error-classified retry (`missing_source` vs `format`), independent blind reviewer, 3-signal HITL router, sliced Brier calibration | Sliced `policy_type × field` Brier score exposed **`umbrella / exclusions` at `conf=0.93, acc=0.00, brier=0.865`** hidden behind aggregate `0.291`; blind reviewer caught `6` overconfident errors (`POL-2025-003` at `0.95` conf). |
| **[`packages/mortgage-extractor`](packages/mortgage-extractor)** | `25 passed` | Two-pass classifier → nullable doc-type schema + Python cross-field arithmetic consistency validator | Deterministically caught `-$1,250.00` paystub earnings/YTD discrepancy (`exit 1`) that passed schema validation; verified clean `delta: 0.0` (`exit 0`) on repaired fixture. |
| **[`packages/supply-chain-risk`](packages/supply-chain-risk)** | `34 passed` | `ReaderResult` timeout isolation, `sentence-transformers` vector claim memory, date-guarded corroboration vs `ESCALATE` | `--simulate-timeout` degraded cleanly (`exit 0`) without polluting Chroma/vector store with partial claims, surfacing `Sources unavailable: logistics` and `[single source only]` provenance badges. |

---

## Evaluation & Perturbation Evidence ([`evaluation/`](evaluation/))

- [`evaluation/calibration_report.py`](evaluation/calibration_report.py) — Computes aggregate and `policy_type × field` sliced Expected Calibration Error (ECE) and Brier decomposition.
- [`evaluation/perturbation-log.md`](evaluation/perturbation-log.md) — Controlled before/after perturbation traces across `missing_source` 1-call retry halting, mortgage arithmetic repair, and reader timeout injection.
- [`evaluation/reflection-brief.md`](evaluation/reflection-brief.md) — Failure-mode analysis, threshold trade-offs, and production observability design.
- [`docs/harness_engineering_case_study.md`](docs/harness_engineering_case_study.md) — Companion study on `stop_reason` loop invariants, `56.8%` deterministic context pruning (`38,708 → 16,736` tokens), and 3-tier atomic state recovery.

---

## Quick Start

```bash
# Run test suites across all three production packages (104 tests)
(cd packages/policy-extractor && pytest)
(cd packages/mortgage-extractor && pytest)
(cd packages/supply-chain-risk && pytest)

# Run sliced Brier confidence calibration report
python evaluation/calibration_report.py
```

## License

MIT License — see [LICENSE](LICENSE).
