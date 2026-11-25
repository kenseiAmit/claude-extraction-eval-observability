# Reflection Brief — Evaluation and Observability Capstone

**Name:** Amit Kumar
**Date:** 2026-10-01

> Ground every answer in your own run. When a question asks for a number, file name, or line, paste
> it from your artifacts — a reviewer should be able to find it. Answers that are correct in the
> abstract but cite nothing do not meet the bar. Keep it short and specific.

---

## 0. Environment

| Field | Value |
|---|---|
| OS & version | macOS 26.6.2 (build 25G83), Apple Silicon / arm64 |
| Python version | Python 3.12.14 (system `python3` is 3.9.6, below the `>=3.11` floor) |
| Date run | 2026-10-01 |
| Ran any system live? (which) | Yes — System 1 (policy pipeline) ran live against `https://api.anthropic.com`. Systems 2 and 3 ran offline (`--mode replay` / `--offline`); the only other live call was the System 2 perturbation, which needed `--mode record`. |

---

## 1. Validated, routed pipeline

| Evidence | Value |
|---|---|
| Passing test count | **45 passed, 3 skipped** ([`01-policy-pipeline/tests.txt`](01-policy-pipeline/tests.txt)) — the 3 skipped are the `@pytest.mark.live` tests, which the course places outside the verify gate |
| Routing output file | [`01-policy-pipeline/routing_decisions.json`](01-policy-pipeline/routing_decisions.json) (9 records) |
| auto_approve / human_review / spot_check counts | **0 / 9 / 0** (plus 1 escalation that never reached routing) |

**1a. Retry boundary.** From your perturbation run (a required field removed), paste the escalation
record. How many API calls did the system make, and why is retrying a futile case worse than
escalating it?

> From [`01-policy-pipeline/perturbation-run.txt`](01-policy-pipeline/perturbation-run.txt):
>
> ```json
> {
>   "category": "missing_source",
>   "detected_pattern": "premium_amount_absent",
>   "field": "premium_amount",
>   "kind": "escalation",
>   "policy_id": "POL-2025-001-PERTURBED",
>   "reason": "Field 'premium_amount' returned null — the source document does not contain this information. Retry is futile; escalate to human review."
> }
> ```
>
> **Exactly one API call.** The capture contains a single
> `POST https://api.anthropic.com/v1/messages` line; `max_retries` defaults to 3, so three further
> calls were available and deliberately not spent.
>
> Retrying a futile case is worse than escalating for three reasons, in increasing order of damage.
> It wastes money and latency — three more calls that cannot succeed. It delays the only actor who
> can actually fix the problem: a human who goes and finds Premium Schedule PS-1. And most
> seriously, it *manufactures risk*. Each retry resends the document with an escalating "your last
> answer was rejected" message. The one thing the model cannot do is produce a premium that is not
> on the page, so the pressure to satisfy the validator pushes it toward the nearest plausible
> number — and this document is full of them ($100,000 liability limits, a $500 deductible). A loop
> designed to improve accuracy would, on this input, be actively recruiting a fabrication. The
> `missing_source` category exists precisely so the system can tell "you got it wrong, try again"
> apart from "the answer isn't here," and only ever apply retry pressure to the first.

**1b. Reading the router.** Pick one `human_review` record from your routing output. Which of the
three signals (confidence, reviewer, integration) sent it to a human? If you had trusted the model's
confidence alone, what would have happened?

