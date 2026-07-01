#!/usr/bin/env python3
"""Build a relocatable Hermes Agent portable directory.

The portable bundle intentionally avoids installing into the user's global
Python, shell PATH, or platform Hermes home.  It creates this shape:

    HermesPortable-<target>/
      hermes / hermes.cmd / hermes.ps1
      app/hermes-agent/        # source snapshot
      app/site/                # wheel + dependencies installed with --target
      runtime/python/          # bundled Python runtime
      data/hermes-home/        # portable HERMES_HOME

Use ``--python-runtime`` for reproducible/offline packaging, or let the builder
ask uv to download a managed Python into the bundle runtime directory.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence


TARGETS = {"linux-x64", "windows-x64"}
DEFAULT_IGNORES = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "docs",
    "tests",
    "website",
    ".plans",
    "node_modules",
    "worktrees",
    ".worktrees",
}

Runner = Callable[..., object]


@dataclass(frozen=True)
class PortableConfig:
    source_root: Path
    output_dir: Path = Path("dist/portable")
    target: str = "linux-x64"
    bundle_name: str | None = None
    python_version: str = "3.12"
    python_runtime: Path | None = None
    extras: tuple[str, ...] = ("all",)
    install_dependencies: bool = True
    archive: bool = True
    force: bool = True
    include_dev_files: bool = False

    def __post_init__(self) -> None:
        if self.target not in TARGETS:
            raise ValueError(f"unsupported target {self.target!r}; expected one of {sorted(TARGETS)}")
        object.__setattr__(self, "source_root", self.source_root.resolve())
        object.__setattr__(self, "output_dir", self.output_dir.resolve())
        if self.python_runtime is not None:
            object.__setattr__(self, "python_runtime", self.python_runtime.resolve())


@dataclass(frozen=True)
class BuildResult:
    bundle_dir: Path
    archive_path: Path | None
    python_executable: Path


def run_command(cmd: Sequence[str], **kwargs: object) -> None:
    subprocess.run([str(part) for part in cmd], check=True, **kwargs)


def bundle_name(config: PortableConfig) -> str:
    return config.bundle_name or f"HermesPortable-{config.target}"


def should_ignore(name: str, *, include_dev_files: bool = False) -> bool:
    if name in DEFAULT_IGNORES or name.endswith(".egg-info"):
        return True
    if not include_dev_files and name in {".github"}:
        # Release workflows are useful in the source repo, not inside the user bundle.
        return True
    return False


def copy_source_tree(source_root: Path, dest: Path, *, include_dev_files: bool = False) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if should_ignore(name, include_dev_files=include_dev_files)}

    shutil.copytree(source_root, dest, ignore=ignore, symlinks=True)


def copy_python_runtime(runtime: Path, dest: Path) -> None:
    if not runtime.exists():
        raise FileNotFoundError(f"python runtime not found: {runtime}")
    shutil.copytree(runtime, dest, symlinks=True)


def find_python_executable(runtime_dir: Path, target: str) -> Path:
    names = ["python.exe"] if target.startswith("windows") else ["python", "python3"]
    preferred = (
        [runtime_dir / "python.exe", runtime_dir / "Scripts" / "python.exe"]
        if target.startswith("windows")
        else [runtime_dir / "bin" / "python", runtime_dir / "bin" / "python3"]
    )
    for candidate in preferred:
        if candidate.exists():
            return candidate
    for name in names:
        matches = sorted(runtime_dir.rglob(name))
        if matches:
            return matches[0]
    raise FileNotFoundError(f"could not find a Python executable under {runtime_dir}")


def install_managed_python(config: PortableConfig, runtime_dir: Path, runner: Runner) -> Path:
    runner(
        [
            "uv",
            "python",
            "install",
            config.python_version,
            "--install-dir",
            str(runtime_dir),
            "--no-bin",
            "--no-registry",
        ]
    )
    return find_python_executable(runtime_dir, config.target)


def install_portable_site(config: PortableConfig, bundle_dir: Path, python_exe: Path, runner: Runner) -> None:
    source_dir = bundle_dir / "app" / "hermes-agent"
    site_dir = bundle_dir / "app" / "site"
    build_dir = bundle_dir / "build"
    requirements = build_dir / "requirements.lock"
    build_dir.mkdir(parents=True, exist_ok=True)
    site_dir.mkdir(parents=True, exist_ok=True)

    export_cmd: list[str] = [
        "uv",
        "export",
        "--locked",
        "--no-dev",
        "--no-emit-project",
    ]
    for extra in config.extras:
        export_cmd.extend(["--extra", extra])
    export_cmd.extend(
        [
            "--format",
            "requirements.txt",
            "--output-file",
            str(requirements),
        ]
    )
    runner(export_cmd, cwd=str(source_dir), stdout=subprocess.DEVNULL)

    runner(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python_exe),
            "--target",
            str(site_dir),
            "--require-hashes",
            "-r",
            str(requirements),
        ]
    )
    runner(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python_exe),
            "--target",
            str(site_dir),
            "--no-deps",
            str(source_dir),
        ]
    )


def write_launchers(bundle_dir: Path, target: str) -> None:
    sh_path = bundle_dir / "hermes"
    sh_path.write_text(
        r'''#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT_DIR/runtime/python/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(find "$ROOT_DIR/runtime/python" \( -type f -o -type l \) \( -name python -o -name python3 \) 2>/dev/null | head -n 1)"
fi
if [ -z "${PYTHON:-}" ] || [ ! -x "$PYTHON" ]; then
  echo "Hermes portable Python runtime not found under $ROOT_DIR/runtime/python" >&2
  exit 1
fi
export HERMES_PORTABLE="1"
export HERMES_HOME="$ROOT_DIR/data/hermes-home"
export HERMES_OPTIONAL_SKILLS="$ROOT_DIR/app/hermes-agent/optional-skills"
export HERMES_OPTIONAL_MCPS="$ROOT_DIR/app/hermes-agent/optional-mcps"
export PYTHONPATH="$ROOT_DIR/app/site:$ROOT_DIR/app/hermes-agent${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$ROOT_DIR/runtime/bin:$ROOT_DIR/runtime/node/bin:$ROOT_DIR/runtime/python/bin:$PATH"
mkdir -p "$HERMES_HOME"
exec "$PYTHON" -m hermes_cli.main "$@"
''',
        encoding="utf-8",
    )
    sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    (bundle_dir / "hermes.cmd").write_text(
        r"""@echo off
