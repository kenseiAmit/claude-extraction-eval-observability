# Reflection Brief — Harness Engineering Capstone

**Author:** Amit Kumar
**Date:** September 2026

Every answer cites at least one artifact from our runs — a run ID, file path, token count, claim outcome, or test count. Short artifact snippets are pasted where they provide direct evidence.

**Environment**

- Model(s): Claude 3.5 Sonnet / Claude 3 Haiku / Claude Haiku 4.5 (`claude-haiku-4-5-20251001` with `anthropic 0.39.0` / `0.69.0`)
- OS / Python: macOS (Darwin) / Python 3.11 / Python 3.14
- Approx. API spend: Live runs on API endpoint ≈ $0.25 (across test runs and full evaluation)

---

## Part 1 — Per-system

### System 1 — Agentic loop

1. **Loop control.** Quote the `stop_reason` sequence from one trace. Name the file and function that decides continue-vs-stop, and how.
   → In `submission/system-1-claims-intake/runs/20260923_011214/traces/claim_01_kitchen_fire.jsonl`, the observed `stop_reason` sequence across 4 turns is `["tool_use", "tool_use", "tool_use", "end_turn"]`. The decision logic resides in `claims_intake/loop.py` inside the `run(...)` function. It executes a `while True:` loop where `response.stop_reason` directly determines control flow: `if response.stop_reason == "end_turn"` it appends the final assistant block and returns a `FinalState` object; `elif response.stop_reason == "tool_use"` it executes each tool block, appends all `tool_result` blocks in a single user turn, and calls `continue`; and any unhandled reason raises an `UnexpectedStopReason` exception.

2. **Anti-pattern.** Name one anti-pattern `test_antipatterns.py` checks for. What would break in your run if the loop used it?
   → The `test_no_integer_literal_iteration_cap_in_loop` in `Build a Claims Intake Agent with a stop_reason-Driven Loop/exercises/03-dynamic-decomposition/tests/test_antipatterns.py` checks for hardcoded iteration caps like `for _ in range(10)` or `while turn < 10`. If the loop used this, a complex claim requiring multiple rounds of clarification and fact recording (such as `claim_06_low_confidence_escalation`, which took 6 turns) would risk premature termination if capped arbitrarily, failing to gather all facts and properly route or escalate. The correct approach, enforced by the AST test and verified in our passing test suite (`29 passed in 0.14s`), is to let `response.stop_reason` govern termination while using a flexible `Budget` object for token/wall-clock safety.

3. **Tool design.** Pick two tools with overlapping inputs. How do the descriptions prevent misrouting? What did a structured tool error let the agent do that a generic string would not?
   → In `Build a Claims Intake Agent with a stop_reason-Driven Loop/exercises/03-dynamic-decomposition/claims_intake/tools.py`, both `classify_claim` and `assess_severity` accept a `rationale` string. Their descriptions prevent misrouting by explicitly bounding their scope: `classify_claim` specifies committing to a high-level `claim_type` enum (with confidence in [0, 1]), whereas `assess_severity` specifies committing to `low`/`medium`/`high` reflecting damage magnitude and policy limits. For structured errors, when `lookup_policy` cannot find a policy ID, it returns `{"is_error": true, "error_category": "permanent", "is_retryable": false, "message": "Policy not found: ..."}`. This structured payload informs the model that retrying the same ID is futile, prompting it to ask for the correct ID or escalate, whereas a generic string could lead to repetitive retries.

4. **Your numbers.** Quote the turn count and cost for one claim. How does it differ from the README sample, and why?
   → For `claim_01_kitchen_fire` in run `20260923_011214` (`submission/system-1-claims-intake/runs/20260923_011214/summary.md`), the interaction took **4 turns**, consuming **14,666 input tokens** and **835 output tokens** for an estimated cost of **$0.0188 USD** over 10.2s elapsed time (successfully routed to `property_damage` queue with `high` severity). In comparison, the README sample estimates an average cost of ≈ $0.006 to $0.010 per simple claim on Haiku 4.5. Our observed cost is slightly higher because cumulative multi-turn conversation history is passed on every turn (accumulating ~2.8k, ~3.5k, ~4.0k, ~4.2k prompt tokens across turns 1–4) and detailed rationales were generated for both classification and severity assessment.

### System 2 — Context strategy

