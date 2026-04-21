import json
import math
import os
import time
import uuid
from datetime import datetime
from itertools import permutations

import requests


class KafkaDataAddressUnsupported(RuntimeError):
    """Raised when the deployed connector does not accept Kafka data addresses."""


class KafkaEdcValidationSuite:
    """Validate an end-to-end EDC + Kafka transfer flow."""

    EDC_NAMESPACE = "https://w3id.org/edc/v0.0.1/ns/"
    KAFKA_EDC_ASSET_PREFIX = "kafka-edc-asset-"
    KAFKA_EDC_POLICY_PREFIX = "kafka-edc-policy-"
    KAFKA_EDC_CONTRACT_PREFIX = "kafka-edc-contract-"
    DEFAULT_MESSAGE_COUNT = 10
    DEFAULT_NEGOTIATION_TIMEOUT_SECONDS = 60
    DEFAULT_TRANSFER_TIMEOUT_SECONDS = 60
    DEFAULT_EDR_TIMEOUT_SECONDS = 30
    DEFAULT_POLL_INTERVAL_SECONDS = 3
    DEFAULT_CONSUMER_POLL_TIMEOUT_SECONDS = 30
    DEFAULT_STARTUP_GRACE_SECONDS = 60
    DEFAULT_PRE_RUN_SETTLE_SECONDS = 10
    DEFAULT_LOGIN_ATTEMPTS = 3
    DEFAULT_LOGIN_RETRY_SECONDS = 2
    DEFAULT_REQUEST_ATTEMPTS = 3
    DEFAULT_REQUEST_RETRY_SECONDS = 2
    DEFAULT_PAIR_ATTEMPTS = 2
    DEFAULT_PAIR_RETRY_SECONDS = 5

    def __init__(
        self,
        load_connector_credentials=None,
        load_deployer_config=None,
        kafka_runtime_loader=None,
        ensure_kafka_topic=None,
        kafka_manager=None,
        experiment_storage=None,
        ds_domain_resolver=None,
        ds_name_loader=None,
        admin_client_class=None,
        new_topic_class=None,
        producer_class=None,
        consumer_class=None,
        session=None,
        time_provider=None,
        uuid_factory=None,
    ):
        self.load_connector_credentials = load_connector_credentials
        self.load_deployer_config = load_deployer_config
        self.kafka_runtime_loader = kafka_runtime_loader
        self.ensure_kafka_topic = ensure_kafka_topic
        self.kafka_manager = kafka_manager
        self.experiment_storage = experiment_storage
        self.ds_domain_resolver = ds_domain_resolver
        self.ds_name_loader = ds_name_loader
        self.admin_client_class = admin_client_class
        self.new_topic_class = new_topic_class
        self.producer_class = producer_class
        self.consumer_class = consumer_class
        self.session = session
        self.time_provider = time_provider or self._default_time_provider
        self.uuid_factory = uuid_factory or (lambda: str(uuid.uuid4()))

    @staticmethod
    def _default_time_provider():
        return time.perf_counter_ns() / 1_000_000.0

    def _require_dependency(self, dependency, name):
        if dependency is None:
            raise RuntimeError(f"KafkaEdcValidationSuite requires dependency: {name}")
        return dependency

    def _load_deployer_values(self):
        loader = self._require_dependency(self.load_deployer_config, "load_deployer_config")
        values = loader() or {}
        if not isinstance(values, dict):
            return {}
        return values

    def _load_kafka_runtime(self):
        runtime = {}
        if callable(self.kafka_runtime_loader):
            loaded = self.kafka_runtime_loader() or {}
            if isinstance(loaded, dict):
                runtime.update(loaded)

        deployer = self._load_deployer_values()
        optional_mapping = {
            "message_count": "KAFKA_EDC_MESSAGE_COUNT",
            "negotiation_timeout_seconds": "KAFKA_EDC_NEGOTIATION_TIMEOUT_SECONDS",
            "transfer_timeout_seconds": "KAFKA_EDC_TRANSFER_TIMEOUT_SECONDS",
            "edr_timeout_seconds": "KAFKA_EDC_EDR_TIMEOUT_SECONDS",
            "poll_interval_seconds": "KAFKA_EDC_POLL_INTERVAL_SECONDS",
            "consumer_poll_timeout_seconds": "KAFKA_EDC_CONSUMER_POLL_TIMEOUT_SECONDS",
            "consumer_group_prefix": "KAFKA_EDC_CONSUMER_GROUP_PREFIX",
            "cluster_bootstrap_servers": "KAFKA_CLUSTER_BOOTSTRAP_SERVERS",
            "startup_grace_seconds": "KAFKA_EDC_STARTUP_GRACE_SECONDS",
            "pre_run_settle_seconds": "KAFKA_EDC_PRE_RUN_SETTLE_SECONDS",
        }
        for key, config_key in optional_mapping.items():
            value = deployer.get(config_key)
            if value not in (None, ""):
                runtime[key] = value

        runtime.setdefault("message_count", self.DEFAULT_MESSAGE_COUNT)
        runtime.setdefault("negotiation_timeout_seconds", self.DEFAULT_NEGOTIATION_TIMEOUT_SECONDS)
        runtime.setdefault("transfer_timeout_seconds", self.DEFAULT_TRANSFER_TIMEOUT_SECONDS)
        runtime.setdefault("edr_timeout_seconds", self.DEFAULT_EDR_TIMEOUT_SECONDS)
        runtime.setdefault("poll_interval_seconds", self.DEFAULT_POLL_INTERVAL_SECONDS)
        runtime.setdefault("consumer_poll_timeout_seconds", self.DEFAULT_CONSUMER_POLL_TIMEOUT_SECONDS)
        runtime.setdefault("consumer_group_prefix", "framework-edc-kafka")
        runtime.setdefault("startup_grace_seconds", self.DEFAULT_STARTUP_GRACE_SECONDS)
        runtime.setdefault("pre_run_settle_seconds", self.DEFAULT_PRE_RUN_SETTLE_SECONDS)

        for integer_key in (
            "message_count",
            "negotiation_timeout_seconds",
            "transfer_timeout_seconds",
            "edr_timeout_seconds",
            "poll_interval_seconds",
            "consumer_poll_timeout_seconds",
            "startup_grace_seconds",
            "pre_run_settle_seconds",
            "request_timeout_ms",
            "api_timeout_ms",
            "max_block_ms",
            "consumer_request_timeout_ms",
        ):
            raw = runtime.get(integer_key)
            if raw in (None, ""):
                continue
            try:
                runtime[integer_key] = int(raw)
            except (TypeError, ValueError):
                pass
        return runtime

    @staticmethod
    def _normalize_bootstrap_servers(bootstrap_servers):
        if bootstrap_servers is None:
            return []
        if isinstance(bootstrap_servers, (list, tuple, set)):
            values = bootstrap_servers
        else:
            values = str(bootstrap_servers).split(",")
        return [value.strip() for value in values if str(value).strip()]

    @staticmethod
    def _split_host_port(address):
        raw = str(address or "").strip()
        if not raw:
            return "", ""
        if "://" in raw:
            raw = raw.split("://", 1)[1]
        if raw.startswith("[") and "]:" in raw:
            host, _, port = raw.rpartition(":")
            return host.strip("[]"), port
        if raw.count(":") >= 1:
            host, port = raw.rsplit(":", 1)
            return host, port
        return raw, ""

    @classmethod
    def _derive_cluster_bootstrap_servers(cls, bootstrap_servers):
        derived = []
        for candidate in cls._normalize_bootstrap_servers(bootstrap_servers):
            host, port = cls._split_host_port(candidate)
            normalized_host = host.strip().lower()
            if normalized_host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
                for alias in ("host.minikube.internal", "host.docker.internal"):
                    value = f"{alias}:{port}" if port else alias
                    if value not in derived:
                        derived.append(value)
            elif candidate not in derived:
                derived.append(candidate)
        return ",".join(derived)

    def _ds_domain(self):
        resolver = self._require_dependency(self.ds_domain_resolver, "ds_domain_resolver")
        return resolver()

    def _dataspace_name(self):
        if callable(self.ds_name_loader):
            return self.ds_name_loader()
        return self.ds_name_loader or "demo"

    def _login(self, connector, role_key):
        config = self._load_deployer_values()
        creds_loader = self._require_dependency(self.load_connector_credentials, "load_connector_credentials")
        connector_creds = creds_loader(connector) or {}
        connector_user = connector_creds.get("connector_user") or {}

        username = connector_user.get("user")
        password = connector_user.get("passwd")
        if not username or not password:
            raise RuntimeError(f"Missing connector_user credentials for {connector}")

        keycloak_url = config.get("KC_INTERNAL_URL") or config.get("KC_URL")
        if not keycloak_url:
            raise RuntimeError("Missing KC_INTERNAL_URL/KC_URL in deployer.config")
        if not keycloak_url.startswith("http"):
            keycloak_url = f"http://{keycloak_url}"

        login_url = f"{keycloak_url}/realms/{self._dataspace_name()}/protocol/openid-connect/token"
        payload = {
            "grant_type": "password",
            "client_id": "dataspace-users",
            "username": username,
            "password": password,
            "scope": "openid profile email",
        }
        attempts = self.DEFAULT_LOGIN_ATTEMPTS
        retry_seconds = self.DEFAULT_LOGIN_RETRY_SECONDS
        last_exc = None

        for attempt in range(1, attempts + 1):
            try:
                response = self._session().post(
                    login_url,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data=payload,
                    timeout=20,
                )
                self._assert_status(response, {200}, f"{role_key} login")
                body = response.json()
                token = body.get("access_token")
                if not token:
                    raise RuntimeError(f"{role_key} login did not return access_token")
                return token
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts:
                    raise
                time.sleep(retry_seconds)

        raise last_exc or RuntimeError(f"{role_key} login failed unexpectedly")

    def _session(self):
        return self.session or requests.Session()

    @staticmethod
    def _read_field(obj, field_name):
        if not isinstance(obj, dict):
            return None
        namespaced = f"https://w3id.org/edc/v0.0.1/ns/{field_name}"
        if field_name in obj:
            return obj[field_name]
        if namespaced in obj:
            return obj[namespaced]
        properties = obj.get("properties")
        if isinstance(properties, dict):
            if field_name in properties:
                return properties[field_name]
            if namespaced in properties:
                return properties[namespaced]
        return None

    @staticmethod
    def _assert_status(response, expected_codes, label):
        if response.status_code not in set(expected_codes):
            raise RuntimeError(
                f"{label} failed with HTTP {response.status_code}: {response.text[:500]}"
            )

    @staticmethod
    def _is_transient_http_response(response):
        return getattr(response, "status_code", None) in {502, 503, 504}

    def _request_with_retry(self, method, url, *, label, accepted_statuses=None, headers=None, json_payload=None, data=None):
        attempts = max(int(self.DEFAULT_REQUEST_ATTEMPTS), 1)
        retry_seconds = max(int(self.DEFAULT_REQUEST_RETRY_SECONDS), 1)
        session = self._session()
        last_exc = None

        for attempt in range(1, attempts + 1):
            try:
                request_fn = getattr(session, method)
                kwargs = {
                    "headers": headers,
                    "timeout": 30,
                }
                if json_payload is not None:
                    kwargs["json"] = json_payload
                if data is not None:
                    kwargs["data"] = data
                response = request_fn(url, **kwargs)
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                if attempt >= attempts:
                    raise
                time.sleep(retry_seconds)
                continue

            if accepted_statuses and response.status_code in set(accepted_statuses):
                return response
            if self._is_transient_http_response(response) and attempt < attempts:
                time.sleep(retry_seconds)
                continue
            return response

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"{label} did not produce a response")

    def _management_url(self, connector, path):
        return f"http://{connector}.{self._ds_domain()}{path}"

    def _protocol_address(self, connector):
        return f"http://{connector}:19194/protocol"

    def _post_json(self, url, token, payload, label):
        response = self._request_with_retry(
            "post",
            url,
            label=label,
            accepted_statuses={200, 201},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_payload=payload,
        )
        self._assert_status(response, {200, 201}, label)
        try:
            return response.json(), response.status_code
        except ValueError as exc:
            raise RuntimeError(f"{label} did not return valid JSON") from exc

    @staticmethod
    def _json_ld_value(value):
        return [{"@value": value}]

    @classmethod
    def _expanded_kafka_address(cls, topic, bootstrap_servers):
        return {
            f"{cls.EDC_NAMESPACE}type": cls._json_ld_value("Kafka"),
            f"{cls.EDC_NAMESPACE}topic": cls._json_ld_value(topic),
            f"{cls.EDC_NAMESPACE}kafka.bootstrap.servers": cls._json_ld_value(bootstrap_servers),
        }

    @staticmethod
    def _response_text(response):
        return str(getattr(response, "text", "") or "")

    @classmethod
    def _is_kafka_dataaddress_type_validation_failure(cls, response):
        if getattr(response, "status_code", None) != 400:
            return False
        body = cls._response_text(response)
        return (
            f"{cls.EDC_NAMESPACE}type" in body
            and (
                "field is not valid" in body
                or "missing or invalid" in body
                or "mandatory value" in body
            )
        )

    def _post_kafka_payload_with_expanded_fallback(
        self,
        url,
        token,
        payload,
        expanded_payload,
        label,
    ):
        response = self._request_with_retry(
            "post",
            url,
            label=label,
            accepted_statuses={200, 201, 400},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_payload=payload,
        )
        if self._is_kafka_dataaddress_type_validation_failure(response):
            response = self._request_with_retry(
                "post",
                url,
                label=f"{label} expanded JSON-LD fallback",
                accepted_statuses={200, 201, 400},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json_payload=expanded_payload,
            )
            if self._is_kafka_dataaddress_type_validation_failure(response):
                raise KafkaDataAddressUnsupported(
                    f"{label} is not supported by the deployed connector runtime: {self._response_text(response)}"
                )

        self._assert_status(response, {200, 201}, label)
        try:
            return response.json(), response.status_code
        except ValueError as exc:
            raise RuntimeError(f"{label} did not return valid JSON") from exc

    def _post_json_optional_body(self, url, token, payload, label, accepted_statuses=None):
        response = self._request_with_retry(
            "post",
            url,
            label=label,
            accepted_statuses=set(accepted_statuses or {200, 201, 204}),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_payload=payload,
        )
        self._assert_status(response, set(accepted_statuses or {200, 201, 204}), label)
        if response.status_code == 204:
            return None, response.status_code
        text = getattr(response, "text", "") or ""
        if not text.strip():
            return None, response.status_code
        try:
            return response.json(), response.status_code
        except ValueError as exc:
            raise RuntimeError(f"{label} did not return valid JSON") from exc

    def _get_json(self, url, token, label, accepted_statuses=None):
        accepted_statuses = set(accepted_statuses or {200})
        response = self._request_with_retry(
            "get",
            url,
            label=label,
            accepted_statuses=accepted_statuses,
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        self._assert_status(response, accepted_statuses, label)
        if response.status_code == 204:
            return None, response.status_code
        try:
            return response.json(), response.status_code
        except ValueError as exc:
            raise RuntimeError(f"{label} did not return valid JSON") from exc

    def _delete(self, url, token, label, accepted_statuses=None):
        accepted_statuses = set(accepted_statuses or {200, 204, 404, 409})
        response = self._request_with_retry(
            "delete",
            url,
            label=label,
            accepted_statuses=accepted_statuses,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        self._assert_status(response, accepted_statuses, label)
        return response.status_code

    def _ensure_kafka_runtime(self, runtime):
        bootstrap_servers = runtime.get("bootstrap_servers")
        kafka_manager = self.kafka_manager
        if kafka_manager is not None:
            resolved = kafka_manager.ensure_kafka_running()
            if resolved:
                runtime["bootstrap_servers"] = resolved
                bootstrap_servers = resolved

        if not bootstrap_servers:
            raise RuntimeError("Kafka bootstrap_servers not configured for EDC+Kafka validation")

        runtime["host_bootstrap_servers"] = bootstrap_servers
        cluster_bootstrap_servers = runtime.get("cluster_bootstrap_servers")
        if not cluster_bootstrap_servers and kafka_manager is not None:
            cluster_bootstrap_servers = getattr(kafka_manager, "cluster_bootstrap_servers", None)
        if not cluster_bootstrap_servers:
            cluster_bootstrap_servers = self._derive_cluster_bootstrap_servers(bootstrap_servers)
            runtime["cluster_bootstrap_servers"] = cluster_bootstrap_servers
        else:
            runtime["cluster_bootstrap_servers"] = cluster_bootstrap_servers

        return runtime

    def _load_kafka_admin_classes(self):
        if self.admin_client_class is not None and self.new_topic_class is not None:
            return self.admin_client_class, self.new_topic_class
        try:
            from kafka.admin import KafkaAdminClient, NewTopic

            return KafkaAdminClient, NewTopic
        except Exception as exc:
            raise RuntimeError(f"Kafka client library not available for EDC+Kafka validation: {exc}") from exc

    @staticmethod
    def _build_kafka_client_kwargs(runtime):
        kwargs = {
            "bootstrap_servers": runtime.get("host_bootstrap_servers") or runtime.get("bootstrap_servers"),
            "security_protocol": runtime.get("security_protocol", "PLAINTEXT"),
            "request_timeout_ms": runtime.get("request_timeout_ms", 60000),
            "api_version_auto_timeout_ms": runtime.get("api_timeout_ms", 60000),
        }
        if runtime.get("sasl_mechanism"):
            kwargs["sasl_mechanism"] = runtime.get("sasl_mechanism")
        if runtime.get("username"):
            kwargs["sasl_plain_username"] = runtime.get("username")
        if runtime.get("password"):
            kwargs["sasl_plain_password"] = runtime.get("password")
        return kwargs

    @staticmethod
    def _wait_for_topic_ready(admin_client, topic_name, timeout_seconds=15):
        deadline = time.time() + max(int(timeout_seconds), 1)
        while time.time() < deadline:
            try:
                if topic_name in admin_client.list_topics():
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _ensure_topic_with_runtime(self, runtime, topic_name):
        admin_client_class, new_topic_class = self._load_kafka_admin_classes()
        last_exc = None

        for attempt in (1, 2):
            admin_client = None
            try:
                admin_client = admin_client_class(**self._build_kafka_client_kwargs(runtime))

                try:
                    existing_topics = admin_client.list_topics()
                except Exception:
                    existing_topics = []

                if topic_name not in existing_topics:
                    topic = new_topic_class(name=topic_name, num_partitions=1, replication_factor=1)
                    try:
                        admin_client.create_topics([topic])
                    except Exception as exc:
                        if "TopicAlreadyExists" not in type(exc).__name__:
                            raise

                if not self._wait_for_topic_ready(
                    admin_client,
                    topic_name,
                    timeout_seconds=runtime.get("topic_ready_timeout_seconds", 15),
                ):
                    raise RuntimeError(f"Kafka topic '{topic_name}' could not be created or verified")
                return True
            except Exception as exc:
                last_exc = exc
                kafka_manager = self.kafka_manager
                if attempt == 1 and kafka_manager is not None:
                    stop_method = getattr(kafka_manager, "stop_kafka", None)
                    if callable(stop_method):
                        stop_method()
                    resolved_bootstrap = kafka_manager.ensure_kafka_running()
                    if resolved_bootstrap:
                        runtime["bootstrap_servers"] = resolved_bootstrap
                        runtime["host_bootstrap_servers"] = resolved_bootstrap
                    cluster_bootstrap = getattr(kafka_manager, "cluster_bootstrap_servers", None)
                    if cluster_bootstrap:
                        runtime["cluster_bootstrap_servers"] = cluster_bootstrap
                    continue
                raise
            finally:
                close_method = getattr(admin_client, "close", None) if admin_client is not None else None
                if callable(close_method):
                    try:
                        close_method()
                    except Exception:
                        pass

        raise last_exc or RuntimeError(f"Kafka topic '{topic_name}' could not be created or verified")

    def _topic_name(self, runtime):
        base_name = str(runtime.get("topic_name") or "edc-kafka-topic").strip() or "edc-kafka-topic"
        suffix = str(self.uuid_factory()).replace("_", "-").lower()
        return f"{base_name}-{suffix[:12]}"

    @staticmethod
    def _destination_topic_name(source_topic):
        return f"{source_topic}-sink"

    def _create_asset(self, provider, provider_jwt, source_topic, runtime, suffix):
        asset_id = f"kafka-edc-asset-{suffix}"
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
                "dct": "http://purl.org/dc/terms/",
                "dcat": "http://www.w3.org/ns/dcat#",
            },
            "@id": asset_id,
            "@type": "Asset",
            "properties": {
                "name": f"Kafka EDC Asset {suffix}",
                "version": "1.0.0",
                "shortDescription": "Kafka topic asset for EDC validation",
                "assetType": "dataset",
                "dct:description": "Kafka topic asset for end-to-end EDC validation",
                "dcat:keyword": ["validation", "edc", "kafka"],
            },
            "dataAddress": {
                "type": "Kafka",
                "topic": source_topic,
                "kafka.bootstrap.servers": runtime["cluster_bootstrap_servers"],
            },
        }
        expanded_payload = {
            **payload,
            "dataAddress": self._expanded_kafka_address(
                source_topic,
                runtime["cluster_bootstrap_servers"],
            ),
        }
        body, status_code = self._post_kafka_payload_with_expanded_fallback(
            self._management_url(provider, "/management/v3/assets"),
            provider_jwt,
            payload,
            expanded_payload,
            "provider Kafka asset creation",
        )
        return asset_id, body.get("@id") or body.get("id") or asset_id, status_code

    def _create_policy(self, provider, provider_jwt, suffix):
        policy_id = f"kafka-edc-policy-{suffix}"
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
                "odrl": "http://www.w3.org/ns/odrl/2/",
            },
            "@id": policy_id,
            "policy": {
                "@context": "http://www.w3.org/ns/odrl.jsonld",
                "@type": "Set",
                "permission": [],
                "prohibition": [],
                "obligation": [],
            },
        }
        body, status_code = self._post_json(
            self._management_url(provider, "/management/v3/policydefinitions"),
            provider_jwt,
            payload,
            "provider policy creation",
        )
        return policy_id, body.get("@id") or body.get("id") or policy_id, status_code

    def _create_contract_definition(self, provider, provider_jwt, asset_id, policy_id, suffix):
        contract_definition_id = f"kafka-edc-contract-{suffix}"
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
            },
            "@id": contract_definition_id,
            "accessPolicyId": policy_id,
            "contractPolicyId": policy_id,
            "assetsSelector": [
                {
                    "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
                    "operator": "=",
                    "operandRight": asset_id,
                }
            ],
        }
        body, status_code = self._post_json(
            self._management_url(provider, "/management/v3/contractdefinitions"),
            provider_jwt,
            payload,
            "provider contract definition creation",
        )
        return contract_definition_id, body.get("@id") or body.get("id") or contract_definition_id, status_code

    def _request_catalog(self, provider, consumer, consumer_jwt):
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
            },
            "@type": "CatalogRequest",
            "counterPartyAddress": self._protocol_address(provider),
            "counterPartyId": provider,
            "protocol": "dataspace-protocol-http",
            "querySpec": {
                "offset": 0,
                "limit": 100,
                "filterExpression": [],
            },
        }
        return self._post_json(
            self._management_url(consumer, "/management/v3/catalog/request"),
            consumer_jwt,
            payload,
            "consumer catalog request",
        )

    @staticmethod
    def _select_catalog_dataset(catalog_body, expected_asset_id, fallback_connector):
        catalog = catalog_body[0] if isinstance(catalog_body, list) and catalog_body else catalog_body
        if not isinstance(catalog, dict):
            raise RuntimeError("Catalog response is empty or invalid")

        datasets = catalog.get("dcat:dataset")
        if not datasets:
            raise RuntimeError("Catalog response does not contain dcat:dataset")
        if not isinstance(datasets, list):
            datasets = [datasets]

        dataset = next(
            (item for item in datasets if item and expected_asset_id in json.dumps(item, ensure_ascii=False)),
            None,
        )
        if dataset is None:
            raise RuntimeError(f"Catalog does not contain asset {expected_asset_id}")

        policy = dataset.get("odrl:hasPolicy")
        if isinstance(policy, list):
            policy = policy[0] if policy else None
        offer_id = policy.get("@id") if isinstance(policy, dict) else None
        if not offer_id:
            raise RuntimeError("Catalog dataset does not expose offer policy id")

        participant_id = catalog.get("dspace:participantId") or fallback_connector
        return {
            "catalog_asset_id": dataset.get("@id") or expected_asset_id,
            "offer_id": offer_id,
            "provider_participant_id": participant_id,
            "dataset": dataset,
            "catalog": catalog,
        }

    @staticmethod
    def _extract_identifier(item):
        if not isinstance(item, dict):
            return None
        return item.get("@id") or item.get("id")

    def _query_collection(self, connector, token, path, label, limit=200):
        body, _ = self._post_json(
            self._management_url(connector, path),
            token,
            {
                "@context": {
                    "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
                },
                "offset": 0,
                "limit": limit,
            },
            label,
        )
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return [body]
        return []

    def _terminate_transfer_process(self, connector, token, transfer_id, reason):
        _, status_code = self._post_json_optional_body(
            self._management_url(connector, f"/management/v3/transferprocesses/{transfer_id}/terminate"),
            token,
            {
                "@context": {
                    "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
                },
                "@type": "TerminateTransfer",
                "reason": reason,
            },
            "Kafka EDC transfer termination",
            accepted_statuses={204, 404, 409},
        )
        return status_code

    def _deprovision_transfer_process(self, connector, token, transfer_id):
        _, status_code = self._post_json_optional_body(
            self._management_url(connector, f"/management/v3/transferprocesses/{transfer_id}/deprovision"),
            token,
            None,
            "Kafka EDC transfer deprovision",
            accepted_statuses={204, 404, 409},
        )
        return status_code

    def _wait_for_transfer_cleanup(self, connector, token, transfer_id, timeout_seconds=20):
        deadline = time.time() + max(int(timeout_seconds), 1)
        last_state = None
        terminal_states = {"TERMINATED", "DEPROVISIONED", "ENDED", "COMPLETED", "FINALIZED"}

        while time.time() <= deadline:
            body, status_code = self._get_json(
                self._management_url(connector, f"/management/v3/transferprocesses/{transfer_id}/state"),
                token,
                "Kafka EDC transfer cleanup state lookup",
                accepted_statuses={200, 404},
            )
            if status_code == 404:
                return {"state": "NOT_FOUND", "status_code": 404}
            if isinstance(body, dict):
                last_state = body.get("state")
                if last_state in terminal_states:
                    return {"state": last_state, "status_code": status_code}
            time.sleep(1)

        return {"state": last_state or "UNKNOWN", "status_code": 200, "timed_out": True}

    def _cleanup_connector_kafka_edc_state(self, connector, token):
        summary = {
            "connector": connector,
            "terminated_transfers": [],
            "deleted_contract_definitions": [],
            "deleted_policies": [],
            "deleted_assets": [],
            "errors": [],
        }

        try:
            transfer_items = self._query_collection(
                connector,
                token,
                "/management/v3/transferprocesses/request",
                "Kafka EDC transfer listing",
            )
            for item in transfer_items:
                transfer_id = self._extract_identifier(item)
                asset_id = self._read_field(item, "assetId") or item.get("assetId")
                if not transfer_id or not str(asset_id or "").startswith(self.KAFKA_EDC_ASSET_PREFIX):
                    continue
                try:
                    terminate_status = self._terminate_transfer_process(
                        connector,
                        token,
                        transfer_id,
                        "Framework cleanup before/after Kafka EDC validation",
                    )
                    state_info = self._wait_for_transfer_cleanup(connector, token, transfer_id)
                    deprovision_status = None
                    if state_info.get("state") not in {"DEPROVISIONED", "NOT_FOUND"}:
                        deprovision_status = self._deprovision_transfer_process(connector, token, transfer_id)
                        state_info = self._wait_for_transfer_cleanup(connector, token, transfer_id)
                    summary["terminated_transfers"].append(
                        {
                            "transfer_id": transfer_id,
                            "asset_id": asset_id,
                            "terminate_status": terminate_status,
                            "deprovision_status": deprovision_status,
                            "state": state_info.get("state"),
                            "timed_out": bool(state_info.get("timed_out")),
                        }
                    )
                except Exception as exc:
                    summary["errors"].append(f"transfer:{transfer_id}:{exc}")
        except Exception as exc:
            summary["errors"].append(f"transfer_list:{exc}")

        def delete_prefixed_resources(path, prefix, bucket, label):
            try:
                items = self._query_collection(connector, token, path, f"Kafka EDC {label} listing")
            except Exception as exc:
                summary["errors"].append(f"{label}_list:{exc}")
                return
            for item in items:
                resource_id = self._extract_identifier(item)
                if not resource_id or not str(resource_id).startswith(prefix):
                    continue
                try:
                    status_code = self._delete(
                        self._management_url(connector, f"{path.rsplit('/', 1)[0]}/{resource_id}"),
                        token,
                        f"Kafka EDC {label} deletion",
                    )
                    summary[bucket].append({"id": resource_id, "status_code": status_code})
                except Exception as exc:
                    summary["errors"].append(f"{label}:{resource_id}:{exc}")

        delete_prefixed_resources(
            "/management/v3/contractdefinitions/request",
            self.KAFKA_EDC_CONTRACT_PREFIX,
            "deleted_contract_definitions",
            "contract_definition",
        )
        delete_prefixed_resources(
            "/management/v3/policydefinitions/request",
            self.KAFKA_EDC_POLICY_PREFIX,
            "deleted_policies",
            "policy_definition",
        )
        delete_prefixed_resources(
            "/management/v3/assets/request",
            self.KAFKA_EDC_ASSET_PREFIX,
            "deleted_assets",
            "asset",
        )
        return summary

    def _cleanup_kafka_edc_state(self, provider, consumer, provider_jwt, consumer_jwt):
        summaries = []
        if consumer_jwt:
            try:
                summaries.append(self._cleanup_connector_kafka_edc_state(consumer, consumer_jwt))
            except Exception:
                pass
        if provider_jwt:
            try:
                summaries.append(self._cleanup_connector_kafka_edc_state(provider, provider_jwt))
            except Exception:
                pass
        return summaries

    @staticmethod
    def _cleanup_has_actions(cleanup_entries):
        for entry in cleanup_entries or []:
            if not isinstance(entry, dict):
                continue
            for key in (
                "terminated_transfers",
                "deleted_contract_definitions",
                "deleted_policies",
                "deleted_assets",
            ):
                if entry.get(key):
                    return True
        return False

    def _wait_for_cleanup_settlement(self, runtime, cleanup_entries):
        seconds = max(int(runtime.get("pre_run_settle_seconds", 0)), 0)
        if seconds <= 0:
            return {
                "status": "skipped",
                "seconds_waited": 0,
                "reason": "disabled",
            }
        if not self._cleanup_has_actions(cleanup_entries):
            return {
                "status": "skipped",
                "seconds_waited": 0,
                "reason": "no_cleanup_actions",
            }
        time.sleep(seconds)
        return {
            "status": "waited",
            "seconds_waited": seconds,
        }

    def _start_negotiation(self, provider, consumer, consumer_jwt, catalog_info):
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
            },
            "@type": "ContractRequest",
            "counterPartyAddress": self._protocol_address(provider),
            "protocol": "dataspace-protocol-http",
            "policy": {
                "@context": "http://www.w3.org/ns/odrl.jsonld",
                "@type": "odrl:Offer",
                "@id": catalog_info["offer_id"],
                "assigner": catalog_info["provider_participant_id"],
                "target": catalog_info["catalog_asset_id"],
                "permission": [],
                "prohibition": [],
                "obligation": [],
            },
        }
        body, status_code = self._post_json(
            self._management_url(consumer, "/management/v3/contractnegotiations"),
            consumer_jwt,
            payload,
            "consumer contract negotiation start",
        )
        negotiation_id = body.get("@id") or body.get("id")
        if not negotiation_id:
            raise RuntimeError("Negotiation creation did not return negotiation id")
        return negotiation_id, status_code

    def _query_negotiation(self, consumer, consumer_jwt, negotiation_id):
        direct_body, direct_status = self._get_json(
            self._management_url(consumer, f"/management/v3/contractnegotiations/{negotiation_id}"),
            consumer_jwt,
            "contract negotiation lookup",
            accepted_statuses={200, 404},
        )
        if direct_status == 200 and isinstance(direct_body, dict):
            return direct_body

        body, _ = self._post_json(
            self._management_url(consumer, "/management/v3/contractnegotiations/request"),
            consumer_jwt,
            {
                "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
                "offset": 0,
                "limit": 100,
            },
            "contract negotiation status query",
        )
        if isinstance(body, list):
            return next(
                (
                    item for item in body
                    if isinstance(item, dict) and (item.get("@id") == negotiation_id or item.get("id") == negotiation_id)
                ),
                None,
            )
        return body if isinstance(body, dict) else None

    def _wait_for_agreement(self, consumer, consumer_jwt, negotiation_id, runtime):
        deadline = time.time() + int(runtime["negotiation_timeout_seconds"])
        last_state = None
        last_detail = None
        while time.time() <= deadline:
            negotiation = self._query_negotiation(consumer, consumer_jwt, negotiation_id)
            if negotiation:
                state = negotiation.get("state")
                last_state = state
                agreement_id = negotiation.get("contractAgreementId")
                if agreement_id:
                    return {
                        "state": state,
                        "agreement_id": agreement_id,
                        "raw": negotiation,
                    }
                if state == "TERMINATED":
                    raise RuntimeError(
                        "Negotiation reached TERMINATED state"
                        + (f": {negotiation.get('errorDetail')}" if negotiation.get("errorDetail") else "")
                    )
                last_detail = negotiation.get("errorDetail")
            time.sleep(max(1, int(runtime["poll_interval_seconds"])))

        raise RuntimeError(
            f"Negotiation {negotiation_id} did not produce contractAgreementId in time"
            + (f" (last_state={last_state}, detail={last_detail})" if last_state or last_detail else "")
        )

    def _start_transfer(self, provider, consumer, consumer_jwt, asset_id, agreement_id, runtime, destination_topic):
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
            },
            "@type": "TransferRequest",
            "assetId": asset_id,
            "contractId": agreement_id,
            "counterPartyAddress": self._protocol_address(provider),
            "protocol": "dataspace-protocol-http",
            "transferType": "Kafka-PUSH",
            "dataDestination": {
                "type": "Kafka",
                "topic": destination_topic,
                "kafka.bootstrap.servers": runtime["cluster_bootstrap_servers"],
            },
        }
        expanded_payload = {
            **payload,
            "dataDestination": self._expanded_kafka_address(
                destination_topic,
                runtime["cluster_bootstrap_servers"],
            ),
        }
        body, status_code = self._post_kafka_payload_with_expanded_fallback(
            self._management_url(consumer, "/management/v3/transferprocesses"),
            consumer_jwt,
            payload,
            expanded_payload,
            "consumer Kafka transfer start",
        )
        transfer_id = body.get("@id") or body.get("id")
        if not transfer_id:
            raise RuntimeError("Transfer creation did not return transfer id")
        return transfer_id, status_code

    def _query_transfer(self, consumer, consumer_jwt, transfer_id):
        direct_body, direct_status = self._get_json(
            self._management_url(consumer, f"/management/v3/transferprocesses/{transfer_id}"),
            consumer_jwt,
            "transfer process lookup",
            accepted_statuses={200, 404},
        )
        if direct_status == 200 and isinstance(direct_body, dict):
            return direct_body

        body, _ = self._post_json(
            self._management_url(consumer, "/management/v3/transferprocesses/request"),
            consumer_jwt,
            {
                "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
                "offset": 0,
                "limit": 100,
            },
            "transfer process status query",
        )
        if isinstance(body, list):
            return next(
                (
                    item for item in body
                    if isinstance(item, dict) and (item.get("@id") == transfer_id or item.get("id") == transfer_id)
                ),
                None,
            )
        return body if isinstance(body, dict) else None

    def _wait_for_transfer_started(self, consumer, consumer_jwt, transfer_id, runtime):
        deadline = time.time() + int(runtime["transfer_timeout_seconds"])
        last_state = None
        last_detail = None
        success_states = {"STARTED", "COMPLETED", "FINALIZED", "ENDED", "DEPROVISIONED"}
        while time.time() <= deadline:
            transfer = self._query_transfer(consumer, consumer_jwt, transfer_id)
            if transfer:
                state = transfer.get("state")
                last_state = state
                if state in success_states:
                    return {"state": state, "raw": transfer}
                if state == "TERMINATED":
                    raise RuntimeError(
                        "Transfer reached TERMINATED state"
                        + (f": {transfer.get('errorDetail')}" if transfer.get("errorDetail") else "")
                    )
                last_detail = transfer.get("errorDetail") or transfer.get("error")
            time.sleep(max(1, int(runtime["poll_interval_seconds"])))

        raise RuntimeError(
            f"Transfer {transfer_id} did not reach a started/finalized state in time"
            + (f" (last_state={last_state}, detail={last_detail})" if last_state or last_detail else "")
        )

    def _build_kafka_client_kwargs(self, runtime, *, endpoint=None, username=None, password=None):
        kwargs = {
            "bootstrap_servers": endpoint or runtime.get("host_bootstrap_servers") or runtime.get("bootstrap_servers"),
            "security_protocol": runtime.get("security_protocol", "PLAINTEXT"),
            "request_timeout_ms": runtime.get("request_timeout_ms", 60000),
            "api_version_auto_timeout_ms": runtime.get("api_timeout_ms", 60000),
        }
        sasl_mechanism = runtime.get("sasl_mechanism")
        if sasl_mechanism:
            kwargs["sasl_mechanism"] = sasl_mechanism
        if username:
            kwargs["sasl_plain_username"] = username
        elif runtime.get("username"):
            kwargs["sasl_plain_username"] = runtime.get("username")
        if password:
            kwargs["sasl_plain_password"] = password
        elif runtime.get("password"):
            kwargs["sasl_plain_password"] = runtime.get("password")
        return kwargs

    def _load_kafka_classes(self):
        producer_class = self.producer_class
        consumer_class = self.consumer_class
        if producer_class is not None and consumer_class is not None:
            return producer_class, consumer_class

        try:
            from kafka import KafkaConsumer, KafkaProducer

            return producer_class or KafkaProducer, consumer_class or KafkaConsumer
        except Exception as exc:
            raise RuntimeError(f"Kafka client library not available: {exc}") from exc

    @staticmethod
    def _decode_message_value(value):
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _compute_percentile(values, percentile):
        ordered = sorted(values)
        if len(ordered) == 1:
            return float(ordered[0])
        rank = (len(ordered) - 1) * percentile
        lower_index = int(rank)
        upper_index = min(lower_index + 1, len(ordered) - 1)
        weight = rank - lower_index
        lower = float(ordered[lower_index])
        upper = float(ordered[upper_index])
        return lower + (upper - lower) * weight

    def _wait_for_transfer_runtime_stabilization(self, runtime, transfer_process, source_topic):
        timeout_seconds = max(int(runtime.get("startup_grace_seconds", 0)), 0)
        correlation_id = None
        if isinstance(transfer_process, dict):
            correlation_id = transfer_process.get("correlationId")

        if timeout_seconds <= 0:
            return {
                "strategy": "disabled",
                "seconds_waited": 0,
            }

        admin_client_class, _ = self._load_kafka_admin_classes()
        admin_client = admin_client_class(**self._build_kafka_client_kwargs(runtime))
        started_at = time.time()
        deadline = started_at + timeout_seconds
        last_state = None
        last_member_count = 0
        matched_group_id = None

        try:
            while time.time() <= deadline:
                group_ids = []
                try:
                    listed_groups = admin_client.list_consumer_groups()
                except Exception:
                    listed_groups = []

                for group in listed_groups or []:
                    if isinstance(group, (list, tuple)) and group:
                        group_ids.append(str(group[0]))
                    else:
                        group_id = getattr(group, "group", None)
                        if group_id:
                            group_ids.append(str(group_id))

                if correlation_id:
                    matching_group_ids = [group_id for group_id in group_ids if correlation_id in group_id]
                else:
                    matching_group_ids = list(group_ids)

                for group_id in matching_group_ids:
                    try:
                        descriptions = admin_client.describe_consumer_groups([group_id])
                    except Exception:
                        continue
                    if not descriptions:
                        continue
                    description = descriptions[0]
                    last_state = str(getattr(description, "state", "") or "")
                    members = getattr(description, "members", None) or []
                    last_member_count = len(members)
                    matched_group_id = group_id
                    if last_member_count > 0 and last_state.lower() == "stable":
                        # Give the dataplane a brief extra moment after assignment before producing.
                        time.sleep(1)
                        return {
                            "strategy": "consumer_group_ready",
                            "seconds_waited": round(time.time() - started_at, 2),
                            "group_id": group_id,
                            "state": last_state,
                            "member_count": last_member_count,
                            "source_topic": source_topic,
                        }

                time.sleep(max(1, int(runtime.get("poll_interval_seconds", 1))))

            return {
                "strategy": "timeout_without_ready_group",
                "seconds_waited": round(time.time() - started_at, 2),
                "correlation_id": correlation_id,
                "group_id": matched_group_id,
                "last_state": last_state,
                "last_member_count": last_member_count,
                "source_topic": source_topic,
            }
        finally:
            close_method = getattr(admin_client, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    pass

    def _wait_for_end_to_end_probe(self, runtime, producer, consumer, source_topic):
        timeout_seconds = max(int(runtime.get("startup_grace_seconds", 0)), 0)
        if timeout_seconds <= 0:
            return {
                "status": "skipped",
                "attempts": 0,
                "seconds_waited": 0,
            }

        started_at = time.time()
        deadline = started_at + timeout_seconds
        attempts = 0
        poll_timeout_ms = max(500, min(2000, int(runtime.get("consumer_request_timeout_ms", 60000))))

        while time.time() <= deadline:
            attempts += 1
            probe_payload = {
                "message_id": f"kafka-edc-probe-{self.uuid_factory()}",
                "producer_timestamp_ms": self.time_provider(),
                "probe": True,
            }
            producer.send(source_topic, json.dumps(probe_payload, separators=(",", ":")).encode("utf-8"))
            producer.flush()

            probe_deadline = time.time() + max(1, int(runtime.get("poll_interval_seconds", 1)))
            while time.time() <= probe_deadline:
                records_by_partition = consumer.poll(timeout_ms=poll_timeout_ms)
                if not records_by_partition:
                    continue
                for records in records_by_partition.values():
                    for record in records:
                        payload = self._decode_message_value(getattr(record, "value", None))
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("message_id") == probe_payload["message_id"]:
                            return {
                                "status": "ready",
                                "attempts": attempts,
                                "seconds_waited": round(time.time() - started_at, 2),
                                "probe_message_id": probe_payload["message_id"],
                            }
            time.sleep(1)

        raise RuntimeError("Kafka transfer path did not relay a probe message in time")

    def _measure_transfer_latency(self, runtime, source_topic, destination_topic):
        producer_class, consumer_class = self._load_kafka_classes()
        producer_kwargs = self._build_kafka_client_kwargs(runtime)
        producer_kwargs.setdefault("acks", "all")
        producer_kwargs.setdefault("retries", 5)
        producer_kwargs.setdefault("max_block_ms", runtime.get("max_block_ms", 60000))
        producer = producer_class(**producer_kwargs)
        group_id = f"{runtime.get('consumer_group_prefix', 'framework-edc-kafka')}-{str(self.uuid_factory())[:12]}"

        consumer_kwargs = self._build_kafka_client_kwargs(runtime)
        consumer_kwargs.setdefault("group_id", group_id)
        consumer_kwargs.setdefault("auto_offset_reset", "earliest")
        consumer_kwargs.setdefault("enable_auto_commit", False)
        consumer_kwargs.setdefault("consumer_timeout_ms", runtime.get("consumer_request_timeout_ms", 60000))
        consumer = consumer_class(**consumer_kwargs)

        if hasattr(consumer, "subscribe"):
            consumer.subscribe([destination_topic])

        message_count = int(runtime["message_count"])
        produced_count = 0
        consumed_count = 0
        invalid_latency_count = 0
        latencies_ms = []
        start_ms = self.time_provider()
        probe_result = None

        try:
            probe_result = self._wait_for_end_to_end_probe(runtime, producer, consumer, source_topic)
            for index in range(message_count):
                payload = {
                    "message_id": f"kafka-edc-{index}-{self.uuid_factory()}",
                    "producer_timestamp_ms": self.time_provider(),
                }
                producer.send(source_topic, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
                produced_count += 1
            producer.flush()

            deadline = time.time() + int(runtime["consumer_poll_timeout_seconds"])
            while time.time() <= deadline and consumed_count < message_count:
                records_by_partition = consumer.poll(timeout_ms=500)
                if not records_by_partition:
                    continue
                for records in records_by_partition.values():
                    for record in records:
                        payload = self._decode_message_value(getattr(record, "value", None))
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("probe"):
                            continue
                        produced_at = payload.get("producer_timestamp_ms")
                        consumed_at = self.time_provider()
                        try:
                            latency = float(consumed_at) - float(produced_at)
                        except (TypeError, ValueError):
                            invalid_latency_count += 1
                            continue
                        if math.isnan(latency) or math.isinf(latency) or latency < 0:
                            invalid_latency_count += 1
                            continue
                        latencies_ms.append(latency)
                        consumed_count += 1
                        if consumed_count >= message_count:
                            break
                    if consumed_count >= message_count:
                        break
        finally:
            try:
                producer.close()
            except Exception:
                pass
            try:
                consumer.close()
            except Exception:
                pass

        duration_seconds = max((self.time_provider() - start_ms) / 1000.0, 0.001)
        if invalid_latency_count > 0:
            raise RuntimeError(f"Detected {invalid_latency_count} invalid Kafka latency samples")
        if not latencies_ms:
            raise RuntimeError("No Kafka messages were consumed through the EDC transfer")

        return {
            "status": "completed",
            "messages_produced": produced_count,
            "messages_consumed": consumed_count,
            "source_topic": source_topic,
            "destination_topic": destination_topic,
            "consumer_group_id": group_id,
            "average_latency_ms": round(sum(latencies_ms) / len(latencies_ms), 2),
            "min_latency_ms": round(min(latencies_ms), 2),
            "max_latency_ms": round(max(latencies_ms), 2),
            "p50_latency_ms": round(self._compute_percentile(latencies_ms, 0.50), 2),
            "p95_latency_ms": round(self._compute_percentile(latencies_ms, 0.95), 2),
            "p99_latency_ms": round(self._compute_percentile(latencies_ms, 0.99), 2),
            "throughput_messages_per_second": round(consumed_count / duration_seconds, 2),
            "probe": probe_result,
        }

    @staticmethod
    def _pair_artifact_path(experiment_dir, provider, consumer):
        artifact_dir = os.path.join(experiment_dir, "kafka_edc")
        os.makedirs(artifact_dir, exist_ok=True)
        return os.path.join(artifact_dir, f"{provider}__{consumer}.json")

    def _save_pair_artifact(self, experiment_dir, provider, consumer, payload):
        if not experiment_dir:
            return None
        path = self._pair_artifact_path(experiment_dir, provider, consumer)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return path

    def _reset_framework_managed_kafka(self):
        kafka_manager = self.kafka_manager
        stop_method = getattr(kafka_manager, "stop_kafka", None) if kafka_manager is not None else None
        if callable(stop_method):
            stop_method()

    @staticmethod
    def _pair_error_message(payload):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or "")
        if error is None:
            return ""
        return str(error)

    def _is_transient_pair_failure(self, payload):
        if not isinstance(payload, dict) or payload.get("status") == "passed":
            return False

        error_message = self._pair_error_message(payload)
        transient_fragments = (
            "NoBrokersAvailable",
            "failed with HTTP 502",
            "failed with HTTP 503",
            "failed with HTTP 504",
            "Unable to obtain credentials",
            "Kafka transfer path did not relay a probe message in time",
        )
        if any(fragment in error_message for fragment in transient_fragments):
            return True

        for step in payload.get("steps", []):
            if step.get("name") == "wait_for_transfer_runtime_stabilization" and step.get("strategy") == "timeout_without_ready_group":
                return True
        return False

    def run_pair(self, provider, consumer, experiment_dir=None):
        runtime = self._ensure_kafka_runtime(self._load_kafka_runtime())
        source_topic = self._topic_name(runtime)
        destination_topic = self._destination_topic_name(source_topic)
        suffix = str(self.uuid_factory()).replace("_", "-").lower()[:12]
        broker_source = None
        if self.kafka_manager is not None:
            broker_source = "auto-provisioned" if getattr(self.kafka_manager, "started_by_framework", False) else "external"

        payload = {
            "provider": provider,
            "consumer": consumer,
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "bootstrap_servers": runtime.get("host_bootstrap_servers") or runtime.get("bootstrap_servers"),
            "cluster_bootstrap_servers": runtime.get("cluster_bootstrap_servers"),
            "broker_source": broker_source,
            "source_topic": source_topic,
            "destination_topic": destination_topic,
            "steps": [],
            "metrics": None,
            "error": None,
        }

        def record_step(name, status, **details):
            step = {"name": name, "status": status}
            if details:
                step.update(details)
            payload["steps"].append(step)

        provider_jwt = None
        consumer_jwt = None

        try:
            try:
                self._ensure_topic_with_runtime(runtime, source_topic)
                record_step(
                    "ensure_source_topic",
                    "passed",
                    topic=source_topic,
                    method="runtime_admin",
                    bootstrap_servers=runtime.get("host_bootstrap_servers") or runtime.get("bootstrap_servers"),
                )
                self._ensure_topic_with_runtime(runtime, destination_topic)
                record_step(
                    "ensure_destination_topic",
                    "passed",
                    topic=destination_topic,
                    method="runtime_admin",
                    bootstrap_servers=runtime.get("host_bootstrap_servers") or runtime.get("bootstrap_servers"),
                )
            except Exception as admin_exc:
                if callable(self.ensure_kafka_topic):
                    if not self.ensure_kafka_topic(source_topic):
                        raise RuntimeError(f"Kafka topic '{source_topic}' could not be created or verified") from admin_exc
                    record_step(
                        "ensure_source_topic",
                        "passed",
                        topic=source_topic,
                        method="fallback_callable",
                        admin_error=str(admin_exc),
                    )
                    if not self.ensure_kafka_topic(destination_topic):
                        raise RuntimeError(f"Kafka topic '{destination_topic}' could not be created or verified") from admin_exc
                    record_step(
                        "ensure_destination_topic",
                        "passed",
                        topic=destination_topic,
                        method="fallback_callable",
                        admin_error=str(admin_exc),
                    )
                else:
                    raise RuntimeError(f"Kafka topics '{source_topic}'/'{destination_topic}' could not be created or verified") from admin_exc

            provider_jwt = self._login(provider, "provider")
            record_step("provider_login", "passed")
            consumer_jwt = self._login(consumer, "consumer")
            record_step("consumer_login", "passed")
            before_run_cleanup = self._cleanup_kafka_edc_state(provider, consumer, provider_jwt, consumer_jwt)
            payload["cleanup"] = {
                "before_run": before_run_cleanup,
            }
            cleanup_settlement = self._wait_for_cleanup_settlement(runtime, before_run_cleanup)
            if cleanup_settlement.get("status") == "waited":
                record_step(
                    "wait_for_pre_run_cleanup_settlement",
                    "passed",
                    seconds_waited=cleanup_settlement["seconds_waited"],
                )

            asset_id, _, asset_status = self._create_asset(provider, provider_jwt, source_topic, runtime, suffix)
            payload["asset_id"] = asset_id
            record_step("create_kafka_asset", "passed", http_status=asset_status, asset_id=asset_id)

            policy_id, _, policy_status = self._create_policy(provider, provider_jwt, suffix)
            payload["policy_id"] = policy_id
            record_step("create_policy", "passed", http_status=policy_status, policy_id=policy_id)

            contract_definition_id, _, contract_status = self._create_contract_definition(
                provider, provider_jwt, asset_id, policy_id, suffix
            )
            payload["contract_definition_id"] = contract_definition_id
            record_step(
                "create_contract_definition",
                "passed",
                http_status=contract_status,
                contract_definition_id=contract_definition_id,
            )

            catalog_body, catalog_status = self._request_catalog(provider, consumer, consumer_jwt)
            catalog_info = self._select_catalog_dataset(catalog_body, asset_id, provider)
            payload["catalog_asset_id"] = catalog_info["catalog_asset_id"]
            payload["offer_id"] = catalog_info["offer_id"]
            payload["provider_participant_id"] = catalog_info["provider_participant_id"]
            record_step(
                "request_catalog",
                "passed",
                http_status=catalog_status,
                catalog_asset_id=catalog_info["catalog_asset_id"],
                offer_id=catalog_info["offer_id"],
            )

            negotiation_id, negotiation_status = self._start_negotiation(provider, consumer, consumer_jwt, catalog_info)
            payload["negotiation_id"] = negotiation_id
            record_step(
                "start_negotiation",
                "passed",
                http_status=negotiation_status,
                negotiation_id=negotiation_id,
            )

            negotiation_result = self._wait_for_agreement(consumer, consumer_jwt, negotiation_id, runtime)
            payload["negotiation_state"] = negotiation_result["state"]
            payload["agreement_id"] = negotiation_result["agreement_id"]
            record_step(
                "wait_for_contract_agreement",
                "passed",
                state=negotiation_result["state"],
                agreement_id=negotiation_result["agreement_id"],
            )

            transfer_id, transfer_status = self._start_transfer(
                provider,
                consumer,
                consumer_jwt,
                asset_id,
                negotiation_result["agreement_id"],
                runtime,
                destination_topic,
            )
            payload["transfer_id"] = transfer_id
            record_step(
                "start_transfer",
                "passed",
                http_status=transfer_status,
                transfer_id=transfer_id,
                transfer_type="Kafka-PUSH",
                destination_topic=destination_topic,
            )

            transfer_result = self._wait_for_transfer_started(consumer, consumer_jwt, transfer_id, runtime)
            payload["transfer_state"] = transfer_result["state"]
            payload["transfer_process"] = transfer_result["raw"]
            record_step(
                "wait_for_transfer_state",
                "passed",
                state=transfer_result["state"],
            )

            stabilization = self._wait_for_transfer_runtime_stabilization(
                runtime,
                transfer_result["raw"],
                source_topic,
            )
            if stabilization.get("strategy") != "disabled":
                record_step(
                    "wait_for_transfer_runtime_stabilization",
                    "passed",
                    **stabilization,
                )

            metrics = self._measure_transfer_latency(runtime, source_topic, destination_topic)
            payload["metrics"] = metrics
            record_step(
                "measure_kafka_transfer_latency",
                "passed",
                messages_consumed=metrics["messages_consumed"],
                average_latency_ms=metrics["average_latency_ms"],
            )

            payload["status"] = "passed"
            return payload
        except Exception as exc:
            unsupported_kafka = isinstance(exc, KafkaDataAddressUnsupported)
            payload["status"] = "skipped" if unsupported_kafka else "failed"
            if unsupported_kafka:
                payload["reason"] = "kafka_dataaddress_not_supported"
            payload["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            record_step(
                "suite_error",
                "skipped" if unsupported_kafka else "failed",
                error=str(exc),
            )
            return payload
        finally:
            if provider_jwt or consumer_jwt:
                cleanup_payload = payload.setdefault("cleanup", {})
                cleanup_payload["after_run"] = self._cleanup_kafka_edc_state(
                    provider,
                    consumer,
                    provider_jwt,
                    consumer_jwt,
                )
            artifact_path = self._save_pair_artifact(experiment_dir, provider, consumer, payload)
            if artifact_path:
                payload["artifact_path"] = artifact_path

    def run_all(self, connectors, experiment_dir=None):
        connectors = list(connectors or [])
        results = []
        for provider, consumer in permutations(connectors, 2):
            result = None
            attempts = 0
            retry_reason = None
            max_attempts = self.DEFAULT_PAIR_ATTEMPTS

            while attempts < max_attempts:
                attempts += 1
                try:
                    result = self.run_pair(provider, consumer, experiment_dir=experiment_dir)
                finally:
                    # Keep bidirectional runs isolated from any broker or port-forward state
                    # created by the previous pair execution.
                    self._reset_framework_managed_kafka()

                if result.get("status") == "passed":
                    break
                if not self._is_transient_pair_failure(result) or attempts >= max_attempts:
                    break

                retry_reason = self._pair_error_message(result)
                time.sleep(self.DEFAULT_PAIR_RETRY_SECONDS)

            if result is None:
                continue
            result["attempt_count"] = attempts
            result["retry_attempted"] = attempts > 1
            if retry_reason:
                result["retry_reason"] = retry_reason
                artifact_path = self._save_pair_artifact(experiment_dir, provider, consumer, result)
                if artifact_path:
                    result["artifact_path"] = artifact_path
            results.append(result)
        return results
