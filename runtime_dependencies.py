import importlib.util
import os
import subprocess
import sys


def _missing_modules(module_names):
    missing = []
    for module_name in module_names:
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    return missing


def ensure_runtime_dependencies(requirements_path, module_names, label="framework"):
    """Ensure the current interpreter can import the required modules.

    If one or more modules are missing, install the provided requirements file
    into the current interpreter and validate imports again.
    """
    missing = _missing_modules(module_names)
    if not missing:
        return

    requirements_path = os.path.abspath(requirements_path)
    if not os.path.exists(requirements_path):
        raise SystemExit(
            f"Missing {label} requirements file: {requirements_path}"
        )

    print(
        f"[INFO] Missing Python dependencies for {label}: {', '.join(missing)}",
        file=sys.stderr,
    )
    print(
        f"[INFO] Installing requirements with: {sys.executable} -m pip install -r {requirements_path}",
        file=sys.stderr,
    )

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", requirements_path],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to install {label} dependencies from {requirements_path}"
        )

    missing_after_install = _missing_modules(module_names)
    if missing_after_install:
        raise SystemExit(
            "Dependencies are still missing after installation for "
            f"{label}: {', '.join(missing_after_install)}"
        )


def ensure_python_requirements(python_executable, requirements_path, label="python environment"):
    """Install a requirements file into the provided interpreter."""
    requirements_path = os.path.abspath(requirements_path)
    if not os.path.exists(requirements_path):
        raise RuntimeError(f"Missing {label} requirements file: {requirements_path}")

    result = subprocess.run(
        [python_executable, "-m", "pip", "install", "-r", requirements_path],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to install {label} dependencies from {requirements_path}"
        )
