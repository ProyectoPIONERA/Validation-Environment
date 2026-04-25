# Acceso externo a los conectores del entorno PIONERA

**Documento técnico para el equipo**  
Fecha: 2026-04-25

---

## Situación actual

El entorno de validación PIONERA está desplegado en una máquina virtual (VM) con IP pública `138.100.15.165`. Dentro de esa VM corre **Minikube**, que es un clúster Kubernetes local. Todos los servicios (conectores, Keycloak, MinIO, etc.) están dentro de Minikube en la red interna `192.168.49.2`.

El problema es que esa red interna **no es accesible desde fuera de la VM**. Los dominios que usan los servicios (`conn-citycouncil-demo.pionera.oeg.fi.upm.es`, `auth.pionera.oeg.fi.upm.es`, etc.) actualmente no resuelven nada en el DNS de la UPM — devuelven `NXDOMAIN`.

### Diagrama del estado actual

```
[PC del usuario]                  [VM pública]               [Minikube interno]
     │                            138.100.15.165              192.168.49.2
     │                                  │                           │
     │  DNS: *.pionera.oeg.fi.upm.es    │                           │
     │  → NO RESUELVE ❌                │                           │
     │                                  │                           │
     │  Aunque resolviese:              │                           │
     │──────────:80 ───────────────────▶│  puerto 80 no expuesto ❌ │
     │                                  │                           │
     │  (Solo desde dentro de la VM):   │──────:80 ────────────────▶│ ✅ funciona
```

---

## Qué se necesita para que funcione

Son **dos cambios independientes**, uno técnico y uno administrativo.

---

### Cambio 1 — Abrir el tráfico en la VM (técnico, ~5 minutos)

La VM tiene IP forwarding activado (`ip_forward=1`) y tiene instalado el nginx ingress controller de Kubernetes. Solo falta una regla **iptables DNAT** que redirija el tráfico entrante del puerto 80 hacia Minikube:

```bash
sudo iptables -t nat -A PREROUTING -d 138.100.15.165 -p tcp --dport 80 -j DNAT --to-destination 192.168.49.2:80
sudo iptables -t nat -A POSTROUTING -d 192.168.49.2 -j MASQUERADE
```

**¿Por qué funciona sin tocar el Ingress de Kubernetes?**

El Ingress de Kubernetes (nginx ingress controller) ya está configurado correctamente con todos los hostnames. Cuando llega una petición HTTP, lee la cabecera `Host:` y la enruta al servicio correcto. La regla iptables solo hace que el tráfico llegue a él — el header `Host` se preserva intacto durante el DNAT.

```
[PC usuario]
  → petición HTTP a 138.100.15.165:80
    con cabecera: Host: conn-citycouncil-demo.pionera.oeg.fi.upm.es

[VM - iptables DNAT]
  → redirige a 192.168.49.2:80
    cabecera Host se mantiene igual ✅

[Minikube - nginx ingress]
  → lee Host: conn-citycouncil-demo.pionera.oeg.fi.upm.es
  → enruta al pod correcto ✅
```

Para que la regla **persista tras reinicios**, hay que guardarla:

```bash
sudo apt install iptables-persistent -y
sudo netfilter-persistent save
```

---

### Cambio 2 — Registro DNS wildcard en la UPM (administrativo)

El DNS de la UPM (`chita.fi.upm.es`, gestionado por `hostmaster.fi.upm.es`) ya tiene el registro raíz:

```
pionera.oeg.fi.upm.es    IN  A  138.100.15.165   ✅ existe
```

Falta añadir un **único registro wildcard**:

```
*.pionera.oeg.fi.upm.es  IN  A  138.100.15.165   ❌ no existe
```

Esto resolvería automáticamente **todos** los subdominios:
- `conn-citycouncil-demo.pionera.oeg.fi.upm.es → 138.100.15.165`
- `conn-company-demo.pionera.oeg.fi.upm.es → 138.100.15.165`
- `auth.pionera.oeg.fi.upm.es → 138.100.15.165`
- `minio.pionera.oeg.fi.upm.es → 138.100.15.165`
- `registration-service-demo.pionera.oeg.fi.upm.es → 138.100.15.165`
- (cualquier subdominio futuro también)

**Acción**: Enviar solicitud a `hostmaster.fi.upm.es` pidiendo añadir el registro wildcard.

---

## Flujo completo con los dos cambios aplicados

```
[Browser en red UPM]

  1. Escribe: http://conn-citycouncil-demo.pionera.oeg.fi.upm.es
  
  2. DNS UPM resuelve: 138.100.15.165
     (gracias al wildcard *.pionera.oeg.fi.upm.es)

  3. Browser manda petición HTTP a 138.100.15.165:80
     con cabecera Host: conn-citycouncil-demo.pionera.oeg.fi.upm.es

  4. VM recibe en :80, iptables redirige a 192.168.49.2:80
     (cabecera Host intacta)

  5. Nginx ingress de Minikube lee la cabecera Host
     → enruta al pod conn-citycouncil-demo ✅

  6. Usuario ve la interfaz del conector ✅
```

---

## Servicios accesibles (URLs definitivas)

> Accesibles desde cualquier PC en red UPM o VPN, sin modificar `/etc/hosts`.

| URL | Servicio |
|-----|----------|
| `https://org1.pionera.oeg.fi.upm.es/c/citycouncil/inesdata-connector-interface/` | Interfaz conector City Council |
| `https://org1.pionera.oeg.fi.upm.es/c/company/inesdata-connector-interface/` | Interfaz conector Company |
| `https://org1.pionera.oeg.fi.upm.es/auth/` | Keycloak (autenticación) |
| `https://org1.pionera.oeg.fi.upm.es/auth/admin/demo/console/` | Consola admin Keycloak |
| `https://org1.pionera.oeg.fi.upm.es/s3-console/` | Consola MinIO (almacenamiento) |
| `https://org1.pionera.oeg.fi.upm.es/rs-demo/` | Servicio de registro del dataspace |

### Credenciales de acceso a los conectores

| Conector | Usuario | Contraseña |
|----------|---------|------------|
| City Council | `user-conn-citycouncil-demo` | `skaEFXy1XaPgrek*` |
| Company | `user-conn-company-demo` | `XMSi1tr*vl*30bjo` |
| Keycloak admin | `admin` | `change-me` |

---

## Resumen de acciones

| # | Acción | Responsable | Tiempo estimado |
|---|--------|-------------|-----------------|
| 1 | Ejecutar reglas iptables en la VM y hacer persistentes | Administrador VM | 5 minutos |
| 2 | Enviar solicitud a `hostmaster.fi.upm.es` para añadir `*.pionera.oeg.fi.upm.es IN A 138.100.15.165` | Equipo PIONERA | 5 min solicitud / días para respuesta |
| 3 | Verificar acceso desde un PC externo a la VM | Cualquiera del equipo | Tras propagación DNS (~24h) |

---

## Nota sobre soluciones alternativas evaluadas

| Solución | Viable | Motivo descarte |
|----------|--------|-----------------|
| SSH tunnel | ✅ pero manual | Requiere configuración en cada PC cliente |
| `/etc/hosts` en cada PC | ✅ pero manual | No escala a todos los usuarios UPM |
| ngrok / Cloudflare Tunnel | ✅ | Cambia las URLs, no usa `*.pionera.oeg.fi.upm.es` |
| **iptables DNAT + DNS wildcard** | ✅ **RECOMENDADO** | Transparente para el usuario, URLs estables |
