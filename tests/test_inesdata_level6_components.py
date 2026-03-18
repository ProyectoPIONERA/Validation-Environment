import contextlib
import io
import unittest
from unittest import mock

import inesdata


class InesdataLevel6ComponentsTests(unittest.TestCase):
    def test_lvl_5_uses_deployer_config_without_prompt_and_prints_urls(self):
        class FakeComponentsAdapter:
            def __init__(self, *args, **kwargs):
                pass

            def list_deployable_components(self):
                return ["ontology-hub"]

            def deploy_components(self, components):
                self.components = components
                return {
                    "deployed": ["ontology-hub"],
                    "urls": {
                        "ontology-hub": "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
                    },
                }

        with (
            mock.patch("adapters.inesdata.components.INESDataComponentsAdapter", FakeComponentsAdapter),
            mock.patch.object(inesdata, "copy_local_deployer_config", lambda: None),
            mock.patch.object(inesdata, "load_deployer_config", lambda: {"COMPONENTS": "ontology-hub"}),
            mock.patch("builtins.input") as mock_input,
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                deployed = inesdata.lvl_5()

        self.assertEqual(deployed, ["ontology-hub"])
        mock_input.assert_not_called()
        self.assertIn("- ontology-hub: http://ontology-hub-demo.dev.ds.dataspaceunit.upm", output.getvalue())


if __name__ == "__main__":
    unittest.main()
