"""Tests for the cross-platform portable Hermes bundle builder."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "packaging" / "portable" / "build.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("hermes_portable_build", BUILDER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_minimal_source(root: Path) -> None:
    (root / "hermes_cli").mkdir()
    (root / "hermes_cli" / "__init__.py").write_text("", encoding="utf-8")
    (root / "hermes_cli" / "main.py").write_text(
        "def main():\n    print('portable hermes')\n", encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'hermes-agent'\nversion = '0.0.0'\n", encoding="utf-8"
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("ignored", encoding="utf-8")
    (root / "venv").mkdir()
    (root / "venv" / "ignored.txt").write_text("ignored", encoding="utf-8")


def make_fake_runtime(root: Path, *, windows: bool = False) -> Path:
    if windows:
        exe = root / "python.exe"
    else:
        exe = root / "bin" / "python"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("fake python", encoding="utf-8")
    return root


def test_build_without_dependency_install_creates_relocatable_layout(tmp_path: Path) -> None:
    builder = load_builder()
    source = tmp_path / "source"
    source.mkdir()
    make_minimal_source(source)
    runtime = make_fake_runtime(tmp_path / "runtime")

    config = builder.PortableConfig(
        source_root=source,
        output_dir=tmp_path / "dist",
        target="linux-x64",
        python_runtime=runtime,
        install_dependencies=False,
        archive=False,
    )

    result = builder.build_portable_bundle(config)
    bundle = result.bundle_dir

    assert (bundle / "hermes").read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
    assert (bundle / "hermes.cmd").exists()
    assert (bundle / "data" / "hermes-home" / ".keep").exists()
    assert (bundle / "runtime" / "python" / "bin" / "python").exists()
    assert (bundle / "app" / "hermes-agent" / "pyproject.toml").exists()
    assert not (bundle / "app" / "hermes-agent" / ".git").exists()
    assert not (bundle / "app" / "hermes-agent" / "venv").exists()
    assert not (bundle / "app" / "hermes-agent" / "tests").exists()
    assert not (bundle / "app" / "hermes-agent" / "website").exists()

    launcher = (bundle / "hermes").read_text(encoding="utf-8")
    assert 'HERMES_PORTABLE="1"' in launcher
    assert 'HERMES_HOME="$ROOT_DIR/data/hermes-home"' in launcher
    assert 'PYTHONPATH="$ROOT_DIR/app/site' in launcher
    assert 'exec "$PYTHON" -m hermes_cli.main "$@"' in launcher


def test_dependency_install_uses_locked_export_and_target_site(tmp_path: Path) -> None:
    builder = load_builder()
    source = tmp_path / "source"
    source.mkdir()
    make_minimal_source(source)
    runtime = make_fake_runtime(tmp_path / "runtime")
    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        commands.append([str(part) for part in cmd])
        return None

    config = builder.PortableConfig(
        source_root=source,
        output_dir=tmp_path / "dist",
        target="linux-x64",
        python_runtime=runtime,
        install_dependencies=True,
        archive=False,
    )

    builder.build_portable_bundle(config, runner=fake_run)

    joined = [" ".join(cmd) for cmd in commands]
    assert any("uv export --locked --no-dev --no-emit-project --extra all" in item for item in joined)
    assert any("uv pip install" in item and "--require-hashes" in item and "--target" in item for item in joined)
    assert any("uv pip install" in item and "--no-deps" in item for item in joined)


def test_windows_launcher_uses_bundled_python_and_portable_home(tmp_path: Path) -> None:
    builder = load_builder()
    source = tmp_path / "source"
    source.mkdir()
    make_minimal_source(source)
    runtime = make_fake_runtime(tmp_path / "runtime", windows=True)

    config = builder.PortableConfig(
        source_root=source,
        output_dir=tmp_path / "dist",
        target="windows-x64",
        python_runtime=runtime,
        install_dependencies=False,
        archive=False,
    )

    result = builder.build_portable_bundle(config)
    bundle = result.bundle_dir
    cmd = (bundle / "hermes.cmd").read_text(encoding="utf-8")
    ps1 = (bundle / "hermes.ps1").read_text(encoding="utf-8")

    assert "set HERMES_PORTABLE=1" in cmd
    assert "set HERMES_HOME=%ROOT_DIR%\\data\\hermes-home" in cmd
    assert 'set "PYTHON=%ROOT_DIR%\\runtime\\python\\python.exe"' in cmd
    assert '"%PYTHON%" -m hermes_cli.main %*' in cmd
    assert '$env:HERMES_HOME = Join-Path $Root "data\\hermes-home"' in ps1
    assert '& $Python -m hermes_cli.main @args' in ps1