> `POL-2025-003` from [`routing_decisions.json`](01-policy-pipeline/routing_decisions.json):
>
> ```json
> {
>   "confidence_summary": {
>     "coverage_limit": 0.95, "deductible": 1.0, "endorsements": 0.95,
>     "exclusions": 0.9, "policy_type": 1.0, "premium_amount": 1.0
>   },
>   "decision": "human_review",
>   "fields_below_threshold": [],
>   "integration_failures": [],
>   "reason": "reviewer_disagreement=['coverage_limit']",
>   "reviewer_disagreements": ["coverage_limit"]
> }
> ```
>
> The **independent reviewer** sent it, and only the reviewer. `fields_below_threshold` is empty and
> `integration_failures` is empty — two of the three signals are completely silent on this record.
>
> Had I trusted confidence alone, this record would have been **auto-approved**. Every field is at
> or above the 0.90 threshold; the extractor rated `coverage_limit` — the exact field the reviewer
> disputed — at **0.95**, and rated three other fields at a flat 1.0. The model was not hedging. It
> was confidently wrong, and its confidence score contained no trace of the problem. The only reason
> a human will ever look at this policy is that a second model, which never saw the extractor's
> prompt or reasoning, read the source document independently and disagreed. That is also why the
> reviewer's independence is load-bearing rather than decorative: had it been shown the extractor's
> output *and* its reasoning, the most likely outcome is that it agrees, and the record ships.

**1c. Where the aggregate lies.** Run the calibration snippet. Quote the one cell whose accuracy lags
its confidence, plus the overall figure. What does slicing by `policy_type × field` catch that a
single number hides?

> From [`01-policy-pipeline/calibration-report.txt`](01-policy-pipeline/calibration-report.txt):
>
> ```
> auto      premium_amount  n=3 conf=0.95 acc=1.00 brier=0.003
> home      deductible      n=1 conf=0.90 acc=1.00 brier=0.010
> umbrella  exclusions      n=2 conf=0.93 acc=0.00 brier=0.865
> OVERALL brier=0.291
> ```
>
> The bad cell is **`umbrella / exclusions`: conf=0.93, acc=0.00, brier=0.865.** It is wrong *every
> single time* while claiming 93% confidence. The overall Brier of **0.291** reads as mediocre —
> the kind of number that prompts "we should improve that next quarter," not "stop the line."
>
> What slicing catches is that **the aggregate is an average over populations that behave nothing
> alike**, and averaging hides the worst one behind the best one. Two-thirds of these samples are
> near-perfect (`brier=0.003`), and they drag a catastrophic 0.865 cell down to a comfortable 0.291.
> Worse, the failure is concentrated exactly where volume is lowest: umbrella policies are the
> smallest stratum, so they contribute least to the overall figure while being the most broken.
> A single number is structurally biased toward whatever you process most of.
>
> That is also the reason `apply_stratified_spot_check` buckets by `policy_type` and promotes
> `max(1, ceil(sample_pct * n))` rather than a flat percentage — with a plain percentage a
> two-record umbrella stratum rounds to zero samples and the one segment that is failing silently
> drops out of the drift-detection net entirely. My own run makes the dependency between the two
> mechanisms concrete in an unexpected way: `spot_check` came back **0**, because spot-checking only
> draws from `auto_approve` records and this run auto-approved none. Drift detection is downstream
> of the router — when every record is already going to a human, there is nothing left to sample,
> and the calibration report becomes the *only* instrument that would surface a degrading cell.

---

## 2. Schema-enforced two-pass extraction

| Evidence | Value |
|---|---|
| Passing test count | **25 passed** ([`02-mortgage-extraction/tests.txt`](02-mortgage-extraction/tests.txt)) |
| Document run | `fixtures/documents/appraisal_informal_sqft.txt`, `income_missing_bonus.txt`, `income_sum_mismatch.txt` |
| Classified type | `appraisal` and `income_verification` — shown by `--verbose`: `classify: model=claude-haiku-4-5 in=2169 out=108 type=appraisal`, then `extract: ... tool=extract_appraisal` |

**2a. Two guarantees.** Paste your discrepancy-run output. Tool use already forces valid JSON, yet the
validator still catches a bad sum. Why are these two different guarantees? Name one error each cannot
catch.

