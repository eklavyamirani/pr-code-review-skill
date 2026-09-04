#!/usr/bin/env bash
# Remove the worktrees a review left behind.
#
#   cleanup-review.sh <outdir> [--all]
#
# A review leaves <outdir>/.work: a --shared clone plus the base and pr
# worktrees, kept so that a later `pr-review ... -- cmd` finds them. That is
# the only state on disk; the container itself is --rm and /repo was mounted
# read-only. --all removes the whole output directory, review page included.
set -euo pipefail

OUT=${1:?usage: cleanup-review.sh <outdir> [--all]}
[ -d "$OUT" ] || { echo "cleanup-review: no such directory: $OUT" >&2; exit 1; }
OUT=$(cd "$OUT" && pwd)

if [ "${2:-}" = "--all" ]; then
  rm -rf "$OUT"
  echo "removed $OUT"
  exit 0
fi

# The worktrees only ever point at the throwaway clone in the same directory,
# so there is no host repository to deregister them from.
rm -rf "$OUT/.work"
echo "removed $OUT/.work — review.json and review.html kept"
