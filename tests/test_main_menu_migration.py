import sys
import unittest
from unittest import mock

import main
from tests.test_main_cli import FakeMetricsCollector, FakeStorage, FakeValidationEngine


class MainMenuMigrationTests(unittest.TestCase):
    def setUp(self):
        self.adapter_registry = {"fake": "fake_adapter_module:FakeAdapter"}
        self.deployer_registry = {"fake": "fake_deployer_module:FakeDeployer"}

    def test_tools_submenu_runs_migrated_action_without_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch(
            "builtins.input",
            side_effect=["T", "1", "B", "Q"],
        ), mock.patch.object(
            main.local_menu_tools,
            "run_framework_bootstrap_interactive",
            return_value="bootstrap-ok",
        ) as bootstrap:
            result = main.main(
                ["menu"],
                adapter_registry=self.adapter_registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        bootstrap.assert_called_once_with()

    def test_ui_submenu_runs_migrated_action_without_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch(
            "builtins.input",
            side_effect=["U", "3", "B", "Q"],
        ), mock.patch.object(
            main.ui_interactive_menu,
            "run_ai_model_hub_ui_tests_interactive",
            return_value="ai-model-ui-ok",
        ) as ai_model_hub:
            result = main.main(
                ["menu"],
                adapter_registry=self.adapter_registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        ai_model_hub.assert_called_once_with()

    def test_legacy_shortcuts_are_routed_by_main_without_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch(
            "builtins.input",
            side_effect=["B", "I", "Q"],
        ), mock.patch.object(
            main.local_menu_tools,
            "run_framework_bootstrap_interactive",
            return_value="bootstrap-ok",
        ) as bootstrap, mock.patch.object(
            main.ui_interactive_menu,
            "run_inesdata_ui_tests_interactive",
            return_value="inesdata-ui-ok",
        ) as inesdata_ui:
            result = main.main(
                ["menu"],
                adapter_registry=self.adapter_registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        bootstrap.assert_called_once_with()
        inesdata_ui.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
