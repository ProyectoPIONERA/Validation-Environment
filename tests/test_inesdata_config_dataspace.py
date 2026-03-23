import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.inesdata.config import INESDataConfigAdapter


class DataspaceAwareConfig:
    DS_NAME = "demo"

    def __init__(self, root):
        self.root = root

    def deployer_config_path(self):
        return os.path.join(self.root, "deployer.config")


class InesdataConfigDataspaceTests(unittest.TestCase):
    def test_primary_dataspace_name_prefers_deployer_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DataspaceAwareConfig(tmpdir)
            with open(config.deployer_config_path(), "w", encoding="utf-8") as handle:
                handle.write("DS_1_NAME=pilot\n")

            adapter = INESDataConfigAdapter(config)

            self.assertEqual(adapter.primary_dataspace_name(), "pilot")

    def test_primary_dataspace_namespace_prefers_deployer_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DataspaceAwareConfig(tmpdir)
            with open(config.deployer_config_path(), "w", encoding="utf-8") as handle:
                handle.write("DS_1_NAME=pilot\nDS_1_NAMESPACE=pilot-ns\n")

            adapter = INESDataConfigAdapter(config)

            self.assertEqual(adapter.primary_dataspace_namespace(), "pilot-ns")

    def test_primary_dataspace_namespace_falls_back_to_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DataspaceAwareConfig(tmpdir)
            with open(config.deployer_config_path(), "w", encoding="utf-8") as handle:
                handle.write("DS_1_NAME=pilot\n")

            adapter = INESDataConfigAdapter(config)

            self.assertEqual(adapter.primary_dataspace_namespace(), "pilot")


if __name__ == "__main__":
    unittest.main()
