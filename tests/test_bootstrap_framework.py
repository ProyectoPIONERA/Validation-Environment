import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class BootstrapFrameworkTests(unittest.TestCase):
    def _prepare_workspace(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = tmpdir.name

        os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
        shutil.copy2(
            os.path.join(PROJECT_ROOT, "scripts", "bootstrap_framework.sh"),
            os.path.join(root, "scripts", "bootstrap_framework.sh"),
        )

        with open(os.path.join(root, "requirements.txt"), "w", encoding="utf-8") as handle:
            handle.write("")

        for deployer, marker in (("infrastructure", "KC_URL=http://keycloak.local\n"), ("inesdata", "DS_1_NAME=demo\n")):
            deployer_dir = os.path.join(root, "deployers", deployer)
            os.makedirs(deployer_dir, exist_ok=True)
            with open(os.path.join(deployer_dir, "deployer.config.example"), "w", encoding="utf-8") as handle:
                handle.write(marker)

        fake_bin = os.path.join(root, "fake-bin")
        os.makedirs(fake_bin, exist_ok=True)
        fake_python = os.path.join(fake_bin, "python3")
        with open(fake_python, "w", encoding="utf-8") as handle:
            handle.write(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
                      venv_dir="${3:?}"
                      mkdir -p "$venv_dir/bin"
                      cat > "$venv_dir/bin/python" <<'PY'
                    #!/usr/bin/env bash
                    exit 0
                    PY
                      chmod +x "$venv_dir/bin/python"
                    fi
                    exit 0
                    """
                )
            )
        os.chmod(fake_python, os.stat(fake_python).st_mode | stat.S_IXUSR)
        return root, fake_bin

    def test_bootstrap_initializes_infrastructure_and_inesdata_configs(self):
        root, fake_bin = self._prepare_workspace()
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

        result = subprocess.run(
            [
                "bash",
                os.path.join(root, "scripts", "bootstrap_framework.sh"),
                "--skip-root-node",
                "--skip-ui-node",
                "--skip-playwright",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(os.path.isfile(os.path.join(root, "deployers", "infrastructure", "deployer.config")))
        self.assertTrue(os.path.isfile(os.path.join(root, "deployers", "inesdata", "deployer.config")))

        with open(os.path.join(root, "deployers", "infrastructure", "deployer.config"), encoding="utf-8") as handle:
            self.assertIn("KC_URL=http://keycloak.local", handle.read())
        with open(os.path.join(root, "deployers", "inesdata", "deployer.config"), encoding="utf-8") as handle:
            self.assertIn("DS_1_NAME=demo", handle.read())

    def test_bootstrap_skip_deployer_config_leaves_configs_absent(self):
        root, fake_bin = self._prepare_workspace()
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

        result = subprocess.run(
            [
                "bash",
                os.path.join(root, "scripts", "bootstrap_framework.sh"),
                "--skip-root-node",
                "--skip-ui-node",
                "--skip-playwright",
                "--skip-deployer-config",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(os.path.exists(os.path.join(root, "deployers", "infrastructure", "deployer.config")))
        self.assertFalse(os.path.exists(os.path.join(root, "deployers", "inesdata", "deployer.config")))


if __name__ == "__main__":
    unittest.main()
