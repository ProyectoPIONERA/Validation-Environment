#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$ADAPTER_DIR/../.." && pwd)"

BUILD_SCRIPT="$SCRIPT_DIR/build_images.sh"
MANIFESTS_DIR="${MANIFESTS_DIR:-/tmp/inesdata-manifests}"
OVERRIDES_DIR="$ADAPTER_DIR/build/local-overrides"

PLATFORM_DIR="${PLATFORM_DIR:-$ROOT_DIR/inesdata-deployment}"
K8S_NAMESPACE="${K8S_NAMESPACE:-demo}"
MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-minikube}"
LOCAL_REGISTRY_HOST="${LOCAL_REGISTRY_HOST:-local}"
LOCAL_NAMESPACE="${LOCAL_NAMESPACE:-inesdata}"

DRY_RUN=1
RUN_DEPLOY=1
RUN_BUILD=1
MANIFEST_FILE=""
ONLY_COMPONENT=""
SKIP_PREBUILD=0
CONNECTOR_HEALTH_TIMEOUT_SECONDS="${CONNECTOR_HEALTH_TIMEOUT_SECONDS:-300}"

usage() {
  cat <<'EOF'
Usage: local_build_load_deploy.sh [--apply] [--manifest <path>] [--platform-dir <path>] [--namespace <name>]
                                 [--minikube-profile <name>] [--component <name>] [--skip-prebuild]
                                 [--skip-build] [--skip-deploy]

Options:
  --apply                     Execute build/load/deploy actions (default is dry-run).
  --manifest <path>           Use an existing build manifest TSV.
  --platform-dir <path>       Path to local platform repo (default: ./inesdata-deployment).
  --namespace <name>          Kubernetes namespace and dataspace name (default: demo).
  --minikube-profile <name>   Minikube profile name (default: minikube).
  --component <name>          Restrict build/load to one component key.
  --skip-prebuild             Skip component pre-build commands in build_images.sh.
  --skip-build                Skip image build, use provided/latest manifest.
  --skip-deploy               Build and load images, but do not run helm upgrade.
  -h, --help                  Show help.

Environment variables:
  PLATFORM_DIR
  K8S_NAMESPACE
  MINIKUBE_PROFILE
  LOCAL_REGISTRY_HOST
  LOCAL_NAMESPACE

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
    --component)
      ONLY_COMPONENT="${2:-}"
      shift 2
      ;;
    --skip-prebuild)
      SKIP_PREBUILD=1
      shift
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

COMPONENTS=(connector connector-interface registration-service public-portal-backend public-portal-frontend)
ACTIVE_COMPONENTS=("${COMPONENTS[@]}")

if [[ -n "$ONLY_COMPONENT" ]]; then
  valid_component=0
  for key in "${COMPONENTS[@]}"; do
    if [[ "$ONLY_COMPONENT" == "$key" ]]; then
      valid_component=1
      break
    fi
  done

  if [[ "$valid_component" -eq 0 ]]; then
    echo "Invalid component: $ONLY_COMPONENT" >&2
    usage
    exit 1
  fi

  ACTIVE_COMPONENTS=("$ONLY_COMPONENT")
fi

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    eval "$@"
  fi
}

