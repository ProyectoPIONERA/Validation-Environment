#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$ADAPTER_DIR/../.." && pwd)"

BUILD_SCRIPT="$SCRIPT_DIR/build_images.sh"
MANIFESTS_DIR="${MANIFESTS_DIR:-/tmp/inesdata-manifests}"
OVERRIDES_DIR="$ADAPTER_DIR/build/local-overrides"

PLATFORM_DIR="${PLATFORM_DIR:-$ROOT_DIR/inesdata-testing}"
K8S_NAMESPACE="${K8S_NAMESPACE:-demo}"
MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-minikube}"
LOCAL_REGISTRY_HOST="${LOCAL_REGISTRY_HOST:-local}"
LOCAL_NAMESPACE="${LOCAL_NAMESPACE:-inesdata}"

DRY_RUN=1
RUN_DEPLOY=1
RUN_BUILD=1
MANIFEST_FILE=""

usage() {
  cat <<'EOF'
Usage: local_build_load_deploy.sh [--apply] [--manifest <path>] [--platform-dir <path>] [--namespace <name>]
                                 [--minikube-profile <name>] [--skip-build] [--skip-deploy]

Options:
  --apply                     Execute build/load/deploy actions (default is dry-run).
  --manifest <path>           Use an existing build manifest TSV.
  --platform-dir <path>       Path to local platform repo (default: ./inesdata-testing).
  --namespace <name>          Kubernetes namespace and dataspace name (default: demo).
  --minikube-profile <name>   Minikube profile name (default: minikube).
  --skip-build                Skip image build, use provided/latest manifest.
  --skip-deploy               Build and load images, but do not run helm upgrade.
  -h, --help                  Show help.

Environment variables:
  PLATFORM_DIR
  K8S_NAMESPACE
  MINIKUBE_PROFILE
  LOCAL_REGISTRY_HOST
  LOCAL_NAMESPACE
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      DRY_RUN=0
      shift
      ;;
    --manifest)
      MANIFEST_FILE="${2:-}"
      shift 2
      ;;
    --platform-dir)
      PLATFORM_DIR="${2:-}"
      shift 2
      ;;
    --namespace)
      K8S_NAMESPACE="${2:-}"
      shift 2
      ;;
    --minikube-profile)
      MINIKUBE_PROFILE="${2:-}"
      shift 2
      ;;
    --skip-build)
      RUN_BUILD=0
      shift
      ;;
    --skip-deploy)
      RUN_DEPLOY=0
      shift
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

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    eval "$@"
  fi
}

resolve_manifest() {
  if [[ -n "$MANIFEST_FILE" ]]; then
    return
  fi
  MANIFEST_FILE="$(ls -1t "$MANIFESTS_DIR"/images-*.tsv 2>/dev/null | head -n 1 || true)"
}

require_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "Required file not found: $p" >&2
    exit 1
  fi
}

echo "Mode: $([[ "$DRY_RUN" -eq 1 ]] && echo "dry-run" || echo "apply")"
echo "Platform dir: $PLATFORM_DIR"
echo "K8s namespace: $K8S_NAMESPACE"
echo "Minikube profile: $MINIKUBE_PROFILE"
echo "Local image prefix: $LOCAL_REGISTRY_HOST/$LOCAL_NAMESPACE"

if [[ "$RUN_BUILD" -eq 1 ]]; then
  echo
  echo "== Build local images =="
  if [[ "$DRY_RUN" -eq 1 ]]; then
    bash "$BUILD_SCRIPT" --registry-host "$LOCAL_REGISTRY_HOST" --namespace "$LOCAL_NAMESPACE"
  else
    bash "$BUILD_SCRIPT" --apply --registry-host "$LOCAL_REGISTRY_HOST" --namespace "$LOCAL_NAMESPACE"
  fi
fi

resolve_manifest
if [[ -z "$MANIFEST_FILE" ]]; then
  echo "No manifest found. Run build_images.sh first or pass --manifest." >&2
  exit 1
fi
require_file "$MANIFEST_FILE"

echo
echo "Manifest: $MANIFEST_FILE"

declare -A IMAGE_BY_COMPONENT=()
while IFS=$'\t' read -r component repo_dir image tag full_image build_cmd; do
  [[ "$component" == "component" ]] && continue
  IMAGE_BY_COMPONENT["$component"]="$full_image"
done < "$MANIFEST_FILE"

