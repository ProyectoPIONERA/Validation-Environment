#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_SCRIPT="$ADAPTER_DIR/scripts/sync_sources.sh"

SOURCE_DIR="$ADAPTER_DIR/sources/connector"
DOCKERFILE="$ADAPTER_DIR/build/docker/connector.Dockerfile"
IMAGE_NAME="validation-environment/edc-connector"
IMAGE_TAG="local"
MINIKUBE_PROFILE="minikube"
GRADLE_TASK=":transfer:transfer-00-prerequisites:connector:shadowJar"
CONNECTOR_JAR="transfer/transfer-00-prerequisites/connector/build/libs/connector.jar"

APPLY=0
FORCE_BUILD=0
SKIP_MINIKUBE_LOAD=0
SYNC_SOURCE=""
SYNC_GIT_URL=""

usage() {
  cat <<'EOF'
Usage: build_image.sh [--apply] [--source-dir <path>] [--image <name>] [--tag <tag>]
                      [--dockerfile <path>] [--gradle-task <task>] [--jar-path <path>]
                      [--minikube-profile <name>] [--skip-minikube-load] [--force-build]
                      [--sync-source <path>] [--sync-git-url <url>]

Build the local generic EDC connector image from adapters/edc/sources/connector.

Options:
  --apply                    Execute the build workflow. Default is dry-run.
  --source-dir <path>        Override the source directory.
  --image <name>             Image repository name.
  --tag <tag>                Image tag.
  --dockerfile <path>        Dockerfile used to package the runtime.
  --gradle-task <task>       Gradle task used to assemble the connector jar.
  --jar-path <path>          Jar path relative to the source directory.
  --minikube-profile <name>  Minikube profile used for image load.
  --skip-minikube-load       Build the image but do not load it into Minikube.
  --force-build              Force rebuilding connector.jar through Gradle even if it already exists.
  --sync-source <path>       Local source directory passed through to sync_sources.sh.
  --sync-git-url <url>       Git URL passed through to sync_sources.sh.
  -h, --help                 Show this help message.
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
    --source-dir)
      SOURCE_DIR="${2:-}"
      shift 2
      ;;
    --image)
      IMAGE_NAME="${2:-}"
      shift 2
      ;;
    --tag)
      IMAGE_TAG="${2:-}"
      shift 2
      ;;
    --dockerfile)
      DOCKERFILE="${2:-}"
      shift 2
      ;;
    --gradle-task)
      GRADLE_TASK="${2:-}"
      shift 2
      ;;
    --jar-path)
      CONNECTOR_JAR="${2:-}"
      shift 2
      ;;
    --minikube-profile)
      MINIKUBE_PROFILE="${2:-}"
      shift 2
      ;;
    --skip-minikube-load)
      SKIP_MINIKUBE_LOAD=1
      shift
      ;;
    --force-build)
      FORCE_BUILD=1
      shift
      ;;
    --sync-source)
      SYNC_SOURCE="${2:-}"
      shift 2
      ;;
    --sync-git-url)
      SYNC_GIT_URL="${2:-}"
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

sync_cmd=("\"$SYNC_SCRIPT\"")
if [[ -n "$SYNC_SOURCE" ]]; then
  sync_cmd+=("--source" "\"$SYNC_SOURCE\"")
fi
if [[ -n "$SYNC_GIT_URL" ]]; then
  sync_cmd+=("--git-url" "\"$SYNC_GIT_URL\"")
fi

if [[ ! -d "$SOURCE_DIR" || ! -x "$SOURCE_DIR/gradlew" ]]; then
  echo "Connector source not ready in $SOURCE_DIR. Syncing first..."
  if [[ "$APPLY" -eq 1 ]]; then
    bash -lc "${sync_cmd[*]} --apply"
  else
    echo "+ ${sync_cmd[*]} --apply"
  fi
fi

if [[ -z "$SOURCE_DIR" || ! -d "$SOURCE_DIR" ]]; then
  echo "Source directory not found after synchronization: $SOURCE_DIR" >&2
  exit 1
fi

if [[ -z "$DOCKERFILE" || ! -f "$DOCKERFILE" ]]; then
  echo "Dockerfile not found: $DOCKERFILE" >&2
  exit 1
fi

if [[ ! -x "$SOURCE_DIR/gradlew" ]]; then
  if [[ -f "$SOURCE_DIR/gradlew" ]]; then
    run_cmd "chmod +x \"$SOURCE_DIR/gradlew\""
  else
    echo "Gradle wrapper not found: $SOURCE_DIR/gradlew" >&2
    exit 1
  fi
fi

FULL_IMAGE="$IMAGE_NAME:$IMAGE_TAG"
ABSOLUTE_CONNECTOR_JAR="$SOURCE_DIR/$CONNECTOR_JAR"
GRADLE_WRAPPER_JAR="$SOURCE_DIR/gradle/wrapper/gradle-wrapper.jar"
GRADLE_USER_HOME="$SOURCE_DIR/.gradle-user-home"

echo "Source dir:        $SOURCE_DIR"
echo "Dockerfile:        $DOCKERFILE"
echo "Gradle task:       $GRADLE_TASK"
echo "Connector jar:     $CONNECTOR_JAR"
echo "Image:             $FULL_IMAGE"
echo "Minikube profile:  $MINIKUBE_PROFILE"

if [[ -f "$ABSOLUTE_CONNECTOR_JAR" && "$FORCE_BUILD" -eq 0 ]]; then
  echo "Reusing existing connector jar: $ABSOLUTE_CONNECTOR_JAR"
else
  if [[ ! -f "$GRADLE_WRAPPER_JAR" ]]; then
    echo "Gradle wrapper jar not found: $GRADLE_WRAPPER_JAR" >&2
    exit 1
  fi

  run_cmd "mkdir -p \"$GRADLE_USER_HOME\""
  run_cmd "cd \"$SOURCE_DIR\" && GRADLE_USER_HOME=\"$GRADLE_USER_HOME\" java -classpath \"$GRADLE_WRAPPER_JAR\" org.gradle.wrapper.GradleWrapperMain --no-daemon -Dorg.gradle.workers.max=1 \"$GRADLE_TASK\" -x test"
fi

if [[ ! -f "$ABSOLUTE_CONNECTOR_JAR" ]]; then
  echo "Connector jar not found after preparation: $ABSOLUTE_CONNECTOR_JAR" >&2
  exit 1
fi

run_cmd "cd \"$SOURCE_DIR\" && docker build -f \"$DOCKERFILE\" --build-arg CONNECTOR_JAR=\"$CONNECTOR_JAR\" -t \"$FULL_IMAGE\" ."

if [[ "$SKIP_MINIKUBE_LOAD" -eq 0 ]]; then
  run_cmd "minikube -p \"$MINIKUBE_PROFILE\" image load \"$FULL_IMAGE\""
fi

echo
echo "Suggested deployment overrides:"
echo "  PIONERA_EDC_CONNECTOR_IMAGE_NAME=$IMAGE_NAME"
echo "  PIONERA_EDC_CONNECTOR_IMAGE_TAG=$IMAGE_TAG"