> From [`02-mortgage-extraction/discrepancy-run.txt`](02-mortgage-extraction/discrepancy-run.txt):
>
> ```json
> "income": {
>   "base_monthly": 5416.67, "bonus_monthly": 1250.0, "commission_monthly": 2140.0,
>   "overtime_monthly": 385.5, "other_monthly": 450.0, "stated_monthly_total": 10892.17
> },
> "validation": {
>   "consistent": false,
>   "discrepancies": [
>     { "field": "total_monthly_income", "calculated": 9642.17, "stated": 10892.17, "delta": -1250.0 }
>   ]
> }
> ```
> ```
> exit code: 1
> ```
>
> They are different guarantees because they constrain different things. `tool_choice` plus the JSON
> Schema guarantees **shape**: `stated_monthly_total` will be a number or null, never the string
> `"$10,892.17"`, and never a missing key. The validator guarantees **internal coherence**: that the
> document's own claims agree with each other. Shape is checked by the API before my code runs;
> coherence can only be checked after, in Python, by recomputing the quantity independently and
> diffing it.
>
> The schema cannot catch this exact bug. `10892.17` is a perfectly well-formed `number` and
> satisfies every constraint in `mortgage_data_schema()`. No amount of schema tightening helps,
> because the error is a *relationship between two valid fields*, and JSON Schema has no vocabulary
> for "this field must equal the sum of those five."
>
> The validator, conversely, cannot catch an error where both sides are wrong in agreement. If OCR
> dropped a digit from `base_monthly` **and** the stated total had been computed from that same
> corrupted figure, `calculated` and `stated` would match to the cent and the report would read
> `consistent: true`. It is a cross-check, not a truth oracle — it proves the document is
> self-consistent, not that it is correct. It is also deliberately silent when there is nothing to
> compare: in my appraisal run every income field is `null`, `calculated_monthly_total` returns
> `None` rather than `0.0`, and the validator reports `consistent: true` with an empty
> `discrepancies` list because there is no comparison to make — not because it verified a zero.

**2b. Refusing to fabricate.** Run on a document missing a field. Paste that field's output. Why null
instead of an invented value? Point to the schema choice that allows it.

> From [`02-mortgage-extraction/extract-run.txt`](02-mortgage-extraction/extract-run.txt), running
> `income_missing_bonus.txt` (classified `income_verification`):
>
> ```json
> "income": {
>   "base_monthly": 5673.08,
>   "bonus_monthly": null,
>   "bonus_ytd": null,
>   "commission_monthly": null,
>   "overtime_monthly": null,
>   "other_monthly": null,
>   "stated_monthly_total": null
> }
> ```
>
> The document contains the word "bonus" **zero times** (`grep -ci bonus` → `0`). So `null` is the
> only honest answer: the document is *silent*, which is a different fact from "the borrower earned
> no bonus." An underwriter reading `0.0` would conclude the borrower's bonus income was verified at
> zero. Reading `null`, they know they still have to go and ask. Collapsing those two states destroys
> the distinction underwriting actually needs.
>
> Two schema choices make `null` legal rather than a contract violation:
>
> 1. **The nullable union.** `income.bonus_monthly` is declared
>    `{"type": ["number", "null"]}` — not `{"type": "number"}`. The model has a legal way to say
>    "unknown" without breaking the tool call.
> 2. **The absent `required` list.** The `income` sub-object has **no** `required` key at all, and
>    `doc_type_extractor(DocumentType.INCOME_VERIFICATION)` narrows the top level to just
>    `['borrower', 'income']`. Every name in a `required` list is a field the model *must* emit, and
>    when the document is silent the only way to comply is to invent something. Requiring
>    `bonus_monthly` would have been a standing licence to fabricate.
>
> The schema makes honesty *possible*; the prompt makes it *likely*. Rule 1 of the categorical
> criteria is "Return null for any field not explicitly stated in the document. Do not infer,
> default, or fabricate," reinforced by a few-shot example whose `<reasoning>` block spells out why
> zero and null are different claims. Both layers are needed — a permissive schema alone would still
> let a helpful model guess.

