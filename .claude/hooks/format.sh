#!/usr/bin/env bash
# PostToolUse(Edit|Write): format the file Claude just changed.
# Reads the hook payload on stdin; never blocks the agent.
set -u
root="$(cd "$(dirname "$0")/../.." && pwd)"
file="$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')"
[ -n "$file" ] && [ -f "$file" ] || exit 0

case "$file" in
  "$root"/*.py)
    cd "$root" && uv run --quiet ruff format "$file" && uv run --quiet ruff check --fix --quiet "$file"
    ;;
  "$root"/apps/web/*.ts|"$root"/apps/web/*.vue)
    case "$file" in *api.gen.ts) exit 0 ;; esac
    cd "$root/apps/web" && bunx eslint --fix "$file"
    ;;
esac
exit 0
