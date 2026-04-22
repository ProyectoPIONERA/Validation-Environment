#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCES_DIR="$ADAPTER_DIR/sources"
MANIFESTS_DIR="${MANIFESTS_DIR:-/tmp/inesdata-manifests}"
DRY_RUN=1
TARGET="TODO"
MANIFEST_FILE_OVERRIDE=""
APPEND_MANIFEST=0
REGISTRY_HOST="${REGISTRY_HOST:-ghcr.io}"
REGISTRY_NAMESPACE="${REGISTRY_NAMESPACE:-inesdata}"

usage() {
  cat <<'EOF'
Usage: build_images.sh [--apply] [--target <TODO|CHANGED|component>] [--manifest <path>] [--append-manifest]
                       [--registry-host <host>] [--namespace <name>]

Options:
  --apply               Execute docker build (default is dry-run).
  --target <value>      Build target. Use TODO for all components, CHANGED for modified source components, or one component key.
  --component <name>    Deprecated alias for --target <name>.
  --manifest <path>     Write output manifest to a specific path.
  --append-manifest     Append rows to an existing manifest file (header created if missing).
  --registry-host       Registry hostname. Default: ghcr.io
  --namespace           Registry namespace/org/user. Default: inesdata

Environment variables:
  REGISTRY_HOST
  REGISTRY_NAMESPACE
  MANIFESTS_DIR (default: /tmp/inesdata-manifests)

Component keys:
  connector
  connector-interface
  registration-service
  public-portal-backend
  public-portal-frontend
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      DRY_RUN=0
      shift
      ;;
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --component)
      TARGET="${2:-}"
      shift 2
      ;;
    --manifest)
      MANIFEST_FILE_OVERRIDE="${2:-}"
      shift 2
      ;;
    --append-manifest)
      APPEND_MANIFEST=1
      shift
      ;;
    --registry-host)
      REGISTRY_HOST="${2:-}"
      shift 2
      ;;
    --namespace)
      REGISTRY_NAMESPACE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

ALL_COMPONENTS=(
  connector
  connector-interface
  registration-service
  public-portal-backend
  public-portal-frontend
)

if [[ -z "$TARGET" ]]; then
  echo "Missing --target value" >&2
  usage
  exit 1
fi

if [[ "$TARGET" != "TODO" && "$TARGET" != "CHANGED" ]]; then
  is_valid_target=0
  for c in "${ALL_COMPONENTS[@]}"; do
    if [[ "$TARGET" == "$c" ]]; then
      is_valid_target=1
      break
    fi
  done
  if [[ "$is_valid_target" -ne 1 ]]; then
    echo "Invalid --target value: $TARGET" >&2
    usage
    exit 1
  fi
fi

mkdir -p "$MANIFESTS_DIR"

if [[ -n "$MANIFEST_FILE_OVERRIDE" ]]; then
  MANIFEST_FILE="$MANIFEST_FILE_OVERRIDE"
else
  TS_UTC="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
  MANIFEST_FILE="$MANIFESTS_DIR/images-$TS_UTC.tsv"
fi

if [[ "$APPEND_MANIFEST" -eq 1 ]]; then
  mkdir -p "$(dirname "$MANIFEST_FILE")"
fi

if [[ "$APPEND_MANIFEST" -eq 0 || ! -f "$MANIFEST_FILE" ]]; then
  echo -e "component\trepo_dir\timage\ttag\tfull_image\tbuild_cmd" > "$MANIFEST_FILE"
fi

declare -A SRC_DIR=(
  ["connector"]="$SOURCES_DIR/inesdata-connector"
  ["connector-interface"]="$SOURCES_DIR/inesdata-connector-interface"
  ["registration-service"]="$SOURCES_DIR/inesdata-registration-service"
  ["public-portal-backend"]="$SOURCES_DIR/inesdata-public-portal-backend"
  ["public-portal-frontend"]="$SOURCES_DIR/inesdata-public-portal-frontend"
)

declare -A IMAGE_NAME=(
  ["connector"]="inesdata-connector"
  ["connector-interface"]="inesdata-connector-interface"
  ["registration-service"]="inesdata-registration-service"
  ["public-portal-backend"]="inesdata-public-portal-backend"
  ["public-portal-frontend"]="inesdata-public-portal-frontend"
)

declare -A DOCKERFILE=(
  ["connector"]="docker/Dockerfile"
  ["connector-interface"]="docker/Dockerfile"
  ["registration-service"]="docker/Dockerfile"
  ["public-portal-backend"]="Dockerfile"
  ["public-portal-frontend"]="docker/Dockerfile"
)