**2c. Normalization.** Quote one field where the source text and extracted value differ in format
("about 2,400 sq ft" → `2400`). Why normalize at extraction time rather than downstream?

> `fixtures/documents/appraisal_informal_sqft.txt`, line 37, reads:
>
> ```
> Gross Living Area:   approximately 2,400 sq ft (above-grade finished)
> ```
>
> and [`extract-run.txt`](02-mortgage-extraction/extract-run.txt) records:
>
> ```json
> "gross_living_area_sqft": 2400
> ```
>
> A bare integer — no hedge word, no comma, no unit, and typed `integer` rather than `string`.
>
> Normalizing at extraction is right because **this is the only moment the full context is still
> available**. Right here the model can see that "approximately" modifies a measurement, that the
> comma is a thousands separator rather than a decimal point (a genuine ambiguity in other locales),
> and that "sq ft" is the unit the field already assumes. A downstream consumer gets a naked string
> and has to reconstruct all of that from scratch.
>
> If I defer it, I don't write the parser once — I write it *n* times, once per consumer, and they
> will quietly disagree. The same document in this one fixture offers `~2,400`, `2,400 sf`, and
> `approximately 2,400 sq ft` (lines 63, 74, 37). One consumer strips non-digits, another regexes
> the first number, a third gives up and stores a string; now the LTV engine and the comparables
> engine report different square footage for the same house and nobody can tell which is right.
> Worse, every one of those parsers fails *silently* on an input it did not anticipate. Normalizing
> once at the boundary means the failure, if it happens, happens in one place, against the full
> document, under a schema that will reject a string where a number belongs. It is also what makes
> downstream arithmetic possible at all — the consistency validator in 2a can only subtract numbers,
> and `$5,416.67` is not a number.

---

## 3. Multi-source synthesis

| Evidence | Value |
|---|---|
| Passing test count | **34 passed** ([`03-supply-chain/tests.txt`](03-supply-chain/tests.txt)) |
| Briefing file | [`03-supply-chain/briefing.md`](03-supply-chain/briefing.md) (same content as `investigation-run.txt`) |
| Section the conflict landed in | **Contested**, flagged `⚠️ ESCALATE` |

**3a. Annotate, don't arbitrate.** Quote one conflicting-metric pair from your briefing — both values,
sources, dates. Give one way a reader is better served by the preserved conflict than by a single
reconciled number.

> From [`03-supply-chain/briefing.md`](03-supply-chain/briefing.md):
>
> ```
> ## Contested
> ### on_time_delivery_rate  _[2 sources, conflicting]_  ⚠️ ESCALATE
> - escalation: high-impact metric is contested across sources
> - Reported values by source:
>     - 95.0 percent — supplier_audit (as of 2026-04-10)
>     - 78.0 percent — logistics (as of 2026-04-05)
> ```
>
> A reconciled number would be ~86.5%, and that number is worse than useless — it is a figure no
> source ever reported, describing a supplier whose actual performance is either excellent or
> alarming. Both readings are actionable; the average is actionable in the wrong direction, because
> 86.5% looks like "slightly below target" and invites a note in a quarterly review rather than a
> phone call.
>
> The concrete way the preserved conflict serves the reader better: **it names a suspect.** The 95%
> is the supplier's own audit; the 78% is our own logistics telemetry, derived from the 50 shipment
> rows in `data/meridian/logistics.csv`, of which 11 missed their promised date — the same 11 the
> briefing reports as `late_shipment_count`. Seeing both with attribution, the reader immediately
> asks the right question — *is the supplier measuring "on-time" against a revised promise date
> while we measure against the original?* That is a specific, checkable hypothesis about a
> definitional mismatch, and it is only visible because the two numbers stayed apart and kept their
> sources. Averaging deletes the question along with the disagreement. The 17-point gap *is* the
> finding; it is the reason this metric is the one thing in the briefing carrying `⚠️ ESCALATE`.

