#!/bin/bash
set -e

REVIEW_DIR=$1

if [ -z "$REVIEW_DIR" ]; then
    echo "Usage: cleanup-review.sh <review-dir>"
    exit 1
fi

if [ ! -d "$REVIEW_DIR" ]; then
    echo "Error: Directory not found: $REVIEW_DIR"
    exit 1
fi

# Remove worktrees
git worktree remove --force "$REVIEW_DIR/base" 2>&1 || true
git worktree remove --force "$REVIEW_DIR/pr" 2>&1 || true

# Clean up directory
rm -rf "$REVIEW_DIR"

echo "Cleaned up: $REVIEW_DIR"
