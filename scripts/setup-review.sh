#!/usr/bin/env bash
# Build a review workspace inside the container.
#
#   setup-review.sh <base-ref> <head-ref>
#   setup-review.sh --pr <N> [base-ref]
#
# The host repo at /repo is never written to. We clone it locally with
# --shared, so objects are read through alternates and the two worktrees cost
# almost nothing on disk.
set -euo pipefail

SRC=/work/src
WORK=/work
OUT=${OUT_DIR:-/out}

if [ "${1:-}" = "--pr" ]; then
  PR=${2:?--pr needs a number}
  BASE=${3:-}
  PR_REF="refs/pull/$PR/head"
else
  BASE=${1:?usage: setup-review.sh <base-ref> <head-ref> | --pr <N>}
  HEAD_REF=${2:?usage: setup-review.sh <base-ref> <head-ref> | --pr <N>}
fi

git clone --quiet --shared --no-checkout /repo "$SRC"
cd "$SRC"

if [ -n "${PR:-}" ]; then
  ORIGIN=$(git -C /repo remote get-url origin)
  git remote set-url origin "$ORIGIN"
  git fetch --quiet origin "$PR_REF:pr$PR"
  HEAD_REF="pr$PR"
  # A PR branch usually carries merged-in base commits; the interesting range
  # starts at the merge base, not at whatever the branch happens to contain.
  [ -n "$BASE" ] || BASE=$(git rev-parse "$HEAD_REF^") || BASE=origin/HEAD
fi

BASE_SHA=$(git rev-parse --verify "$BASE")
HEAD_SHA=$(git rev-parse --verify "$HEAD_REF")
MERGE_BASE=$(git merge-base "$BASE_SHA" "$HEAD_SHA")

git worktree add --quiet --detach "$WORK/base" "$MERGE_BASE"
git worktree add --quiet --detach "$WORK/pr"   "$HEAD_SHA"

mkdir -p "$OUT"
git diff "$MERGE_BASE..$HEAD_SHA" --stat > "$OUT/changes.txt"
git diff "$MERGE_BASE..$HEAD_SHA"         > "$OUT/full.diff"
git log --format='%H%n%an%n%ad%n%s%n%n%b' "$MERGE_BASE..$HEAD_SHA" > "$OUT/commits.txt"

# Machine-readable per-file summary, so the annotator can order hunks without
# re-parsing the diff.
python3 - "$OUT" <<'PY'
import json, re, subprocess, sys, pathlib
out = pathlib.Path(sys.argv[1])
files = []
for line in (out / "changes.txt").read_text().splitlines():
    m = re.match(r"\s*(\S.*?)\s*\|\s*(\d+)\s*([+-]*)$", line)
    if m:
        files.append({"file": m.group(1), "changed": int(m.group(2)),
                      "adds": m.group(3).count("+"), "dels": m.group(3).count("-"),
                      "docs": bool(re.search(r"\.(md|rst|txt)$|^docs/", m.group(1)))})
(out / "files.json").write_text(json.dumps(files, indent=2))
print(f"{len(files)} files, {sum(not f['docs'] for f in files)} non-doc")
PY

cat > "$OUT/context.md" <<EOF
# Review workspace (container)

base worktree : $WORK/base   ($MERGE_BASE)
pr   worktree : $WORK/pr     ($HEAD_SHA)
outputs       : $OUT

Files: $OUT/full.diff, changes.txt, files.json, commits.txt

Next:
  1. read full.diff; run things in $WORK/pr and $WORK/base
  2. trace-review.py --cmd '<cmd>' --watch PATH --out $OUT/trace.json
  3. write $OUT/review.json  (protocol: SKILL.md)
  4. render-review.py $OUT/review.json -o $OUT/review.html
EOF

echo "workspace ready — see $OUT/context.md" >&2
cat "$OUT/changes.txt"