**3b. Source goes dark.** Run with `--simulate-timeout`. Paste the part of the briefing showing the
failed source. How is "unreachable" handled differently from "nothing to report," and why does the run
still finish?

> From [`03-supply-chain/timeout-run.txt`](03-supply-chain/timeout-run.txt):
>
> ```
> > Sources unavailable: logistics unavailable (timeout)
> ```
> ```
> ## Incomplete
> ### late_shipment_count  _[missing source: timeout reading logistics]_
> - missing source: timeout reading logistics
> ```
>
> "Unreachable" and "nothing to report" are kept apart structurally, not by wording. A reader that
> succeeds returns `ok=True` with a possibly-empty `claims` list, and its metrics simply do not
> appear. A reader that *fails* returns `ok=False` carrying a `FailureContext` with
> `failure_type="timeout"`, and the coordinator turns that into an **Incomplete finding that names
> the cause**. So `late_shipment_count` does not silently vanish, and it emphatically does not
> render as `0` — it appears as a labelled hole with the reason attached. The difference matters
> because zero late shipments is excellent news and an unreachable logistics feed is no news at all.
>
> The run finishes because failure is modelled as a **value, not an exception**. `read_logistics`
> returns a `ReaderResult(ok=False, error=FailureContext(...))` instead of raising, so the
> coordinator's control flow is never interrupted; it collects claims from the three readers that
> did succeed, annotates the gap left by the one that didn't, and renders. Exit code is **0**. The
> alternative — letting one dead source abort the investigation — would mean a flaky 3PL portal can
> deny an analyst the audit, quality, and news findings that were retrieved perfectly well.
>
> One detail worth flagging: the partial claims computed from the first 5 rows before the timeout
> are carried inside the `FailureContext` but are deliberately **not** added to shared memory or the
> briefing. A 5-row sample would produce a real-looking on-time percentage indistinguishable from
> the 50-row figure. Keeping partials out of the vector store is what stops a truncated read from
> masquerading as a complete one.

**3c. Dates as a guardrail.** Quote two claims about the same supplier with different dates. How does
requiring a date stop a time difference from reading as a contradiction?

> Two pairs from [`briefing.md`](03-supply-chain/briefing.md), which behave in opposite ways:
>
> ```
> ### defect_rate_ppm  _[corroborated across 2 sources]_
>     - 180.0 ppm — supplier_audit (as of 2026-04-10)
>     - 190.0 ppm — internal_quality (as of 2026-04-08)
> ```
> ```
> ### on_time_delivery_rate  _[2 sources, conflicting]_
>     - 95.0 percent — supplier_audit (as of 2026-04-10)
>     - 78.0 percent — logistics (as of 2026-04-05)
> ```
>
> `source_date` is a **required field with no default** on the `Claim` model — a claim literally
> cannot be constructed without one. That forces every value to arrive as "X, as measured on D"
> rather than a free-floating fact, and that framing is what keeps a time difference from reading as
> a contradiction.
>
> The defect pair makes the point. 180 ppm and 190 ppm are different numbers from different systems
> two days apart. Without dates they look like two systems disagreeing about one quantity. With
> dates they are two consistent readings of a drifting process, and the 10 ppm gap is explained by
> the two days rather than by anyone being wrong — which is exactly how the system classifies it
> (`corroborated across 2 sources`, within the 10% relative tolerance).
>
> The dates also change what a human *does* about the on-time conflict. 95% is the **later** reading
> (2026-04-10) and 78% the **earlier** (2026-04-05). That ordering makes "did performance recover in
> those five days?" a real hypothesis worth checking — distinct from "one of these sources is
> broken." Both remain on the table, and the reader has the one piece of information needed to tell
> them apart. Strip the dates and the finding collapses to "two numbers, pick one." Note too that
> dates alone are not sufficient: the 17-point on-time gap stays Contested *despite* having clean
> dates, because the gap exceeds tolerance. Dates explain small divergences; they do not excuse
> large ones.

