#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -z "${NODE_AUTH_TOKEN:-}" ]]; then
  if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "Missing token. Set NODE_AUTH_TOKEN or GITHUB_TOKEN with a GitHub PAT (write:packages)." >&2
    exit 1
  fi
  export NODE_AUTH_TOKEN="$GITHUB_TOKEN"
fi

REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export npm_config_cache="$REPO_ROOT/.tmp_npm_cache_publish"

npm run release:github
