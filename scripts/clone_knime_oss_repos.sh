#!/usr/bin/env bash
set -euo pipefail

ORG="knime-oss"

usage() {
  printf 'Usage: %s TARGET_DIRECTORY\n' "$(basename "$0")" >&2
  printf 'Clone all public %s repositories into TARGET_DIRECTORY.\n' "$ORG" >&2
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Error: required command not found: %s\n' "$1" >&2
    exit 1
  fi
}

if [ "$#" -ne 1 ]; then
  usage
  exit 1
fi

target_dir="$1"

require_command curl
require_command jq
require_command git

mkdir -p "$target_dir"

page=1
per_page=100
repo_count=0

while :; do
  response="$(curl -fsSL "https://api.github.com/orgs/${ORG}/repos?per_page=${per_page}&page=${page}")"
  count="$(printf '%s' "$response" | jq 'length')"

  if [ "$count" -eq 0 ]; then
    break
  fi

  while IFS=$'\t' read -r name clone_url; do
    repo_count=$((repo_count + 1))
    repo_dir="${target_dir%/}/$name"

    if [ -d "$repo_dir/.git" ]; then
      printf '[skip] %s already exists\n' "$name"
      continue
    fi

    printf '[clone] %s\n' "$name"
    git clone --filter=blob:none "$clone_url" "$repo_dir"
  done < <(printf '%s' "$response" | jq -r '.[] | [.name, .clone_url] | @tsv')

  page=$((page + 1))
done

printf 'Processed %d %s repositories into %s\n' "$repo_count" "$ORG" "$target_dir"
