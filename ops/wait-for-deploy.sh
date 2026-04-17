#!/usr/bin/env bash
# ops/wait-for-deploy.sh
#
# Wait for Railway to deploy the current commit. Polls /health and
# compares the `version` field against the checked-out `.version`
# file. Exits non-zero after ~10 min of polling so CI fails loudly
# instead of hanging indefinitely.
#
# Used from .github/workflows/post-deploy.yml right before the smoke
# test step so we never probe the *previous* deploy.

set -euo pipefail

BASE_URL="${BASE_URL:-https://flow-procurement.up.railway.app}"
EXPECTED_VERSION=$(cat .version)

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
