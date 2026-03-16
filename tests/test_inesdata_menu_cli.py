import unittest
from unittest import mock
import os

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


if __name__ == "__main__":
    unittest.main()
