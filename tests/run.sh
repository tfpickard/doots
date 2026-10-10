#!/usr/bin/env bash
# Run every tests/test-*.sh. Exit non-zero if any file reports a failure.
set -uo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT=$(pwd)
export REPO_ROOT

rc=0
for t in tests/test-*.sh; do
    printf '%s\n' "$t"
    bash "$t" || rc=1
done
exit "$rc"