declare -A EXTRA_ARGS=(
  ["connector"]="--build-arg CONNECTOR_JAR=./launchers/connector/build/libs/connector-app.jar"
  ["connector-interface"]=""
  ["registration-service"]=""
  ["public-portal-backend"]=""
  ["public-portal-frontend"]=""
)

declare -A REQUIRED_ARTIFACT=(
  ["connector"]="launchers/connector/build/libs/connector-app.jar"
  ["registration-service"]="build/libs/*.jar"
)

declare -A PREBUILD_CMD=(
  ["connector"]="./gradlew launchers:connector:build -x test"
  ["registration-service"]="./gradlew bootJar -x test"
)

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    eval "$@"
  fi
}

component_has_changes() {
  local repo_dir="$1"

  if [[ ! -d "$repo_dir" ]]; then
    return 1
  fi

  if ! git -C "$repo_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # If git metadata is unavailable, treat as changed to avoid skipping local sources.
    return 0
  fi

  if [[ -n "$(git -C "$repo_dir" status --porcelain -- .)" ]]; then
    return 0
  fi

  return 1
}

artifact_exists() {
  local pattern="$1"
  compgen -G "$pattern" > /dev/null
}

prepare_component_artifacts() {
  local component="$1"
  local repo_dir="$2"
  local artifact_rel="${REQUIRED_ARTIFACT[$component]:-}"
  local prebuild_cmd="${PREBUILD_CMD[$component]:-}"
  local artifact_path="$repo_dir/$artifact_rel"
  local should_prebuild=0

  if [[ -z "$artifact_rel" ]]; then
    return
  fi

  if ! artifact_exists "$artifact_path"; then
    should_prebuild=1
  elif component_has_changes "$repo_dir"; then
    should_prebuild=1
  fi

  if [[ "$should_prebuild" -ne 1 ]]; then
    return
  fi

  if [[ -z "$prebuild_cmd" ]]; then
    echo "Missing required artifact for $component: $artifact_path" >&2
    exit 1
  fi

  echo "Preparing artifacts for $component ($artifact_rel)"
  run_cmd "cd $repo_dir && $prebuild_cmd"

  if [[ "$DRY_RUN" -eq 0 ]] && ! artifact_exists "$artifact_path"; then
    echo "Artifact still missing after prebuild for $component: $artifact_path" >&2
    exit 1
  fi
}

echo "Sources directory: $SOURCES_DIR"
echo "Manifest: $MANIFEST_FILE"
echo "Mode: $([[ "$DRY_RUN" -eq 1 ]] && echo "dry-run" || echo "apply")"
echo "Registry host: $REGISTRY_HOST"
echo "Registry namespace: $REGISTRY_NAMESPACE"
echo "Target: $TARGET"

if [[ "$TARGET" == "TODO" ]]; then
  selected_components=("${ALL_COMPONENTS[@]}")
elif [[ "$TARGET" == "CHANGED" ]]; then
  selected_components=()
  for component in "${ALL_COMPONENTS[@]}"; do
    if component_has_changes "${SRC_DIR[$component]}"; then
      selected_components+=("$component")
    fi
  done

  if [[ "${#selected_components[@]}" -eq 0 ]]; then
    echo "No changed components detected under $SOURCES_DIR."
    echo "Build manifest generated: $MANIFEST_FILE"
    exit 0
  fi
else
  selected_components=("$TARGET")
fi

for component in "${selected_components[@]}"; do

  repo_dir="${SRC_DIR[$component]}"
  image="$REGISTRY_HOST/$REGISTRY_NAMESPACE/${IMAGE_NAME[$component]}"
  dockerfile="${DOCKERFILE[$component]}"
  extra_args="${EXTRA_ARGS[$component]}"

  if [[ ! -d "$repo_dir" ]]; then
    echo "Skipping $component: missing source directory at $repo_dir"
    continue
  fi

  prepare_component_artifacts "$component" "$repo_dir"

  date_tag="$(date -u +%Y%m%d)"
  if shortsha="$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null)"; then
    if [[ -z "$(git -C "$repo_dir" status --porcelain -- .)" ]]; then
      tag="$date_tag-$shortsha"
    else
      dirty_stamp="$(date -u +%H%M%S)"
      tag="$date_tag-$shortsha-dirty-$dirty_stamp"
    fi
  else
    # Sources can be provided as plain directories without .git metadata.
    tag="$(date -u +%Y%m%d-%H%M%S)-local"
  fi
  full_image="$image:$tag"

  build_cmd="docker build -f $dockerfile -t $full_image $extra_args ."
  echo -e "$component\t$repo_dir\t$image\t$tag\t$full_image\t$build_cmd" >> "$MANIFEST_FILE"

  echo
  echo "== $component =="
  run_cmd "cd $repo_dir && $build_cmd"
done

echo
echo "Build manifest generated: $MANIFEST_FILE"