setlocal
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set HERMES_PORTABLE=1
set HERMES_HOME=%ROOT_DIR%\data\hermes-home
set HERMES_OPTIONAL_SKILLS=%ROOT_DIR%\app\hermes-agent\optional-skills
set HERMES_OPTIONAL_MCPS=%ROOT_DIR%\app\hermes-agent\optional-mcps
set PYTHONPATH=%ROOT_DIR%\app\site;%ROOT_DIR%\app\hermes-agent;%PYTHONPATH%
set PATH=%ROOT_DIR%\runtime\bin;%ROOT_DIR%\runtime\node;%ROOT_DIR%\runtime\python;%ROOT_DIR%\runtime\python\Scripts;%PATH%
if not exist "%HERMES_HOME%" mkdir "%HERMES_HOME%"
set "PYTHON=%ROOT_DIR%\runtime\python\python.exe"
if not exist "%PYTHON%" (
  for /r "%ROOT_DIR%\runtime\python" %%F in (python.exe) do (
    set "PYTHON=%%F"
    goto :found_python
  )
)
:found_python
if not exist "%PYTHON%" (
  echo Hermes portable Python runtime not found under %ROOT_DIR%\runtime\python 1>&2
  exit /b 1
)
"%PYTHON%" -m hermes_cli.main %*
""",
        encoding="utf-8",
    )

    (bundle_dir / "hermes.ps1").write_text(
        r"""$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:HERMES_PORTABLE = "1"
$env:HERMES_HOME = Join-Path $Root "data\hermes-home"
$env:HERMES_OPTIONAL_SKILLS = Join-Path $Root "app\hermes-agent\optional-skills"
$env:HERMES_OPTIONAL_MCPS = Join-Path $Root "app\hermes-agent\optional-mcps"
$env:PYTHONPATH = (Join-Path $Root "app\site") + ";" + (Join-Path $Root "app\hermes-agent") + ";" + $env:PYTHONPATH
$env:PATH = (Join-Path $Root "runtime\bin") + ";" + (Join-Path $Root "runtime\node") + ";" + (Join-Path $Root "runtime\python") + ";" + (Join-Path $Root "runtime\python\Scripts") + ";" + $env:PATH
New-Item -ItemType Directory -Force -Path $env:HERMES_HOME | Out-Null
$Python = Join-Path $Root "runtime\python\python.exe"
if (-not (Test-Path $Python)) {
    $Python = Get-ChildItem -Path (Join-Path $Root "runtime\python") -Filter python.exe -Recurse -File | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Python -or -not (Test-Path $Python)) {
    Write-Error "Hermes portable Python runtime not found under $Root\runtime\python"
    exit 1
}
& $Python -m hermes_cli.main @args
exit $LASTEXITCODE
""",
        encoding="utf-8",
    )


def write_readme(bundle_dir: Path, target: str) -> None:
    (bundle_dir / "README-PORTABLE.md").write_text(
        f"""# Hermes Agent Portable ({target})