---

## 4. Synthesis

**4a. One principle.** Name the single moment in your runs (system + artifact) where *evaluate the
output, don't trust the model's word* most clearly caught something a trusting design would have
shipped.

> **System 1, `POL-2025-003` in [`routing_decisions.json`](01-policy-pipeline/routing_decisions.json).**
>
> The extractor returned a complete, schema-valid record and rated it `coverage_limit: 0.95`,
> `deductible: 1.0`, `policy_type: 1.0`, `premium_amount: 1.0`. Nothing in the model's own output
> suggested a problem — `fields_below_threshold` is `[]` and `integration_failures` is `[]`. A design
> that asked the model how it did and believed the answer would have auto-approved this policy, and
> a wrong coverage limit would have gone to a customer.
>
> It was caught because the system never asked the model to grade itself as the deciding step. It
> paid for a second, independent opinion — a reviewer that saw only the source document and the
> proposed extraction, with none of the extractor's prompts or reasoning — and that reviewer
> disagreed on `coverage_limit`. The entire reason a human will look at this record is a judgement
> formed outside the extractor's own context.
>
> The sharpest part is the specificity: the reviewer disputed `coverage_limit`, the exact field the
> extractor rated 0.95. The model's confidence was not merely uninformative, it was
> *anti-informative* — highest precisely where it was wrong.

**4b. Confidence ≠ correctness.** Pick the system where this mattered most, and explain why using
something you observed.

> **The policy pipeline**, and the two artifacts compound each other.
>
> At the record level, `POL-2025-003` shows self-rated confidence and correctness coming apart on a
> single field. At the population level,
> [`calibration-report.txt`](01-policy-pipeline/calibration-report.txt) shows the same divergence is
> *systematic*: `umbrella / exclusions` runs `conf=0.93, acc=0.00, brier=0.865`. That is not noise
> or an unlucky draw. The model is confidently wrong about umbrella exclusions **every time**,
> always in the same place, with no change in its stated confidence between the cases it gets right
> and the cases it gets wrong.
>
> This is why confidence cannot be the gate, and it is a stronger claim than "models are sometimes
> overconfident." A threshold only works if the score *moves* when accuracy moves. Here it doesn't:
> 0.93 on a cell that is never right sits comfortably above the 0.90 bar, so raising the threshold
> to 0.92 or 0.94 changes nothing about which records escape. The failure is not a miscalibrated
> cutoff, it is that the signal carries no information in the region that matters.
>
> The design conclusion the pipeline draws is the right one: confidence is demoted to *one of three*
> independent inputs, any of which can escalate. Two of those three — reviewer agreement and the
> integration pass — are computed without consulting the extractor at all, and the integration pass
> is not a model at all but deterministic Python. In my run that structure was load-bearing rather
> than theoretical. All **9** routed records went to `human_review`; the reviewer flagged **9**,
> confidence flagged **3** (`POL-2025-001`, `POL-2025-006`, `POL-2025-010` — all three also flagged
> by the reviewer), and the integration pass flagged **0**. So confidence alone would have caught 3
> and let the other **6 ship unreviewed**, while the reviewer alone would have caught all 9.

**4c. Apply it.** Describe a real workflow where an LLM pulls structured results from messy input.
Which pattern — validated retry with escalation, independent review with deterministic routing, or
provenance-preserving conflict annotation — would you reach for first, and what would you instrument
to know when it broke?

