#!/usr/bin/env bash
# Container entrypoint. /repo is the host repository, read-only. /out is the
# only writable path shared with the host.
set -euo pipefail

# The container may run as an arbitrary host uid (see bin/pr-review --user),
# so nothing may assume /home/reviewer exists or is writable.
export HOME=${HOME:-/tmp}
[ -w "$HOME" ] || export HOME=$(mktemp -d)
export GIT_CONFIG_GLOBAL=$HOME/.gitconfig
git config --global --add safe.directory '*' 2>/dev/null || true
git config --global user.email review@localhost 2>/dev/null || true
git config --global user.name  "pr-review"      2>/dev/null || true

# A bare invocation drops you in a shell with the tools on PATH.
if [ $# -eq 0 ]; then exec bash; fi

# Anything that isn't a ref pair is a command to run inside the container.
case "${1:-}" in
  --pr|-*|"") ;;
  *) if command -v "$1" >/dev/null 2>&1; then exec "$@"; fi ;;
esac

exec /opt/pr-review/scripts/setup-review.sh "$@"
