#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-/tmp/inesdata_seed}"
NAMESPACE="${NAMESPACE:-demo}"
COUNT="${COUNT:-8}"
CONNECTORS_CSV="${CONNECTORS_CSV:-conn-citycouncil-demo,conn-company-demo}"
CREDENTIALS_DIR="${CREDENTIALS_DIR:-$ROOT_DIR/inesdata-testing/deployments/DEV/demo}"
KEYCLOAK_TOKEN_URL="${KEYCLOAK_TOKEN_URL:-}"
VOCABULARY_ID="${VOCABULARY_ID:-JS_Pionera_Daimo}"
VOCABULARY_NAME="${VOCABULARY_NAME:-JS Metadata Daimo}"
VOCABULARY_CATEGORY="${VOCABULARY_CATEGORY:-machineLearning}"
VOCABULARY_SCHEMA_FILE="${VOCABULARY_SCHEMA_FILE:-}"
MODEL_FILE="$WORK_DIR/LGBM_Classifier_1.pkl"
STRICT_MODE="${STRICT_MODE:-0}"

usage() {
  cat <<'EOF'
Usage: seed_ml_assets_for_connectors.sh [options]

Options:
  --namespace <ns>            Kubernetes namespace (default: demo)
  --count <n>                 Number of assets per connector (default: 8)
  --connectors <csv>          Connectors list (default: conn-citycouncil-demo,conn-company-demo)
  --credentials-dir <path>    Folder containing credentials-connector-<name>.json
  --keycloak-token-url <url>  Token endpoint. If omitted, read from deployer.config
  --vocabulary-id <id>        Vocabulary ID used in assetData (default: JS_Pionera_Daimo)
  --vocabulary-name <name>    Vocabulary display name (default: JS Metadata Daimo)
  --vocabulary-category <cat> Vocabulary category (default: machineLearning)
  --vocabulary-schema <path>  JSON schema file. Default auto-detect from project root
  --strict                    Fail if any connector fails (default: disabled)
  -h, --help                  Show this help

Notes:
  - Connector passwords are always read from credentials files at runtime.
  - The vocabulary is created/updated first in each connector.
  - Asset insertion uses Management API upload-chunk + finalize-upload with retries.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    --count)
      COUNT="${2:-}"
      shift 2
      ;;
    --connectors)
      CONNECTORS_CSV="${2:-}"
      shift 2
      ;;
    --credentials-dir)
      CREDENTIALS_DIR="${2:-}"
      shift 2
      ;;
    --keycloak-token-url)
      KEYCLOAK_TOKEN_URL="${2:-}"
      shift 2
      ;;
    --vocabulary-id)
      VOCABULARY_ID="${2:-}"
      shift 2
      ;;
    --vocabulary-name)
      VOCABULARY_NAME="${2:-}"
      shift 2
      ;;
    --vocabulary-category)
      VOCABULARY_CATEGORY="${2:-}"
      shift 2
      ;;
    --vocabulary-schema)
      VOCABULARY_SCHEMA_FILE="${2:-}"
      shift 2
      ;;
    --strict)
      STRICT_MODE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

mkdir -p "$WORK_DIR"

if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [[ "$COUNT" -lt 1 ]]; then
  echo "Invalid --count value: $COUNT" >&2
  exit 1
fi

