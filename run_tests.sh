#!/usr/bin/env bash
# One command to verify the whole engine. Rebuilds the golden file first
# (the independent authority the formatter is checked against), then runs
# all thirteen suites. Exits non-zero if any fail.
set -e
cd "$(dirname "$0")"
python3 build_golden.py >/dev/null
fail=0
for t in test_tracciato test_validate test_parser test_textmail test_stay test_orchestrator test_infer test_llm_parser test_storage test_export test_supplements test_name_plausibility test_skip_nondestructive; do
  if python3 "$t.py" >/dev/null 2>&1; then echo "PASS  $t"; else echo "FAIL  $t"; fail=1; fi
done
rm -f soglia.db
[ $fail -eq 0 ] && echo "ALL GREEN (13/13)" || { echo "SOME FAILED"; exit 1; }
