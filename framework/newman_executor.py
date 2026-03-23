import json
import os
import shutil
import subprocess
import tempfile
import time

import requests


class NewmanExecutor:
    """Runs Postman collections through Newman.

    Encapsulates Newman command execution, environment variable injection,
    and dynamic test script loading for validation collections.
    """

    CONTRACT_AGREEMENT_TIMEOUT_SECONDS = 60
    CONTRACT_AGREEMENT_POLL_INTERVAL_SECONDS = 3
    ASYNC_COLLECTION_DELAY_REQUEST_MS = 2000

    def ensure_available(self):
        newman_cmd = self.resolve_newman_command()
        if newman_cmd is not None:
            return newman_cmd

        package_json = "package.json"
        if os.path.exists(package_json):
            print("[INFO] Newman not found. Installing local Node.js tooling with npm...")
            result = subprocess.run(
                ["npm", "install"],
                check=False,
                capture_output=False,
                text=True,
            )
            if result.returncode == 0:
                newman_cmd = self.resolve_newman_command()
                if newman_cmd is not None:
                    return newman_cmd

        return None

    def resolve_newman_command(self):
        local_newman = os.path.join("node_modules", ".bin", "newman")
        if os.path.exists(local_newman):
            return [local_newman]

        global_newman = shutil.which("newman")
        if global_newman:
            return [global_newman]

        return None

    def is_available(self):
        return self.ensure_available() is not None

    def _load_file(self, path):
        """Read a file and return its content as string."""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def load_test_scripts(self, collection_name):
        scripts = []

        scripts.append(self._load_file("validation/shared/api/common_tests.js"))

        if "management" in collection_name:
            scripts.append(self._load_file("validation/core/tests/management_tests.js"))

        if "provider" in collection_name:
            scripts.append(self._load_file("validation/core/tests/provider_tests.js"))

        if "catalog" in collection_name:
            scripts.append(self._load_file("validation/core/tests/catalog_tests.js"))

        if "negotiation" in collection_name:
            scripts.append(self._load_file("validation/core/tests/negotiation_tests.js"))

        if "transfer" in collection_name:
            scripts.append(self._load_file("validation/core/tests/transfer_tests.js"))

        return "\n".join(scripts)

    def _write_environment_file(self, env_vars, environment_path):
        payload = {
            "id": "validation-environment",
            "name": "Validation Environment",
            "values": [
                {
                    "key": key,
                    "value": value,
                    "type": "text",
                    "enabled": True,
                }
                for key, value in env_vars.items()
            ],
            "_postman_variable_scope": "environment",
        }
        with open(environment_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _read_environment_payload(self, environment_path):
        with open(environment_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _read_environment_values(self, environment_path):
        payload = self._read_environment_payload(environment_path)
        values = {}
        for entry in payload.get("values", []):
            key = entry.get("key")
            if key:
                values[key] = entry.get("value")
        return payload, values

    def _write_environment_values(self, environment_path, updates):
        payload = self._read_environment_payload(environment_path)
        entries = payload.setdefault("values", [])
        indexed_entries = {
            entry.get("key"): entry
            for entry in entries
            if entry.get("key")
        }

        for key, value in updates.items():
            if key in indexed_entries:
                indexed_entries[key]["value"] = value
                indexed_entries[key]["enabled"] = True
                indexed_entries[key]["type"] = indexed_entries[key].get("type") or "text"
                continue

            entries.append({
                "key": key,
                "value": value,
                "type": "text",
                "enabled": True,
            })

        with open(environment_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _should_wait_for_contract_agreement(self, environment_path):
        _, env_vars = self._read_environment_values(environment_path)
        return bool(env_vars.get("e2e_negotiation_id") and not env_vars.get("e2e_agreement_id"))

    @staticmethod
    def _find_negotiation(body, negotiation_id):
        if isinstance(body, list):
            for item in body:
                if not isinstance(item, dict):
                    continue
                if item.get("@id") == negotiation_id or item.get("id") == negotiation_id:
                    return item
            return body[0] if body else None

        if isinstance(body, dict):
            if not negotiation_id:
                return body
            if body.get("@id") == negotiation_id or body.get("id") == negotiation_id:
                return body

        return None

    def wait_for_contract_agreement(self, environment_path, timeout=None, poll_interval=None):
        timeout = (
            self.CONTRACT_AGREEMENT_TIMEOUT_SECONDS
            if timeout is None
            else timeout
        )
        poll_interval = (
            self.CONTRACT_AGREEMENT_POLL_INTERVAL_SECONDS
            if poll_interval is None
            else poll_interval
        )

        _, env_vars = self._read_environment_values(environment_path)
        agreement_id = env_vars.get("e2e_agreement_id")
        if agreement_id:
            return agreement_id

        negotiation_id = env_vars.get("e2e_negotiation_id")
        consumer = env_vars.get("consumer")
        ds_domain = env_vars.get("dsDomain")
        consumer_jwt = env_vars.get("consumer_jwt")
        missing = [
            key for key, value in (
                ("e2e_negotiation_id", negotiation_id),
                ("consumer", consumer),
                ("dsDomain", ds_domain),
                ("consumer_jwt", consumer_jwt),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Cannot wait for contractAgreementId because these environment variables are missing: "
                + ", ".join(missing)
            )

        url = f"http://{consumer}.{ds_domain}/management/v3/contractnegotiations/request"
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/"
            },
            "offset": 0,
            "limit": 10,
        }
        deadline = time.time() + float(timeout)
        last_state = None
        last_issue = None

        while time.time() <= deadline:
            try:
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {consumer_jwt}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10,
                )
            except requests.RequestException as exc:
                last_issue = str(exc)
            else:
                if response.status_code != 200:
                    last_issue = f"HTTP {response.status_code}"
                else:
                    try:
                        body = response.json()
                    except ValueError:
                        last_issue = "response body is not valid JSON"
                    else:
                        negotiation = self._find_negotiation(body, negotiation_id)
                        if negotiation is None:
                            last_issue = f"negotiation {negotiation_id} not found"
                        else:
                            last_state = negotiation.get("state")
                            agreement_id = negotiation.get("contractAgreementId")
                            if agreement_id:
                                self._write_environment_values(
                                    environment_path,
                                    {"e2e_agreement_id": agreement_id},
                                )
                                print(
                                    "[INFO] contractAgreementId obtained before transfer: "
                                    f"{agreement_id}"
                                )
                                return agreement_id
                            last_issue = negotiation.get("errorDetail") or f"state={last_state or 'unknown'}"

            remaining = deadline - time.time()
            if remaining <= 0:
                break

            wait_detail = last_issue or f"state={last_state or 'unknown'}"
            print(
                "[INFO] Waiting for contractAgreementId from negotiation "
                f"{negotiation_id} ({wait_detail})"
            )
            time.sleep(min(float(poll_interval), remaining))

        raise RuntimeError(
            "Timed out waiting for contractAgreementId before 06_consumer_transfer.json. "
            f"Negotiation={negotiation_id}, last_state={last_state or 'unknown'}, "
            f"detail={last_issue or 'no detail'}"
        )

    def run_newman(self, collection_path, env_vars, report_path=None, environment_path=None):
        """
        Execute a Postman collection using Newman with dynamic environment variables,
        injected test scripts, and optional JSON report export.
        """
        print(f"\nExecuting: newman run {collection_path}")

        test_script = self.load_test_scripts(collection_path)
        newman_cmd = self.ensure_available()
        if newman_cmd is None:
            print("ERROR: Newman is not installed or not available locally")
            print("Install with: npm install or npm install -g newman")
            return None

        cmd = newman_cmd + [
            "run",
            collection_path,
            "--reporters",
            "cli,json",
        ]

        collection_name = os.path.basename(collection_path)
        if collection_name in {"05_consumer_negotiation.json", "06_consumer_transfer.json"}:
            cmd.extend([
                "--delay-request",
                str(self.ASYNC_COLLECTION_DELAY_REQUEST_MS),
            ])

        if environment_path:
            cmd.extend([
                "--environment",
                environment_path,
                "--export-environment",
                environment_path,
            ])
        else:
            for key, value in env_vars.items():
                cmd.extend([
                    "--env-var",
                    f"{key}={value}"
                ])

        cmd.extend([
            "--env-var",
            f"test_script={test_script}"
        ])

        if report_path:
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            cmd.extend([
                "--reporter-json-export",
                report_path,
            ])

        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=False,
                text=True
            )

            if result.returncode != 0:
                print(f"[WARNING] Newman returned exit code {result.returncode}")

            return report_path

        except FileNotFoundError:
            print("ERROR: Newman is not installed or not available locally")
            print("Install with: npm install or npm install -g newman")
            return None

    def run_validation_collections(self, env_vars, report_dir=None):
        """Run all validation collections in sequence and optionally export JSON reports."""
        base = os.path.join("validation", "core", "collections")

        collections = [
            "01_environment_health.json",
            "02_connector_management_api.json",
            "03_provider_setup.json",
            "04_consumer_catalog.json",
            "05_consumer_negotiation.json",
            "06_consumer_transfer.json"
        ]

        total = len(collections)
        exported_reports = []

        with tempfile.TemporaryDirectory(prefix="validation-newman-env-") as tmpdir:
            environment_path = os.path.join(tmpdir, "environment.json")
            self._write_environment_file(env_vars, environment_path)

            for i, c in enumerate(collections, 1):
                collection_path = os.path.join(base, c)
                print(f"[{i}/{total}] Running collection: {c}")

                report_path = None
                if report_dir:
                    report_name = f"{os.path.splitext(c)[0]}.json"
                    report_path = os.path.join(report_dir, report_name)

                exported_report = self.run_newman(
                    collection_path,
                    env_vars,
                    report_path=report_path,
                    environment_path=environment_path,
                )
                if exported_report:
                    exported_reports.append(exported_report)

                if c == "05_consumer_negotiation.json" and self._should_wait_for_contract_agreement(environment_path):
                    self.wait_for_contract_agreement(environment_path)

        return exported_reports

    def describe(self) -> str:
        return "NewmanExecutor runs Postman collections using Newman."