resolve_vocabulary_schema_file() {
  if [[ -n "$VOCABULARY_SCHEMA_FILE" ]]; then
    if [[ -f "$VOCABULARY_SCHEMA_FILE" ]]; then
      return 0
    fi
    echo "Vocabulary schema file not found: $VOCABULARY_SCHEMA_FILE" >&2
    return 1
  fi

  local candidates=(
    "$ROOT_DIR/JS_Metada_Daimo.schema.json"
    "$ROOT_DIR/JS_Metadata_Daimo.schema.json"
    "$ROOT_DIR/JS_Metadata_Daimo.schema.JSON"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      VOCABULARY_SCHEMA_FILE="$candidate"
      return 0
    fi
  done

  echo "Could not find vocabulary schema file in project root." >&2
  echo "Expected one of: JS_Metada_Daimo.schema.json or JS_Metadata_Daimo.schema.json" >&2
  return 1
}

if [[ -z "$KEYCLOAK_TOKEN_URL" ]]; then
  cfg_file="$ROOT_DIR/deployer.config"
  if [[ ! -f "$cfg_file" ]]; then
    echo "Missing deployer config: $cfg_file" >&2
    exit 1
  fi

  kc_base="$(sed -n 's/^KC_URL=//p' "$cfg_file" | tail -n1)"
  if [[ -z "$kc_base" ]]; then
    kc_base="$(sed -n 's/^KC_INTERNAL_URL=//p' "$cfg_file" | tail -n1)"
  fi
  if [[ -z "$kc_base" ]]; then
    echo "Could not resolve KC_URL/KC_INTERNAL_URL from deployer.config" >&2
    exit 1
  fi
  if [[ "$kc_base" != http* ]]; then
    kc_base="http://$kc_base"
  fi
  KEYCLOAK_TOKEN_URL="$kc_base/realms/$NAMESPACE/protocol/openid-connect/token"
fi

if ! resolve_vocabulary_schema_file; then
  exit 1
fi

echo "Using vocabulary schema: $VOCABULARY_SCHEMA_FILE"
echo "Using vocabulary id: $VOCABULARY_ID"

printf 'placeholder-model-bytes-%s\n' "$(date -u +%s)" > "$MODEL_FILE"

request_retry() {
  local out_file="$1"
  shift

  local code attempt
  for attempt in 1 2 3; do
    code="$(curl -s --max-time 45 -o "$out_file" -w '%{http_code}' "$@")"
    if [[ "$code" == "200" ]]; then
      echo "$code"
      return 0
    fi
    if [[ "$code" != "504" && "$code" != "000" ]]; then
      echo "$code"
      return 1
    fi
    sleep 2
  done

  echo "$code"
  return 1
}

schema_as_json_string() {
  local schema_file="$1"
  tr -d '\n' < "$schema_file" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

get_json_value() {
  local file="$1"
  local block="$2"
  local key="$3"
  sed -n "/\"$block\"[[:space:]]*:[[:space:]]*{/,/}/p" "$file" \
    | sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" \
    | head -n1
}

extract_token_field() {
  local response="$1"
  local field="$2"
  printf '%s' "$response" \
    | sed -n "s/.*\"$field\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" \
    | head -n1
}

request_connector_token() {
  local username="$1"
  local password="$2"
  local connector="$3"
  local creds_label="$4"
  local response token err

  response="$(curl -s -X POST "$KEYCLOAK_TOKEN_URL" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode 'client_id=dataspace-users' \
    --data-urlencode "username=$username" \
    --data-urlencode "password=$password")"

  token="$(extract_token_field "$response" "access_token")"
  if [[ -n "$token" ]]; then
    printf '%s' "$token"
    return 0
  fi

  err="$(extract_token_field "$response" "error_description")"
  if [[ -z "$err" ]]; then
    err="$(extract_token_field "$response" "error")"
  fi
  [[ -z "$err" ]] && err="unknown token error"
  echo "[$connector] token request failed using $creds_label: $err" >&2
  return 1
}

ensure_vocabulary() {
  local connector="$1"
  local token="$2"
  local mgmt_url="$3"
  local vocab_base="$4"
  local schema_str payload_file create_out update_out get_out get_code post_code put_code

  schema_str="$(schema_as_json_string "$VOCABULARY_SCHEMA_FILE")"
  payload_file="$WORK_DIR/vocabulary_${connector}.json"

  cat > "$payload_file" <<EOF
{
  "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
  "@id": "$VOCABULARY_ID",
  "name": "$VOCABULARY_NAME",
  "connectorId": "$connector",
  "category": "$VOCABULARY_CATEGORY",
  "jsonSchema": "$schema_str"
}
EOF

  get_out="$WORK_DIR/vocabulary_${connector}.get.out"
  create_out="$WORK_DIR/vocabulary_${connector}.create.out"
  update_out="$WORK_DIR/vocabulary_${connector}.update.out"

  get_code="$(curl -s -o "$get_out" -w '%{http_code}' \
    "$mgmt_url/$vocab_base/$VOCABULARY_ID" \
    -H "Authorization: Bearer $token")"

  if [[ "$get_code" == "200" ]]; then
    put_code="$(curl -s -o "$update_out" -w '%{http_code}' \
      -X PUT "$mgmt_url/$vocab_base" \
      -H "Authorization: Bearer $token" \
      -H 'Content-Type: application/json' \
      --data-binary "@$payload_file")"
    if [[ "$put_code" == "204" || "$put_code" == "200" ]]; then
      echo "[$connector] vocabulary '$VOCABULARY_ID' updated"
      return 0
    fi
    echo "[$connector] failed to update vocabulary '$VOCABULARY_ID' (HTTP $put_code)" >&2
    cat "$update_out" >&2 || true
    return 1
  fi

  post_code="$(curl -s -o "$create_out" -w '%{http_code}' \
    -X POST "$mgmt_url/$vocab_base" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data-binary "@$payload_file")"

  if [[ "$post_code" == "200" ]]; then
    echo "[$connector] vocabulary '$VOCABULARY_ID' created"
    return 0
  fi

  if [[ "$post_code" == "409" ]]; then
    put_code="$(curl -s -o "$update_out" -w '%{http_code}' \
      -X PUT "$mgmt_url/$vocab_base" \
      -H "Authorization: Bearer $token" \
      -H 'Content-Type: application/json' \
      --data-binary "@$payload_file")"
    if [[ "$put_code" == "204" || "$put_code" == "200" ]]; then
      echo "[$connector] vocabulary '$VOCABULARY_ID' updated after conflict"
      return 0
    fi
    echo "[$connector] vocabulary conflict but update failed (HTTP $put_code)" >&2
    cat "$update_out" >&2 || true
    return 1
  fi

  echo "[$connector] failed to create vocabulary '$VOCABULARY_ID' (HTTP $post_code)" >&2
  cat "$create_out" >&2 || true
  return 1
}

seed_connector_assets() {
  local connector="$1"
  local creds_file="$CREDENTIALS_DIR/credentials-connector-$connector.json"
  local fallback_creds_file="$ROOT_DIR/inesdata-deployment/deployments/DEV/$NAMESPACE/credentials-connector-$connector.json"
  local mgmt_url="http://127.0.0.1:19193/management"
  local pf_pid=""

  if [[ ! -f "$creds_file" ]]; then
    echo "Credentials file not found for $connector: $creds_file" >&2
    return 1
  fi

  local username password token
  local vocab_base
  username="$(get_json_value "$creds_file" connector_user user)"
  password="$(get_json_value "$creds_file" connector_user passwd)"

  if [[ -z "$username" || -z "$password" ]]; then
    echo "Missing connector_user credentials in $creds_file" >&2
    return 1
  fi

  token="$(request_connector_token "$username" "$password" "$connector" "$creds_file" || true)"

  if [[ -z "$token" && -f "$fallback_creds_file" && "$fallback_creds_file" != "$creds_file" ]]; then
    username="$(get_json_value "$fallback_creds_file" connector_user user)"
    password="$(get_json_value "$fallback_creds_file" connector_user passwd)"
    if [[ -n "$username" && -n "$password" ]]; then
      token="$(request_connector_token "$username" "$password" "$connector" "$fallback_creds_file" || true)"
      if [[ -n "$token" ]]; then
        echo "[$connector] using fallback credentials file: $fallback_creds_file"
      fi
    fi
  fi

  if [[ -z "$token" ]]; then
    echo "Failed to obtain token for $connector" >&2
    return 1
  fi

  cleanup_pf() {
    if [[ -n "$pf_pid" ]] && kill -0 "$pf_pid" 2>/dev/null; then
      kill "$pf_pid" >/dev/null 2>&1 || true
      wait "$pf_pid" 2>/dev/null || true
    fi
  }

  kubectl -n "$NAMESPACE" port-forward "svc/$connector" 19193:19193 >"$WORK_DIR/port_forward_$connector.log" 2>&1 &
  pf_pid=$!
  sleep 2

  local probe
  probe="$(curl -s -o "$WORK_DIR/${connector}.probe.out" -w '%{http_code}' "$mgmt_url/v3/assets/request" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    -d '{"@context":{"@vocab":"https://w3id.org/edc/v0.0.1/ns/"},"offset":0,"limit":1,"filterExpression":[]}' || true)"
  if [[ "$probe" != "200" && "$probe" != "400" && "$probe" != "401" && "$probe" != "403" ]]; then
    cleanup_pf
    echo "Management API probe failed for $connector: HTTP $probe" >&2
    return 1
  fi

  # Vocabulary API differs by runtime: some expose /management/vocabularies, others /management/v3/vocabularies.
  vocab_base=""
  local vocab_probe_code
  vocab_probe_code="$(curl -s -o "$WORK_DIR/${connector}.vocab_probe.out" -w '%{http_code}' \
    -X POST "$mgmt_url/vocabularies/request" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    -d '{"@context":{"@vocab":"https://w3id.org/edc/v0.0.1/ns/"},"offset":0,"limit":1,"filterExpression":[]}')"
  if [[ "$vocab_probe_code" == "200" || "$vocab_probe_code" == "400" || "$vocab_probe_code" == "401" || "$vocab_probe_code" == "403" ]]; then
    vocab_base="vocabularies"
  else
    vocab_probe_code="$(curl -s -o "$WORK_DIR/${connector}.vocab_probe_v3.out" -w '%{http_code}' \
      -X POST "$mgmt_url/v3/vocabularies/request" \
      -H "Authorization: Bearer $token" \
      -H 'Content-Type: application/json' \
      -d '{"@context":{"@vocab":"https://w3id.org/edc/v0.0.1/ns/"},"offset":0,"limit":1,"filterExpression":[]}')"
    if [[ "$vocab_probe_code" == "200" || "$vocab_probe_code" == "400" || "$vocab_probe_code" == "401" || "$vocab_probe_code" == "403" ]]; then
      vocab_base="v3/vocabularies"
    fi
  fi

  if [[ -z "$vocab_base" ]]; then
    cleanup_pf
    echo "Could not resolve vocabulary API endpoint for $connector" >&2
    return 1
  fi

  if ! ensure_vocabulary "$connector" "$token" "$mgmt_url" "$vocab_base"; then
    cleanup_pf
    return 1
  fi

  local stamp created idx
  stamp="$(date -u +%Y%m%d%H%M%S)"
  created=0
  : > "$WORK_DIR/${connector}_created_ids.txt"

  for idx in $(seq 1 "$COUNT"); do
    local id title auc recall f1 json_file up_code fin_code
    id="ml-${connector//-/_}-seed-${stamp}-$(printf '%02d' "$idx")"
    title="LGBM ${connector} Model $(printf '%02d' "$idx")"
    auc="$(awk -v n="$idx" 'BEGIN{printf "%.2f", 0.84 + (n*0.01)}')"
    recall="$(awk -v n="$idx" 'BEGIN{printf "%.2f", 0.72 + (n*0.01)}')"
    f1="$(awk -v n="$idx" 'BEGIN{printf "%.2f", 0.70 + (n*0.01)}')"
    json_file="$WORK_DIR/$id.json"

    cat > "$json_file" <<EOF
{
  "@context": {
    "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "daimo": "https://w3id.org/daimo/ns#",
    "mls": "http://www.w3.org/ns/mls#"
  },
  "@id": "$id",
  "properties": {
    "name": "$title",
    "version": "1.0.$idx",
    "contenttype": "application/octet-stream",
    "assetType": "machineLearning",
    "shortDescription": "Seeded LightGBM machine learning asset $idx for $connector.",
    "dcterms:description": "Machine learning model seeded automatically for connector initialization.",
    "dcat:byteSize": 5242880,
    "dcterms:format": "pkl",
    "dcat:keyword": ["machine-learning","lightgbm","inesdata","$connector"],
    "assetData": {
      "$VOCABULARY_ID": {
        "dcterms:title": "$title",
        "dcterms:description": "Binary classifier for default probability estimation.",
        "daimo:task": "Tabular",
        "daimo:subtask": "Calculate default probability",
        "daimo:algorithm": "Gradient Boosting Decision Trees",
        "daimo:framework": "LightGBM",
        "daimo:library": "LightGBM",
        "dcterms:language": ["English","Spanish"],
        "dcterms:license": "apache-2.0",
        "daimo:input_features": [
          {"name":"age","type":"integer","description":"Applicant age in years","nullable":false,"minValue":18,"maxValue":99},
          {"name":"annual_income","type":"number","description":"Annual income in EUR","nullable":false,"minValue":0,"maxValue":1000000},
          {"name":"debt_ratio","type":"number","description":"Debt to income ratio","nullable":false,"minValue":0,"maxValue":2},
          {"name":"late_payments_12m","type":"integer","description":"Late payments in last 12 months","nullable":false,"minValue":0,"maxValue":24}
        ],
        "daimo:input_example": "{\"age\":41,\"annual_income\":52000,\"debt_ratio\":0.36,\"late_payments_12m\":1}",
        "mls:ModelEvaluation": [
          {"metric":"AUC","value":$auc},
          {"metric":"Recall","value":$recall},
          {"metric":"F1","value":$f1}
        ]
      }
    }
  },
  "dataAddress": {"type":"InesDataStore","folder":"ml-seeded-assets"}
}
EOF

    up_code="$(request_retry "$WORK_DIR/$id.upload.out" \
      -X POST "$mgmt_url/s3assets/upload-chunk" \
      -H "Authorization: Bearer $token" \
      -H 'Content-Disposition: attachment; filename="LGBM_Classifier_1.pkl"' \
      -H 'Chunk-Index: 0' \
      -H 'Total-Chunks: 1' \
      -F "json=@$json_file;type=application/json" \
      -F "file=@$MODEL_FILE;type=application/octet-stream")" || true

    fin_code="$(request_retry "$WORK_DIR/$id.finalize.out" \
      -X POST "$mgmt_url/s3assets/finalize-upload" \
      -H "Authorization: Bearer $token" \
      -F "json=@$json_file;type=application/json" \
      -F 'fileName=LGBM_Classifier_1.pkl')" || true

    if [[ "$fin_code" == "200" && ( "$up_code" == "200" || "$up_code" == "000" ) ]]; then
      created=$((created + 1))
      echo "$id" >> "$WORK_DIR/${connector}_created_ids.txt"
      echo "[$connector] $id upload=$up_code finalize=200"
    else
      cleanup_pf
      echo "[$connector] $id upload=${up_code:-NA} finalize=${fin_code:-NA}" >&2
      echo "finalize body:" >&2
      cat "$WORK_DIR/$id.finalize.out" >&2 || true
      return 1
    fi
  done

  cleanup_pf
  echo "[$connector] created_assets=$created stamp=$stamp"
  return 0
}

IFS=',' read -r -a connectors <<< "$CONNECTORS_CSV"

total_created=0
failed_connectors=()
for connector in "${connectors[@]}"; do
  connector="$(echo "$connector" | xargs)"
  [[ -z "$connector" ]] && continue
  if ! seed_connector_assets "$connector"; then
    failed_connectors+=("$connector")
    echo "[$connector] warning: seeding failed, continuing with remaining connectors" >&2
    continue
  fi
  connector_created="$(wc -l < "$WORK_DIR/${connector}_created_ids.txt" 2>/dev/null || echo 0)"
  total_created=$((total_created + connector_created))
done

echo "total_created_assets=$total_created connectors=${#connectors[@]} count_per_connector=$COUNT"

if [[ "${#failed_connectors[@]}" -gt 0 ]]; then
  echo "failed_connectors=${failed_connectors[*]}" >&2
  if [[ "$STRICT_MODE" == "1" ]]; then
    exit 1
  fi
fi

if [[ "$total_created" -eq 0 ]]; then
  if [[ "$STRICT_MODE" == "1" ]]; then
    echo "No assets were created for any connector" >&2
    exit 1
  fi
  echo "warning: no assets were created for any connector (continuing because strict mode is disabled)" >&2
fi
