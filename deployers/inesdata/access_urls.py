"""Pure INESData access URL helpers.

These helpers are intentionally free from CLI/bootstrap dependencies so they
can be reused by the menu, previews and tests without requiring optional
packages such as ``click``.
"""

from urllib.parse import urlparse


URL_DEV = ".dev.ds.dataspaceunit.upm"


def clean_hostname(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    parsed = urlparse(raw_value)
    if parsed.netloc:
        return parsed.netloc
    if "://" not in raw_value:
        return raw_value.split("/", 1)[0]
    return ""


def normalize_base_href(value):
    base_href = str(value or "/edc-dashboard/").strip() or "/edc-dashboard/"
    if not base_href.startswith("/"):
        base_href = f"/{base_href}"
    if not base_href.endswith("/"):
        base_href = f"{base_href}/"
    return base_href


def access_protocol(environment):
    return "https" if str(environment or "").strip().upper() == "PRO" else "http"


def dataspace_domain_base(config, environment):
    if str(environment or "").strip().upper() == "PRO":
        return "ds.dataspaceunit-project.eu"
    configured = str(config.get("DS_DOMAIN_BASE", "")).strip()
    return configured or URL_DEV.lstrip(".")


def build_dataspace_access_urls(dataspace, environment, config):
    protocol = access_protocol(environment)
    ds_domain = dataspace_domain_base(config, environment)
    urls = {
        "public_portal_login": f"{protocol}://{dataspace}.{ds_domain}",
        "public_portal_backend_admin": f"{protocol}://backend-{dataspace}.{ds_domain}/admin",
        "registration_service": f"{protocol}://registration-service-{dataspace}.{ds_domain}",
    }
    urls.update(common_access_urls(dataspace, environment, config))
    return urls


def build_connector_access_urls(connector, dataspace, environment, config, dashboard=False):
    protocol = access_protocol(environment)
    ds_domain = dataspace_domain_base(config, environment)
    connector_base = f"{protocol}://{connector}.{ds_domain}"
    connector_interface_base_href = normalize_base_href(
        config.get("INESDATA_CONNECTOR_INTERFACE_BASE_HREF", "/inesdata-connector-interface/")
    )
    urls = {
        "connector_ingress": connector_base,
        "connector_interface_login": f"{connector_base}{connector_interface_base_href}",
        "connector_management_api": f"{connector_base}/management",
        "connector_protocol_api": f"{connector_base}/protocol",
        "connector_shared_api": f"{connector_base}/shared",
        "minio_bucket": f"{dataspace}-{connector}",
    }
    if dashboard:
        dashboard_base_href = normalize_base_href(config.get("EDC_DASHBOARD_BASE_HREF", "/edc-dashboard/"))
        urls["edc_dashboard_login"] = f"{connector_base}{dashboard_base_href}"
        if str(config.get("EDC_DASHBOARD_PROXY_AUTH_MODE", "")).strip().lower() == "oidc-bff":
            urls["edc_dashboard_oidc_login"] = f"{connector_base}/edc-dashboard-api/auth/login"
    urls.update(common_access_urls(dataspace, environment, config))
    return urls


def common_access_urls(dataspace, environment, config):
    protocol = access_protocol(environment)
    domain_base = str(config.get("DOMAIN_BASE", "dev.ed.dataspaceunit.upm")).strip() or "dev.ed.dataspaceunit.upm"
    keycloak_hostname = (
        clean_hostname(config.get("KEYCLOAK_HOSTNAME"))
        or clean_hostname(config.get("KC_INTERNAL_URL"))
        or f"keycloak.{domain_base}"
    )
    keycloak_admin_hostname = (
        clean_hostname(config.get("KEYCLOAK_ADMIN_HOSTNAME"))
        or clean_hostname(config.get("KC_URL"))
        or f"keycloak-admin.{domain_base}"
    )
    minio_api_hostname = (
        clean_hostname(config.get("MINIO_HOSTNAME"))
        or clean_hostname(config.get("MINIO_ENDPOINT"))
        or f"minio.{domain_base}"
    )
    minio_console_hostname = (
        clean_hostname(config.get("MINIO_CONSOLE_HOSTNAME"))
        or f"console.minio-s3.{domain_base}"
    )
    return {
        "keycloak_realm": f"{protocol}://{keycloak_hostname}/realms/{dataspace}",
        "keycloak_account": f"{protocol}://{keycloak_hostname}/realms/{dataspace}/account",
        "keycloak_admin_console": f"{protocol}://{keycloak_admin_hostname}/admin/{dataspace}/console/",
        "minio_api": f"{protocol}://{minio_api_hostname}",
        "minio_console": f"{protocol}://{minio_console_hostname}",
    }


def dataspace_index(config, dataspace_name, dataspace_namespace=None):
    target_name = str(dataspace_name or "").strip()
    target_namespace = str(dataspace_namespace or "").strip()
    index = 1

    while True:
        configured_name = str(config.get(f"DS_{index}_NAME", "") or "").strip()
        configured_namespace = str(config.get(f"DS_{index}_NAMESPACE", "") or configured_name).strip()
        if not configured_name:
            break
        if target_name and configured_name == target_name:
            return index
        if target_namespace and configured_namespace == target_namespace:
            return index
        index += 1

    return 1


def registration_service_namespace(config, dataspace_name, dataspace_namespace=None):
    resolved_namespace = str(dataspace_namespace or dataspace_name or "").strip() or str(dataspace_name or "").strip()
    index = dataspace_index(config, dataspace_name, dataspace_namespace)
    configured = str(config.get(f"DS_{index}_REGISTRATION_NAMESPACE", "") or "").strip()
    if configured:
        return configured

    profile = str(config.get("NAMESPACE_PROFILE", "compact") or "compact").strip().lower().replace("_", "-")
    if profile in {"role-aligned", "rolealigned", "aligned", "roles"}:
        return f"{dataspace_name}-core"

    return resolved_namespace


def registration_service_internal_hostname(
    config,
    dataspace_name,
    environment,
    *,
    connector_namespace=None,
    dataspace_namespace=None,
):
    if str(environment or "").strip().upper() == "PRO":
        return f"registration-service-{dataspace_name}.ds.dataspaceunit-project.eu"

    index = dataspace_index(config, dataspace_name, dataspace_namespace)
    resolved_dataspace_namespace = (
        str(dataspace_namespace or "").strip()
        or str(config.get(f"DS_{index}_NAMESPACE", "") or "").strip()
        or str(dataspace_name or "").strip()
    )
    resolved_connector_namespace = str(connector_namespace or resolved_dataspace_namespace).strip() or resolved_dataspace_namespace
    resolved_registration_namespace = registration_service_namespace(
        config,
        dataspace_name,
        resolved_dataspace_namespace,
    )
    service_name = f"{dataspace_name}-registration-service"
    if resolved_registration_namespace and resolved_registration_namespace != resolved_connector_namespace:
        return f"{service_name}.{resolved_registration_namespace}.svc.cluster.local:8080"
    return f"{service_name}:8080"
