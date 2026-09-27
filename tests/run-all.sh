#!/usr/bin/env bash
# Every offline test. No game required, nothing is launched.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
failed=0
for test in "$here"/test_*.py; do
  echo "== $(basename "$test")"
  python3 "$test" || failed=1
done
echo "== doctor"
python3 -m civ7lab doctor >/dev/null || failed=1
exit $failed
