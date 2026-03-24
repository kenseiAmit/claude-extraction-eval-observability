# Perturbation Log

One deliberate change per system. Each entry states what was changed, the command, the prediction
made *before* running, the key output line, and how it differs from the unperturbed run.

All three perturbed inputs are included in this evidence pack so a reviewer can diff them against
the originals.

---

### System 1 — validated, routed pipeline

- **Change I made (file + what I changed):**
  Copied `data/policies/POL-2025-001.txt` to
  [`01-policy-pipeline/POL-2025-001-PERTURBED.txt`](01-policy-pipeline/POL-2025-001-PERTURBED.txt)
  and blanked the one required field the document actually carries on line 16. The premium figure
  was replaced with a reference to a schedule that is not enclosed, so the information is
  *genuinely absent* rather than merely hard to read:

  ```diff
  - Total Policy Premium ........................  $ 1,847.62
  + Total Policy Premium ........................  (see enclosed Premium Schedule PS-1)
  + *** (Premium Schedule PS-1 referenced but NOT enclosed) ***
  ```

  Nothing else in the document was touched (`diff` shows exactly this one hunk).

- **Command I ran:**
  ```bash
  .venv/bin/python .../01-policy-pipeline/run_with_pinned_model.py \
      extract .../01-policy-pipeline/POL-2025-001-PERTURBED.txt \
      --policy-id POL-2025-001-PERTURBED
  ```
  (`run_with_pinned_model.py` only overrides the model string — see `environment.txt` note (a).
  It calls the package's own CLI entry point, so the retry/validation logic is untouched.)

- **What I predicted:**
  The validator classifies this as `missing_source`, not `format`. Retry cannot conjure a number
  that is not in the document, so I expected the run to halt after **exactly one** API call and
  escalate — and critically, I expected `premium_amount` to come back `null` rather than the model
  inferring a plausible premium from the coverage limits elsewhere on the page.

- **What actually happened (paste the key output line):**
  From [`01-policy-pipeline/perturbation-run.txt`](01-policy-pipeline/perturbation-run.txt):

  ```
  2026-10-01 20:02:23,764 INFO HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
  2026-10-01 20:02:23,786 INFO validation_failed
  {
    "category": "missing_source",
    "detected_pattern": "premium_amount_absent",
    "field": "premium_amount",
    "kind": "escalation",
    "policy_id": "POL-2025-001-PERTURBED",
    "reason": "Field 'premium_amount' returned null — the source document does not contain this information. Retry is futile; escalate to human review."
  }
  exit code: 1
  ```

  Counting the API calls in that capture gives **1**:
  `grep -c "POST https://api.anthropic.com/v1/messages" perturbation-run.txt` → `1`.
  The default is `max_retries=3`, so three further calls were available and deliberately not spent.

- **How this differs from the unperturbed run:**
  In [`01-policy-pipeline/pipeline-run.txt`](01-policy-pipeline/pipeline-run.txt) the untouched
  `POL-2025-001` extracted cleanly and reached the router, landing in
  [`routing_decisions.json`](01-policy-pipeline/routing_decisions.json) as
  `"decision": "human_review"` with
  `"reason": "fields_below_threshold=['endorsements']; reviewer_disagreement=[...]"`.
  That is a *reviewable* record — a human sees a filled-in extraction and adjudicates it.
  The perturbed document never produced a record at all; it exited the pipeline before routing with
  `kind: "escalation"`. The system distinguishes "the model may be wrong here, have someone check"
  from "the document cannot answer this question, stop spending money," and the two land in
  different queues.

---

### System 2 — schema-enforced two-pass extraction

Rather than break a clean document (the suggested starter), I ran the experiment in reverse: I took
the document that *is* flagged and **repaired** its arithmetic. If the validator is genuinely
computing a sum rather than recognising a known-bad fixture, the flag must disappear while every
extracted line item stays identical.

- **Change I made (file + what I changed):**
  Copied `fixtures/documents/income_sum_mismatch.txt` to
  [`02-mortgage-extraction/income_sum_mismatch-PERTURBED.txt`](02-mortgage-extraction/income_sum_mismatch-PERTURBED.txt)
  and corrected the stated total on lines 37 and 78 to the true sum of the five line items
  (5,416.67 + 2,140.00 + 1,250.00 + 385.50 + 450.00 = 9,642.17):

  ```diff
  - TOTAL MONTHLY EARNINGS                         10,892.17   35,929.43
  + TOTAL MONTHLY EARNINGS                          9,642.17   35,929.43
  - Gross Earnings (Monthly)              10,892.17    35,929.43
  + Gross Earnings (Monthly)               9,642.17    35,929.43
  ```

  The five earnings line items were **not** touched.

- **Command I ran:**
  ```bash
  .venv/bin/mortgage-extract .../income_sum_mismatch-PERTURBED.txt \
      --mode replay --model claude-haiku-4-5-20251001 --verbose
  ```
  The response was recorded once with `--mode record` (an edited document has no entry in the
  shipped cache); the captured run above is the offline `--mode replay` of that recording, so a
  reviewer can reproduce it without an API key. `--model` is required because the model name is
  part of the cache key.

- **What I predicted:**
  Identical extraction for all five `*_monthly` components, `stated_monthly_total` of `9642.17`,
  `consistent: true`, an empty `discrepancies` list, and exit code `0` instead of `1`.

- **What actually happened (paste the key output line):**
  From [`02-mortgage-extraction/perturbation-run.txt`](02-mortgage-extraction/perturbation-run.txt):

  ```json
  "income": {
    "base_monthly": 5416.67,
    "bonus_monthly": 1250.0,
    "commission_monthly": 2140.0,
    "overtime_monthly": 385.5,
    "other_monthly": 450.0,
    "stated_monthly_total": 9642.17
  },
  "validation": {
    "consistent": true,
    "discrepancies": []
  }
  ```
  ```
  exit code: 0
  ```

- **How this differs from the unperturbed run:**
  [`02-mortgage-extraction/discrepancy-run.txt`](02-mortgage-extraction/discrepancy-run.txt) on the
  original document reports:

  ```json
  "validation": {
    "consistent": false,
    "discrepancies": [
      { "field": "total_monthly_income", "calculated": 9642.17, "stated": 10892.17, "delta": -1250.0 }
    ]
  }
  ```
  ```
  exit code: 1
  ```

  The five component values are **byte-identical across both runs**; only `stated_monthly_total`
  moved, and the verdict flipped with it. That is the point of the experiment: the validator is
  recomputing `calculated` in Python and diffing it against what the document claims, so the signal
  tracks the arithmetic and nothing else. Note also the `delta` of exactly `-1250.00` in the
  unperturbed run — precisely the bonus line — which tells an underwriter *which* line to go look
  at, not merely that something is wrong.

---

### System 3 — multi-source synthesis

- **Change I made (file + what I changed):**
  No file edit — a configuration change. Added the `--simulate-timeout` flag, which makes
  `read_logistics` abandon the shipment CSV after 5 rows and return
  `ok=False` with a `FailureContext(failure_type="timeout")` instead of raising.
  The logistics source is the only provider of `late_shipment_count` and one of only two providers
  of `on_time_delivery_rate`.

- **Command I ran:**
  ```bash
  .venv/bin/supply-chain-investigate meridian --offline                      # baseline
  .venv/bin/supply-chain-investigate meridian --offline --simulate-timeout   # perturbed
  ```

- **What I predicted:**
  The run finishes rather than aborting; `late_shipment_count` moves out of Well-Established and
  into Incomplete with the timeout named as the cause.

- **What actually happened (paste the key output line):**
  [`03-supply-chain/timeout-run.txt`](03-supply-chain/timeout-run.txt) opens with a banner and the
  gap is attributed to the specific failure:

  ```
  > Sources unavailable: logistics unavailable (timeout)
  ```
  ```
  ## Incomplete
  ### late_shipment_count  _[missing source: timeout reading logistics]_
  - missing source: timeout reading logistics
  ```
  The process exited `0`. The partial claims computed from the first 5 rows were carried in the
  `FailureContext` but were **not** written into shared memory or the briefing.

- **How this differs from the unperturbed run:**
  Two changes, and the second one is the interesting one.

  1. *The expected gap.* In [`03-supply-chain/investigation-run.txt`](03-supply-chain/investigation-run.txt),
     `late_shipment_count` sits under Well-Established with a real value
     (`| late_shipment_count | 11.0 shipments | 2026-04-05 | logistics |`). Under timeout it becomes
     an Incomplete entry naming the cause. "Unreachable" is reported as a coverage gap, not as zero
     late shipments.

  2. *The gap I did not predict — losing a source silently retires a conflict.* In the baseline the
     headline finding is:

     ```
     ## Contested
     ### on_time_delivery_rate  _[2 sources, conflicting]_  ⚠️ ESCALATE
     - escalation: high-impact metric is contested across sources
         - 95.0 percent — supplier_audit (as of 2026-04-10)
         - 78.0 percent — logistics (as of 2026-04-05)
     ```

     Under `--simulate-timeout` the entire Contested section reads `_none_`, and the same metric
     reappears under Well-Established as:

     ```
     ### on_time_delivery_rate  _[single source only]_
         - 95.0 percent — supplier_audit (as of 2026-04-10)
     ```

     The supplier's own flattering 95% figure is now unchallenged and no longer escalated — not
     because anyone disproved the 78%, but because the source that contradicted it went dark. A
     reader skimming only the findings would come away *more* confident and *less* correct. The
     only thing standing between them and that mistake is the `Sources unavailable: logistics
     unavailable (timeout)` banner and the `_[single source only]_` coverage badge. That is a strong
     argument for why coverage annotations must travel with every finding rather than being
     relegated to a footer: degraded coverage can masquerade as consensus.
