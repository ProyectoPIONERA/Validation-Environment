import os
import shutil
import subprocess
import json
import tempfile


class NewmanExecutor:
    """Runs Postman collections through Newman.

    Encapsulates Newman command execution, environment variable injection,
    and dynamic test script loading for validation collections.
    """

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

        return exported_reports

    def describe(self) -> str:
        return "NewmanExecutor runs Postman collections using Newman."

