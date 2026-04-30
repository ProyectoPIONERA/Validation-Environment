# Tutorial: Despliegue del entorno PIONERA en VM con k3s

Este tutorial describe paso a paso cómo desplegar el entorno de validación PIONERA
en una VM Linux usando k3s como cluster Kubernetes, y cómo configurar el acceso
externo HTTPS desde un navegador.

**Entorno de referencia:**
- VM: Ubuntu 22.04, IP interna `192.168.122.64`
- Hipervisor KVM: IP pública `138.100.15.165`
- Dominio: `org1.pionera.oeg.fi.upm.es` → resuelve a `138.100.15.165`

---

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Instalar k3s](#2-instalar-k3s)
3. [Clonar el repositorio y preparar dependencias](#3-clonar-el-repositorio-y-preparar-dependencias)
4. [Configurar el entorno](#4-configurar-el-entorno)
5. [Ejecutar los niveles de despliegue](#5-ejecutar-los-niveles-de-despliegue)
6. [Configurar el proxy nginx](#6-configurar-el-proxy-nginx)
7. [Verificar el acceso desde el navegador](#7-verificar-el-acceso-desde-el-navegador)
8. [Ejecutar las validaciones](#8-ejecutar-las-validaciones)
9. [Solución de problemas frecuentes](#9-solución-de-problemas-frecuentes)

---

## 1. Requisitos previos

### En la VM

```bash
# Actualizar sistema
sudo apt-get update && sudo apt-get upgrade -y

# Instalar dependencias base
sudo apt-get install -y \
  git curl wget python3 python3-pip python3-venv \
  postgresql-client nginx iptables-persistent \
  nodejs npm

# Verificar versiones
python3 --version   # >= 3.10
node --version      # >= 18
npm --version
psql --version
```

### Helm

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

---

## 2. Instalar k3s

```bash
# Instalar k3s (servidor single-node)
curl -sfL https://get.k3s.io | sh -

# Verificar que está corriendo
sudo systemctl status k3s

# Hacer accesible kubectl sin sudo
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config

# Verificar cluster
kubectl get nodes
kubectl get pods -A
```

Espera a que el nodo esté en estado `Ready` (puede tardar 1-2 minutos).

---

## 3. Clonar el repositorio y preparar dependencias

```bash
git clone --branch feature/new-pionera-automation-kubernetes --single-branch \
  https://github.com/ProyectoPIONERA/Validation-Environment.git
cd Validation-Environment

# Preparar dependencias Python y Node
bash scripts/bootstrap_framework.sh
source .venv/bin/activate

# Verificar
python3 main.py list
```

---

## 4. Configurar el entorno

### 4.1 Configuración de infraestructura

```bash
cp deployers/infrastructure/deployer.config.example deployers/infrastructure/deployer.config
```

Edita `deployers/infrastructure/deployer.config`:

```text
ENVIRONMENT=DEV
KC_PASSWORD=change-me
PG_PASSWORD=change-me
MINIO_PASSWORD=change-me
PUBLIC_HOSTNAME=org1.pionera.oeg.fi.upm.es
VM_COMMON_IP=192.168.122.64
```

### 4.2 Configuración del adapter INESData

```bash
# Verificar que existe el deployer.config de inesdata
cat deployers/inesdata/deployer.config
```

Las variables mínimas necesarias:

```text
DS_1_NAME=demo
DS_1_NAMESPACE=demo
DS_1_CONNECTORS=citycouncil,company
```

### 4.3 Ficheros de credenciales

Los ficheros en `deployers/inesdata/deployments/DEV/demo/` contienen las credenciales
generadas por el framework. Se crean automáticamente durante Level 3. Si ya existen
de un despliegue anterior, el framework los reutiliza.

---

## 5. Ejecutar los niveles de despliegue

```bash
python3 main.py menu
```

Ejecuta los niveles en orden:

### Level 1 — Setup Cluster

Prepara el cluster k3s:
- Instala `ingress-nginx` con Helm
- Habilita `allow-snippet-annotations` en el configmap (necesario para las anotaciones de Keycloak)
- Cambia el servicio `ingress-nginx-controller` a tipo `NodePort` para evitar que k3s ServiceLB intercepte los puertos 80/443

```
Menú → 1
```

**Verificación:**

```bash
kubectl get pods -n ingress-nginx
kubectl get svc ingress-nginx-controller -n ingress-nginx
# Debe mostrar TYPE=NodePort, no LoadBalancer
```

### Level 2 — Deploy Common Services

Despliega Keycloak, MinIO, PostgreSQL y Vault:

```
Menú → 2
```

**Verificación:**

```bash
kubectl get pods -n common-srvs
# Esperar: keycloak Running, minio Running, postgresql Running, vault Running
```

### Level 3 — Deploy Dataspace

Crea el dataspace `demo`, configura Keycloak (realms, clientes, usuarios) y genera
los ficheros de credenciales:

```
Menú → 3
```

### Level 4 — Deploy Connectors

Despliega los conectores `conn-citycouncil-demo` y `conn-company-demo`:

```
Menú → 4
```

Al finalizar, si `PUBLIC_HOSTNAME` está configurado, el framework ejecuta
automáticamente `setup-nginx-proxy.sh`. Si `sudo` requiere contraseña, muestra
el comando a ejecutar manualmente (ver sección 6).

### Level 5 — Deploy Components (opcional)

Despliega componentes opcionales como Ontology Hub y AI Model Hub:

```
Menú → 5
```

### Level 6 — Run Validation Tests

Ejecuta la suite de validación completa (Newman + Playwright):

```
Menú → 6
```

---

## 6. Configurar el proxy nginx

Este paso expone los servicios internos de k3s a través de nginx en la VM.

### Ejecución automática (recomendada)

Si `sudo` es passwordless o si el framework ya lo ejecutó en Level 4:

```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  192.168.49.2 192.168.122.64 org1.pionera.oeg.fi.upm.es pionera.oeg.fi.upm.es
```

El script realiza las siguientes acciones:

1. **Instala nginx e iptables-persistent** si no están presentes.

2. **Detecta k3s** y configura el backend como `192.168.122.64:31667` (NodePort de k3s).
   En minikube, usaría `192.168.49.2:80` directamente.

3. **Configura iptables DNAT** para redirigir el tráfico del hipervisor:
   ```
   138.100.15.165:80  → 192.168.122.64:80  (nginx VM)
   138.100.15.165:443 → 192.168.122.64:443 (nginx VM con TLS)
   ```

4. **Genera un certificado TLS autofirmado** válido 10 años:
   ```
   /etc/nginx/pionera-selfsigned.crt
   /etc/nginx/pionera-selfsigned.key
   ```

5. **Parchea `app.config.json`** en los pods con las URLs externas HTTPS correctas.

6. **Escribe la configuración nginx** con:
   - Rutas por prefijo: `/auth/`, `/c/citycouncil/`, `/c/company/`, `/s3-console/`
   - Routing por cookie para el callback OIDC
   - `proxy_cookie_path /realms/ /auth/realms/` para que la cookie de sesión
     Keycloak tenga el path correcto en el browser
   - `sub_filter` para reescribir URLs internas a URLs externas HTTPS

7. **Establece el `frontendUrl`** de Keycloak vía Admin API para que los tokens JWT
   contengan el issuer correcto (`https://org1.pionera.oeg.fi.upm.es/auth`).

### Verificación del proxy

```bash
# nginx escucha en los puertos correctos
sudo ss -tlnp | grep nginx
# Debe mostrar: 192.168.122.64:80, 192.168.122.64:443, 192.168.49.2:80

# NO deben existir reglas kube-proxy para la IP de la VM en :80/:443
sudo iptables -t nat -L KUBE-SERVICES -n | grep "192.168.122.64"
# Debe devolver vacío

# Test HTTP
curl -H "Host: org1.pionera.oeg.fi.upm.es" http://192.168.122.64/ | grep INESData

# Test HTTPS
curl -sk -H "Host: org1.pionera.oeg.fi.upm.es" https://192.168.122.64/ | grep INESData

# Test ruta conector
curl -sk -o /dev/null -w "%{http_code}" \
  -H "Host: org1.pionera.oeg.fi.upm.es" \
  "https://192.168.122.64/c/citycouncil/inesdata-connector-interface/"
# Debe devolver 200
```

---

## 7. Verificar el acceso desde el navegador

Desde cualquier PC en red UPM o VPN:

1. Abre el navegador y ve a:
   ```
   https://org1.pionera.oeg.fi.upm.es/c/citycouncil/inesdata-connector-interface/
   ```

2. El browser muestra una advertencia de certificado (es autofirmado). Acepta la
   excepción de seguridad.

3. Aparece la pantalla de login de Keycloak.

4. Introduce las credenciales del conector:
   - **Usuario:** `user-conn-citycouncil-demo`
   - **Contraseña:** ver `deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-citycouncil-demo.json` → campo `connector_user.passwd`

5. Tras el login deberías ver la interfaz del conector INESData.

### URLs disponibles

| URL | Servicio | Usuario |
|-----|----------|---------|
| `/c/citycouncil/inesdata-connector-interface/` | Conector City Council | `user-conn-citycouncil-demo` |
| `/c/company/inesdata-connector-interface/` | Conector Company | `user-conn-company-demo` |
| `/auth/admin/demo/console/` | Admin Keycloak | `admin` / `change-me` |
| `/s3-console/` | Consola MinIO | `admin` / `change-me` |
| `/rs-demo/` | Registration Service | — |

---

## 8. Ejecutar las validaciones

### Validaciones API (Newman)

```bash
python3 main.py inesdata validate --topology vm-single
```

O desde el menú con la opción `6`.

### Validaciones UI (Playwright)

```bash
cd validation/ui
npx playwright test --config playwright.config.ts
```

Los tests de Playwright se conectan directamente a las URLs internas de k3s
(sin pasar por el nginx). La cookie `AUTH_SESSION_ID` se arregla mediante la
anotación del ingress de Keycloak (`proxy_cookie_flags AUTH_SESSION_ID nosecure
samesite=lax`), que se aplica automáticamente en Level 2.

---

## 9. Solución de problemas frecuentes

### nginx devuelve 404 en todos los paths

**Causa:** k3s ServiceLB tiene el tipo `LoadBalancer` activo y crea reglas `KUBE-EXT`
en iptables que interceptan el tráfico a `192.168.122.64:80` antes de que llegue
al nginx de la VM.

**Diagnóstico:**
```bash
sudo iptables -t nat -L KUBE-SERVICES -n | grep "192.168.122.64"
# Si aparecen líneas KUBE-EXT, el problema está aquí
sudo k3s kubectl get svc ingress-nginx-controller -n ingress-nginx
# Si TYPE=LoadBalancer, este es el problema
```

**Solución:**
```bash
sudo k3s kubectl patch svc ingress-nginx-controller -n ingress-nginx \
  -p '{"spec":{"type":"NodePort"}}'
sleep 3
sudo iptables -t nat -L KUBE-SERVICES -n | grep "192.168.122.64"
# Debe estar vacío ahora
```

---

### `cookie_not_found` al hacer login en Keycloak

**Causa:** Cookie `AUTH_SESSION_ID` con `Path=/realms/demo/` — el browser no la
envía cuando la URL es `/auth/realms/demo/...`.

**Diagnóstico:** En las DevTools del browser (Network → la petición POST al login),
verificar si en los request headers aparece `AUTH_SESSION_ID`.
Si aparece pero Keycloak da 400, revisar el log de Keycloak:

```bash
sudo k3s kubectl logs common-srvs-keycloak-0 -n common-srvs --since=5m | grep cookie
```

**Solución:** Re-ejecutar el script de proxy (ya incluye `proxy_cookie_path`):

```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  192.168.49.2 192.168.122.64 org1.pionera.oeg.fi.upm.es pionera.oeg.fi.upm.es
```

O añadir manualmente en `/etc/nginx/sites-enabled/pionera-dataspace.conf` dentro
del bloque `location /auth/`:

```nginx
proxy_cookie_path /realms/ /auth/realms/;
```

Y recargar:
```bash
sudo nginx -s reload
```

---

### Tests Playwright fallan con `cookie_not_found`

**Causa:** Keycloak 24+ establece `AUTH_SESSION_ID` con `Secure;SameSite=None`.
Playwright usa HTTP interno, y el flag `Secure` impide que el browser envíe la cookie.

**Solución:** El framework aplica automáticamente en Level 2 la anotación de ingress:

```
nginx.ingress.kubernetes.io/configuration-snippet:
  proxy_cookie_flags AUTH_SESSION_ID nosecure samesite=lax;
```

Para verificar que está aplicada:

```bash
sudo k3s kubectl get ingress common-srvs-keycloak -n common-srvs \
  -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/configuration-snippet}'
```

Si no está, re-ejecutar Level 2.

---

### El servicio vuelve a `LoadBalancer` tras reiniciar k3s

**Causa:** k3s restaura el estado de los servicios desde etcd. Si el servicio fue
creado como `LoadBalancer`, vuelve a serlo tras reiniciar.

**Solución permanente:** Parchear el chart de ingress-nginx para que use `NodePort`
desde el despliegue inicial, o ejecutar Level 1 de nuevo (el framework aplica el
patch automáticamente).

---

### Los logs de nginx están vacíos

Si `/var/log/nginx/access.log` está vacío después de hacer peticiones, el tráfico
no está llegando al nginx de la VM. Posibles causas:

1. Las reglas `KUBE-EXT` de k3s están interceptando el tráfico (ver primer problema).
2. El hipervisor no está reenviando a la VM correcta.

Verificar directamente desde la VM:

```bash
curl -H "Host: org1.pionera.oeg.fi.upm.es" http://192.168.122.64/
# Si devuelve HTML → nginx OK, el problema es upstream
# Si devuelve 404 con nginx en server header → ver problema KUBE-EXT
```
