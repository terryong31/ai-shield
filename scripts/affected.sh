#!/usr/bin/env bash
# The single list of which paths affect which part of the monorepo. CI and Vercel use it.
# Usage: affected.sh <target> <base> [head]
# Exit 0: affected. Exit 1: not affected. Exit 2: error (callers must not skip the work).
set -uo pipefail

[ "$#" -ge 2 ] || exit 2
target="$1" base="$2" head="${3:-HEAD}"
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

# Shared CI tooling: a change here runs every CI job.
ci=(.github mise.toml scripts/affected.sh)

case "$target" in
  # Vercel: only the files that go into the deployment.
  deploy-web)
    paths=(
      apps/web package.json bun.lock
      ':(exclude)apps/web/test' ':(exclude)apps/web/e2e' ':(exclude)apps/web/Dockerfile'
      ':(exclude,glob)apps/web/*.md' ':(exclude)apps/web/.env.example'
      ':(exclude)apps/web/vitest.config.ts' ':(exclude)apps/web/playwright.config.ts'
    ) ;;
  deploy-api)
    paths=(
      apps/api packages/engine pyproject.toml uv.lock
      ':(exclude)apps/api/tests' ':(exclude)apps/api/Dockerfile'
      ':(exclude,glob)apps/api/*.md' ':(exclude)apps/api/.env.example'
      ':(exclude)packages/engine/tests' ':(exclude)packages/engine/data'
      ':(exclude,glob)packages/engine/*.md'
    ) ;;
  # GitHub Actions: also the tests and the files that the tests read.
  ci-web)
    paths=("${ci[@]}" apps/web package.json bun.lock contracts ':(exclude,glob)apps/web/*.md') ;;
  ci-python)
    paths=(
      "${ci[@]}" apps/api packages/engine scripts conftest.py pyproject.toml uv.lock
      contracts supabase ':(exclude,glob)apps/api/*.md' ':(exclude,glob)packages/engine/*.md'
    ) ;;
  ci-database)
    paths=("${ci[@]}" supabase) ;;
  *)
    echo "Unknown target: $target" >&2
    exit 2 ;;
esac

git diff --quiet --no-ext-diff --no-renames "$base" "$head" -- "${paths[@]}"
case $? in
  0) exit 1 ;;
  1) exit 0 ;;
  *) exit 2 ;;
esac
