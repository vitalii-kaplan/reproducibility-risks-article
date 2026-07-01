#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s SOURCE_ROOT YYYY-MM-DD [MANIFEST_CSV]\n' "$(basename "$0")" >&2
  printf 'Checkout each Git repository below SOURCE_ROOT to the latest commit at or before the date.\n' >&2
  printf 'Default MANIFEST_CSV: data/original/knime_snapshots/YYYY-MM-DD/checkout_YYYY-MM-DD.csv\n' >&2
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Error: required command not found: %s\n' "$1" >&2
    exit 1
  fi
}

csv_escape() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/"/""/g')"
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  usage
  exit 1
fi

source_root="${1%/}"
target_date="$2"
manifest="${3:-data/original/knime_snapshots/${target_date}/checkout_${target_date}.csv}"
before="${target_date} 23:59:59"

require_command git
require_command sed

export GIT_LFS_SKIP_SMUDGE=1
export GIT_TERMINAL_PROMPT=0

if [ ! -d "$source_root" ]; then
  printf 'Error: source root is not a directory: %s\n' "$source_root" >&2
  exit 2
fi

if [ -n "$manifest" ]; then
  mkdir -p "$(dirname "$manifest")"
  printf 'repo,status,target_date,commit,commit_date,previous_head\n' > "$manifest"
fi

processed=0
checked_out=0
skipped=0

for git_dir in "$source_root"/*/.git; do
  [ -d "$git_dir" ] || continue
  repo_dir="$(dirname "$git_dir")"
  repo="$(basename "$repo_dir")"
  processed=$((processed + 1))

  previous_head="$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || true)"
  commit="$(git -C "$repo_dir" rev-list -n 1 --before="$before" --all 2>/dev/null || true)"

  if [ -z "$commit" ]; then
    printf '[skip] %s: no commit at or before %s\n' "$repo" "$target_date"
    skipped=$((skipped + 1))
    if [ -n "$manifest" ]; then
      {
        csv_escape "$repo"; printf ','
        csv_escape "no_commit"; printf ','
        csv_escape "$target_date"; printf ','
        csv_escape ""; printf ','
        csv_escape ""; printf ','
        csv_escape "$previous_head"; printf '\n'
      } >> "$manifest"
    fi
    continue
  fi

  commit_date="$(git -C "$repo_dir" show -s --format=%cI "$commit")"
  git -C "$repo_dir" checkout --detach --quiet "$commit"
  printf '[checkout] %s: %s %s\n' "$repo" "${commit:0:12}" "$commit_date"
  checked_out=$((checked_out + 1))

  if [ -n "$manifest" ]; then
    {
      csv_escape "$repo"; printf ','
      csv_escape "checked_out"; printf ','
      csv_escape "$target_date"; printf ','
      csv_escape "$commit"; printf ','
      csv_escape "$commit_date"; printf ','
      csv_escape "$previous_head"; printf '\n'
    } >> "$manifest"
  fi
done

printf 'Processed %d repositories; checked out %d; skipped %d.\n' "$processed" "$checked_out" "$skipped"