ensure_vault_unsealed() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] Ensure Vault is unsealed"
    return 0
  fi

  local -a py_candidates=(
    "python3"
    "$ROOT_DIR/.venv/bin/python"
    "$PLATFORM_DIR/.venv/bin/python"
    "python"
  )
  local py_exec=""

  for candidate in "${py_candidates[@]}"; do
    if [[ "$candidate" == */* ]]; then
      if [[ -x "$candidate" ]]; then
        py_exec="$candidate"
        break
      fi
    elif command -v "$candidate" >/dev/null 2>&1; then
      py_exec="$candidate"
      break
    fi
  done

  if [[ -z "$py_exec" ]]; then
    echo "No Python interpreter found to parse Vault status JSON." >&2
    echo "Expected one of: python3, $ROOT_DIR/.venv/bin/python, $PLATFORM_DIR/.venv/bin/python, python" >&2
    return 1
  fi

  local vault_ns="common-srvs"
  local vault_pod=""
  vault_pod="$(kubectl -n "$vault_ns" get pods -o name 2>/dev/null | grep 'vault-0' | head -n 1 | sed 's#^pod/##')"
  if [[ -z "$vault_pod" ]]; then
    echo "Vault pod not found in namespace $vault_ns." >&2
    return 1
  fi

  local status_json
  status_json="$(kubectl -n "$vault_ns" exec "$vault_pod" -- sh -lc 'export VAULT_ADDR=http://127.0.0.1:8200; vault status -format=json' 2>/dev/null || true)"
  if [[ -z "$status_json" ]]; then
    echo "Could not read Vault status." >&2
    return 1
  fi

  local sealed initialized
  sealed="$(printf '%s' "$status_json" | "$py_exec" -c 'import json,sys; data=json.load(sys.stdin); print("true" if data.get("sealed") else "false")' 2>/dev/null || echo "unknown")"
  initialized="$(printf '%s' "$status_json" | "$py_exec" -c 'import json,sys; data=json.load(sys.stdin); print("true" if data.get("initialized") else "false")' 2>/dev/null || echo "unknown")"

  if [[ "$initialized" != "true" ]]; then
    echo "Vault is not initialized; run Level 2 setup first." >&2
    return 1
  fi

  if [[ "$sealed" == "false" ]]; then
    echo "Vault already unsealed"
    return 0
  fi

  if [[ "$sealed" != "true" ]]; then
    echo "Could not determine whether Vault is sealed." >&2
    return 1
  fi

  local keys_file="$PLATFORM_DIR/common/init-keys-vault.json"
  if [[ ! -f "$keys_file" ]]; then
    echo "Vault keys file not found: $keys_file" >&2
    return 1
  fi

  local unseal_key
  unseal_key="$("$py_exec" -c 'import json,sys; print(json.load(open(sys.argv[1]))["unseal_keys_hex"][0])' "$keys_file" 2>/dev/null || true)"
  if [[ -z "$unseal_key" ]]; then
    echo "Could not read unseal key from $keys_file" >&2
    return 1
  fi

  echo "Running vault operator unseal..."
  if ! kubectl -n "$vault_ns" exec "$vault_pod" -- vault operator unseal "$unseal_key" >/dev/null; then
    echo "Vault unseal command failed." >&2
    return 1
  fi

  status_json="$(kubectl -n "$vault_ns" exec "$vault_pod" -- sh -lc 'export VAULT_ADDR=http://127.0.0.1:8200; vault status -format=json' 2>/dev/null || true)"
  sealed="$(printf '%s' "$status_json" | "$py_exec" -c 'import json,sys; data=json.load(sys.stdin); print("true" if data.get("sealed") else "false")' 2>/dev/null || echo "unknown")"

  if [[ "$sealed" == "false" ]]; then
    echo "Vault unsealed"
    return 0
  fi

  echo "Vault remains sealed after unseal attempt." >&2
  return 1
}

wait_for_connector_rollout() {
  local deployment_name="$1"
  run_cmd "kubectl -n \"$K8S_NAMESPACE\" rollout status deployment/\"$deployment_name\" --timeout=\"${CONNECTOR_HEALTH_TIMEOUT_SECONDS}s\""
}

check_connector_health() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] Check connector deployment health"
    return 0
  fi

  local -a connector_names=("$@")
  local connector_name

  if [[ "${#connector_names[@]}" -eq 0 ]]; then
    echo "No connector values files detected, skipping connector health gate."
    return 0
  fi

  for connector_name in "${connector_names[@]}"; do
    if ! kubectl -n "$K8S_NAMESPACE" get deployment "$connector_name" >/dev/null 2>&1; then
      echo "Connector deployment not found: $connector_name" >&2
      return 1
    fi

    wait_for_connector_rollout "$connector_name"

    if kubectl -n "$K8S_NAMESPACE" get deployment "$connector_name-inteface" >/dev/null 2>&1; then
      wait_for_connector_rollout "$connector_name-inteface"
    elif kubectl -n "$K8S_NAMESPACE" get deployment "$connector_name-interface" >/dev/null 2>&1; then
      wait_for_connector_rollout "$connector_name-interface"
    else
      echo "Connector interface deployment not found for $connector_name (expected -inteface or -interface suffix)." >&2
      return 1
    fi
  done

  local unhealthy
  unhealthy="$(kubectl -n "$K8S_NAMESPACE" get pods --no-headers 2>/dev/null | awk '$3=="CrashLoopBackOff" || $3=="Error" || $3=="ImagePullBackOff" || $3=="ErrImagePull" || $3=="CreateContainerConfigError" || $3=="RunContainerError" {print}')"
  if [[ -n "$unhealthy" ]]; then
    echo "Detected unhealthy pods after deploy:" >&2
    echo "$unhealthy" >&2
    return 1
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
echo "Component filter: ${ONLY_COMPONENT:-all}"
echo "Skip pre-build: $([[ "$SKIP_PREBUILD" -eq 1 ]] && echo "yes" || echo "no")"

if [[ "$RUN_BUILD" -eq 1 ]]; then
  echo
  echo "== Build local images =="
  build_cmd=(bash "$BUILD_SCRIPT")
  if [[ "$DRY_RUN" -eq 0 ]]; then
    build_cmd+=(--apply)
  fi
  build_cmd+=(--registry-host "$LOCAL_REGISTRY_HOST" --namespace "$LOCAL_NAMESPACE")
  if [[ -n "$ONLY_COMPONENT" ]]; then
    build_cmd+=(--component "$ONLY_COMPONENT")
  fi
  if [[ "$SKIP_PREBUILD" -eq 1 ]]; then
    build_cmd+=(--skip-prebuild)
  fi
  "${build_cmd[@]}"
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

for key in "${ACTIVE_COMPONENTS[@]}"; do
  if [[ -z "${IMAGE_BY_COMPONENT[$key]:-}" ]]; then
    echo "Missing component in manifest: $key" >&2
    exit 1
  fi
done

echo
echo "== Load images into minikube =="
for key in "${ACTIVE_COMPONENTS[@]}"; do
  full_image="${IMAGE_BY_COMPONENT[$key]}"
  echo "$key -> $full_image"
  run_cmd "minikube -p \"$MINIKUBE_PROFILE\" image load \"$full_image\""
done

if [[ -n "$ONLY_COMPONENT" && "$RUN_DEPLOY" -eq 1 ]]; then
  echo "Deploy for a single component is not supported yet." >&2
  echo "Use --skip-deploy with --component, or run without --component for full deploy." >&2
  exit 1
fi

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

echo "Ensuring Vault is unsealed before Helm upgrade..."
if ! ensure_vault_unsealed; then
  echo "Vault pre-check failed. Aborting deploy." >&2
  exit 1
fi

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
  connector_names=()
  for values_file in "${connector_values[@]}"; do
    connector_name="$(basename "$values_file")"
    connector_name="${connector_name#values-}"
    connector_name="${connector_name%.yaml}"
    connector_names+=("$connector_name")
    release_name="${connector_name}-${K8S_NAMESPACE}"
    run_cmd "helm upgrade --install \"$release_name\" \"$CONNECTOR_DIR\" -n \"$K8S_NAMESPACE\" --create-namespace -f \"$values_file\" -f \"$CONNECTOR_OVERRIDE\""
  done

  echo
  echo "Checking connector rollout health..."
  if ! check_connector_health "${connector_names[@]}"; then
    echo "Connector health check failed." >&2
    exit 1
  fi
fi

echo
echo "Ensuring Vault is still unsealed after Helm upgrade..."
if ! ensure_vault_unsealed; then
  echo "Vault post-check failed after Helm upgrade." >&2
  exit 1
fi

echo
echo "Local build/load/deploy workflow complete."
