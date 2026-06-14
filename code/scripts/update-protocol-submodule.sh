#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  code/scripts/update-protocol-submodule.sh
  code/scripts/update-protocol-submodule.sh --commit <protocol-commit>

Default:
  Update code/protocol_repo to the latest configured origin/main.

Explicit commit mode:
  Pin code/protocol_repo to the given protocol commit.
USAGE
}

target_commit=""

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
elif [[ "${1:-}" == "--commit" ]]; then
  target_commit="${2:-}"
  if [[ -z "$target_commit" ]]; then
    echo "Missing commit after --commit."
    usage
    exit 1
  fi
elif [[ $# -gt 0 ]]; then
  echo "Unknown argument: $1"
  usage
  exit 1
fi

if ! git -C code/protocol_repo diff --quiet || ! git -C code/protocol_repo diff --cached --quiet; then
  echo "code/protocol_repo has uncommitted changes. Commit or stash them first."
  exit 1
fi

if [[ -n "$target_commit" ]]; then
  git -C code/protocol_repo fetch origin
  git -C code/protocol_repo checkout "$target_commit"
else
  git submodule update --remote code/protocol_repo
fi

if git diff --quiet -- code/protocol_repo; then
  echo "code/protocol_repo is already up to date."
  exit 0
fi

git add code/protocol_repo
if [[ -n "$target_commit" ]]; then
  git commit -m "Pin protocol submodule to $target_commit"
else
  git commit -m "Update protocol submodule to latest main"
fi
git push
