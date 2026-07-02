# Hermes Agent Portable Bundles

This builder creates a **complete portable directory** for Hermes Agent. The
result is intended for users who want to download, unzip, and run Hermes without
installing Python packages into the system environment.

## Layout

```text
HermesPortable-<target>/
├─ hermes                 # POSIX launcher
├─ hermes.cmd             # Windows cmd launcher
├─ hermes.ps1             # Windows PowerShell launcher
├─ app/
│  ├─ hermes-agent/       # source snapshot used for data files/skills/catalogs
│  └─ site/               # Hermes wheel + dependencies installed with --target
├─ runtime/
│  └─ python/             # bundled Python runtime
└─ data/
   └─ hermes-home/        # portable HERMES_HOME: config, .env, sessions, logs
```

The launcher sets:

- `HERMES_PORTABLE=1`
- `HERMES_HOME=<bundle>/data/hermes-home`
- `HERMES_OPTIONAL_SKILLS=<bundle>/app/hermes-agent/optional-skills`
- `HERMES_OPTIONAL_MCPS=<bundle>/app/hermes-agent/optional-mcps`
- `PYTHONPATH=<bundle>/app/site;<bundle>/app/hermes-agent;...`

## Build locally

From the repository root:

```bash
uv run --extra dev python packaging/portable/build.py --target linux-x64
```

On Windows:

```powershell
uv run --extra dev python packaging/portable/build.py --target windows-x64
```

Outputs are written under `dist/portable/` by default:

- `HermesPortable-linux-x64/` plus `HermesPortable-linux-x64.tar.gz`
- `HermesPortable-windows-x64/` plus `HermesPortable-windows-x64.zip`

## Reproducible/offline runtime input

For CI or air-gapped builds, pass an existing Python runtime directory:

```bash
uv run --extra dev python packaging/portable/build.py \
  --target linux-x64 \
  --python-runtime /path/to/python-runtime
```

If `--python-runtime` is omitted, the builder uses:

```bash
uv python install <python-version> --install-dir <bundle>/runtime/python --no-bin --no-registry
```

## Fast layout-only smoke build

To verify launchers and directory shape without installing dependencies:

```bash
uv run --extra dev python packaging/portable/build.py \
  --target linux-x64 \
  --python-runtime /path/to/python-runtime \
  --no-install-deps \
  --no-archive
```

## User startup

After downloading and extracting the archive:

- Linux: `./hermes`
- Windows cmd: `hermes.cmd`
- Windows PowerShell: `./hermes.ps1`

First run should normally be:

```bash
hermes setup
```

API keys and provider configuration are stored in the portable `data/hermes-home`
directory, not in the user's global `~/.hermes` or `%LOCALAPPDATA%\\hermes`.
