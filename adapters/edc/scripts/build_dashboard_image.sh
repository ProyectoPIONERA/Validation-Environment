#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCES_DIR="$ADAPTER_DIR/sources"
DASHBOARD_REPO_DIR="$SOURCES_DIR/dashboard"
BUILD_DIR="$ADAPTER_DIR/build"
DOCKERFILE="$BUILD_DIR/docker/dashboard.Dockerfile"
NGINX_CONF="$BUILD_DIR/docker/dashboard-nginx.conf"
CONTEXT_DIR="$BUILD_DIR/dashboard-image-context"
IMAGE_NAME="${PIONERA_EDC_DASHBOARD_IMAGE_NAME:-validation-environment/edc-dashboard}"
IMAGE_TAG="${PIONERA_EDC_DASHBOARD_IMAGE_TAG:-latest}"
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

if [[ ! -d "$DASHBOARD_REPO_DIR/.git" ]]; then
  "$SCRIPT_DIR/sync_dashboard_sources.sh" --apply
fi

DASHBOARD_DIR="$DASHBOARD_REPO_DIR"
if [[ -d "$DASHBOARD_REPO_DIR/DataDashboard" ]]; then
  DASHBOARD_DIR="$DASHBOARD_REPO_DIR/DataDashboard"
fi

if [[ "$APPLY" != true ]]; then
  echo "Dashboard image build preview"
  echo "  source: $DASHBOARD_DIR"
  echo "  dockerfile: $DOCKERFILE"
  echo "  nginx_conf: $NGINX_CONF"
  echo "  context: $CONTEXT_DIR"
  echo "  image: $IMAGE_NAME:$IMAGE_TAG"
  echo "  minikube_profile: $MINIKUBE_PROFILE"
  exit 0
fi

if [[ ! -f "$DASHBOARD_DIR/package.json" ]]; then
  echo "Dashboard application package.json not found in $DASHBOARD_DIR" >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required to prepare the dashboard image context" >&2
  exit 1
fi

rm -rf "$CONTEXT_DIR"
mkdir -p "$CONTEXT_DIR/app"
rsync -a \
  --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude 'dist' \
  --exclude '.angular' \
  "$DASHBOARD_DIR"/ "$CONTEXT_DIR/app/"
cp "$NGINX_CONF" "$CONTEXT_DIR/dashboard-nginx.conf"

docker build -f "$DOCKERFILE" -t "$IMAGE_NAME:$IMAGE_TAG" "$CONTEXT_DIR"

if command -v minikube >/dev/null 2>&1; then
  minikube -p "$MINIKUBE_PROFILE" image load "$IMAGE_NAME:$IMAGE_TAG" >/dev/null
fi

echo "Dashboard image ready: $IMAGE_NAME:$IMAGE_TAG"
