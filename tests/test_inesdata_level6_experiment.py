import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import inesdata

FIXTURE_DIR = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "newman",
    "minimal_run",
)


def _materialize_fixture_reports(experiment_dir):
    report_dir = inesdata.ExperimentStorage.newman_reports_dir(experiment_dir)
    pair_dir = os.path.join(report_dir, "run_001", "conn-a__conn-b")
    os.makedirs(pair_dir, exist_ok=True)

    exported = []
    for file_name in (
        "01_environment_health.json",
        "05_consumer_negotiation.json",
        "06_consumer_transfer.json",
    ):
        source = os.path.join(FIXTURE_DIR, file_name)
        target = os.path.join(pair_dir, file_name)
        shutil.copyfile(source, target)
        exported.append(target)

    return exported


class InesdataLevel6ExperimentTests(unittest.TestCase):
    def setUp(self):
        self._ensure_vault_unsealed_patcher = mock.patch.object(
            inesdata,
            "ensure_vault_unsealed",
            return_value=True,
        )
        self._ensure_vault_unsealed_patcher.start()
        self.addCleanup(self._ensure_vault_unsealed_patcher.stop)

        self._manage_hosts_entries_patcher = mock.patch.object(
            inesdata.INESDATA_ADAPTER.infrastructure,
            "manage_hosts_entries",
            return_value=None,
        )
        self._manage_hosts_entries_patcher.start()
        self.addCleanup(self._manage_hosts_entries_patcher.stop)

        self._socket_gethostbyname_patcher = mock.patch.object(
            inesdata.socket,
            "gethostbyname",
            return_value="127.0.0.1",
        )
        self._socket_gethostbyname_patcher.start()
        self.addCleanup(self._socket_gethostbyname_patcher.stop)

    def test_level6_attempts_vault_recovery_before_declaring_no_connectors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_isdir = os.path.isdir
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "ensure_vault_unsealed", return_value=True) as mock_unseal,
                mock.patch.object(
                    inesdata,
                    "get_connectors_from_cluster",
                    side_effect=[[], ["conn-a", "conn-b"]],
                ) as mock_get_connectors,
                mock.patch.object(
                    inesdata.INESDATA_ADAPTER.infrastructure,
                    "wait_for_namespace_pods",
                    return_value=True,
                ) as mock_wait_namespace,
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == os.path.join(inesdata.Config.script_dir(), "validation", "ui") else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            mock_unseal.assert_called_once_with()
            self.assertEqual(mock_get_connectors.call_count, 2)
            mock_wait_namespace.assert_called_once_with(inesdata.Config.namespace_demo(), timeout=120)

    def test_level6_fails_fast_when_connector_hosts_do_not_resolve(self):
        with (
            mock.patch.object(inesdata, "load_deployer_config", return_value={"DS_DOMAIN_BASE": "example.local"}),
            mock.patch.object(
                inesdata.INESDATA_ADAPTER.config_adapter,
                "generate_connector_hosts",
                return_value=[
                    "127.0.0.1 conn-a.example.local",
                    "127.0.0.1 conn-b.example.local",
                ],
            ),
            mock.patch.object(
                inesdata.INESDATA_ADAPTER.infrastructure,
                "manage_hosts_entries",
                return_value=None,
            ) as mock_manage_hosts,
            mock.patch.object(
                inesdata.socket,
                "gethostbyname",
                side_effect=OSError("Name or service not known"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Connector hostnames do not resolve locally"):
                inesdata._ensure_level6_connector_hosts(["conn-a", "conn-b"])

        mock_manage_hosts.assert_called_once()

    def test_level6_persists_storage_checks_exposed_by_validation_engine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_isdir = os.path.isdir

            def _run_validation(connectors, experiment_dir=None):
                inesdata.VALIDATION_ENGINE.last_storage_checks = [
                    {
                        "provider": "conn-a",
                        "consumer": "conn-b",
                        "status": "passed",
                        "bucket_name": "demo-conn-b",
                    }
                ]
                return ["pair-report.json"]

            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    side_effect=_run_validation,
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == os.path.join(inesdata.Config.script_dir(), "validation", "ui") else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(len(stored["storage_checks"]), 1)
            self.assertEqual(stored["storage_checks"][0]["status"], "passed")
            self.assertEqual(stored["storage_checks"][0]["bucket_name"], "demo-conn-b")

    def test_level6_creates_experiment_before_validation_and_passes_experiment_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_isdir = os.path.isdir
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ) as mock_validation,
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None) as mock_kafka,
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == os.path.join(inesdata.Config.script_dir(), "validation", "ui") else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            metadata_path = os.path.join(tmpdir, "metadata.json")
            experiment_results_path = os.path.join(tmpdir, "experiment_results.json")
            newman_reports_dir = os.path.join(tmpdir, "newman_reports")

            mock_validation.assert_called_once_with(["conn-a", "conn-b"], experiment_dir=tmpdir)
            mock_kafka.assert_called_once_with(tmpdir)
            self.assertTrue(os.path.exists(metadata_path))
            self.assertTrue(os.path.exists(experiment_results_path))
            self.assertTrue(os.path.isdir(newman_reports_dir))

            with open(experiment_results_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(stored["status"], "completed")
            self.assertEqual(stored["validation_reports"], ["pair-report.json"])
            self.assertEqual(stored["storage_checks"], [])
            self.assertEqual(stored["kafka_edc_results"], [])
            self.assertEqual(stored["ui_results"], [])
            self.assertEqual(stored["component_results"], [])
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "raw_requests.jsonl")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "aggregated_metrics.json")))

    def test_level6_persists_failed_state_when_validation_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_isdir = os.path.isdir
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    side_effect=RuntimeError("validation boom"),
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == os.path.join(inesdata.Config.script_dir(), "validation", "ui") else original_isdir(path),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "validation boom"):
                    inesdata.lvl_6()

            metadata_path = os.path.join(tmpdir, "metadata.json")
            experiment_results_path = os.path.join(tmpdir, "experiment_results.json")
            newman_reports_dir = os.path.join(tmpdir, "newman_reports")

            self.assertTrue(os.path.exists(metadata_path))
            self.assertTrue(os.path.exists(experiment_results_path))
            self.assertTrue(os.path.isdir(newman_reports_dir))

            with open(experiment_results_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(stored["status"], "failed")
            self.assertEqual(stored["error"]["type"], "RuntimeError")
            self.assertIn("validation boom", stored["error"]["message"])
            self.assertEqual(stored["storage_checks"], [])
            self.assertEqual(stored["kafka_edc_results"], [])
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "raw_requests.jsonl")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "aggregated_metrics.json")))

    def test_level6_collects_metrics_from_exported_newman_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_isdir = os.path.isdir
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    side_effect=lambda connectors, experiment_dir=None: _materialize_fixture_reports(experiment_dir),
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == os.path.join(inesdata.Config.script_dir(), "validation", "ui") else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            with open(os.path.join(tmpdir, "aggregated_metrics.json"), "r", encoding="utf-8") as handle:
                aggregated_metrics = json.load(handle)
            with open(os.path.join(tmpdir, "test_results.json"), "r", encoding="utf-8") as handle:
                test_results = json.load(handle)
            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(len(test_results), 5)
            self.assertEqual(len(stored["newman_request_metrics"]), 5)
            self.assertEqual(stored["storage_checks"], [])
            self.assertEqual(stored["kafka_edc_results"], [])
            self.assertIn("request_metrics", aggregated_metrics)
            self.assertEqual(aggregated_metrics["test_summary"]["tests_failed"], 1)

    def test_level6_routes_ui_smoke_evidence_into_experiment_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ui_test_dir = os.path.join(inesdata.Config.script_dir(), "validation", "ui")
            original_isdir = os.path.isdir
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(
                    inesdata,
                    "load_connector_credentials",
                    return_value={
                        "connector_user": {
                            "user": "portal-user",
                            "passwd": "portal-pass",
                        }
                    },
                ),
                mock.patch.object(
                    inesdata,
                    "build_connector_url",
                    side_effect=lambda connector: f"https://{connector}.example.local",
                ),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: True if path == ui_test_dir else original_isdir(path),
                ),
                mock.patch.object(
                    inesdata.subprocess,
                    "run",
                    return_value=mock.Mock(returncode=0),
                ) as mock_run,
            ):
                inesdata.lvl_6()

            self.assertEqual(mock_run.call_count, 2)

            first_call = mock_run.call_args_list[0]
            first_command = first_call.args[0]
            first_env = first_call.kwargs["env"]

            self.assertEqual(first_command[:3], ["npx", "playwright", "test"])
            self.assertEqual(first_command[3:], list(inesdata.LEVEL6_UI_SPECS))
            self.assertEqual(first_call.kwargs["cwd"], ui_test_dir)
            self.assertEqual(first_env["PORTAL_BASE_URL"], "https://conn-a.example.local")
            self.assertEqual(first_env["PORTAL_USER"], "portal-user")
            self.assertEqual(first_env["PORTAL_PASSWORD"], "portal-pass")
            self.assertEqual(
                first_env["PLAYWRIGHT_OUTPUT_DIR"],
                os.path.join(tmpdir, "ui", "conn-a", "test-results"),
            )
            self.assertEqual(
                first_env["PLAYWRIGHT_HTML_REPORT_DIR"],
                os.path.join(tmpdir, "ui", "conn-a", "playwright-report"),
            )
            self.assertEqual(
                first_env["PLAYWRIGHT_BLOB_REPORT_DIR"],
                os.path.join(tmpdir, "ui", "conn-a", "blob-report"),
            )
            self.assertEqual(
                first_env["PLAYWRIGHT_JSON_REPORT_FILE"],
                os.path.join(tmpdir, "ui", "conn-a", "results.json"),
            )

            self.assertTrue(os.path.isdir(os.path.join(tmpdir, "ui", "conn-a", "test-results")))
            self.assertTrue(os.path.isdir(os.path.join(tmpdir, "ui", "conn-a", "playwright-report")))
            self.assertTrue(os.path.isdir(os.path.join(tmpdir, "ui", "conn-a", "blob-report")))

            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(len(stored["ui_results"]), 2)
            self.assertEqual(stored["ui_results"][0]["test"], "ui-core-smoke")
            self.assertEqual(stored["ui_results"][0]["status"], "passed")
            self.assertEqual(
                stored["ui_results"][0]["artifacts"]["json_report_file"],
                os.path.join(tmpdir, "ui", "conn-a", "results.json"),
            )

    def test_level6_runs_component_validation_by_default_when_components_are_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ui_test_dir = os.path.join(inesdata.Config.script_dir(), "validation", "ui")
            original_isdir = os.path.isdir
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={"COMPONENTS": "ontology-hub"}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(
                    inesdata,
                    "_run_level6_component_validations",
                    return_value=[
                        {
                            "component": "ontology-hub",
                            "status": "passed",
                            "summary": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
                            "suites": {
                                "api": {"status": "passed"},
                                "ui": {"status": "passed"},
                            },
                        }
                    ],
                ) as mock_component_validation,
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == ui_test_dir else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            mock_component_validation.assert_called_once_with(tmpdir)
            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(len(stored["component_results"]), 1)
            self.assertEqual(stored["component_results"][0]["component"], "ontology-hub")
            self.assertEqual(stored["component_results"][0]["status"], "passed")
            self.assertEqual(stored["component_results"][0]["suites"]["api"]["status"], "passed")
            self.assertEqual(stored["component_results"][0]["suites"]["ui"]["status"], "passed")

    def test_level6_runs_optional_kafka_edc_validation_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ui_test_dir = os.path.join(inesdata.Config.script_dir(), "validation", "ui")
            original_isdir = os.path.isdir
            kafka_edc_results = [
                {
                    "provider": "conn-a",
                    "consumer": "conn-b",
                    "status": "passed",
                    "metrics": {
                        "messages_consumed": 5,
                        "average_latency_ms": 12.5,
                    },
                },
                {
                    "provider": "conn-b",
                    "consumer": "conn-a",
                    "status": "failed",
                    "error": {
                        "type": "RuntimeError",
                        "message": "EDR did not expose authKey/authCode",
                    },
                },
            ]
            with (
                mock.patch.dict(os.environ, {"LEVEL6_RUN_KAFKA_EDC": "true"}, clear=False),
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ),
                mock.patch.object(
                    inesdata,
                    "_run_level6_kafka_edc_validation",
                    return_value=kafka_edc_results,
                ) as mock_kafka_edc,
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == ui_test_dir else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            mock_kafka_edc.assert_called_once_with(["conn-a", "conn-b"], tmpdir)
            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(len(stored["kafka_edc_results"]), 2)
            self.assertEqual(stored["kafka_edc_results"][0]["status"], "passed")
            self.assertEqual(stored["kafka_edc_results"][0]["metrics"]["messages_consumed"], 5)
            self.assertEqual(stored["kafka_edc_results"][1]["status"], "failed")
            self.assertIn("authKey/authCode", stored["kafka_edc_results"][1]["error"]["message"])

    def test_level6_skips_component_validation_when_override_is_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ui_test_dir = os.path.join(inesdata.Config.script_dir(), "validation", "ui")
            original_isdir = os.path.isdir
            with (
                mock.patch.dict(os.environ, {"LEVEL6_RUN_COMPONENT_VALIDATION": "false"}, clear=False),
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={"COMPONENTS": "ontology-hub"}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(
                    inesdata,
                    "_run_level6_component_validations",
                    return_value=[
                        {
                            "component": "ontology-hub",
                            "status": "passed",
                        }
                    ],
                ) as mock_component_validation,
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == ui_test_dir else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            mock_component_validation.assert_not_called()
            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(stored["component_results"], [])

    def test_level6_marks_ui_smoke_skipped_when_playwright_command_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ui_test_dir = os.path.join(inesdata.Config.script_dir(), "validation", "ui")
            original_isdir = os.path.isdir
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(
                    inesdata,
                    "load_connector_credentials",
                    return_value={
                        "connector_user": {
                            "user": "portal-user",
                            "passwd": "portal-pass",
                        }
                    },
                ),
                mock.patch.object(
                    inesdata,
                    "build_connector_url",
                    side_effect=lambda connector: f"https://{connector}.example.local",
                ),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: True if path == ui_test_dir else original_isdir(path),
                ),
                mock.patch.object(
                    inesdata.subprocess,
                    "run",
                    side_effect=FileNotFoundError("npx not found"),
                ),
            ):
                inesdata.lvl_6()

            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(len(stored["ui_results"]), 2)
            self.assertEqual(stored["ui_results"][0]["status"], "skipped")
            self.assertIsNone(stored["ui_results"][0]["exit_code"])
            self.assertEqual(stored["ui_results"][0]["error"]["type"], "FileNotFoundError")
            self.assertIn("npx not found", stored["ui_results"][0]["error"]["message"])

    def test_level6_runs_optional_ui_ops_suite_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ui_test_dir = os.path.join(inesdata.Config.script_dir(), "validation", "ui")
            original_isdir = os.path.isdir
            with (
                mock.patch.dict(os.environ, {"LEVEL6_RUN_UI_OPS": "true"}, clear=False),
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "load_deployer_config", return_value={}),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(
                    inesdata.VALIDATION_ENGINE,
                    "run_all_dataspace_tests",
                    return_value=["pair-report.json"],
                ),
                mock.patch.object(inesdata, "_run_level6_kafka_benchmark", return_value=None),
                mock.patch.object(
                    inesdata,
                    "load_connector_credentials",
                    return_value={
                        "connector_user": {
                            "user": "portal-user",
                            "passwd": "portal-pass",
                        }
                    },
                ),
                mock.patch.object(
                    inesdata,
                    "build_connector_url",
                    side_effect=lambda connector: f"https://{connector}.example.local",
                ),
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: True if path == ui_test_dir else original_isdir(path),
                ),
                mock.patch.object(
                    inesdata.subprocess,
                    "run",
                    return_value=mock.Mock(returncode=0),
                ) as mock_run,
            ):
                inesdata.lvl_6()

            self.assertEqual(mock_run.call_count, 3)

            ops_call = mock_run.call_args_list[2]
            ops_command = ops_call.args[0]
            ops_env = ops_call.kwargs["env"]

            self.assertEqual(
                ops_command,
                [
                    "npx",
                    "playwright",
                    "test",
                    "--config",
                    inesdata.LEVEL6_UI_OPS_CONFIG,
                    inesdata.LEVEL6_UI_OPS_SPEC,
                ],
            )
            self.assertEqual(ops_call.kwargs["cwd"], ui_test_dir)
            self.assertEqual(ops_env["UI_PROVIDER_CONNECTOR"], "conn-a")
            self.assertEqual(ops_env["UI_CONSUMER_CONNECTOR"], "conn-b")
            self.assertEqual(
                ops_env["PLAYWRIGHT_OPS_OUTPUT_DIR"],
                os.path.join(tmpdir, "ui-ops", "minio-console", "test-results"),
            )
            self.assertEqual(
                ops_env["PLAYWRIGHT_OPS_HTML_REPORT_DIR"],
                os.path.join(tmpdir, "ui-ops", "minio-console", "playwright-report"),
            )
            self.assertEqual(
                ops_env["PLAYWRIGHT_OPS_BLOB_REPORT_DIR"],
                os.path.join(tmpdir, "ui-ops", "minio-console", "blob-report"),
            )
            self.assertEqual(
                ops_env["PLAYWRIGHT_OPS_JSON_REPORT_FILE"],
                os.path.join(tmpdir, "ui-ops", "minio-console", "results.json"),
            )

            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

            self.assertEqual(len(stored["ui_results"]), 3)
            self.assertEqual(stored["ui_results"][2]["test"], "ui-ops-minio-console")
            self.assertEqual(stored["ui_results"][2]["status"], "passed")
            self.assertEqual(stored["ui_results"][2]["provider_connector"], "conn-a")
            self.assertEqual(stored["ui_results"][2]["consumer_connector"], "conn-b")


if __name__ == "__main__":
    unittest.main()
