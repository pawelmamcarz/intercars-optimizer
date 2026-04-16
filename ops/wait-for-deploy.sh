#!/usr/bin/env bash
# ops/wait-for-deploy.sh
#
# Wait for Railway to deploy the current commit. Polls /health and
# compares the `version` field (bumped by the pre-commit hook) against
# the short version in app/config.py:app_version from the checked-out
# working tree. Exits non-zero after ~10 min of polling so CI fails
# loudly instead of hanging indefinitely.
#
# Used from .github/workflows/post-deploy.yml right before the smoke
# test step so we never probe the *previous* deploy.

set -euo pipefail

BASE_URL="${BASE_URL:-https://flow-procurement.up.railway.app}"
EXPECTED_VERSION=$(python3 -c "
import re, pathlib
text = pathlib.Path('app/config.py').read_text()
m = re.search(r'app_version:\s*str\s*=\s*\"([\d.]+)\"', text)
print(m.group(1) if m else 'unknown')
")

if [ "$EXPECTED_VERSION" = "unknown" ]; then
  echo "could not extract app_version from app/config.py" >&2
  exit 2
fi

echo "Waiting for $BASE_URL to report version=$EXPECTED_VERSION"

for i in $(seq 1 60); do
  actual=$(curl -sf "$BASE_URL/health" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("version",""))' 2>/dev/null || echo "")
  if [ "$actual" = "$EXPECTED_VERSION" ]; then
    echo "  v$actual live after ${i} attempts (~$((i*10))s)"
    exit 0
  fi
  echo "  attempt $i: server reports v'$actual', expecting v$EXPECTED_VERSION"
  sleep 10
done

echo "Timed out after 10 min waiting for $EXPECTED_VERSION on $BASE_URL" >&2
exit 1
