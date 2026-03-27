import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("helm"), "helm binary is required for chart rendering tests")
class OntologyHubChartSampleDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validation_environment_dir = Path(__file__).resolve().parents[1]
        cls.chart_dir = (
            cls.validation_environment_dir
            / "inesdata-deployment"
            / "components"
            / "ontology-hub"
        )

    def _render_chart(self, values_file: str) -> str:
        rendered = subprocess.run(
            [
                "helm",
                "template",
                "ontology-hub-test",
                str(self.chart_dir),
                "-f",
                str(self.chart_dir / values_file),
            ],
            cwd=self.validation_environment_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return rendered.stdout

    def test_demo_values_render_sample_data_resources(self):
        rendered = self._render_chart("values-demo.yaml")

        self.assertIn("name: ontology-hub-test-sample-data", rendered)
        self.assertIn("seed-ontology-hub-mongodb", rendered)
        self.assertIn("seed-ontology-hub-elasticsearch", rendered)
        self.assertIn("prepare-ontology-hub-version-files", rendered)
        self.assertIn("mongo-vocabularies.json", rendered)
        self.assertIn("version-latest.n3", rendered)
        self.assertIn("\"index.default_pipeline\": \"ontology-hub-sample-data\"", rendered)

    def test_default_values_do_not_render_optional_sample_data_resources(self):
        rendered = self._render_chart("values.yaml")

        self.assertNotIn("name: ontology-hub-test-sample-data", rendered)
        self.assertNotIn("seed-ontology-hub-mongodb", rendered)
        self.assertNotIn("seed-ontology-hub-elasticsearch", rendered)
        self.assertNotIn("prepare-ontology-hub-version-files", rendered)
        self.assertNotIn("ontology-hub-versions", rendered)


if __name__ == "__main__":
    unittest.main()