> **Workflow.** Supplier invoice intake for a retail group: a few thousand PDFs a month from
> hundreds of vendors, arriving as scans, emailed photos, and EDI printouts in several languages and
> currencies. Each must yield vendor identity, invoice number, currency, line items, tax, and total,
> which then feed three-way matching against purchase orders and goods receipts. Errors are not
> abstract — they become duplicate payments, missed early-payment discounts, and VAT filings that
> have to be amended.
>
> **First pattern: validated retry with escalation.** This workflow's dominant failure mode is
> ambiguity in the document itself, not model incompetence, and the retry/escalation split is the
> only one of the three patterns that distinguishes those. Most of what goes wrong is mechanically
> checkable — line items must sum to the subtotal, subtotal plus tax must equal the total, the
> currency must be one the vendor actually trades in, the invoice date cannot be in the future.
> Those are `format`/`consistency` failures and feeding the offending value back verbatim genuinely
> fixes them, exactly as the retry loop does. But a scan whose second page is missing, or a photo
> with the total obscured by a thumb, is `missing_source`: no number of retries produces the figure,
> and a retry loop that keeps pushing is, as in 1a, applying pressure toward a plausible invention
> on a document where the plausible wrong answer costs real money. The $1.00-tolerance idea
> transfers directly too — cent-level rounding from OCR must not trip a discrepancy, or every
> itemised invoice escalates and the queue becomes noise.
>
> I would layer the other two rather than choose between them. Independent review is worth its cost
> on the small, expensive tail — invoices above a value threshold, or from vendors with no payment
> history — on the strength of 1b: the reviewer caught what confidence missed. And I would borrow
> conflict annotation for three-way matching specifically: when the invoice says 500 units and the
> goods receipt says 480, the system must surface *both with their sources and dates*, never
> silently reconcile. That is precisely the 95%/78% situation, and the 20-unit gap is the finding.
>
> **What I would instrument.**
>
> 1. **A sliced calibration report, `vendor × field`, not a global accuracy number.** Straight from
>    1c: a single aggregate would have hidden `umbrella/exclusions` at `acc=0.00` behind healthy
>    cells. The analogue here is one vendor changing their invoice template and that vendor's
>    `tax_amount` cell going to zero accuracy while the overall figure barely moves. With hundreds
>    of vendors the dilution is far worse than in the 6-sample report I ran.
> 2. **Escalation rate split by `detected_pattern`, tracked per vendor.** The pipeline already
>    emits this — my run's `pattern_summary` named `endorsements_absent` and
>    `premium_does_not_match_components` with the exact policy ids. A sudden spike in one pattern
>    for one vendor is a template change; a spike in `missing_source` across all vendors points at
>    the scanning pipeline, not the model. The pattern tag is what makes the alert actionable
>    instead of merely alarming.
> 3. **Stratified spot-checks of auto-approved invoices, bucketed by vendor,** with
>    `max(1, ceil(pct * n))` per stratum. Without the `max(1, ...)` floor, low-volume vendors round
>    to zero samples and are never audited — and low-volume, unusual-format vendors are exactly
>    where extraction breaks. My own run taught me the prerequisite the hard way: `spot_check` came
>    back **0**, because the sampler only draws from auto-approved records and nothing auto-approved.
>    So I would alert on the *auto-approve rate itself*. A rate near zero means the pipeline is
>    paying for extraction and still sending everything to a human; a rate near 100% means the
>    checks have gone slack. Either way the spot-check sample silently stops being representative,
>    and I would not learn that from the sample.
> 4. **Coverage annotations that travel with the record, and an alert when a source goes quiet.**
>    My System 3 perturbation taught me this one. When the logistics feed timed out, the Contested
>    section went to `_none_` and the supplier's flattering 95% became an unchallenged
>    Well-Established fact. Degraded coverage *looked like* consensus. Translated: if the goods-receipt
>    system is down, invoices must not quietly pass three-way matching on two legs. They need a
>    visible `[single source only]` badge and a count of how many records were approved under
>    degraded coverage — because the dangerous failure here is not an error, it is a check that
>    stopped running without anyone noticing.
