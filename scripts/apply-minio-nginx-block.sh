#!/bin/bash
# Apply MinIO direct-access server block to pioneer40 host nginx.
# Fixes EDC data-plane AWS SDK S3 502 errors on vm-distributed topology.
# Run with: sudo bash scripts/apply-minio-nginx-block.sh

set -e
CONF=/etc/nginx/sites-enabled/pionera-dataspace.conf

BLOCK='
# MinIO S3 API — direct hostname access (EDC data-plane AWS SDK)
server {
    listen 192.168.122.64:80;
    server_name minio.pionera.oeg.fi.upm.es console.minio-s3.pionera.oeg.fi.upm.es;
    client_max_body_size 0;
    location / {
        proxy_pass http://192.168.122.64:31667;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
    }
}
'

# Check if block already present
if grep -q "minio.pionera.oeg.fi.upm.es" "$CONF" 2>/dev/null; then
    echo "MinIO block already in $CONF — skipping append."
else
    printf '%s\n' "$BLOCK" >> "$CONF"
    echo "MinIO block appended to $CONF."
fi

nginx -t && nginx -s reload && echo "nginx reloaded OK."
