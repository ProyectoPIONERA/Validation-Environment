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