5. **The reduction.** From `budget.json`: baseline tokens, assembled tokens, reduction %. Which section dominates the assembled context, and why keep it verbatim?
   → In `submission/system-2-retail-context/runs/20260923-014423/budget.json`, the baseline transcript contains **38,708 tokens**, the assembled context contains **16,736 tokens**, achieving a **56.76% reduction**. The **`active` section dominates** the assembled context at **15,789 tokens** (~94.3% of the total assembled volume). We keep the active segment byte-exact and verbatim because it represents the ongoing, unresolved customer interaction (`payment_update`) where exact phrasing, card details, failure error codes, and customer turn-by-turn context are actively being resolved; summarizing the active segment would introduce loss of fidelity or state hallucination.

6. **Summarize vs preserve.** State the rule for what gets summarized vs kept byte-exact, citing your per-section token numbers.
   → The rule is: **Resolved historical threads are summarized and structured into case facts, while active unresolved threads are preserved byte-exact at the bottom attention boundary.** Specifically:
     - `case_facts`: Structured key-value block at the top boundary (**204 tokens**).
     - `resolved_refund`: Summarized to **370 tokens** (compressed from 12,334 input tokens).
     - `resolved_subscription`: Summarized to **391 tokens** (compressed from 11,475 input tokens).
     - `active` (payment update): Preserved 100% byte-exact at **15,789 tokens**.

7. **Facts block.** Compare `eval.jsonl` to `eval_control.jsonl`. Which question regressed, and what does that prove?
   → In `submission/system-2-retail-context/runs/20260923-014423/eval.jsonl`, all 6 evaluation questions passed (**6/6 PASS**). In `eval_control.jsonl` (expanded to evaluate all 6 questions with the `# Case Facts` header block stripped), questions answerable from narrative summaries (Q1 refund amount, Q2 cancellation reason, Q5 proration) and active verbatim turns (Q3 failure code, Q4 card last-4) remained robust (PASS). However, **Question 6 regressed from PASS to FAIL** (the model failed to return the exact structured status `in_progress`, falling back to paraphrasing "Active issue"). This proves that the top-boundary Case Facts block is load-bearing: critical structured state tokens cannot be reliably inferred from unstructured narrative text alone, proving the necessity of structured context engineering for long conversations.

### System 3 — Claude Code config

8. **Path-scoped rules.** Quote the glob frontmatter from one rule file. Why is it better than a directory-level CLAUDE.md for cross-cutting conventions?
   → In `submission/system-3-claude-code-config/.claude/rules/react.md`:
     ```yaml
     ---
     description: Conventions for React components and pages
     paths:
       - "src/components/**/*"
       - "src/pages/**/*"
     ---
     ```
     Path-scoped rules dynamically inject guidance into the prompt *only* when the model reads or edits files matching the glob pattern, saving context budget. Unlike a directory-level `CLAUDE.md` which requires scattered maintenance and bloats whenever navigating folders, path-scoped rules centralize conventions and naturally support cross-cutting concerns (e.g., `.claude/rules/tests.md` matching `src/**/*.test.{ts,tsx}` across both frontend and backend domains simultaneously).

9. **Forked skill.** Quote the `context: fork` and `allowed-tools` lines. What does running forked + read-only buy you? What breaks without it?
   → In `submission/system-3-claude-code-config/.claude/skills/deploy-check/SKILL.md`:
     ```yaml
     context: fork
     allowed-tools:
       - Read
       - Grep
       - Glob
       - Bash(git status:*)
       - Bash(git diff:*)
       - Bash(git log:*)
       - Bash(git rev-parse:*)
       - Bash(git ls-files:*)
       - Bash(gh pr view:*)
       - Bash(gh pr checks:*)
     ```
     Running forked executes the pre-deployment verification in an isolated sub-agent, preventing megabytes of verbose discovery output (diffs, branch listings, log dumps) from polluting the main session's context window. Restricting tools to read-only guarantees safety during pre-deployment audits. Without `context: fork`, verbose validation logs displace prior task history in the main context; without read-only restrictions, an agent performing validation could inadvertently mutate files or execute stateful git operations immediately prior to shipping.

10. **Scope.** From the validator output: project-level vs user-level scope. Give one example of each from this config.
    → As verified by `python -m ecommerce_team_config .` (`OK` across all 35 test assertions):
      - **Project-level scope:** Committed into the repository under `.claude/` (e.g., `.claude/rules/api.md`, `.claude/commands/review.md`), establishing shared, team-wide conventions that apply uniformly to all developers on the codebase.
      - **User-level scope:** Local developer configuration stored in `~/.claude/` or `~/.claude.json` (such as individual developer API keys, custom CLI aliases, or local scratchpad notes), which are explicitly not committed to version control to avoid stomping team standards.