for key in connector connector-interface registration-service public-portal-backend public-portal-frontend; do
  if [[ -z "${IMAGE_BY_COMPONENT[$key]:-}" ]]; then
    echo "Missing component in manifest: $key" >&2
    exit 1
  fi
done

echo
echo "== Load images into minikube =="
for key in connector connector-interface registration-service public-portal-backend public-portal-frontend; do
  full_image="${IMAGE_BY_COMPONENT[$key]}"
  echo "$key -> $full_image"
  run_cmd "minikube -p \"$MINIKUBE_PROFILE\" image load \"$full_image\""
done

if [[ "$RUN_DEPLOY" -eq 0 ]]; then
  echo
  echo "Deploy step skipped (--skip-deploy)."
  exit 0
fi

if [[ ! -d "$PLATFORM_DIR" ]]; then
  echo "Platform directory not found: $PLATFORM_DIR" >&2
  exit 1
fi

mkdir -p "$OVERRIDES_DIR"

CONNECTOR_OVERRIDE="$OVERRIDES_DIR/connector-local-overrides.yaml"
RS_OVERRIDE="$OVERRIDES_DIR/registration-local-overrides.yaml"
PP_OVERRIDE="$OVERRIDES_DIR/public-portal-local-overrides.yaml"

cat > "$CONNECTOR_OVERRIDE" <<EOF
connector:
  image:
    name: ${IMAGE_BY_COMPONENT[connector]%:*}
    tag: ${IMAGE_BY_COMPONENT[connector]##*:}
connectorInterface:
  image:
    name: ${IMAGE_BY_COMPONENT[connector-interface]%:*}
    tag: ${IMAGE_BY_COMPONENT[connector-interface]##*:}
EOF

cat > "$RS_OVERRIDE" <<EOF
registration:
  image:
    name: ${IMAGE_BY_COMPONENT[registration-service]%:*}
    tag: ${IMAGE_BY_COMPONENT[registration-service]##*:}
EOF

cat > "$PP_OVERRIDE" <<EOF
backend:
  image:
    name: ${IMAGE_BY_COMPONENT[public-portal-backend]%:*}
    tag: ${IMAGE_BY_COMPONENT[public-portal-backend]##*:}
frontend:
  image:
    name: ${IMAGE_BY_COMPONENT[public-portal-frontend]%:*}
    tag: ${IMAGE_BY_COMPONENT[public-portal-frontend]##*:}
EOF

echo
echo "== Helm upgrade (local images) =="

RS_BASE_VALUES="$PLATFORM_DIR/dataspace/registration-service/values-$K8S_NAMESPACE.yaml"
PP_BASE_VALUES="$PLATFORM_DIR/dataspace/public-portal/values-$K8S_NAMESPACE.yaml"
CONNECTOR_DIR="$PLATFORM_DIR/connector"

require_file "$RS_BASE_VALUES"
require_file "$PP_BASE_VALUES"

run_cmd "helm upgrade --install \"$K8S_NAMESPACE-dataspace-rs\" \"$PLATFORM_DIR/dataspace/registration-service\" -n \"$K8S_NAMESPACE\" --create-namespace -f \"$RS_BASE_VALUES\" -f \"$RS_OVERRIDE\""
run_cmd "helm upgrade --install \"$K8S_NAMESPACE-dataspace-pp\" \"$PLATFORM_DIR/dataspace/public-portal\" -n \"$K8S_NAMESPACE\" --create-namespace -f \"$PP_BASE_VALUES\" -f \"$PP_OVERRIDE\""

connector_values=()
while IFS= read -r file; do
  connector_values+=("$file")
done < <(find "$CONNECTOR_DIR" -maxdepth 1 -type f -name "values-*.yaml" ! -name "values.yaml" ! -name "values.yaml.tpl" | sort)

if [[ "${#connector_values[@]}" -eq 0 ]]; then
  echo "No connector values files found in $CONNECTOR_DIR"
else
  for values_file in "${connector_values[@]}"; do
    connector_name="$(basename "$values_file")"
    connector_name="${connector_name#values-}"
    connector_name="${connector_name%.yaml}"
    release_name="${connector_name}-${K8S_NAMESPACE}"
    run_cmd "helm upgrade --install \"$release_name\" \"$CONNECTOR_DIR\" -n \"$K8S_NAMESPACE\" --create-namespace -f \"$values_file\" -f \"$CONNECTOR_OVERRIDE\""
  done
fi

echo
echo "Local build/load/deploy workflow complete."
