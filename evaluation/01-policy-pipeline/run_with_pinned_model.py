"""Run the real `policy-extractor` CLI with a dated model id pinned.

Why this exists: the API gateway resolves the dated id
`claude-haiku-4-5-20251001` reliably, but intermittently rejects the alias
`claude-haiku-4-5` with HTTP 400 ("not available for your organization").
The alias is the package default AND is asserted verbatim by
tests/test_us03_review.py::test_default_models, so it is pinned here at call
time instead of being edited in the package source.

This changes only the model string. All pipeline logic -- retry loop,
validator, escalation -- runs exactly as the installed package defines it.

Usage (from the policy pipeline solution/ directory):
    .venv/bin/python <this file> extract <document> --policy-id <id>
"""

import sys

from policy_extractor import __main__ as cli
from policy_extractor.retry import extract_with_retry
from policy_extractor.reviewer import independent_review

EXTRACTOR_MODEL = "claude-haiku-4-5-20251001"
REVIEWER_MODEL = "claude-sonnet-4-5-20250929"

extract_with_retry.__kwdefaults__["model"] = EXTRACTOR_MODEL
independent_review.__kwdefaults__["model"] = REVIEWER_MODEL

if __name__ == "__main__":
    print(f"[model pin] extractor={EXTRACTOR_MODEL}", file=sys.stderr)
    raise SystemExit(cli.main(sys.argv[1:]))