### System 4 — Orchestration

11. **Push work down.** Defects the SQL query returned vs warm-tier total. Name the indexed query. Why does the model never see the full history?
    → In `Build a Multi-Shift Quality Monitoring System with Claude Orchestration/04-fork-scratchpad/shift_monitor/warm.py`, `WarmStore.defects_since` executes the indexed query `SELECT * FROM defects WHERE ts > ? ORDER BY ts DESC LIMIT ?` using index `idx_defects_ts ON defects(ts)`. In our evaluation against `fixtures/defects.json`, the query returned only **5 defects** out of the **40 total defects** stored in the warm SQLite tier (`data_test/warm.sqlite`). The model never sees the full raw history because time filtering and monthly aggregations are pushed down into SQLite and `ColdStore`, preventing token bloat, lowering inference latency, and keeping Claude focused on shift anomalies.

12. **Crash recovery.** The resume-vs-fresh decision and its staleness threshold (`recovery.py`). Why is a fresh start with an injected summary sometimes more reliable than resuming?
    → In `Build a Multi-Shift Quality Monitoring System with Claude Orchestration/04-fork-scratchpad/shift_monitor/recovery.py`, the `decide(state, now)` function checks `STALE_RESUME_THRESHOLD_MINUTES = 30` (representing ~1/16 of an 8-hour shift). If a crash occurred within 30 minutes, it returns `"resume"`; beyond 30 minutes or on an empty/completed manifest, it returns `"fresh"`. A fresh start with an injected summary is more reliable than resuming stale runs because physical equipment conditions, defect queues, and shift contexts drift over time; resuming a half-executed prompt hours later risks acting on stale premises, whereas a fresh run cleanly ingests latest state alongside summarized prior findings.

13. **Small state.** Byte size of your `hot_state.json`. Why does the budget matter for a system run once per shift, indefinitely?
    → Our live `submission/system-4-shift-orchestrator/hot_state.json` file measures **584 bytes** (validated against the `HOT_STATE_BYTE_BUDGET = 5_120` byte ceiling in `shift_monitor/state.py` with `MAX_RECENT_HASHES = 20`). This tight byte budget is vital because in a multi-shift production system running 3 shifts a day (over 1,000 runs per year), unbounded state accumulation would continually inflate prompt token sizes, causing cost explosion and context dilution. The strictly enforced 5 KB bound ensures constant, predictable $O(1)$ token overhead per shift indefinitely.

---

## Part 2 — Synthesis

*Graded on connecting two or more systems. Cite a named file/artifact from each.*

14. **Three layers.** Point to a file/artifact for each layer and justify.
    → **Model Layer:** `submission/system-1-claims-intake/runs/20260923_011214/traces/claim_01_kitchen_fire.jsonl` (and `retail_context/case_facts.py`). Responsible for core semantic inference, intent understanding, claim severity rationale generation, and structured factual extraction.
    → **Harness Layer:** `Build a Claims Intake Agent with a stop_reason-Driven Loop/exercises/03-dynamic-decomposition/claims_intake/loop.py` (and `retail_context/assemble.py`). Governs the deterministic execution loop, parses `response.stop_reason`, executes tool calls, enforces AST safety constraints, and arranges context anatomy (headers and top/bottom boundaries).
    → **Orchestration Layer:** `Build a Multi-Shift Quality Monitoring System with Claude Orchestration/04-fork-scratchpad/shift_monitor/pipeline.py` (and `recovery.py`, `fork.py`). Manages multi-shift operational lifecycles, database pushdown queries (`defects_since`), atomic hot state persistence, crash-recovery decisions, and hypothesis branch isolation.

15. **Deterministic vs prompt.** Cite one behavior guaranteed in code (terminal tool, read-only allowlist, atomic write, byte budget) and one guided by prompt. When is each right?
    → **Guaranteed in code:** `shift_monitor/state.py` (lines 34–45) enforcing atomic writes via `os.fsync` + `os.replace` and strict byte budgeting (`HOT_STATE_BYTE_BUDGET = 5_120`), and `claims_intake/loop.py` terminating deterministically upon `response.stop_reason == "end_turn"`.
    → **Guided by prompt:** `claims_intake/prompts/system.md` instructing the assistant on how to empathetically probe claimants for missing damage information without sounding interrogative.
    → **When is each right:** Deterministic code is non-negotiable for system invariants, state integrity, memory/token safety caps, error categorization, and security permissions. Prompt guidance is appropriate for probabilistic semantic behaviors, tone management, synthesis, and conversational diplomacy.

