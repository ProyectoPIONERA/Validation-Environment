import unittest
from unittest import mock
import os
import tempfile

import inesdata


class InesdataMenuCliTests(unittest.TestCase):
    @mock.patch.object(inesdata.framework_cli, "main", return_value={"status": "ok"})
    @mock.patch.object(inesdata.framework_cli, "print_available_adapters", return_value=["inesdata", "fake"])
    def test_run_new_cli_interactive_uses_defaults(self, mock_list, mock_main):
        with mock.patch("builtins.input", side_effect=["", "", "N"]):
            result = inesdata.run_new_cli_interactive()

        self.assertEqual(result, {"status": "ok"})
        mock_list.assert_called_once()
        mock_main.assert_called_once_with(["inesdata", "run"])

    @mock.patch.object(inesdata.framework_cli, "main", return_value={"status": "dry-run"})
    @mock.patch.object(inesdata.framework_cli, "print_available_adapters", return_value=["inesdata", "fake"])
    def test_run_new_cli_interactive_supports_dry_run(self, mock_list, mock_main):
        with mock.patch("builtins.input", side_effect=["fake", "deploy", "Y"]):
            result = inesdata.run_new_cli_interactive()

        self.assertEqual(result, {"status": "dry-run"})
        mock_main.assert_called_once_with(["fake", "deploy", "--dry-run"])

    @mock.patch.object(inesdata.framework_cli, "main")
    @mock.patch.object(inesdata.framework_cli, "print_available_adapters", return_value=["inesdata"])
    def test_run_new_cli_interactive_rejects_unknown_adapter(self, mock_list, mock_main):
        with mock.patch("builtins.input", side_effect=["unknown"]):
            result = inesdata.run_new_cli_interactive()

        self.assertIsNone(result)
        mock_main.assert_not_called()

    @mock.patch.object(inesdata, "run_new_cli_interactive")
    def test_show_menu_routes_option_n_to_new_cli(self, mock_run_new_cli):
        with mock.patch("builtins.input", side_effect=["N", "Q"]):
            inesdata.show_menu()

        mock_run_new_cli.assert_called_once()

    @mock.patch.object(inesdata, "run_local_images_workflow_interactive")
    def test_show_menu_routes_option_l_to_local_workflow(self, mock_run_local_workflow):
        with mock.patch("builtins.input", side_effect=["L", "Q"]):
            inesdata.show_menu()

        mock_run_local_workflow.assert_called_once()

    @mock.patch.object(inesdata, "run_workspace_cleanup_interactive")
    def test_show_menu_routes_option_c_to_workspace_cleanup(self, mock_cleanup):
        with mock.patch("builtins.input", side_effect=["C", "Q"]):
            inesdata.show_menu()

        mock_cleanup.assert_called_once()

    @mock.patch.object(inesdata, "run_framework_bootstrap_interactive")
    def test_show_menu_routes_option_b_to_framework_bootstrap(self, mock_bootstrap):
        with mock.patch("builtins.input", side_effect=["B", "Q"]):
            inesdata.show_menu()

        mock_bootstrap.assert_called_once()

    @mock.patch.object(inesdata, "run_framework_doctor")
    def test_show_menu_routes_option_d_to_framework_doctor(self, mock_doctor):
        with mock.patch("builtins.input", side_effect=["D", "Q"]):
            inesdata.show_menu()

        mock_doctor.assert_called_once()

    @mock.patch.object(inesdata, "run_connector_recovery_after_wsl_restart")
    def test_show_menu_routes_option_r_to_connector_recovery(self, mock_recovery):
        with mock.patch("builtins.input", side_effect=["R", "Q"]):
            inesdata.show_menu()

        mock_recovery.assert_called_once()

    @mock.patch.object(inesdata, "run_ai_model_hub_ui_tests_interactive")
    def test_show_menu_routes_option_a_to_ai_model_hub_ui_tests(self, mock_run_ai_model_hub_ui):
        with mock.patch("builtins.input", side_effect=["A", "Q"]):
            inesdata.show_menu()

        mock_run_ai_model_hub_ui.assert_called_once()

    @mock.patch.object(inesdata, "_run_ai_model_hub_ui_functional")
    @mock.patch.object(inesdata, "_resolve_ui_mode", return_value={"label": "Normal", "args": [], "env": {}})
    def test_run_ai_model_hub_ui_tests_interactive_routes_functional(
        self,
        _mock_resolve_mode,
        mock_run_functional,
    ):
        with mock.patch("builtins.input", side_effect=["1"]):
            inesdata.run_ai_model_hub_ui_tests_interactive()

        mock_run_functional.assert_called_once_with({"label": "Normal", "args": [], "env": {}})

    @mock.patch.object(inesdata, "_run_ai_model_hub_ui_integration")
    @mock.patch.object(inesdata, "_resolve_ui_mode", return_value={"label": "Normal", "args": [], "env": {}})
    def test_run_ai_model_hub_ui_tests_interactive_routes_integration(
        self,
        _mock_resolve_mode,
        mock_run_integration,
    ):
        with mock.patch("builtins.input", side_effect=["2"]):
            inesdata.run_ai_model_hub_ui_tests_interactive()

        mock_run_integration.assert_called_once_with({"label": "Normal", "args": [], "env": {}})

    @mock.patch.object(inesdata, "run_ai_model_hub_ui_tests_interactive")
    def test_run_inesdata_ui_tests_interactive_routes_ai_model_hub_to_submenu(self, mock_run_ai_model_hub_ui):
        with mock.patch("builtins.input", side_effect=["3"]):
            inesdata.run_inesdata_ui_tests_interactive()

        mock_run_ai_model_hub_ui.assert_called_once()

    @mock.patch.object(inesdata, "run")
    @mock.patch.object(inesdata.subprocess, "run")
    @mock.patch.object(inesdata.Config, "script_dir")
    @mock.patch.object(inesdata, "_resolve_ai_model_hub_base_url", return_value="http://example.test")
    def test_run_ai_model_hub_ui_functional_uses_absolute_artifact_paths(
        self,
        _mock_resolve_base_url,
        mock_script_dir,
        mock_subprocess_run,
        mock_run,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_script_dir.return_value = tmpdir
            mock_subprocess_run.return_value = mock.Mock(returncode=0)

            inesdata._run_ai_model_hub_ui_functional({"label": "Normal", "args": [], "env": {}})

            mock_subprocess_run.assert_called_once()
            env = mock_subprocess_run.call_args.kwargs["env"]
            cwd = mock_subprocess_run.call_args.kwargs["cwd"]
            base_experiments_dir = os.path.join(tmpdir, "experiments")

            self.assertEqual(cwd, "validation/ui")
            self.assertTrue(env["PLAYWRIGHT_OUTPUT_DIR"].startswith(base_experiments_dir))
            self.assertTrue(env["PLAYWRIGHT_HTML_REPORT_DIR"].startswith(base_experiments_dir))
            self.assertTrue(env["PLAYWRIGHT_BLOB_REPORT_DIR"].startswith(base_experiments_dir))
            self.assertTrue(env["PLAYWRIGHT_JSON_REPORT_FILE"].startswith(base_experiments_dir))
            self.assertTrue(os.path.isdir(env["PLAYWRIGHT_OUTPUT_DIR"]))
            self.assertTrue(os.path.isdir(env["PLAYWRIGHT_HTML_REPORT_DIR"]))
            self.assertTrue(os.path.isdir(env["PLAYWRIGHT_BLOB_REPORT_DIR"]))
            mock_run.assert_called_once_with("pkill -f '(chrome|chromium).*playwright' || true", check=False)

    @mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True)
    @mock.patch.object(inesdata, "_ensure_level6_connector_hosts", return_value=None)
    @mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"])
    @mock.patch.object(inesdata, "ensure_vault_unsealed", return_value=True)
    @mock.patch.object(inesdata, "wait_for_vault_pod", return_value=True)
    @mock.patch.object(inesdata, "run")
    def test_run_connector_recovery_after_wsl_restart_restarts_detected_connectors(
        self,
        mock_run,
        _mock_wait_for_vault,
        _mock_unseal,
        _mock_get_connectors,
        _mock_hosts,
        mock_validate,
    ):
        mock_run.return_value = mock.Mock(returncode=0)

        result = inesdata.run_connector_recovery_after_wsl_restart()

        self.assertTrue(result)
        commands = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn("kubectl rollout restart deployment/conn-a -n demo", commands)
        self.assertIn("kubectl rollout restart deployment/conn-b -n demo", commands)
        self.assertIn("kubectl rollout status deployment/conn-a -n demo --timeout=180s", commands)
        self.assertIn("kubectl rollout status deployment/conn-b -n demo --timeout=180s", commands)
        mock_validate.assert_called_once_with(["conn-a", "conn-b"])

    @mock.patch.object(inesdata, "_get_connector_runtime_deployments", return_value=["conn-a"])
    @mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=[])
    @mock.patch.object(inesdata, "ensure_vault_unsealed", return_value=True)
    @mock.patch.object(inesdata, "wait_for_vault_pod", return_value=True)
    @mock.patch.object(inesdata, "_ensure_level6_connector_hosts", return_value=None)
    @mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True)
    @mock.patch.object(inesdata, "run")
    def test_run_connector_recovery_after_wsl_restart_falls_back_to_deployments_when_no_pods(
        self,
        mock_run,
        _mock_validate,
        _mock_hosts,
        _mock_wait_for_vault,
        _mock_unseal,
        _mock_get_connectors,
        _mock_get_deployments,
    ):
        mock_run.return_value = mock.Mock(returncode=0)

        result = inesdata.run_connector_recovery_after_wsl_restart()

        self.assertTrue(result)
        commands = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn("kubectl rollout restart deployment/conn-a -n demo", commands)

    def test_show_menu_blocks_guarded_level_when_deployer_config_is_not_ready(self):
        blocked_level = mock.Mock()

        with (
            mock.patch.dict(inesdata.LEVELS, {"2": blocked_level}, clear=False),
            mock.patch.object(inesdata, "_ensure_local_deployer_config_ready_for_levels", return_value=False) as mock_guard,
            mock.patch("builtins.input", side_effect=["2", "Q"]),
        ):
            inesdata.show_menu()

        mock_guard.assert_called_once_with({"2"})
        blocked_level.assert_not_called()

    def test_run_all_levels_stops_early_when_deployer_config_is_not_ready(self):
        with mock.patch.object(
            inesdata,
            "_ensure_local_deployer_config_ready_for_levels",
            return_value=False,
        ) as mock_guard:
            inesdata.run_all_levels()

        mock_guard.assert_called_once_with(inesdata.CONFIG_GUARDED_LEVELS)

    def test_validate_local_deployer_config_for_levels_fails_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(inesdata.Config, "script_dir", return_value=tmpdir):
                ready, issues = inesdata._validate_local_deployer_config_for_levels({"2"})

        self.assertFalse(ready)
        self.assertEqual(len(issues), 1)
        self.assertIn("Missing local deployer.config", issues[0])

    def test_validate_local_deployer_config_for_levels_passes_with_example_shaped_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            example_path = os.path.join(tmpdir, "deployer.config.example")
            config_path = os.path.join(tmpdir, "deployer.config")
            content = "\n".join(
                [
                    "ENVIRONMENT=DEV",
                    "PG_HOST=localhost",
                    "PG_USER=postgres",
                    "PG_PASSWORD=secret",
                    "KC_URL=http://keycloak-admin.dev.ed.dataspaceunit.upm",
                    "KC_USER=admin",
                    "KC_PASSWORD=secret",
                    "KC_INTERNAL_URL=http://keycloak.dev.ed.dataspaceunit.upm",
                    "VT_URL=http://localhost:8200",
                    "VT_TOKEN=X",
                    "DATABASE_HOSTNAME=common-srvs-postgresql.common-srvs.svc",
                    "KEYCLOAK_HOSTNAME=keycloak.dev.ed.dataspaceunit.upm",
                    "MINIO_HOSTNAME=minio.dev.ed.dataspaceunit.upm",
                    "VAULT_URL=http://common-srvs-vault.common-srvs.svc:8200",
                    "DOMAIN_BASE=dev.ed.dataspaceunit.upm",
                    "DS_DOMAIN_BASE=dev.ds.dataspaceunit.upm",
                    "MINIO_USER=admin",
                    "MINIO_PASSWORD=secret",
                    "DS_1_NAME=demo",
                    "DS_1_NAMESPACE=demo",
                    "DS_1_CONNECTORS=citycouncil,company",
                    "COMPONENTS=ontology-hub",
                ]
            )
            with open(example_path, "w", encoding="utf-8") as handle:
                handle.write(content + "\n")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(content + "\n")

            with mock.patch.object(inesdata.Config, "script_dir", return_value=tmpdir):
                ready, issues = inesdata._validate_local_deployer_config_for_levels({"2", "6"})

        self.assertTrue(ready)
        self.assertEqual(issues, [])

    @mock.patch.object(inesdata.os.path, "isfile", return_value=True)
    @mock.patch.object(inesdata.subprocess, "run")
    def test_run_workspace_cleanup_interactive_runs_include_results_mode(self, mock_run, _mock_isfile):
        mock_run.return_value = mock.Mock(returncode=0)

        with mock.patch("builtins.input", side_effect=["2", "Y"]):
            inesdata.run_workspace_cleanup_interactive()

        script_path = os.path.join(inesdata.Config.script_dir(), "scripts", "clean_workspace.sh")
        mock_run.assert_called_once_with(
            ["bash", script_path, "--apply", "--include-results"],
            cwd=inesdata.Config.script_dir(),
        )

    @mock.patch.object(inesdata.os.path, "isfile", return_value=True)
    @mock.patch.object(inesdata.subprocess, "run")
    def test_run_framework_bootstrap_interactive_executes_bootstrap_script(self, mock_run, _mock_isfile):
        mock_run.return_value = mock.Mock(returncode=0)

        with mock.patch("builtins.input", side_effect=["Y"]):
            inesdata.run_framework_bootstrap_interactive()

        script_path = os.path.join(inesdata.Config.script_dir(), "scripts", "bootstrap_framework.sh")
        mock_run.assert_called_once_with(
            ["bash", script_path],
            cwd=inesdata.Config.script_dir(),
        )


if __name__ == "__main__":
    unittest.main()