This directory is self-contained. It does not install Hermes globally and keeps
runtime state under `data/hermes-home`.

## Start

- Linux/macOS shell: `./hermes`
- Windows cmd: `hermes.cmd`
- Windows PowerShell: `./hermes.ps1`

Run `hermes setup` from the launcher on first use to add model/provider keys.
The `.env`, config, sessions, skills, logs, cron state, and auth files live in
`data/hermes-home` inside this folder.

## Move or copy

Copy the whole directory. Do not copy only `app/` or only `runtime/`.
""",
        encoding="utf-8",
    )


def create_archive(bundle_dir: Path, target: str) -> Path:
    if target.startswith("windows"):
        archive_path = bundle_dir.with_suffix(".zip")
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in bundle_dir.rglob("*"):
                zf.write(path, path.relative_to(bundle_dir.parent))
        return archive_path

    archive_path = bundle_dir.with_suffix(".tar.gz")
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(bundle_dir, arcname=bundle_dir.name)
    return archive_path


def build_portable_bundle(config: PortableConfig, runner: Runner = run_command) -> BuildResult:
    source_root = config.source_root
    if not (source_root / "pyproject.toml").exists():
        raise FileNotFoundError(f"source root does not look like Hermes Agent: {source_root}")

    bundle_dir = config.output_dir / bundle_name(config)
    if bundle_dir.exists():
        if not config.force:
            raise FileExistsError(bundle_dir)
        shutil.rmtree(bundle_dir)

    (bundle_dir / "app").mkdir(parents=True)
    (bundle_dir / "data" / "hermes-home").mkdir(parents=True)
    (bundle_dir / "data" / "hermes-home" / ".keep").write_text("", encoding="utf-8")
    (bundle_dir / "runtime").mkdir()
    copy_source_tree(source_root, bundle_dir / "app" / "hermes-agent", include_dev_files=config.include_dev_files)

    runtime_dir = bundle_dir / "runtime" / "python"
    if config.python_runtime is not None:
        copy_python_runtime(config.python_runtime, runtime_dir)
        python_exe = find_python_executable(runtime_dir, config.target)
    else:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        python_exe = install_managed_python(config, runtime_dir, runner)

    if config.install_dependencies:
        install_portable_site(config, bundle_dir, python_exe, runner)
    else:
        (bundle_dir / "app" / "site").mkdir(parents=True, exist_ok=True)

    write_launchers(bundle_dir, config.target)
    write_readme(bundle_dir, config.target)
    archive_path = create_archive(bundle_dir, config.target) if config.archive else None
    return BuildResult(bundle_dir=bundle_dir, archive_path=archive_path, python_executable=python_exe)


def parse_args(argv: Iterable[str] | None = None) -> PortableConfig:
    parser = argparse.ArgumentParser(description="Build a Hermes Agent portable bundle")
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("dist/portable"))
    parser.add_argument("--target", choices=sorted(TARGETS), default=("windows-x64" if sys.platform == "win32" else "linux-x64"))
    parser.add_argument("--bundle-name")
    parser.add_argument("--python-version", default="3.12")
    parser.add_argument("--python-runtime", type=Path, help="Existing Python runtime directory to copy instead of downloading via uv")
    parser.add_argument("--extra", action="append", dest="extras", default=None, help="pyproject extra to include; repeatable; default: all")
    parser.add_argument("--no-install-deps", action="store_true", help="Create layout only; skip dependency installation")
    parser.add_argument("--no-archive", action="store_true", help="Leave directory only; do not create zip/tar.gz")
    parser.add_argument("--no-force", action="store_true", help="Fail if the bundle directory already exists")
    parser.add_argument("--include-dev-files", action="store_true", help="Keep repo development files such as .github in app/hermes-agent")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return PortableConfig(
        source_root=args.source_root,
        output_dir=args.output_dir,
        target=args.target,
        bundle_name=args.bundle_name,
        python_version=args.python_version,
        python_runtime=args.python_runtime,
        extras=tuple(args.extras or ["all"]),
        install_dependencies=not args.no_install_deps,
        archive=not args.no_archive,
        force=not args.no_force,
        include_dev_files=args.include_dev_files,
    )


def main(argv: Iterable[str] | None = None) -> int:
    config = parse_args(argv)
    result = build_portable_bundle(config)
    print(f"Portable bundle: {result.bundle_dir}")
    print(f"Python: {result.python_executable}")
    if result.archive_path:
        print(f"Archive: {result.archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
