#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TARGET_DIR="$ADAPTER_DIR/sources/connector"
DEFAULT_GIT_URL="https://github.com/luciamartinnunez/Connector"

APPLY=0
SOURCE_REPO=""
GIT_URL="$DEFAULT_GIT_URL"

usage() {
  cat <<'EOF'
Usage: sync_sources.sh [--apply] [--source <path>] [--git-url <url>]

Synchronize the local EDC connector source repository used by adapters/edc.

Options:
  --apply           Execute the synchronization. Default is dry-run.
  --source <path>   Use a local source directory instead of GitHub.
  --git-url <url>   Override the Git upstream URL used when cloning/updating.
  -h, --help        Show this help message.
EOF
}

run_cmd() {
  local cmd="$1"
  echo "+ $cmd"
  if [[ "$APPLY" -eq 1 ]]; then
    bash -lc "$cmd"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      shift
      ;;
    --source)
      SOURCE_REPO="${2:-}"
      shift 2
      ;;
    --git-url)
      GIT_URL="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$(dirname "$TARGET_DIR")"

echo "EDC adapter dir: $ADAPTER_DIR"
echo "Target dir:      $TARGET_DIR"
if [[ -n "$SOURCE_REPO" ]]; then
  echo "Source repo:     $SOURCE_REPO"
else
  echo "Git upstream:    $GIT_URL"
fi

sync_from_local_source() {
  if [[ -z "$SOURCE_REPO" || ! -d "$SOURCE_REPO" ]]; then
    echo "Source repository not found: $SOURCE_REPO" >&2
    exit 1
  fi

  if command -v rsync >/dev/null 2>&1; then
    run_cmd "mkdir -p \"$TARGET_DIR\""
    run_cmd "rsync -a --delete --exclude .git --exclude .gradle --exclude .gradle-user-home \"$SOURCE_REPO\"/ \"$TARGET_DIR\"/"
  else
    run_cmd "rm -rf \"$TARGET_DIR\""
    run_cmd "mkdir -p \"$TARGET_DIR\""
    run_cmd "cp -a \"$SOURCE_REPO\"/. \"$TARGET_DIR\"/"
    run_cmd "rm -rf \"$TARGET_DIR/.git\" \"$TARGET_DIR/.gradle\" \"$TARGET_DIR/.gradle-user-home\""
  fi

  echo "Source synchronization complete."
}

sync_from_git_upstream() {
  if [[ -d "$TARGET_DIR/.git" ]]; then
    run_cmd "git -C \"$TARGET_DIR\" remote set-url origin \"$GIT_URL\""
    run_cmd "git -C \"$TARGET_DIR\" fetch --all --tags"
    run_cmd "git -C \"$TARGET_DIR\" pull --ff-only"
  else
    run_cmd "rm -rf \"$TARGET_DIR\""
    run_cmd "git clone \"$GIT_URL\" \"$TARGET_DIR\""
  fi

  echo "Git synchronization complete."
}

if [[ -n "$SOURCE_REPO" ]]; then
  sync_from_local_source
else
  sync_from_git_upstream
fi

if [[ -f "$TARGET_DIR/gradlew" ]]; then
  run_cmd "chmod +x \"$TARGET_DIR/gradlew\""
fi
