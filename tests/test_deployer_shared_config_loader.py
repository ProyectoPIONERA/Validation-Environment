import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deployers.shared.lib.config_loader import (
    iter_dataspace_slots,
    load_deployer_config,
    load_layered_deployer_config,
)


class SharedConfigLoaderTests(unittest.TestCase):
    def test_load_deployer_config_reads_key_value_pairs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "deployer.config")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "# comment\n"
                    "DS_1_NAME=demoedc\n"
                    "DS_1_NAMESPACE=demoedc\n"
                    "COMMON_SERVICES_NAMESPACE=common-srvs\n"
                )

            config = load_deployer_config(path)

        self.assertEqual(config["DS_1_NAME"], "demoedc")
        self.assertEqual(config["DS_1_NAMESPACE"], "demoedc")
        self.assertEqual(config["COMMON_SERVICES_NAMESPACE"], "common-srvs")

    def test_load_layered_deployer_config_applies_ordered_overlays(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            common_path = os.path.join(tmpdir, "common.config")
            adapter_path = os.path.join(tmpdir, "adapter.config")
            with open(common_path, "w", encoding="utf-8") as handle:
                handle.write("KC_URL=http://shared-keycloak\nDS_1_NAME=shared\n")
            with open(adapter_path, "w", encoding="utf-8") as handle:
                handle.write("DS_1_NAME=adapter\n")

            config = load_layered_deployer_config(
                [common_path, adapter_path],
                defaults={"KC_USER": "admin"},
                apply_environment=False,
            )

        self.assertEqual(config["KC_USER"], "admin")
        self.assertEqual(config["KC_URL"], "http://shared-keycloak")
        self.assertEqual(config["DS_1_NAME"], "adapter")

    def test_iter_dataspace_slots_groups_values_per_slot(self):
        slots = iter_dataspace_slots(
            {
                "DS_1_NAME": "demo",
                "DS_1_NAMESPACE": "demo",
                "DS_2_NAME": "demoedc",
                "DS_2_CONNECTORS": "citycounciledc,companyedc",
                "UNRELATED": "ignored",
            }
        )

        self.assertEqual(
            slots,
            [
                {"slot": "1", "NAME": "demo", "NAMESPACE": "demo"},
                {"slot": "2", "NAME": "demoedc", "CONNECTORS": "citycounciledc,companyedc"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
