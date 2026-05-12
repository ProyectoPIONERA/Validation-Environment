# Tutorial: Setup del entorno PIONERA — topología vm-distributed (3 clusters k3s)

**Objetivo:** partir de un `git clone` y llegar a un entorno funcional con
`python3 main.py menu`, ejecutando todos los niveles en orden, con acceso HTTPS
desde el navegador sin modificar `/etc/hosts`.

**Referencia de arquitectura:** [docs/pionera-distributed-architecture.md](./pionera-distributed-architecture.md)

---

## Índice

1. [Panorama del entorno objetivo](#1-panorama-del-entorno-objetivo)
2. [Prerrequisitos — qué se necesita en cada VM](#2-prerrequisitos--qué-se-necesita-en-cada-vm)
3. [Instalar k3s en cada VM](#3-instalar-k3s-en-cada-vm)
4. [Configurar acceso remoto a los clusters desde pionera40](#4-configurar-acceso-remoto-a-los-clusters-desde-pionera40)
5. [Clonar el repositorio](#5-clonar-el-repositorio)
6. [Preparar las dependencias del framework](#6-preparar-las-dependencias-del-framework)
7. [Configurar deployer.config](#7-configurar-deployerconfig)
8. [Ejecutar los niveles con python3 main.py menu](#8-ejecutar-los-niveles-con-python3-mainpy-menu)
9. [Configurar el proxy nginx (acceso externo)](#9-configurar-el-proxy-nginx-acceso-externo)
10. [Verificar el acceso desde el navegador](#10-verificar-el-acceso-desde-el-navegador)
11. [Resolución de problemas frecuentes](#11-resolución-de-problemas-frecuentes)

---

## 1. Panorama del entorno objetivo

Al finalizar este tutorial tendrás:

```
[Browser HTTPS] → host KVM 138.100.15.165 → VM pionera40 nginx
                                                    │
                              ┌─────────────────────┼──────────────────────┐
                              ▼                     ▼                      ▼
                   k3s pionera40              k3s pionera20           k3s pionera3
                   (shared services)          (citycouncil)           (company)
                   Keycloak, MinIO,           conn-citycouncil        conn-company
                   PostgreSQL, Vault          -demo                   -demo
```

URLs finales (accesibles desde cualquier PC en red UPM o VPN):

| URL | Servicio |
|-----|----------|
| `https://org1.pionera.oeg.fi.upm.es/c/citycouncil/inesdata-connector-interface/` | Conector City Council |
| `https://org1.pionera.oeg.fi.upm.es/c/company/inesdata-connector-interface/` | Conector Company |
| `https://org1.pionera.oeg.fi.upm.es/auth/admin/demo/console/` | Keycloak Admin |
| `https://org1.pionera.oeg.fi.upm.es/s3-console/` | Consola MinIO |

---

## 2. Prerrequisitos — qué se necesita en cada VM

Ejecutar en **las 3 VMs** (pionera40, pionera20, pionera3):

```bash
sudo apt-get update && sudo apt-get upgrade -y

sudo apt-get install -y \
  git curl wget \
  python3 python3-pip python3-venv python3-full \
  postgresql-client \
  nginx iptables-persistent \
  nodejs npm

# Helm (solo en pionera40, donde corre el framework)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verificaciones
python3 --version    # >= 3.10
helm version
node --version       # >= 18
```

---

## 3. Instalar k3s en cada VM

Ejecutar en **cada VM por separado** (no es un cluster multi-nodo):

### En pionera40 (192.168.122.64)

```bash
curl -sfL https://get.k3s.io | sh -
sudo systemctl enable k3s
sudo systemctl start k3s

mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config

kubectl get nodes
# NAME        STATUS   ROLES                  AGE   VERSION
# pionera40   Ready    control-plane,master   1m    v1.x.x+k3s1
```

### En pionera20 (192.168.122.134)

```bash
ssh pionera@192.168.122.134

curl -sfL https://get.k3s.io | sh -
sudo systemctl enable k3s

# Hacer el kubeconfig legible por el usuario
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
```

### En pionera3 (192.168.122.9)

```bash
ssh pionera@192.168.122.9

curl -sfL https://get.k3s.io | sh -
sudo systemctl enable k3s
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
```

---

## 4. Configurar acceso remoto a los clusters desde pionera40

El framework usa kubeconfigs separados para desplegar en los clusters remotos sin SSH.

### Recoger los kubeconfigs de las VMs remotas

**Desde pionera40**, copiar el kubeconfig de cada VM remota:

```bash
# kubeconfig de pionera20
ssh pionera@192.168.122.134 "sudo cat /etc/rancher/k3s/k3s.yaml" \
  | sed 's|https://127.0.0.1:6443|https://192.168.122.134:6443|' \
  > ~/.kube/k3s-pionera20.yaml

# kubeconfig de pionera3
ssh pionera@192.168.122.9 "sudo cat /etc/rancher/k3s/k3s.yaml" \
  | sed 's|https://127.0.0.1:6443|https://192.168.122.9:6443|' \
  > ~/.kube/k3s-pionera3.yaml

chmod 600 ~/.kube/k3s-pionera20.yaml ~/.kube/k3s-pionera3.yaml
```

El `sed` es esencial: el kubeconfig de k3s usa `127.0.0.1` como servidor,
pero desde pionera40 hay que alcanzar los clusters con sus IPs reales.

### Verificar la conectividad

```bash
KUBECONFIG=~/.kube/k3s-pionera20.yaml kubectl get nodes
# NAME        STATUS   ROLES                  AGE
# pionera20   Ready    control-plane,master   Xm

KUBECONFIG=~/.kube/k3s-pionera3.yaml kubectl get nodes
# NAME       STATUS   ROLES                  AGE
# pionera3   Ready    control-plane,master   Xm
```

Si falla la conexión, verificar que el puerto `6443` esté abierto en el firewall
de las VMs remotas:
```bash
ssh pionera@192.168.122.134 "sudo ufw allow 6443/tcp" 2>/dev/null || true
ssh pionera@192.168.122.9   "sudo ufw allow 6443/tcp" 2>/dev/null || true
```

---

## 5. Clonar el repositorio

**En pionera40:**

```bash
git clone --branch feature/pionera-vm-distributed --single-branch \
  https://github.com/ProyectoPIONERA/Validation-Environment.git
cd Validation-Environment
```

---

## 6. Preparar las dependencias del framework

```bash
cd /home/pionera/vm-distributed/Validation-Environment

bash scripts/bootstrap_framework.sh
source .venv/bin/activate

# Verificar
python3 main.py list
```

Si `bootstrap_framework.sh` falla, crear el entorno manualmente:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Dependencias Node para Newman
npm install
```

---

## 7. Configurar deployer.config

El framework usa dos ficheros de configuración:

```
deployers/infrastructure/deployer.config   ← infraestructura común
deployers/inesdata/deployer.config         ← parámetros específicos INESData
```

### 7.1 deployers/infrastructure/deployer.config

Copiar desde la plantilla:

```bash
cp deployers/infrastructure/deployer.config.example \
   deployers/infrastructure/deployer.config
```

Editar con un editor. Variables obligatorias:

```bash
# ── Credenciales de servicios ─────────────────────────────────────────────────
ENVIRONMENT=DEV
KC_USER=admin
KC_PASSWORD=<elige-contraseña-keycloak>        # ej. MyKCpass2024!
PG_USER=postgres
PG_PASSWORD=<elige-contraseña-postgres>        # ej. MyPGpass2024!
MINIO_USER=admin
MINIO_ADMIN_USER=admin
MINIO_PASSWORD=<elige-contraseña-minio>        # ej. MyMinIOpass2024!
MINIO_ADMIN_PASS=<misma-contraseña-minio>
VT_TOKEN=                                      # dejar vacío, se genera en Level 2

# ── Red ───────────────────────────────────────────────────────────────────────
DOMAIN_BASE=pionera.oeg.fi.upm.es
DS_DOMAIN_BASE=pionera.oeg.fi.upm.es
VM_COMMON_IP=192.168.122.64                    # IP de la VM pionera40

# ── Hostnames internos de Keycloak ───────────────────────────────────────────
KC_URL=http://auth.pionera.oeg.fi.upm.es
KC_INTERNAL_URL=http://auth.pionera.oeg.fi.upm.es
KEYCLOAK_HOSTNAME=auth.pionera.oeg.fi.upm.es
KEYCLOAK_ADMIN_HOSTNAME=admin.auth.pionera.oeg.fi.upm.es
MINIO_HOSTNAME=minio.pionera.oeg.fi.upm.es
MINIO_CONSOLE_HOSTNAME=console.minio-s3.pionera.oeg.fi.upm.es

# ── Kubernetes ────────────────────────────────────────────────────────────────
CLUSTER_TYPE=k3s                               # IMPORTANTE: usar k3s, no minikube
K3S_KUBECONFIG=/etc/rancher/k3s/k3s.yaml       # kubeconfig local de pionera40

# ── Topología distribuida ─────────────────────────────────────────────────────
TOPOLOGY=vm-distributed                        # activa la topología 3 clusters

VM_PROVIDER_IP=192.168.122.134                 # pionera20
VM_CONSUMER_IP=192.168.122.9                   # pionera3

K3S_KUBECONFIG_PROVIDER=/home/pionera/.kube/k3s-pionera20.yaml
K3S_KUBECONFIG_CONSUMER=/home/pionera/.kube/k3s-pionera3.yaml

VM_PROVIDER_CONNECTORS=citycouncil
VM_CONSUMER_CONNECTORS=company

# ── Acceso externo HTTPS ──────────────────────────────────────────────────────
PUBLIC_HOSTNAME=org1.pionera.oeg.fi.upm.es     # hostname público para el navegador
```

> **Nota sobre `PUBLIC_HOSTNAME`:** este valor activa la configuración automática
> del proxy nginx al finalizar el Level 4. El framework también establece el
> `frontendUrl` de Keycloak para que los JWT contengan el issuer correcto.

### 7.2 deployers/inesdata/deployer.config

```bash
# Verificar que contiene:
cat deployers/inesdata/deployer.config
```

Valores mínimos necesarios:

```bash
DS_1_NAME=demo
DS_1_NAMESPACE=demo
DS_1_CONNECTORS=citycouncil,company
COMPONENTS=ontology-hub,ai-model-hub
KC_INTERNAL_URL=http://auth.pionera.oeg.fi.upm.es
MINIO_HOSTNAME=minio.pionera.oeg.fi.upm.es
CLUSTER_TYPE=k3s
```

Si el fichero no existe:

```bash
cp deployers/inesdata/deployer.config.example deployers/inesdata/deployer.config
```

---

## 8. Ejecutar los niveles con python3 main.py menu

```bash
cd /home/pionera/vm-distributed/Validation-Environment
source .venv/bin/activate   # si no está ya activo
python3 main.py menu
```

Ejecutar los niveles en **orden 1 → 2 → 3 → 4 → 5 → 6**.

---

### Level 1 — Setup Cluster

Seleccionar `1` en el menú.

**Qué hace:**
- Instala `ingress-nginx` con Helm en **los 3 clusters** (pionera40, pionera20, pionera3)
- Habilita `allow-snippet-annotations` en el configmap de ingress-nginx (necesario para las anotaciones de cookie de Playwright)
- Cambia `ingress-nginx-controller` de `LoadBalancer` a `NodePort` en cada cluster

**Por qué NodePort es esencial:** k3s en modo `LoadBalancer` crea reglas iptables `KUBE-EXT`
que interceptan el tráfico en `:80/:443` antes de que llegue al nginx de la VM.
Con `NodePort`, el tráfico llega al nginx de la VM, que lo reenvía al NodePort `31667`.

**Verificación:**

```bash
# Cluster principal (pionera40)
kubectl get svc ingress-nginx-controller -n ingress-nginx
# TYPE debe ser NodePort

# Cluster pionera20
KUBECONFIG=~/.kube/k3s-pionera20.yaml \
  kubectl get svc ingress-nginx-controller -n ingress-nginx

# Cluster pionera3
KUBECONFIG=~/.kube/k3s-pionera3.yaml \
  kubectl get svc ingress-nginx-controller -n ingress-nginx
```

---

### Level 2 — Deploy Common Services

Seleccionar `2` en el menú.

**Qué hace:**
- Despliega Keycloak, MinIO, PostgreSQL, Vault en el namespace `common-srvs` en **pionera40**
- Configura los ingress k3s con el hostname correcto
- Aplica la anotación `proxy_cookie_flags AUTH_SESSION_ID nosecure samesite=lax`
  en el ingress de Keycloak (necesario para Playwright y para evitar `cookie_not_found`)
- Inicializa Vault

**Verificación:**

```bash
kubectl get pods -n common-srvs
# Esperar: keycloak-0 Running, minio-* Running, postgresql-* Running, vault-* Running

# Test de Keycloak accesible internamente
curl -s http://auth.pionera.oeg.fi.upm.es/realms/master/.well-known/openid-configuration \
  | python3 -m json.tool | grep issuer
```

---

### Level 3 — Deploy Dataspace

Seleccionar `3` en el menú.

**Qué hace:**
- Crea el realm `demo` en Keycloak
- Crea usuarios, cliente OIDC (`dataspace-users`) y roles
- Crea el dataspace `demo` en PostgreSQL
- Genera los ficheros de credenciales de los conectores en:
  ```
  deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-citycouncil-demo.json
  deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-company-demo.json
  ```
- Registra los conectores en la tabla `edc_participant` de PostgreSQL

**Verificación:**

```bash
# Las credenciales deben existir
cat deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-citycouncil-demo.json
cat deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-company-demo.json
```

---

### Level 4 — Deploy Connectors

Seleccionar `4` en el menú.

**Qué hace:**
- Despliega `conn-citycouncil-demo` en **pionera20** (usa `K3S_KUBECONFIG_PROVIDER`)
- Despliega `conn-company-demo` en **pionera3** (usa `K3S_KUBECONFIG_CONSUMER`)
- Cada conector lleva su Helm chart con:
  - Ingress con hostname `conn-citycouncil-demo.pionera.oeg.fi.upm.es`
  - Anotación de eliminación de HSTS: `more_clear_headers Strict-Transport-Security`
  - Credenciales de Vault, PostgreSQL, MinIO generadas en el Level 3
- Al finalizar: ejecuta `setup-nginx-proxy.sh` automáticamente si `PUBLIC_HOSTNAME` está configurado

**Verificación:**

```bash
# Conector citycouncil en pionera20
KUBECONFIG=~/.kube/k3s-pionera20.yaml \
  kubectl get pods -n demo
# conn-citycouncil-demo-* Running

# Conector company en pionera3
KUBECONFIG=~/.kube/k3s-pionera3.yaml \
  kubectl get pods -n demo
# conn-company-demo-* Running

# Test management API (desde pionera40)
curl -s -H "Host: conn-citycouncil-demo.pionera.oeg.fi.upm.es" \
  http://192.168.122.134:31667/management/v3/assets/request \
  -X POST -H "Content-Type: application/json" -d '{}' | head -c 200
```

> **Si Level 4 imprime `sudo requires a password — run manually:`**  
> Copiar y ejecutar el comando que aparece en pantalla. Solo es necesario una vez.

---

### Level 5 — Deploy Components (opcional)

Seleccionar `5` en el menú.

**Qué hace:**
- Despliega Ontology Hub y AI Model Hub en pionera40 (si están configurados en `COMPONENTS`)

Se puede omitir este nivel si no se necesitan estos componentes.

---

### Level 6 — Run Validation Tests

Seleccionar `6` en el menú.

**Qué hace:**
- Ejecuta las colecciones Newman en orden:
  1. `01_environment_health.json` — health check y autenticación
  2. `02_connector_management_api.json` — CRUD Management API
  3. `03_provider_setup.json` — preparación escenario E2E provider
  4. `04_consumer_catalog.json` — descubrimiento de catálogo
  5. `05_consumer_negotiation.json` — negociación de contrato
  6. `06_consumer_transfer.json` — transferencia de datos
- Ejecuta los tests de Playwright UI
- Guarda los resultados en `experiments/experiment_<timestamp>/`

**Prerrequisitos para Level 6:**
- Level 4 completado con éxito
- Proxy nginx configurado (acceso HTTPS funcionando)
- Verificar manualmente el acceso desde el navegador antes de lanzar Playwright

---

## 9. Configurar el proxy nginx (acceso externo)

Si el Level 4 no ejecutó el proxy automáticamente, ejecutarlo manualmente.

### Script setup-nginx-proxy.sh

```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  192.168.49.2 192.168.122.64 org1.pionera.oeg.fi.upm.es pionera.oeg.fi.upm.es
```

Parámetros: `<minikube_ip> <vm_ip> <public_hostname> <internal_domain>`

El primer parámetro (`192.168.49.2`) se ignora en topología k3s — el framework
lo sustituye automáticamente por `192.168.122.64:31667` (NodePort k3s).

**Qué hace el script:**

1. Instala nginx e iptables-persistent
2. Genera certificado TLS autofirmado (`/etc/nginx/pionera-selfsigned.crt`)
3. Escribe `/etc/nginx/sites-enabled/pionera-dataspace.conf` con:
   - Routing `/c/citycouncil/` → `192.168.122.134:31667`
   - Routing `/c/company/` → `192.168.122.9:31667`
   - Routing `/auth/` → `192.168.122.64:31667` + `sub_filter` HTTPS + `proxy_cookie_path`
   - Routing por cookie para `/inesdata-connector-interface/`
4. Crea los ficheros `app.config.*.https.json` con URLs `https://` en `/var/www/connector-configs/`
5. Configura reglas iptables DNAT para los puertos del host KVM
6. Establece `frontendUrl` de Keycloak vía Admin API

El script es **idempotente**: se puede volver a ejecutar sin problemas.

### Verificación post-proxy

```bash
# nginx en escucha
sudo ss -tlnp | grep nginx
# Debe mostrar: 192.168.122.64:80, 192.168.49.2:80, 192.168.122.64:443

# Sin reglas KUBE-EXT que intercepten :80/:443
sudo iptables -t nat -L KUBE-SERVICES -n | grep "192.168.122.64"
# Debe estar vacío

# Test HTTP
curl -H "Host: org1.pionera.oeg.fi.upm.es" http://192.168.122.64/ | grep INESData

# Test ruta conector
curl -sk -o /dev/null -w "%{http_code}" \
  -H "Host: org1.pionera.oeg.fi.upm.es" \
  "https://192.168.122.64/c/citycouncil/inesdata-connector-interface/"
# Esperado: 200

# Test app.config (debe devolver JSON con URLs https://)
curl -sk -H "Host: org1.pionera.oeg.fi.upm.es" \
  -b "inesdata_connector=citycouncil" \
  "https://192.168.122.64/inesdata-connector-interface/assets/config/app.config.json" \
  | python3 -m json.tool | grep managementApiUrl
# Esperado: "https://org1.pionera.oeg.fi.upm.es/c/citycouncil/management"
```

---

## 10. Verificar el acceso desde el navegador

Desde cualquier PC en red UPM o VPN (sin modificar `/etc/hosts`):

1. Ir a: `https://org1.pionera.oeg.fi.upm.es/c/citycouncil/inesdata-connector-interface/`
2. El navegador muestra un aviso de certificado autofirmado → aceptar la excepción
3. Aparece la pantalla de login de Keycloak
4. Credenciales:
   - **Usuario:** `user-conn-citycouncil-demo`
   - **Contraseña:** valor de `connector_user.passwd` en `credentials-connector-conn-citycouncil-demo.json`
5. Tras el login se muestra la interfaz INESData Connector

Repetir con `/c/company/inesdata-connector-interface/` usando `user-conn-company-demo`.

### Obtener las contraseñas generadas por el framework

```bash
python3 -c "
import json
for f in [
    'deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-citycouncil-demo.json',
    'deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-company-demo.json']:
    d = json.load(open(f))
    print(f.split('/')[-1].replace('.json',''), '->', d.get('connector_user', {}).get('passwd', d))
"
```

---

## 11. Resolución de problemas frecuentes

### nginx devuelve 404 en todas las rutas

k3s ServiceLB está interceptando el tráfico.

```bash
# Diagnóstico
sudo iptables -t nat -L KUBE-SERVICES -n | grep "192.168.122.64"
kubectl get svc ingress-nginx-controller -n ingress-nginx

# Fix en pionera40
kubectl patch svc ingress-nginx-controller -n ingress-nginx \
  -p '{"spec":{"type":"NodePort"}}'

# Mismo fix en pionera20 y pionera3
KUBECONFIG=~/.kube/k3s-pionera20.yaml \
  kubectl patch svc ingress-nginx-controller -n ingress-nginx \
  -p '{"spec":{"type":"NodePort"}}'
KUBECONFIG=~/.kube/k3s-pionera3.yaml \
  kubectl patch svc ingress-nginx-controller -n ingress-nginx \
  -p '{"spec":{"type":"NodePort"}}'
```

---

### Página en blanco al cargar el conector (error mixed content)

El navegador bloquea una petición `http://` desde una página `https://`.

```bash
# Verificar que app.config sirve URLs https://
curl -sk -H "Host: org1.pionera.oeg.fi.upm.es" \
  -b "inesdata_connector=citycouncil" \
  "https://192.168.122.64/inesdata-connector-interface/assets/config/app.config.json" \
  | grep "http://"
# No debe encontrar nada
```

Si encuentra URLs `http://`, regenerar el app.config:

```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  192.168.49.2 192.168.122.64 org1.pionera.oeg.fi.upm.es pionera.oeg.fi.upm.es
```

---

### `cookie_not_found` en el login de Keycloak

Verificar que `proxy_cookie_path` está en el bloque nginx:

```bash
sudo grep -n "proxy_cookie_path" /etc/nginx/sites-enabled/pionera-dataspace.conf
# Esperado: proxy_cookie_path /realms/ /auth/realms/;
```

Si no está, volver a ejecutar `setup-nginx-proxy.sh`.

---

### El kubeconfig remoto no funciona tras reiniciar la VM

```bash
# Regenerar kubeconfig desde pionera20
ssh pionera@192.168.122.134 "sudo cat /etc/rancher/k3s/k3s.yaml" \
  | sed 's|https://127.0.0.1:6443|https://192.168.122.134:6443|' \
  > ~/.kube/k3s-pionera20.yaml

# Regenerar desde pionera3
ssh pionera@192.168.122.9 "sudo cat /etc/rancher/k3s/k3s.yaml" \
  | sed 's|https://127.0.0.1:6443|https://192.168.122.9:6443|' \
  > ~/.kube/k3s-pionera3.yaml
```

---

### Conector duplicado en una VM incorrecta

Verificar las releases de Helm en pionera20:

```bash
KUBECONFIG=~/.kube/k3s-pionera20.yaml helm list -n demo
# No debe aparecer conn-company-demo
```

Si aparece:

```bash
KUBECONFIG=~/.kube/k3s-pionera20.yaml helm uninstall conn-company-demo-demo -n demo
```

---

### Cómo resetear completamente y empezar de nuevo

```bash
# Listar todas las releases de Helm en los 3 clusters
helm list -A
KUBECONFIG=~/.kube/k3s-pionera20.yaml helm list -A
KUBECONFIG=~/.kube/k3s-pionera3.yaml helm list -A

# Desinstalar en orden inverso (conectores primero, luego servicios comunes)
KUBECONFIG=~/.kube/k3s-pionera20.yaml helm uninstall conn-citycouncil-demo-demo -n demo
KUBECONFIG=~/.kube/k3s-pionera3.yaml  helm uninstall conn-company-demo-demo -n demo
helm uninstall common-srvs-keycloak common-srvs-minio common-srvs-postgresql \
  common-srvs-vault common-srvs-registration-service -n common-srvs

# Volver a ejecutar los niveles 1 → 6 desde el menú
python3 main.py menu
```
