# Acceso externo a los conectores del entorno PIONERA

**Documento técnico para el equipo**
Última actualización: 2026-04-30

---

## Situación actual

El entorno de validación PIONERA está desplegado en una máquina virtual (VM) con IP interna `192.168.122.64`, accesible a través del hipervisor KVM en `138.100.15.165`. Dentro de la VM corre **k3s**, un clúster Kubernetes ligero. Todos los servicios (conectores, Keycloak, MinIO, etc.) están dentro de k3s.

El dominio `org1.pionera.oeg.fi.upm.es` resuelve a `138.100.15.165`. El hipervisor tiene un nginx que reenvía el tráfico a la VM.

---

## Arquitectura de red

```
[Browser en red UPM/VPN]
    │
    │  HTTPS → org1.pionera.oeg.fi.upm.es
    │  DNS: org1.pionera.oeg.fi.upm.es → 138.100.15.165
    ▼
[Hipervisor KVM 138.100.15.165]
    │  nginx proxy → 192.168.122.64:443
    ▼
[VM nginx 192.168.122.64:443 / :80]
    │  Termina TLS (certificado autofirmado)
    │  Reescribe rutas: /auth/ → /realms/, /c/<conn>/ → /
    │  proxy_pass → http://192.168.122.64:31667
    ▼
[k3s ingress-nginx NodePort :31667]
    │  Lee cabecera Host: para enrutar
    ▼
[Pods k3s: Keycloak, MinIO, Conectores, Registration Service]
```

### Por qué NodePort y no LoadBalancer

k3s incluye ServiceLB: cuando un servicio es de tipo `LoadBalancer`, k3s asigna
automáticamente la IP de la VM (`192.168.122.64`) como IP del load balancer y crea
reglas `KUBE-EXT` en iptables que interceptan el tráfico al puerto 80/443 antes de
que llegue al nginx de la VM. Esto impide que el nginx escuche en esos puertos.

La solución es configurar el servicio `ingress-nginx-controller` como `NodePort`.
Así kube-proxy no crea reglas para los puertos 80/443, el nginx de la VM puede
escuchar en ellos, y el nginx reenvía al NodePort de k3s (31667 para HTTP,
32079 para HTTPS).

El framework aplica este cambio automáticamente en Level 1 mediante
`patch_ingress_external_ip()` en `adapters/inesdata/infrastructure.py`.

---

## Cookie de sesión Keycloak y proxy_cookie_path

Keycloak establece la cookie `AUTH_SESSION_ID` con `Path=/realms/demo/`. Sin
embargo, el nginx de la VM expone Keycloak bajo el prefijo `/auth/`, por lo que
la URL en el browser es `/auth/realms/demo/...`.

El navegador solo envía una cookie si la ruta de la petición comienza con el
`Path` de la cookie. Como `/auth/realms/demo/...` no comienza con `/realms/demo/`,
el browser envía la cookie de una sesión antigua (expirada) y Keycloak responde
con `cookie_not_found`.

La solución es `proxy_cookie_path /realms/ /auth/realms/;` en el bloque
`location /auth/` del nginx de la VM. Esto reescribe el `Path` de la cookie de
`/realms/demo/` a `/auth/realms/demo/`, y el browser envía la cookie correcta.

Esta directiva está incluida en `setup-nginx-proxy.sh` y se aplica automáticamente.

---

## URLs de acceso

> Accesibles desde cualquier PC en red UPM o VPN, sin modificar `/etc/hosts`.

| URL | Servicio |
|-----|----------|
| `https://org1.pionera.oeg.fi.upm.es/c/citycouncil/inesdata-connector-interface/` | Interfaz conector City Council |
| `https://org1.pionera.oeg.fi.upm.es/c/company/inesdata-connector-interface/` | Interfaz conector Company |
| `https://org1.pionera.oeg.fi.upm.es/auth/` | Keycloak (autenticación) |
| `https://org1.pionera.oeg.fi.upm.es/auth/admin/demo/console/` | Consola admin Keycloak |
| `https://org1.pionera.oeg.fi.upm.es/s3-console/` | Consola MinIO (almacenamiento) |
| `https://org1.pionera.oeg.fi.upm.es/rs-demo/` | Servicio de registro del dataspace |

### Credenciales

| Servicio | Usuario | Contraseña |
|----------|---------|------------|
| Conector City Council | `user-conn-citycouncil-demo` | ver `credentials-connector-conn-citycouncil-demo.json` → `connector_user.passwd` |
| Conector Company | `user-conn-company-demo` | ver `credentials-connector-conn-company-demo.json` → `connector_user.passwd` |
| Keycloak admin | `admin` | `change-me` |
| MinIO | `admin` | `change-me` |

Los ficheros de credenciales están en:

```text
deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-citycouncil-demo.json
deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-company-demo.json
```

---

## Configuración manual del proxy (si se necesita re-ejecutar)

```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  192.168.49.2 192.168.122.64 org1.pionera.oeg.fi.upm.es pionera.oeg.fi.upm.es
```

El script detecta k3s automáticamente y configura el backend como NodePort.

---

## Diagnóstico rápido

```bash
# Verificar que nginx escucha en los puertos correctos
sudo ss -tlnp | grep nginx

# Verificar que NO hay reglas KUBE-EXT para :80/:443
sudo iptables -t nat -L KUBE-SERVICES -n | grep "192.168.122.64"

# Verificar que ingress-nginx es NodePort
sudo k3s kubectl get svc ingress-nginx-controller -n ingress-nginx

# Test directo del proxy
curl -sk -H "Host: org1.pionera.oeg.fi.upm.es" https://192.168.122.64/ | grep -o "<h1>.*</h1>"

# Test ruta conector
curl -sk -o /dev/null -w "%{http_code}" \
  -H "Host: org1.pionera.oeg.fi.upm.es" \
  "https://192.168.122.64/c/citycouncil/inesdata-connector-interface/"
```

---

## Resumen de problemas conocidos y soluciones

| Problema | Causa | Solución |
|----------|-------|----------|
| nginx devuelve 404 en todos los paths | k3s ServiceLB intercepta :80/:443 con `KUBE-EXT` iptables antes de nginx | Cambiar ingress-nginx a `NodePort` |
| `cookie_not_found` en login Keycloak | Cookie `AUTH_SESSION_ID` con `Path=/realms/demo/` no coincide con URL `/auth/realms/demo/` | `proxy_cookie_path /realms/ /auth/realms/;` en nginx |
| `AUTH_SESSION_ID Secure` bloquea tests Playwright (HTTP) | Keycloak 24+ fuerza `Secure;SameSite=None` | `proxy_cookie_flags AUTH_SESSION_ID nosecure samesite=lax` en anotación del ingress k3s |
