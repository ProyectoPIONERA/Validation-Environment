#!/bin/bash
# Sets up nginx reverse proxy on a connector-only VM (pionera20/pionera3).
# Exposes a single connector via its public org domain (org2.* or org3.*).
#
# Usage: bash setup-nginx-proxy-connector.sh <VM_IP> <PUBLIC_HOST> <CONNECTOR_SHORT> <CONN_FULL_NAME> <INTERNAL_DOMAIN>
# Example: bash setup-nginx-proxy-connector.sh 192.168.122.134 org2.pionera.oeg.fi.upm.es citycouncil conn-citycouncil-demo pionera.oeg.fi.upm.es

set -e

VM_IP="${1:?VM_IP required}"
PUBLIC_HOST="${2:?PUBLIC_HOST required}"
CONNECTOR="${3:?CONNECTOR_SHORT required}"
CONN_NAME="${4:?CONN_FULL_NAME required}"
INTERNAL_DOMAIN="${5:-pionera.oeg.fi.upm.es}"

INGRESS_BACKEND="${VM_IP}:31667"

echo "[1/4] Installing nginx..."
sudo apt-get install -y nginx 2>/dev/null || true

echo "[2/4] Generating self-signed TLS certificate..."
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/nginx/pionera-selfsigned.key \
  -out /etc/nginx/pionera-selfsigned.crt \
  -subj "/CN=${PUBLIC_HOST}/O=Pionera" \
  -addext "subjectAltName=DNS:${PUBLIC_HOST}" 2>/dev/null
sudo chmod 600 /etc/nginx/pionera-selfsigned.key

echo "[3/4] Writing connector config for browser..."
sudo mkdir -p /var/www/connector-configs

# Build app.config.json from the connector pod's template
KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
export KUBECONFIG

NAMESPACE=$(kubectl get pods -A --no-headers 2>/dev/null | grep "${CONN_NAME}" | grep -v "inteface\|interface" | awk '{print $1}' | head -1)
POD=$(kubectl get pods -n "${NAMESPACE:-demo}" --no-headers 2>/dev/null | grep "${CONN_NAME}" | grep -v "inteface\|interface" | awk '{print $1}' | head -1)

if [ -n "$POD" ] && [ -n "$NAMESPACE" ]; then
    CONFIG_PATH="/usr/share/nginx/html/inesdata-connector-interface/assets/config/app.config.json"
    TEMPLATE_PATH="/usr/share/nginx/html/inesdata-connector-interface/assets/config/app.config.template.json"
    READ_PATH=$(kubectl exec -n "$NAMESPACE" "$POD" -- sh -c "[ -s '$CONFIG_PATH' ] && echo '$CONFIG_PATH' || echo '$TEMPLATE_PATH'" 2>/dev/null || echo "$TEMPLATE_PATH")

    kubectl exec -n "$NAMESPACE" "$POD" -- cat "$READ_PATH" 2>/dev/null | python3 -c "
import sys, json, re
content = sys.stdin.read()
content = re.sub(r':\s*(\\\$[A-Z0-9_]+)', ': false', content)
try:
    c = json.loads(content)
except Exception:
    c = {}
base = 'https://${PUBLIC_HOST}'
c['managementApiUrl'] = f'{base}/c/${CONNECTOR}/management'
c['catalogUrl']       = f'{base}/c/${CONNECTOR}/federatedcatalog'
c['sharedUrl']        = f'{base}/c/${CONNECTOR}/shared'
c.setdefault('oauth2', {})
c['oauth2']['issuer']       = 'https://org1.${INTERNAL_DOMAIN}/auth/realms/demo'
c['oauth2']['clientId']     = 'dataspace-users'
c['oauth2']['scope']        = 'openid profile email'
c['oauth2']['responseType'] = 'code'
c['oauth2']['allowedUrls']  = base
c['oauth2']['redirectPath'] = '/inesdata-connector-interface'
print(json.dumps(c, indent=2))
" | sudo tee /var/www/connector-configs/app.config.${CONNECTOR}.json > /dev/null
    echo "  Config written: /var/www/connector-configs/app.config.${CONNECTOR}.json"
else
    echo "  WARNING: connector pod not found, creating minimal config"
    python3 -c "
