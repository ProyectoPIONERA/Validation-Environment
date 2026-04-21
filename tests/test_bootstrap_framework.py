import os
import platform
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
        os.makedirs(os.path.join(root, "validation", "ui"), exist_ok=True)

        for deployer, marker in (
            ("infrastructure", "KC_URL=http://keycloak.local\n"),
            ("inesdata", "DS_1_NAME=demo\n"),
            ("edc", "EDC_DASHBOARD_ENABLED=true\n"),
        ):
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

        for command_name in ("npm", "npx"):
            command_path = os.path.join(fake_bin, command_name)
            with open(command_path, "w", encoding="utf-8") as handle:
                if command_name == "npx":
                    handle.write(
                        textwrap.dedent(
                            """\
                            #!/usr/bin/env bash
                            set -euo pipefail
                            if [[ -n "${BOOTSTRAP_NPX_LOG:-}" ]]; then
                              printf '%s\n' "$*" >> "$BOOTSTRAP_NPX_LOG"
                            fi
                            exit 0
                            """
                        )
                    )
                else:
                    handle.write("#!/usr/bin/env bash\nexit 0\n")
            os.chmod(command_path, os.stat(command_path).st_mode | stat.S_IXUSR)
        return root, fake_bin

    def test_bootstrap_initializes_deployer_configs(self):
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
        self.assertTrue(os.path.isfile(os.path.join(root, "deployers", "edc", "deployer.config")))

        with open(os.path.join(root, "deployers", "infrastructure", "deployer.config"), encoding="utf-8") as handle:
            self.assertIn("KC_URL=http://keycloak.local", handle.read())
        with open(os.path.join(root, "deployers", "inesdata", "deployer.config"), encoding="utf-8") as handle:
            self.assertIn("DS_1_NAME=demo", handle.read())
        with open(os.path.join(root, "deployers", "edc", "deployer.config"), encoding="utf-8") as handle:
            self.assertIn("EDC_DASHBOARD_ENABLED=true", handle.read())

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
        self.assertFalse(os.path.exists(os.path.join(root, "deployers", "edc", "deployer.config")))

    def test_bootstrap_installs_playwright_system_deps_by_default_on_linux(self):
        root, fake_bin = self._prepare_workspace()
        npx_log = os.path.join(root, "npx.log")
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
        env["BOOTSTRAP_NPX_LOG"] = npx_log

        result = subprocess.run(
            [
                "bash",
                os.path.join(root, "scripts", "bootstrap_framework.sh"),
                "--skip-root-node",
                "--skip-ui-node",
                "--skip-deployer-config",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        with open(npx_log, encoding="utf-8") as handle:
            npx_commands = handle.read()

        expected = (
            "playwright install --with-deps"
            if platform.system() == "Linux"
            else "playwright install"
        )
        self.assertIn(expected, npx_commands)

    def test_bootstrap_can_skip_playwright_system_deps(self):
        root, fake_bin = self._prepare_workspace()
        npx_log = os.path.join(root, "npx.log")
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
        env["BOOTSTRAP_NPX_LOG"] = npx_log

        result = subprocess.run(
            [
                "bash",
                os.path.join(root, "scripts", "bootstrap_framework.sh"),
                "--skip-root-node",
                "--skip-ui-node",
                "--skip-deployer-config",
                "--without-system-deps",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        with open(npx_log, encoding="utf-8") as handle:
            npx_commands = handle.read()
        self.assertIn("playwright install", npx_commands)
        self.assertNotIn("--with-deps", npx_commands)


if __name__ == "__main__":
    unittest.main()
