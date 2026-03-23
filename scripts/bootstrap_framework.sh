#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_VENV_DIR="$ROOT_DIR/.venv"
ROOT_PYTHON_BIN="$ROOT_VENV_DIR/bin/python"
ROOT_REQUIREMENTS="$ROOT_DIR/requirements.txt"
ROOT_PACKAGE_JSON="$ROOT_DIR/package.json"
UI_DIR="$ROOT_DIR/validation/ui"
UI_PACKAGE_JSON="$UI_DIR/package.json"
DEPLOYER_CONFIG="$ROOT_DIR/deployer.config"
DEPLOYER_CONFIG_EXAMPLE="$ROOT_DIR/deployer.config.example"

WITH_SYSTEM_DEPS=false
SKIP_PLAYWRIGHT=false
SKIP_ROOT_NODE=false
SKIP_UI_NODE=false
SKIP_DEPLOYER_CONFIG_INIT=false

log() {
  printf '[bootstrap] %s\n' "$*"
}

fail() {
  printf '[bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: bash scripts/bootstrap_framework.sh [options]

Prepare the local framework workspace from a fresh machine checkout.

Options:
  --with-system-deps        Run 'npx playwright install --with-deps'
  --skip-playwright         Skip Playwright browser installation
  --skip-root-node          Skip 'npm install' in the repo root
  --skip-ui-node            Skip 'npm install' in validation/ui
  --skip-deployer-config    Do not create deployer.config from the example file
  -h, --help                Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-system-deps)
      WITH_SYSTEM_DEPS=true
      shift
      ;;
    --skip-playwright)
      SKIP_PLAYWRIGHT=true
      shift
      ;;
    --skip-root-node)
      SKIP_ROOT_NODE=true
      shift
      ;;
    --skip-ui-node)
      SKIP_UI_NODE=true
      shift
      ;;
    --skip-deployer-config)
      SKIP_DEPLOYER_CONFIG_INIT=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

command -v python3 >/dev/null 2>&1 || fail "python3 is required"

if [[ ! -d "$ROOT_VENV_DIR" ]]; then
  log "Creating root virtual environment at $ROOT_VENV_DIR"
  python3 -m venv "$ROOT_VENV_DIR"
else
  log "Reusing existing root virtual environment at $ROOT_VENV_DIR"
fi

[[ -x "$ROOT_PYTHON_BIN" ]] || fail "Virtual environment python not found: $ROOT_PYTHON_BIN"
[[ -f "$ROOT_REQUIREMENTS" ]] || fail "Missing requirements file: $ROOT_REQUIREMENTS"

log "Upgrading pip in the root virtual environment"
"$ROOT_PYTHON_BIN" -m pip install --upgrade pip

log "Installing Python requirements from $ROOT_REQUIREMENTS"
"$ROOT_PYTHON_BIN" -m pip install -r "$ROOT_REQUIREMENTS"

if [[ "$SKIP_ROOT_NODE" == false ]]; then
  [[ -f "$ROOT_PACKAGE_JSON" ]] || fail "Missing root package.json: $ROOT_PACKAGE_JSON"
  command -v npm >/dev/null 2>&1 || fail "npm is required for root Node.js tooling"
  log "Installing root Node.js tooling (Newman)"
  (
    cd "$ROOT_DIR"
    npm install
  )
else
  log "Skipping root npm install"
fi

if [[ "$SKIP_UI_NODE" == false ]]; then
  [[ -f "$UI_PACKAGE_JSON" ]] || fail "Missing validation/ui package.json: $UI_PACKAGE_JSON"
  command -v npm >/dev/null 2>&1 || fail "npm is required for Playwright tooling"
  log "Installing validation/ui Node.js tooling (Playwright)"
  (
    cd "$UI_DIR"
    npm install
  )
else
  log "Skipping validation/ui npm install"
fi

if [[ "$SKIP_PLAYWRIGHT" == false ]]; then
  command -v npx >/dev/null 2>&1 || fail "npx is required for Playwright browser installation"
  log "Installing Playwright browsers"
  (
    cd "$UI_DIR"
    if [[ "$WITH_SYSTEM_DEPS" == true ]]; then
      npx playwright install --with-deps
    else
      npx playwright install
    fi
  )
else
  log "Skipping Playwright browser installation"
fi

if [[ "$SKIP_DEPLOYER_CONFIG_INIT" == false ]]; then
  if [[ ! -f "$DEPLOYER_CONFIG" && -f "$DEPLOYER_CONFIG_EXAMPLE" ]]; then
    log "Creating deployer.config from deployer.config.example"
    cp "$DEPLOYER_CONFIG_EXAMPLE" "$DEPLOYER_CONFIG"
  elif [[ -f "$DEPLOYER_CONFIG" ]]; then
    log "Reusing existing deployer.config"
  else
    log "deployer.config.example not found; skipping deployer.config initialization"
  fi
else
  log "Skipping deployer.config initialization"
fi

log "Bootstrap completed"
log "Next steps:"
log "  1. Activate the root environment: source .venv/bin/activate"
log "  2. Review deployer.config if needed"
log "  3. Run: python3 inesdata.py"