import json
base = 'https://${PUBLIC_HOST}'
c = {
  'managementApiUrl': f'{base}/c/${CONNECTOR}/management',
  'catalogUrl':       f'{base}/c/${CONNECTOR}/federatedcatalog',
  'sharedUrl':        f'{base}/c/${CONNECTOR}/shared',
  'oauth2': {
    'issuer':       'https://org1.${INTERNAL_DOMAIN}/auth/realms/demo',
    'clientId':     'dataspace-users',
    'scope':        'openid profile email',
    'responseType': 'code',
    'allowedUrls':  base,
    'redirectPath': '/inesdata-connector-interface',
  }
}
print(json.dumps(c, indent=2))
" | sudo tee /var/www/connector-configs/app.config.${CONNECTOR}.json > /dev/null
fi

echo "[4/4] Writing nginx config..."

sudo tee /etc/nginx/sites-available/pionera-connector.conf > /dev/null << NGINXEOF
server {
    listen ${VM_IP}:80;
    server_name ${PUBLIC_HOST};
    return 301 https://\$host\$request_uri;
}

server {
    listen ${VM_IP}:443 ssl;
    ssl_certificate     /etc/nginx/pionera-selfsigned.crt;
    ssl_certificate_key /etc/nginx/pionera-selfsigned.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    server_name ${PUBLIC_HOST};

    location = /inesdata-connector-interface/assets/config/app.config.json {
        alias /var/www/connector-configs/app.config.${CONNECTOR}.json;
        default_type application/json;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
    }
    location = /c/${CONNECTOR}/inesdata-connector-interface/assets/config/app.config.json {
        alias /var/www/connector-configs/app.config.${CONNECTOR}.json;
        default_type application/json;
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }

    location = / {
        default_type text/html;
        return 200 "<html><body><h1>${PUBLIC_HOST}</h1><ul><li><a href=\"/c/${CONNECTOR}/inesdata-connector-interface/\">${CONNECTOR} Connector</a></li></ul></body></html>";
    }

    location /c/${CONNECTOR}/management/ {
        rewrite ^/c/${CONNECTOR}/management/(.*) /management/\$1 break;
        proxy_pass http://${INGRESS_BACKEND};
        proxy_set_header Host ${CONN_NAME}.${INTERNAL_DOMAIN};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        client_max_body_size 0;
    }
    location /c/${CONNECTOR}/shared/ {
        rewrite ^/c/${CONNECTOR}/shared/(.*) /shared/\$1 break;
        proxy_pass http://${INGRESS_BACKEND};
        proxy_set_header Host ${CONN_NAME}.${INTERNAL_DOMAIN};
        proxy_set_header X-Real-IP \$remote_addr;
    }
    location /c/${CONNECTOR}/federatedcatalog/ {
        rewrite ^/c/${CONNECTOR}/federatedcatalog/(.*) /management/federatedcatalog/\$1 break;
        proxy_pass http://${INGRESS_BACKEND};
        proxy_set_header Host ${CONN_NAME}.${INTERNAL_DOMAIN};
        proxy_set_header X-Real-IP \$remote_addr;
    }
    location /c/${CONNECTOR}/ {
        add_header Set-Cookie "inesdata_connector=${CONNECTOR}; Path=/; SameSite=Lax" always;
        rewrite ^/c/${CONNECTOR}/(.*) /\$1 break;
        proxy_pass http://${INGRESS_BACKEND};
        proxy_set_header Host ${CONN_NAME}.${INTERNAL_DOMAIN};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    location /inesdata-connector-interface/ {
        proxy_pass http://${INGRESS_BACKEND};
        proxy_set_header Host ${CONN_NAME}.${INTERNAL_DOMAIN};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    location / {
        proxy_pass http://${INGRESS_BACKEND};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        client_max_body_size 0;
    }
}
NGINXEOF

sudo ln -sf /etc/nginx/sites-available/pionera-connector.conf /etc/nginx/sites-enabled/pionera-connector.conf
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

sudo nginx -t && sudo systemctl enable nginx && sudo systemctl restart nginx
echo ""
echo "=========================================="
echo "Nginx proxy configured. URL:"
echo "  https://${PUBLIC_HOST}/c/${CONNECTOR}/inesdata-connector-interface/"
echo "=========================================="
