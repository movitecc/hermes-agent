# Hermes Agent Portable Bundles

便携版 Hermes Agent — 下载解压即用，无需安装 Python、uv 或任何依赖。

## 用户使用指南

### 下载

从 [Releases](https://github.com/movitecc/hermes-agent/releases) 下载对应平台的包：

| 平台 | 文件 |
|---|---|
| Linux x64 | `HermesPortable-linux-x64.tar.gz` |
| Windows x64 | `HermesPortable-windows-x64.zip` |

### 解压

**Linux:**
```bash
tar xzf HermesPortable-linux-x64.tar.gz
cd HermesPortable-linux-x64
```

**Windows (PowerShell):**
```powershell
Expand-Archive HermesPortable-windows-x64.zip
cd HermesPortable-windows-x64
```

### 首次配置

```bash
# Linux
./hermes setup

# Windows PowerShell
.\hermes.ps1 setup

# Windows CMD
hermes.cmd setup
```

引导式配置 API Key。所有配置、sessions、skills 存在便携目录内 `data/hermes-home/`，不影响系统全局。

### 日常使用

```bash
# Linux
./hermes                    # 交互聊天
./hermes model              # 管理模型
./hermes config             # 编辑配置
./hermes skills             # 管理技能
./hermes gateway            # 启动消息网关

# Windows (PowerShell)
.\hermes.ps1

# Windows (CMD)
hermes.cmd
```

### 目录结构

```text
HermesPortable-<platform>/
├── hermes / hermes.cmd / hermes.ps1  ← 启动器
├── app/
│   ├── hermes-agent/                 ← 源码 & 数据文件
│   └── site/                         ← Python 依赖（已预装）
├── runtime/
│   └── python/                       ← 内置 Python 3.12
└── data/
    └── hermes-home/                  ← 便携 HERMES_HOME
```

### 特点

- **无需 Python** — 内置 Python 3.12 运行时
- **无需 uv/pip** — 依赖已预装在 `app/site/`
- **不碰系统环境** — 不修改 PATH、不创建全局 venv
- **可移动** — 整个目录拷到 U 盘 / 其他机器直接用
- **数据隔离** — 不与 `~/.hermes` 冲突

### 升级

下载新版本压缩包，解压到新目录，将旧目录的 `data/hermes-home/` 复制过去即可保留所有配置。

---

## 开发者文档

This builder creates a **complete portable directory** for Hermes Agent.

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
