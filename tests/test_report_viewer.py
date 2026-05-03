import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from validation.orchestration import reports


class FakeProcess:
    pid = 12345

    def poll(self):
        return None

    def terminate(self):
        return None


class FakeSubprocess:
    def __init__(self):
        self.calls = []

    def Popen(self, command, **kwargs):
        self.calls.append({"command": command, "kwargs": kwargs})
        return FakeProcess()


class ReportViewerTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _create_experiment(self, root):
        experiment = Path(root) / "experiments" / "experiment_2026-05-03_10-00-00"
        self._write_json(
            experiment / "metadata.json",
            {
                "timestamp": "2026-05-03T10:00:00",
                "adapter": "InesdataAdapter",
                "topology": "local",
                "cluster": "minikube",
            },
        )
        (experiment / "ui" / "inesdata" / "playwright-report").mkdir(parents=True)
        (experiment / "ui" / "inesdata" / "playwright-report" / "index.html").write_text(
            "<html>playwright</html>",
            encoding="utf-8",
        )
        self._write_json(
            experiment / "ui" / "inesdata" / "results.json",
            {
                "suites": [
                    {
                        "specs": [
                            {
                                "tests": [
                                    {"status": "expected"},
                                    {"status": "unexpected"},
                                ]
                            }
                        ]
                    }
                ]
            },
        )
        self._write_json(
            experiment / "test_results.json",
            [
                {"status": "pass", "test_name": "ok"},
                {"status": "fail", "test_name": "not ok"},
            ],
        )
        self._write_json(
            experiment / "newman_results.json",
            [{"checks": [{"ok": True}, {"ok": False}]}],
        )
        self._write_json(
            experiment / "kafka_transfer_results.json",
            [
                {
                    "status": "passed",
                    "metrics": {
                        "average_latency_ms": 10.5,
                        "throughput_messages_per_second": 42.0,
                    },
                }
            ],
        )
        self._write_json(
            experiment / "local_stability_postflight.json",
            {
                "blocking_issues": [],
                "comparison": {
                    "status": "warning",
                    "warnings": [{"name": "pod_restart_delta"}],
                    "node_not_ready_delta": 0,
                },
            },
        )
        self._write_json(
            experiment / "components" / "ontology-hub" / "ontology_hub_component_validation.json",
            {
                "component": "ontology-hub",
                "status": "failed",
                "summary": {"total": 4, "passed": 3, "failed": 1, "skipped": 0},
                "runtime": {"adminPassword": "must-not-appear-in-dashboard"},
            },
        )
        return experiment

    def test_discovers_experiments_and_report_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_experiment(tmp)

            experiments = reports.discover_report_experiments(root=tmp)

        self.assertEqual(len(experiments), 1)
        experiment = experiments[0]
        self.assertEqual(experiment["name"], "experiment_2026-05-03_10-00-00")
        self.assertEqual(experiment["adapter"], "inesdata")
        self.assertEqual(experiment["topology"], "local")
        self.assertEqual(experiment["cluster_runtime"], "minikube")
        self.assertIn("Playwright", experiment["reports"])
        self.assertIn("Newman", experiment["reports"])
        self.assertIn("Kafka", experiment["reports"])
        self.assertIn("Components", experiment["reports"])
        self.assertIn("Stability", experiment["reports"])

    def test_dashboard_summarizes_without_leaking_runtime_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment_path = self._create_experiment(tmp)
            experiment = reports.inspect_experiment(experiment_path)

            dashboard = reports.build_experiment_dashboard(experiment)
            content = dashboard.read_text(encoding="utf-8")

        self.assertIn("Framework validation dashboard", content)
        self.assertIn("Dashboard status", content)
        self.assertIn("Cluster runtime", content)
        self.assertIn("Open ui / inesdata", content)
        self.assertIn("Newman", content)
        self.assertIn("Kafka transfer", content)
        self.assertNotIn("must-not-appear-in-dashboard", content)

    def test_legacy_metadata_does_not_use_minikube_as_topology(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "experiments" / "experiment_2026-05-03_11-00-00"
            self._write_json(
                experiment / "metadata.json",
                {
                    "timestamp": "2026-05-03T11:00:00",
                    "adapter": "EdcAdapter",
                    "cluster": "minikube",
                    "environment": "minikube",
                },
            )

            inspected = reports.inspect_experiment(experiment)

        self.assertEqual(inspected["topology"], "not recorded")
        self.assertEqual(inspected["cluster_runtime"], "minikube")
        self.assertEqual(inspected["adapter"], "edc")

    def test_stability_existing_warnings_are_not_reported_as_new_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "experiments" / "experiment_2026-05-03_12-00-00"
            self._write_json(
                experiment / "local_stability_postflight.json",
                {
                    "blocking_issues": [],
                    "comparison": {
                        "status": "warning",
                        "warnings": [],
                        "node_not_ready_delta": 0,
                    },
                    "snapshot": {
                        "warnings": [{"name": "pod_restarts"}],
                    },
                },
            )

            inspected = reports.inspect_experiment(experiment)

        stability = next(suite for suite in inspected["suites"] if suite["kind"] == "stability")
        self.assertEqual(stability["status"], "warning-existing")
        self.assertEqual(stability["warnings"], 0)
        self.assertEqual(stability["snapshot_warnings"], 1)
        self.assertEqual(inspected["result"], "Warnings detected")

    def test_component_playwright_json_is_not_duplicated_when_component_summary_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "experiments" / "experiment_2026-05-03_13-00-00"
            self._write_json(
                experiment / "components" / "ontology-hub" / "ontology_hub_component_validation.json",
                {
                    "component": "ontology-hub",
                    "status": "failed",
                    "summary": {"total": 1, "passed": 0, "failed": 1, "skipped": 0},
                },
            )
            self._write_json(
                experiment / "components" / "ontology-hub" / "functional" / "results.json",
                {
                    "suites": [
                        {
                            "specs": [
                                {"tests": [{"status": "unexpected"}]},
                            ]
                        }
                    ]
                },
            )

            inspected = reports.inspect_experiment(experiment)

        titles = [suite["title"] for suite in inspected["suites"]]
        self.assertEqual(titles.count("ontology-hub"), 1)
        self.assertNotIn("components / ontology-hub / functional", titles)

    def test_static_report_server_binds_only_to_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_subprocess = FakeSubprocess()
            result = reports.launch_static_report_server(
                tmp,
                port=9341,
                subprocess_module=fake_subprocess,
                python_executable="python3",
                wait_for_server=lambda host, port: True,
            )

        self.assertEqual(result["url"], "http://127.0.0.1:9341")
        self.assertTrue(result["ready"])
        command = fake_subprocess.calls[0]["command"]
        self.assertIn("--bind", command)
        self.assertIn("127.0.0.1", command)
        with self.assertRaises(ValueError):
            reports.launch_static_report_server(tmp, host="0.0.0.0", subprocess_module=fake_subprocess)

    def test_playwright_report_launcher_uses_official_show_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "experiments" / "experiment_1" / "ui" / "inesdata" / "playwright-report"
            report_dir.mkdir(parents=True)
            (report_dir / "index.html").write_text("<html></html>", encoding="utf-8")
            (root / "validation" / "ui").mkdir(parents=True)
            fake_subprocess = FakeSubprocess()

            result = reports.launch_playwright_report(
                report_dir,
                root=root,
                port=9444,
                subprocess_module=fake_subprocess,
                wait_for_server=lambda host, port: True,
            )

        self.assertEqual(result["url"], "http://127.0.0.1:9444")
        self.assertTrue(result["ready"])
        command = fake_subprocess.calls[0]["command"]
        self.assertEqual(command[:3], ["npx", "playwright", "show-report"])
        self.assertIn("--host", command)
        self.assertIn("127.0.0.1", command)
        self.assertIn("--port", command)
        self.assertIn("9444", command)

    def test_local_url_open_uses_windows_cmd_fallback_when_wslview_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_cmd = root / "cmd.exe"
            fake_cmd.write_text("", encoding="utf-8")
            fake_subprocess = FakeSubprocess()

            with mock.patch("validation.orchestration.reports.shutil.which", return_value=None), mock.patch.object(
                reports, "WINDOWS_CMD_EXE", fake_cmd
            ), mock.patch.object(
                reports, "WINDOWS_POWERSHELL_EXE", root / "missing-powershell.exe"
            ), mock.patch.object(
                reports, "WINDOWS_EXPLORER_EXE", root / "missing-explorer.exe"
            ):
                result = reports.open_local_url(
                    "http://127.0.0.1:9000/framework-report/index.html",
                    subprocess_module=fake_subprocess,
                )

        self.assertTrue(result["opened"])
        self.assertEqual(result["method"], "windows-cmd-start")
        command = fake_subprocess.calls[0]["command"]
        self.assertEqual(command[:4], [str(fake_cmd), "/c", "start", ""])
        self.assertEqual(command[-1], "http://127.0.0.1:9000/framework-report/index.html")


if __name__ == "__main__":
    unittest.main()