16. **Context, two faces.** Compare context management in System 2 (intra-session) and System 4 (cross-session) with cited numbers from both. Same principle, different mechanism — how?
    → **System 2 (Intra-session):** In `submission/system-2-retail-context/runs/20260923-014423/budget.json`, an active 48-turn transcript was compressed from **38,708 baseline tokens** down to **16,736 tokens** (**56.76% reduction**) by structuring `# Case Facts` (204 tokens) at the top boundary, summarizing resolved threads (370 and 391 tokens), and preserving the active segment (15,789 tokens) verbatim at the bottom.
    → **System 4 (Cross-session):** In `submission/system-4-shift-orchestrator/`, instead of feeding accumulated shift histories (40+ defects in `warm.sqlite`), `WarmStore.defects_since` SQL index filters down to only **5 new defects**, keeping `hot_state.json` at a compact **584 bytes** (well under the 5,120-byte ceiling).
    → **Principle vs Mechanism:** Both systems uphold the core harness engineering principle of protecting the context window from attention degradation ("lost in the middle") and runaway token costs. System 2 achieves this *within a session* via LLM-driven structured compression and boundary positioning; System 4 achieves this *across sessions* via relational database pushdown filtering and bounded atomic state files.

17. **Reliability you can't see in one run.** Name one behavior a test guarantees that a single successful run would not reveal. Why does it matter before shipping?
    → `Build a Multi-Shift Quality Monitoring System with Claude Orchestration/04-fork-scratchpad/tests/test_us03_crash_recovery.py::test_mid_write_read_reveals_prior_complete_lines` in System 4 and `Build a Claims Intake Agent with a stop_reason-Driven Loop/exercises/03-dynamic-decomposition/tests/test_antipatterns.py::test_no_integer_literal_iteration_cap_in_loop` in System 1. A single happy-path live run will never reveal whether an unexpected mid-write crash or power outage leaves corrupt JSON on disk, or whether a complex 6-turn claim (like `claim_06_low_confidence_escalation`) would get truncated prematurely by an arbitrary hardcoded iteration counter (`for _ in range(5)`). Automated AST and recovery testing guarantees system survivability under edge cases before deploying to production.

18. **Blast radius.** Pick one system. What's the blast radius if it misbehaves, and what's the kill switch? Ground it in that system's tools, enforcement points, and state.
    → **System 1 (Insurance Claims Intake Agent):**
      - **Blast radius:** If unconstrained, a hallucinating agent could emit invalid financial coverage guarantees to claimants or misclassify severe liability claims into low-priority queues, delaying emergency response.
      - **Kill switch & Containment:**
        1. *Strict Tool Schema:* The model only has access to read-only tools (`lookup_policy`, `check_coverage_limits`) and terminal action tools (`route_claim`, `escalate_claim`). It cannot directly issue payouts.
        2. *Deterministic Routing & Confidence Gate:* Low confidence (< 0.6) or ambiguous multi-party bodily injuries are mandatorily directed to `escalate_claim` for human adjuster review.
        3. *Budget Termination:* `claims_intake/budget.py` enforces a maximum turn cap (10 turns) and token limits, aborting any runaway loops via `BudgetExceededError`.

---

## Part 3 — Honest assessment

19. **What broke.** One thing that failed first try in your environment, and how you fixed it. (If nothing, what you checked to be sure.)
    → During initial live SDK inference runs, requests to the evaluation API gateway encountered an SSL handshake verification failure due to our local environment running behind an enterprise TLS inspection proxy. We diagnosed this via connection traceback and fixed it by configuring `export SSL_CERT_FILE="<custom-ca-certs>/custom-root-ca.pem"` and `REQUESTS_CA_BUNDLE` in the environment, while updating the client initialization in `shift_monitor/client.py` and `retail_context/client.py` to seamlessly read custom endpoint base URLs and target model names.

20. **What you'd change.** One architectural decision you'd make differently, grounded in what you observed.
    → In System 2 (Context Strategy), the compression pipeline executes sequential synchronous API calls for each resolved thread (`resolved/refund` followed by `resolved/subscription`). In a production copilot, I would re-architect `compressor.py` to use `asyncio.gather` with `AsyncAnthropic` to run segment summarizations concurrently. Furthermore, I would use Anthropic Structured Outputs (`tool_use` schema extraction) for `case_facts.py` rather than standard prompt extraction, completely eliminating downstream parsing errors.
