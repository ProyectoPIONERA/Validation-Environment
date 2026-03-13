#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCES_DIR="$ADAPTER_DIR/sources"
MANIFESTS_DIR="${MANIFESTS_DIR:-/tmp/inesdata-manifests}"
DRY_RUN=1
ONLY_COMPONENT=""
SKIP_PREBUILD=0
REGISTRY_HOST="${REGISTRY_HOST:-ghcr.io}"
REGISTRY_NAMESPACE="${REGISTRY_NAMESPACE:-inesdata}"

usage() {
  cat <<'EOF'
Usage: build_images.sh [--apply] [--component <name>] [--skip-prebuild] [--registry-host <host>] [--namespace <name>]

Options:
  --apply             Execute docker build (default is dry-run).
  --component <name>  Restrict to one component key.
  --skip-prebuild     Skip pre-build commands configured per component.
  --registry-host     Registry hostname. Default: ghcr.io
  --namespace         Registry namespace/org/user. Default: inesdata

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
    --component)
      ONLY_COMPONENT="${2:-}"
      shift 2
      ;;
    --skip-prebuild)
      SKIP_PREBUILD=1
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

mkdir -p "$MANIFESTS_DIR"

TS_UTC="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
MANIFEST_FILE="$MANIFESTS_DIR/images-$TS_UTC.tsv"

echo -e "component\trepo_dir\timage\ttag\tfull_image\tbuild_cmd" > "$MANIFEST_FILE"

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

declare -A PRE_BUILD_CMD=(
  ["connector"]="./gradlew :launchers:connector:shadowJar"
  ["connector-interface"]=""
  ["registration-service"]="./gradlew bootJar"
  ["public-portal-backend"]=""
  ["public-portal-frontend"]=""
)

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    eval "$@"
  fi
}

echo "Sources directory: $SOURCES_DIR"
echo "Manifest: $MANIFEST_FILE"
echo "Mode: $([[ "$DRY_RUN" -eq 1 ]] && echo "dry-run" || echo "apply")"
echo "Registry host: $REGISTRY_HOST"
echo "Registry namespace: $REGISTRY_NAMESPACE"

for component in connector connector-interface registration-service public-portal-backend public-portal-frontend; do
  if [[ -n "$ONLY_COMPONENT" && "$ONLY_COMPONENT" != "$component" ]]; then
    continue
  fi

  repo_dir="${SRC_DIR[$component]}"
  image="$REGISTRY_HOST/$REGISTRY_NAMESPACE/${IMAGE_NAME[$component]}"
  dockerfile="${DOCKERFILE[$component]}"
  extra_args="${EXTRA_ARGS[$component]}"
  pre_build_cmd="${PRE_BUILD_CMD[$component]}"

  if [[ ! -d "$repo_dir" ]]; then
    echo "Skipping $component: missing source directory at $repo_dir"
    continue
  fi

  date_tag="$(date -u +%Y%m%d)"
  time_tag="$(date -u +%H%M%S)"

  if [[ -d "$repo_dir/.git" ]]; then
    shortsha="$(git -C "$repo_dir" rev-parse --short HEAD)"
    tag="$date_tag-$shortsha"
  else
    tag="$date_tag-$time_tag-local"
  fi

  full_image="$image:$tag"

  echo
  echo "== $component =="
  if [[ -n "$pre_build_cmd" && "$SKIP_PREBUILD" -eq 0 ]]; then
    echo "Running pre-build for $component: $pre_build_cmd"
    run_cmd "cd $repo_dir && $pre_build_cmd"
  fi

  build_cmd="docker build -f $dockerfile -t $full_image $extra_args ."
  echo -e "$component\t$repo_dir\t$image\t$tag\t$full_image\t$build_cmd" >> "$MANIFEST_FILE"

  run_cmd "cd $repo_dir && $build_cmd"
done

echo
echo "Build manifest generated: $MANIFEST_FILE"
