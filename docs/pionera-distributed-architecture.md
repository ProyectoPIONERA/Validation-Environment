# Arquitectura distribuida PIONERA — 3 clusters k3s

**Fecha:** 2026-05-11  
**Topología:** `vm-distributed`  
**Entorno:** DEV, VMs KVM en host UPM

---

## Índice

1. [Panorama general](#1-panorama-general)
2. [Infraestructura física](#2-infraestructura-física)
3. [Topología de clusters k3s](#3-topología-de-clusters-k3s)
4. [Flujo de red end-to-end](#4-flujo-de-red-end-to-end)
5. [nginx en pionera40: routing y proxy](#5-nginx-en-pionera40-routing-y-proxy)
6. [Routing por cookie](#6-routing-por-cookie)
7. [HTTPS, HSTS y mixed content](#7-https-hsts-y-mixed-content)
8. [Keycloak, OIDC e issuer JWT](#8-keycloak-oidc-e-issuer-jwt)
9. [Dataspace: por qué org1 y no org2/org3](#9-dataspace-por-qué-org1-y-no-org2org3)
10. [Configuraciones runtime críticas](#10-configuraciones-runtime-críticas)
11. [Credenciales](#11-credenciales)
12. [Problemas resueltos y soluciones](#12-problemas-resueltos-y-soluciones)

---

## 1. Panorama general

El PIONERA Validation Environment es un framework para el despliegue y validación
de dataspaces EDC/INESData sobre Kubernetes. En topología `vm-distributed` usa
**3 clusters k3s independientes**, uno por VM, coordinados por un nginx reverse
proxy en la VM principal.

El punto de entrada para el usuario es siempre `python3 main.py menu`.

---

## 2. Infraestructura física

```
[Internet / red UPM / VPN]
         │
         │  DNS: *.pionera.oeg.fi.upm.es → 138.100.15.165
         ▼
[Host KVM — 138.100.15.165]
  nginx hipervisor (gestionado por el administrador UPM)
  Reenvía todo el tráfico (HTTP y HTTPS) a 192.168.49.2:80
  Añade cabecera: X-Forwarded-Proto: https (cuando la petición era HTTPS)
         │
         ▼
[VM pionera40 — 192.168.122.64]   ← VM principal (shared services)
[VM pionera20 — 192.168.122.134]  ← conector citycouncil
[VM pionera3  — 192.168.122.9  ]  ← conector company
```

Las 3 VMs están en la misma red KVM (`192.168.122.0/24`) y se alcanzan
directamente entre ellas. El acceso desde el exterior pasa siempre por pionera40.

---

## 3. Topología de clusters k3s

Cada VM es un **cluster k3s autónomo** (single-node, control-plane y worker en
la misma máquina). No forman un cluster multi-nodo.

| VM | IP | Cluster | Contenido |
|----|----|---------|-----------|
| pionera40 | 192.168.122.64 | k3s-pionera40 | Keycloak, MinIO, PostgreSQL, Vault, Registration Service |
| pionera20 | 192.168.122.134 | k3s-pionera20 | Conector `conn-citycouncil-demo` |
| pionera3 | 192.168.122.9 | k3s-pionera3 | Conector `conn-company-demo` |

Los kubeconfigs de los clusters remotos están en pionera40 en:

```
~/.kube/k3s-pionera20.yaml   ← acceso al cluster de pionera20
~/.kube/k3s-pionera3.yaml    ← acceso al cluster de pionera3
```

El framework los usa para desplegar y gestionar los conectores de forma remota
sin necesidad de SSH.

---

## 4. Flujo de red end-to-end

```
Browser (HTTPS 443)
    │
    │  org1.pionera.oeg.fi.upm.es → 138.100.15.165
    ▼
Host KVM nginx
    │  proxy_pass http://192.168.49.2:80
    │  + cabecera X-Forwarded-Proto: https
    ▼
VM pionera40 nginx (192.168.49.2:80 = 192.168.122.64:80)
    │  Recibe HTTP puro (TLS ya terminado en el host)
    │  Sirve siempre app.config.*.https.json (URLs https://)
    │  Reescribe /auth/ → https:// mediante sub_filter
    │  Cookie inesdata_connector → selecciona backend conector
    │  proxy_pass → 192.168.122.64:31667  (k3s NodePort pionera40)
    │           o → 192.168.122.134:31667 (pionera20, citycouncil)
    │           o → 192.168.122.9:31667   (pionera3, company)
    ▼
k3s ingress-nginx (NodePort 31667)
    │  Cabecera Host → selecciona Ingress k3s
    ▼
Pods: Keycloak / MinIO / Conector (por Host específico)
```

**Nota crítica:** el browser ve HTTPS porque el TLS se termina en el host KVM.
La VM recibe HTTP puro por el puerto 80. Por eso el server block nginx de la VM
debe escuchar en el puerto 80, no en el 443. La cabecera `X-Forwarded-Proto: https`
informa a la aplicación de que la sesión del browser es HTTPS.

---

## 5. nginx en pionera40: routing y proxy

Fichero: `/etc/nginx/sites-enabled/pionera-dataspace.conf`

Estructura del server block principal:

```nginx
server {
    listen 192.168.122.64:80;
    listen 192.168.49.2:80;          # alias IP usado por el host KVM
    listen 192.168.122.64:443 ssl;   # para acceso directo desde red interna
    server_name org1.pionera.oeg.fi.upm.es;

    # app.config siempre con URLs https://
    location = /inesdata-connector-interface/assets/config/app.config.json {
        rewrite ^ /internal-connector-config/$connector_config_name last;
    }
    location = /internal-connector-config/citycouncil {
        internal;
        alias /var/www/connector-configs/app.config.citycouncil.https.json;
    }
    location = /internal-connector-config/company {
        internal;
        alias /var/www/connector-configs/app.config.company.https.json;
    }

    # Keycloak: siempre reescribe a https://
    location /auth/ {
        rewrite ^/auth/(.*) /$1 break;
        proxy_pass http://192.168.122.64:31667;
        proxy_set_header Host auth.pionera.oeg.fi.upm.es;
        proxy_set_header X-Forwarded-Proto https;
        proxy_cookie_path /realms/ /auth/realms/;
        sub_filter_once off;
        sub_filter "http://auth.pionera.oeg.fi.upm.es/realms/"    "https://org1.pionera.oeg.fi.upm.es/auth/realms/";
        sub_filter "http://org1.pionera.oeg.fi.upm.es/auth/"      "https://org1.pionera.oeg.fi.upm.es/auth/";
        # ... otros sub_filter para resources/, js/
    }

    # Conectores en VMs remotas (routing por path)
    location /c/citycouncil/management/ { proxy_pass http://192.168.122.134:31667; }
    location /c/citycouncil/            { proxy_pass http://192.168.122.134:31667; }
    location /c/company/management/     { proxy_pass http://192.168.122.9:31667;   }
    location /c/company/                { proxy_pass http://192.168.122.9:31667;   }

    # Frontend conector: routing dinámico por cookie
    location /inesdata-connector-interface/ {
        proxy_pass http://$connector_backend;
        proxy_set_header Host $connector_host;
    }
}
```

Fichero map: `/etc/nginx/conf.d/connector-routing.conf`

```nginx
map $cookie_inesdata_connector $connector_backend {
    "company"   192.168.122.9:31667;
    default     192.168.122.134:31667;
}
map $cookie_inesdata_connector $connector_host {
    "company"   conn-company-demo.pionera.oeg.fi.upm.es;
    default     conn-citycouncil-demo.pionera.oeg.fi.upm.es;
}
```

---

## 6. Routing por cookie

El frontend Angular (`inesdata-connector-interface`) es la misma app desplegada en
ambos conectores. Cuando el browser solicita `/inesdata-connector-interface/`,
nginx necesita saber qué conector servir.

El mecanismo:

1. Cuando el browser visita `/c/citycouncil/`, nginx establece la cookie:
   ```
   Set-Cookie: inesdata_connector=citycouncil; Path=/; SameSite=Lax
   ```
2. Cuando visita `/c/company/`, establece `inesdata_connector=company`.
3. La siguiente petición a `/inesdata-connector-interface/assets/config/app.config.json`
   lleva la cookie `inesdata_connector`.
4. nginx usa el map `$cookie_inesdata_connector` para elegir `$connector_backend`
   y `$connector_host`.
5. También se usa `$connector_config_name` para servir el fichero
   `app.config.<conector>.https.json` correcto.

---

## 7. HTTPS, HSTS y mixed content

### El problema

El browser visitaba `https://org1.pionera.oeg.fi.upm.es/inesdata-connector-interface/`
(HTTPS) pero el `app.config` contenía URLs `http://` para el OIDC discovery doc.
El browser bloqueaba la petición XHR como **mixed content** → página en blanco.

### Causa raíz: HSTS poisoning desde k3s

k3s ingress-nginx envía por defecto:
```
Strict-Transport-Security: max-age=7884000
```

Una vez que el browser recibía esta cabecera sobre `http://org1...`,
**forzaba automáticamente HTTPS** para todas las peticiones siguientes.
El `app.config` con URLs `http://` quedaba inutilizable.

### Solución 1: eliminar HSTS de todos los ingress k3s

```bash
kubectl annotate ingress <nombre> -n <namespace> \
  "nginx.ingress.kubernetes.io/configuration-snippet=more_clear_headers Strict-Transport-Security;" \
  --overwrite
```

Aplicado a todos los ingress: conectores, Keycloak, MinIO.

### Solución 2: app.config siempre con URLs https://

En lugar de parchear los pods a runtime, nginx sirve directamente los ficheros
`app.config.*.https.json` desde `/var/www/connector-configs/`.

```json
{
  "managementApiUrl": "https://org1.pionera.oeg.fi.upm.es/c/company/management",
  "oauth2": {
    "issuer": "https://org1.pionera.oeg.fi.upm.es/auth/realms/demo",
    "allowedUrls": "https://org1.pionera.oeg.fi.upm.es"
  }
}
```

### Solución 3: sub_filter nginx para el discovery doc de Keycloak

El OIDC discovery doc (`/.well-known/openid-configuration`) lo genera Keycloak
con URLs internas `http://auth.pionera.../`. nginx los reescribe al vuelo:

```nginx
sub_filter "http://auth.pionera.oeg.fi.upm.es/realms/" "https://org1.pionera.oeg.fi.upm.es/auth/realms/";
sub_filter "http://org1.pionera.oeg.fi.upm.es/auth/"   "https://org1.pionera.oeg.fi.upm.es/auth/";
```

### Solución 4: server block único en puerto 80

Error inicial: server blocks separados para HTTP (puerto 80) y HTTPS (puerto 443).
El problema: el host KVM reenvía **todo** a `192.168.49.2:80` (HTTP puro).
El server block HTTPS en el 443 nunca era alcanzado por el tráfico del browser.

Solución: un único server block que escucha tanto en 80 como en 443, y sirve
siempre los ficheros HTTPS independientemente del puerto de entrada.

---

## 8. Keycloak, OIDC e issuer JWT

### Cookie AUTH_SESSION_ID y proxy_cookie_path

Keycloak establece `AUTH_SESSION_ID` con `Path=/realms/demo/`.
El browser accede a Keycloak por `/auth/realms/demo/...`.
Como `/auth/realms/demo/` no empieza por `/realms/demo/`, el browser
no enviaba la cookie → Keycloak respondía `cookie_not_found`.

Solución en nginx:
```nginx
proxy_cookie_path /realms/ /auth/realms/;
```
Reescribe el `Path` de la cookie de `/realms/demo/` a `/auth/realms/demo/`.

### Playwright y cookie Secure

Keycloak 24+ establece `AUTH_SESSION_ID` con flag `Secure;SameSite=None`.
Playwright usa HTTP interno → el browser no envía cookies `Secure` por HTTP.

Solución: anotación del ingress de Keycloak en k3s:
```
nginx.ingress.kubernetes.io/configuration-snippet:
  proxy_cookie_flags AUTH_SESSION_ID nosecure samesite=lax;
```
Aplicada automáticamente por el framework en Level 2.

---

## 9. Dataspace: por qué org1 y no org2/org3

`deployers/inesdata/deployer.config`:
```
DS_1_NAME=demo
DS_1_CONNECTORS=citycouncil,company
```

El framework crea **un solo dataspace** (`demo`) con dos conectores.
Ambos conectores viven bajo el mismo dominio `org1.pionera.oeg.fi.upm.es`
con routing por path (`/c/citycouncil/` y `/c/company/`).

`org2` y `org3` se usarían en una topología con 3 dataspaces separados
(un dominio por conector), que requeriría DNS separados y configuración
multi-dataspace no implementada aún para `vm-distributed`.

**El diseño actual es correcto para validación:** un dataspace, dos participantes,
acceso externo unificado bajo org1.

---

## 10. Configuraciones runtime críticas

Estas configuraciones solo existen a runtime en pionera40 (no están en git):

### `/etc/nginx/sites-enabled/pionera-dataspace.conf`

Gestiona todo el routing público. Debe regenerarse con
`setup-nginx-proxy.sh` si se pierde.

### `/var/www/connector-configs/app.config.*.https.json`

Servidos por nginx como respuesta a `GET /inesdata-connector-interface/assets/config/app.config.json`.
Contienen todas las URLs `https://` para los conectores.

Regenerar con:
```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  192.168.49.2 192.168.122.64 org1.pionera.oeg.fi.upm.es pionera.oeg.fi.upm.es
```

### Anotaciones ingress k3s (eliminación HSTS)

Deben estar presentes en todos los ingress de conectores y servicios comunes.
Verificar:
```bash
kubectl get ingress -A \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.annotations.nginx\.ingress\.kubernetes\.io/configuration-snippet}{"\n"}{end}'
```

---

## 11. Credenciales

| Servicio | URL | Usuario | Contraseña |
|----------|-----|---------|------------|
| Conector City Council | `/c/citycouncil/inesdata-connector-interface/` | `user-conn-citycouncil-demo` | ver `credentials-connector-conn-citycouncil-demo.json` |
| Conector Company | `/c/company/inesdata-connector-interface/` | `user-conn-company-demo` | ver `credentials-connector-conn-company-demo.json` |
| Keycloak Admin | `/auth/admin/demo/console/` | `admin` | `KC_PASSWORD` en `deployer.config` |
| MinIO | `/s3-console/` | `admin` | `MINIO_PASSWORD` en `deployer.config` |

Ficheros de credenciales generados por el framework:
```
deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-citycouncil-demo.json
deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-company-demo.json
```

---

## 12. Problemas resueltos y soluciones

| Problema | Causa | Solución |
|----------|-------|----------|
| Página en blanco — mixed content | `app.config` con URLs `http://` en página HTTPS | Servir `app.config.*.https.json` desde nginx |
| HSTS poisoning | k3s ingress-nginx envía `Strict-Transport-Security` | Anotar ingress con `more_clear_headers Strict-Transport-Security` |
| `cookie_not_found` en Keycloak | Cookie `AUTH_SESSION_ID` con `Path=/realms/` incompatible con prefijo `/auth/` | `proxy_cookie_path /realms/ /auth/realms/` en nginx |
| Discovery doc OIDC con `http://` | Keycloak genera URLs internas con hostname interno | `sub_filter` nginx reescribe al vuelo |
| Server HTTPS no alcanzable | Host KVM reenvía por puerto 80, no 443 | Server block único en 80 y 443 |
| nginx devuelve 404 en todo | k3s ServiceLB intercepta `:80/:443` antes de nginx | Cambiar ingress-nginx a `NodePort` |
| Playwright `cookie_not_found` | Cookie `Secure` no enviado por HTTP | Anotación ingress `proxy_cookie_flags AUTH_SESSION_ID nosecure` |
| Conector company duplicado en pionera20 | Release Helm residual del despliegue antiguo single-VM | `helm uninstall conn-company-demo-demo -n demo` en pionera20 |
