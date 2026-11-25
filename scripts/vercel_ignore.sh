#!/usr/bin/env bash
# Vercel Ignored Build Step. Usage: vercel_ignore.sh <web|api>
# Exit 0: Vercel skips the build. Exit 1: Vercel builds. If in doubt, build.
set -uo pipefail

build() {
  echo "Build: $1"
  exit 1
}

target="deploy-${1:-}"
cd "$(dirname "${BASH_SOURCE[0]}")/.." || build "the repository root is not available"

# Vercel clones 10 commits of one branch, so the base can be missing.
remote="https://github.com/${VERCEL_GIT_REPO_OWNER:-}/${VERCEL_GIT_REPO_SLUG:-}.git"
remote="${SHIELD_GIT_REMOTE:-$remote}"
export GIT_TERMINAL_PROMPT=0

base="${VERCEL_GIT_PREVIOUS_SHA:-}"
if [ -n "$base" ]; then
  # The last successful deployment of this branch, so changes in skipped commits are not lost.
  git cat-file -e "$base^{commit}" 2>/dev/null \
    || git fetch --quiet --no-tags --depth=1 "$remote" "$base" \
    || build "the last deployed commit is not available"
elif [ "${VERCEL_ENV:-}" = "preview" ]; then
  # The first deployment of a branch: compare with the point where it left main.
  head="$(git rev-parse HEAD)" || build "HEAD is not available"
  git fetch --quiet --no-tags --depth=200 "$remote" main || build "main is not available"
  main="$(git rev-parse FETCH_HEAD)" || build "main is not available"
  git fetch --quiet --no-tags --depth=200 "$remote" "$head" || build "the history is not available"
  base="$(git merge-base "$main" "$head")" || build "there is no common commit with main"
else
  build "there is no earlier deployment"
fi

bash scripts/affected.sh "$target" "$base"
case $? in
  0) build "$target changed since $base" ;;
  1) echo "Skip: no change to $target since $base" ;;
  *) build "the comparison failed" ;;
esac
