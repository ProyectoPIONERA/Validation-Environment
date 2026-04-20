#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$ADAPTER_DIR/build"
DOCKERFILE="$BUILD_DIR/docker/dashboard-proxy.Dockerfile"
SERVER_FILE="$BUILD_DIR/dashboard-proxy/server.py"
CONTEXT_DIR="$BUILD_DIR/dashboard-proxy-image-context"
IMAGE_NAME="${PIONERA_EDC_DASHBOARD_PROXY_IMAGE_NAME:-validation-environment/edc-dashboard-proxy}"
IMAGE_TAG="${PIONERA_EDC_DASHBOARD_PROXY_IMAGE_TAG:-latest}"
MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-minikube}"

APPLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=true
      shift
      ;;
    --minikube-profile)
      MINIKUBE_PROFILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$APPLY" != true ]]; then
  echo "Dashboard proxy image build preview"
  echo "  dockerfile: $DOCKERFILE"
  echo "  server: $SERVER_FILE"
  echo "  context: $CONTEXT_DIR"
  echo "  image: $IMAGE_NAME:$IMAGE_TAG"
  echo "  minikube_profile: $MINIKUBE_PROFILE"
  exit 0
fi

if [[ ! -f "$DOCKERFILE" ]]; then
  echo "Dashboard proxy Dockerfile not found in $DOCKERFILE" >&2
  exit 1
fi

if [[ ! -f "$SERVER_FILE" ]]; then
  echo "Dashboard proxy server not found in $SERVER_FILE" >&2
  exit 1
fi

rm -rf "$CONTEXT_DIR"
mkdir -p "$CONTEXT_DIR"
cp "$SERVER_FILE" "$CONTEXT_DIR/server.py"

docker build -f "$DOCKERFILE" -t "$IMAGE_NAME:$IMAGE_TAG" "$CONTEXT_DIR"

if command -v minikube >/dev/null 2>&1; then
  minikube -p "$MINIKUBE_PROFILE" image load "$IMAGE_NAME:$IMAGE_TAG" >/dev/null
fi

echo "Dashboard proxy image ready: $IMAGE_NAME:$IMAGE_TAG"
