#!/usr/bin/env python3

"""
NIVEL 9 – Portal Público (FASE LÓGICA)

Responsabilidades:
- Verificar precondiciones
- Normalizar values-demo.yaml
- Garantizar alias DNS cross-namespace (ExternalName)
- Idempotente
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

ROOT = Path(__file__).resolve().parents[3]
STEP2_DIR = ROOT / "runtime/workdir/inesdata-deployment/dataspace/step-2"
VALUES_FILE = STEP2_DIR / "values-demo.yaml"

NAMESPACE = "demo"
POSTGRES_ALIAS_NAME = "common-srvs-postgresql"
POSTGRES_FQDN = "common-srvs-postgresql.common-srvs.svc"

# =============================================================================
# UTILIDADES
# =============================================================================

def header(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

def run(cmd, check=True):
    return subprocess.run(cmd, check=check)

def run_output(cmd):
    return subprocess.check_output(cmd, text=True).strip()

def backup(path: Path):
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_suffix(path.suffix + f".backup.{ts}")
    backup_path.write_text(path.read_text())
    return backup_path

# =============================================================================
# FASE 1 – PRECONDICIONES
# =============================================================================

def check_preconditions():
    header("NIVEL 9 – Verificación de precondiciones")

    if not VALUES_FILE.exists():
        print("❌ values-demo.yaml no encontrado")
        sys.exit(1)

    deployments = run_output([
        "kubectl", "get", "deploy",
        "-n", NAMESPACE,
        "-o", "jsonpath={.items[*].metadata.name}"
    ])

    connectors = [d for d in deployments.split() if d.startswith("conn-")]

    if not connectors:
        print("❌ No se detectó ningún connector en namespace demo")
        sys.exit(1)

    connector_name = connectors[0]
    print(f"✓ Connector detectado: {connector_name}")

    return connector_name

# =============================================================================
# FASE 2 – NORMALIZACIÓN VALUES
# =============================================================================

def normalize(connector_name):
    header("NIVEL 9 – Normalización values-demo.yaml")

    bkp = backup(VALUES_FILE)
    if bkp:
        print(f"✓ Backup creado: {bkp}")

    content = VALUES_FILE.read_text()
    original_content = content

    content = content.replace(
        POSTGRES_ALIAS_NAME,
        POSTGRES_FQDN
    )

    content = content.replace(
        "CHANGEME-conn-NAME-demo",
        connector_name
    )

    if "CHANGEME" in content:
        print("❌ Persisten valores CHANGEME")
        sys.exit(1)

    if content != original_content:
        VALUES_FILE.write_text(content)
        print("✓ values-demo.yaml normalizado")
    else:
        print("✓ values-demo.yaml ya normalizado")

# =============================================================================
# FASE 3 – GARANTÍA DE ALIAS DNS
# =============================================================================

def ensure_postgres_alias():
    header("NIVEL 9 – Garantía alias DNS cross-namespace")

    try:
        existing = run_output([
            "kubectl", "get", "service",
            POSTGRES_ALIAS_NAME,
            "-n", NAMESPACE,
            "-o", "jsonpath={.spec.externalName}"
        ])

        if existing == POSTGRES_FQDN:
            print("✓ Alias DNS ya existe y es correcto")
            return
        else:
            print("❌ Alias existe pero apunta a otro destino")
            sys.exit(1)

    except subprocess.CalledProcessError:
        print("→ Alias no existe. Creando...")

        yaml_content = f"""
apiVersion: v1
kind: Service
metadata:
  name: {POSTGRES_ALIAS_NAME}
  namespace: {NAMESPACE}
spec:
  type: ExternalName
  externalName: {POSTGRES_FQDN}
"""

        proc = subprocess.Popen(
            ["kubectl", "apply", "-f", "-"],
            stdin=subprocess.PIPE,
            text=True
        )
        proc.communicate(yaml_content)

        if proc.returncode != 0:
            print("❌ Error creando alias DNS")
            sys.exit(1)

        print("✓ Alias DNS creado correctamente")

# =============================================================================
# MAIN
# =============================================================================

def main():
    connector = check_preconditions()
    normalize(connector)
    ensure_postgres_alias()

    header("NIVEL 9 – FASE LÓGICA COMPLETADA")
    print("✔ values coherente")
    print("✔ Alias DNS garantizado")
    print("➡ Ejecutar portal-deploy.py")

if __name__ == "__main__":
    main()
