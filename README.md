# MPV配置管理工具

一个用于自动下载、配置和打包MPV播放器及其插件的Python工具，产出 [fntv-electron](https://github.com/JayYa/fntv-electron) 在 Windows、macOS、Linux 上共用的 MPV 归档 `mpv-package-<时间>.zip`。三个平台用到归档的哪些部分不同，见[平台差异](#平台差异)。支持版本管理、插件热插拔和GitHub Actions自动化构建。

## 功能特点

- 🎯 **自动化管理**: 自动下载MPV播放器和插件
- 🔧 **版本控制**: 通过配置文件管理所有组件版本
- 🔌 **插件可配置**: 在 package_cfg.json 里增删或停用依赖项
- 📦 **智能打包**: 自动创建便携式安装包
- 🗜️ **多格式支持**: 支持7z、zip、rar等多种压缩格式
- 🛠️ **自定义配置**: 支持自定义配置文件
- 🚀 **CI/CD支持**: 推送到 `release` 分支时由 GitHub Actions 构建并发布 Release
- 🚫 **智能过滤**: 双层文件过滤系统，排除不需要的文件
- ⚙️ **灵活配置**: 分离式配置设计，清晰的文件排除和自定义安装规则
- 📋 **归档清单**: 生成 `fntv-manifest.json`，打包后跑契约测试，失败不发版

## 平台差异

同一个归档供 fntv-electron 的三个平台使用，但各平台用到的部分不同：

| 平台 | 客户端安装包里带的 | 运行的 mpv | 便携配置同步到 |
| --- | --- | --- | --- |
| Windows | 整个归档，含 `mpv.exe` | 附带的 `mpv.exe`，用户也可以自选 | `%APPDATA%\mpv`；自选的 `mpv.exe` 旁边有 `portable_config` 时写那里 |
| macOS | 只有 `portable_config/` 和 `fntv-manifest.json` | 用户自己安装的 mpv（Homebrew 或 `mpv.app`） | `$XDG_CONFIG_HOME/mpv`，未设时 `~/.config/mpv`；只有 `~/.mpv` 时写 `~/.mpv` |
| Linux | 同 macOS | 系统里安装的 mpv | 同 macOS |

三个平台上，设了 `MPV_HOME` 时都同步到它。客户端的完整规则见 fntv-electron 的 [external-runtime.md](https://github.com/JayYa/fntv-electron/blob/main/docs/external-runtime.md)。

改归档内容时要注意：

- `mpv` 依赖项来自 `shinchiro/mpv-winbuild-cmake`，只有 Windows 版。macOS 和 Linux 上的 mpv 版本不由本仓库决定，所以 `portable_config` 里的配置和脚本要能在用户自己的 mpv 上工作。`mpv.conf` 分层的生效顺序只在附带的 Windows mpv 上实测过。
- 插件脚本要兼容三个平台。例如 `thumbfast.lua` 按 mpv 的 `platform` 属性区分 Windows、macOS、Linux 的行为。
- 配置里的路径用 `~~/` 开头（mpv 配置目录），不要写某个平台的绝对路径。三个平台的配置目录位置不同，`~~/` 都能解析。

构建工具本身也有平台差异。CI 在 Windows 上构建。在 macOS 或 Linux 上本地运行 `run.py` 时：

- py7zr 解不开 mpv 的 7z 包时，程序回退到 7-Zip 命令行，但只查找 `7z.exe`，所以这一步在 macOS 和 Linux 上会失败。

## 项目结构

```
fntv-mpv-config/
├── src/                    # 源代码目录
│   ├── __init__.py
│   ├── main.py            # 命令行：把参数翻译成一次构建、列出依赖或清理目录
│   ├── build.py           # 构建流程：按构建范围取依赖、安装、打包
│   ├── package_config.py  # 打包配置：读 package_cfg.json，加载时校验全部字段
│   ├── dependency_layout.py # 依赖布局：安装目标、入口文件、托管目录和基础配置
│   ├── dependency_source.py # 依赖来源：把一个依赖变成内容目录
│   ├── download_manager.py # 从 GitHub Release 选出唯一资产并下载
│   ├── previous_manifest.py # 上一版清单：从 Release 或本地文件取、校验，并进已知哈希
│   ├── extract.py         # 按扩展名解压
│   ├── install_manager.py # 安装管理
│   ├── log_setup.py       # 日志输出设置
│   ├── package_archive.py # 安装包构建：生成清单、打包、跑契约测试
│   ├── contract_test.py   # 契约测试：安装包与清单的一致性检查
│   ├── manifest.py        # 清单格式与解析、归属规则、历史哈希和已知哈希
│   └── release.py         # 构建结果 JSON 和 Release 说明
├── custom_config/         # 自定义配置目录：base/ 是基础配置，其余按依赖项名分子目录
│   ├── base/              # 基础配置：mpv.conf、input.conf、fntv/defaults.conf、shaders/
│   ├── uosc/              # script-opts/uosc.conf
│   ├── uosc_danmaku/      # script-opts/uosc_danmaku.conf、danmaku-history.json
│   └── thumbfast/         # script-opts/thumbfast.conf
├── local_packages/        # 本地插件源码（smart_skip、thumbfast）
├── types/                 # mpv Lua API 类型声明，供编辑器补全，不进安装包
├── tests/                 # 测试目录
├── templates/             # Release 说明模板（release-notes.md）
├── .github/workflows/     # GitHub Actions工作流
├── package_cfg.json       # 主配置文件
├── manifest-history.json  # 历史归档的文件哈希
├── requirements.txt       # Python依赖
├── run.py                 # 运行脚本
├── run_tests.py           # 测试运行器
├── check_archive.py       # 对打包出的 zip 跑契约测试
└── README.md              # 文档
```

## 快速开始

### 1. 环境准备

#### 系统要求
- Python 3.11.4 及以上（解压 tar 用到 `filter="data"`；CI 用 3.11）
- 7-Zip（py7zr 解不开 mpv 的 7z 包时用它）
- 可访问 GitHub。设置 `GITHUB_TOKEN` 或 `GH_TOKEN` 后，GitHub API 请求带认证，不受匿名每小时 60 次的限额

#### 安装7-Zip (Windows)
```bash
# Windows (使用winget包管理器)
winget install --id 7zip.7zip

# 或者手动下载安装
# 访问 https://7-zip.org/ 下载并安装
```

程序先找 `C:\Program Files\7-Zip\7z.exe` 和 `C:\Program Files (x86)\7-Zip\7z.exe`，再找 `PATH` 里的 `7z.exe`。macOS 和 Linux 上找不到它，见[平台差异](#平台差异)。

#### 克隆项目并安装依赖
```bash
# 克隆仓库
git clone https://github.com/JayYa/fntv-mpv-config.git
cd fntv-mpv-config

# 安装Python依赖
pip install -r requirements.txt
```

### 2. 配置管理

编辑 `package_cfg.json` 文件来配置版本和下载源：

```json
{
  "dependencies": {
    "mpv": {
      "version": "20261108"
    },
    "uosc": {
      "version": "5.13.0"
    },
    "uosc_danmaku": {
      "version": "v2.1.0",
      "enabled": false
    }
  }
}
```

依赖默认启用。写 `"enabled": false` 就停用：它照样在加载时校验，但不下载、不安装，`custom_config/<名>/` 也不装；它的入口文件不再是必需的，装过的托管文件进清单的 `obsolete`，客户端会删掉，用户的 `script-opts/<名>.conf` 保留。mpv 本体也能停用。停用前先确认基础配置（如 `input.conf` 里的 `script-binding uosc/menu`）和其它插件不依赖它，构建不检查这些引用。`--list` 会标出停用的依赖，`--deps` 指定停用的依赖会报错。

### 3. 基本使用

一次完整运行会下载并安装所有启用的依赖项，生成 `fntv-manifest.json`，打包 `<输出目录>/mpv-package-<时间>.zip` 并跑契约测试，最后删除 `temp_dir`。安装内容放在 `<输出目录>/<package_cfg.json 的 name>/`，当前是 `fntv-mpv/`；这个目录每次安装前都会先清空，安装包里只有本次安装的文件。任何一个依赖项失败或契约测试失败，程序都以退出码 1 结束。

```bash
# 处理所有启用的依赖项
python run.py

# 只处理指定的依赖项（空格分隔）。只装一部分依赖打不出完整的安装包，必须同时带 --skip-package 或 --skip-install
python run.py --deps mpv uosc --skip-package

# 检查 package_cfg.json 并列出所有依赖项及来源，标出停用的；配置不合法时退出码为 1
python run.py --list

# 离线构建：不访问网络，网络依赖用 temp/<名称>/ 里上次下载的压缩包，没有就失败；
# 改了依赖的仓库、版本、filename_pattern 或 format 后，缓存的压缩包对不上，也会失败，要先联网构建一次。
# 默认运行结束会删掉 temp（离线构建也一样），所以先带 --skip-cleanup 联网构建一次；
# 要连续离线构建，每次都带 --skip-cleanup
python run.py --skip-cleanup
python run.py --skip-download --skip-cleanup

# 只下载，不安装，也不打包
python run.py --skip-install

# 安装但不生成清单、不打包
python run.py --skip-package

# 指定安装包和 Release tag 里的时间（yyyyMMdd_HHmmss）；不传时用当前北京时间
python run.py --package-timestamp 20261115_120000

# 打包成功后写出构建结果 JSON，同目录生成 release-notes.md（CI 用；预览说明也可用）
python run.py --result-file ./build/build-result.json

# 并入上一版清单（默认只用仓库里的 manifest-history.json，可用 --manifest-history 换文件）
python run.py --previous-release JayYa/fntv-mpv-config   # 下载该仓库最新一版 Release 的清单，拿不到就失败（CI 用）
python run.py --previous-manifest ./fntv-manifest.json   # 或用本地文件；两者只能选一个

# 使用本地包文件
python run.py --deps local_plugin --skip-package  # 配置文件中指定了local_path的依赖项

# 输出到其它目录（不改 package_cfg.json；也可设环境变量 FNTV_MPV_OUTPUT_DIR）
python run.py --output-dir ./output

# 清理下载和构建目录
python run.py --clean temp      # 删掉整个 temp_dir
python run.py --clean output    # 删掉 <输出目录>/fntv-mpv/、mpv-package-<时间>.zip 和 fntv-manifest.json，输出目录里的其它文件不动
python run.py --clean all       # 两者都删
```

## 本地包支持

除了从网络下载，现在也支持安装本地文件包和文件夹：

### 配置方式

#### 方式1：使用 local_path 字段（压缩文件）
```json
{
  "my_local_plugin": {
    "name": "本地插件",
    "local_path": "./local_packages/plugin.zip",
    "version": "local",
    "install_to": "portable_config/scripts/my_local_plugin",
    "exclude_files": ["*.md", "LICENSE*"]
  }
}
```

#### 方式2：使用 local_path 字段（文件夹）
```json
{
  "my_folder_plugin": {
    "name": "本地文件夹插件",
    "local_path": "./local_packages/extracted_plugin",
    "version": "local",
    "custom_install_rules": [
      {
        "from": "src",
        "to": "portable_config/scripts/my_plugin",
        "filter": ["**/*.lua"],
        "exclude": ["**/debug/**"]
      }
    ]
  }
}
```

本地依赖只认 `local_path`：路径是文件夹就当内容目录，是文件就按扩展名解压；不写 `url`、`filename_pattern`、`format`，写了会报错。`local_path` 在加载时就要存在。

### 支持格式
- **压缩文件**：zip、7z、rar、tar、tar.gz、tar.bz2等所有支持的格式
- **文件夹**：已解压的目录结构，系统会自动检测并跳过解压步骤

### 路径规则
- **相对路径**：相对于配置文件（`package_cfg.json`）所在目录，如 `./local_packages/file.zip` 或 `./local_packages/folder`
- **绝对路径**：完整路径，如 `C:/packages/file.zip` 或 `C:/packages/folder`

### 使用场景
- 🧪 **测试开发**：测试新插件而不需要上传到GitHub
- 📦 **离线环境**：在没有网络的环境中安装
- 🔧 **自定义包**：安装修改过的插件版本
- 🚀 **快速部署**：跳过下载和解压时间（文件夹方式）
- 🔄 **增量开发**：直接使用开发目录进行测试

### 注意事项
- 支持所有网络下载支持的格式（zip、7z、rar等）
- 文件夹方式支持直接指向已解压的目录
- 依赖布局字段（install_to、custom_install_rules、exclude_files、entry、managed_dir、config_roles）完全相同
- 本地压缩包直接解压到 `temp/<名称>/content/`，不先复制
- 本地文件夹直接作为内容目录安装，不复制、不解压

## 配置文件详解

### package_cfg.json 主配置文件

```json
{
  "name": "fntv-mpv",                  // 输出子目录名：安装内容放在 <输出目录>/fntv-mpv/
  "version": "1.0.0",
  "config": {
    "output_dir": "../fntv-electron/third_party",  // 输出目录：同级检出的 fntv-electron
    "temp_dir": "./temp",              // 临时目录，运行结束后整个删除
    "custom_config_dir": "./custom_config",  // 自定义配置目录
    "github_proxy": "https://ghfast.top",    // 下载链接的代理前缀
    "enable_proxy": false              // true 时下载链接加代理前缀；GitHub API 请求不走代理
  },
  "dependencies": {
    "mpv": {
      "name": "mpv播放器",
      "url": "https://github.com/shinchiro/mpv-winbuild-cmake/releases",
      "version": "20261108",
      "filename_pattern": "mpv-x86_64-{version}",
      "format": "7z",
      "install_to": ".",                // 内容目录整个装到安装包根目录
      "entry": "mpv.exe",               // 安装包里必须有的入口文件
      "exclude_files": [                // 排除不需要的文件，只能和 install_to 一起用
        "doc/**"
      ]
    },
    "uosc": {
      "name": "uosc插件",
      "url": "https://github.com/tomasklaen/uosc/releases", 
      "version": "5.13.0",
      "filename_pattern": "uosc",
      "format": "zip",
      "entry": "portable_config/scripts/uosc/main.lua",
      "managed_dir": "portable_config/scripts/uosc",  // 客户端整体替换的目录
      "custom_install_rules": [          // 自定义安装规则，和 install_to 二选一
        {
          "from": "scripts",            // 从内容目录的scripts目录
          "to": "portable_config/scripts", // 安装到portable_config/scripts
          "filter": ["**/*"]            // 包含所有文件
        },
        {
          "from": "fonts",              // 从内容目录的fonts目录
          "to": "portable_config/fonts", // 安装到portable_config/fonts
          "filter": ["**/*"]
        }
      ]
    }
  }
}
```

### 配置参数说明

#### 核心配置参数

每个依赖项在加载时校验，不合法就不构建；不认识的字段也报错。停用的依赖同样要校验通过。下面的路径都相对安装包根目录，不能是绝对路径或含 `..`：

- `install_to`: 内容目录整个装到哪，如 mpv 的 `"."`、插件的 `"portable_config/scripts/<名>"`。和 `custom_install_rules` 必须且只能写一个，没有默认值
- `custom_install_rules`: 自定义安装规则数组，按规则挑文件装
- `exclude_files`: 排除文件数组，只能和 `install_to` 一起用；和 `custom_install_rules` 一起写会报错，排除要写进规则的 `exclude`
- `entry`: 客户端离不开的入口文件（可选）。契约测试要求每个启用的依赖的 `entry` 都在安装包里；停用的依赖不要求
- `managed_dir`: 客户端整体替换的目录（可选），必须在 `portable_config/` 下并包含 `entry`，写进清单的 `managedDirs`
- `config_roles`: `custom_config/<依赖项名>/` 里不是 `config` 的文件（可选），模式到 `managed` 或 `seed` 的对象，见[归档清单](#归档清单-fntv-manifestjson)
- `name`、`version`: 所有依赖必填的非空字符串；`name` 是显示名，写进 Release 说明
- `url` 和 `local_path` 必须且只能写一个，决定依赖来源。`url` 必须是 `https://github.com/<owner>/<repo>/releases`，不能写本地路径
- `url`、`filename_pattern`、`format`: GitHub Release 依赖必填。程序用 GitHub API 读 `version` 这个 tag 的 Release，先找名字等于 `<filename_pattern>.<format>` 的资产，没有时取唯一一个以 `filename_pattern` 开头、以 `.<format>` 结尾的资产。一个都没有、有不止一个，或 API 请求失败（如 403 限流）时构建失败，报错里列出现有资产或 HTTP 状态，不会猜文件名。`filename_pattern` 可含 `{version}` 占位符。`format` 只能是 `zip`、`7z`、`rar`、`tar`、`tar.gz`、`tar.bz2`、`tar.xz`，加载时校验；本地压缩包的扩展名也按这组格式校验。temp 里已有同名、大小与 Release 资产一致的文件时不重复下载
- `enabled`: 是否打进安装包（可选），布尔值，默认 `true`
- `version` 也写进清单的 `components`；停用的依赖不写

#### 输出目录

`config.output_dir` 是默认输出目录，可以按次覆盖，优先级从高到低：

1. 命令行 `--output-dir <目录>`
2. 环境变量 `FNTV_MPV_OUTPUT_DIR`（空值视为未设置）
3. `package_cfg.json` 的 `config.output_dir`

覆盖值只作用于本次运行，不会写回配置文件。`--clean output` 同样按这个顺序确定要清理的目录。

`config` 里的 `output_dir`、`temp_dir`、`custom_config_dir` 必填，相对路径按 `package_cfg.json` 所在目录解析；`--output-dir` 和环境变量按当前工作目录解析。`github_proxy`、`enable_proxy` 可不写。顶层只能写 `name`（必填）、`version`、`description`、`config`、`base_config_roles`、`dependencies`。

#### exclude_files 排除模式

`exclude_files` 用于排除下载内容中不需要的文件，模式作用于相对内容根的路径：

```json
{
  "exclude_files": [
    "*.md",              // 任意深度的 markdown 文档
    "LICENSE*",          // 任意深度的许可证文件
    "doc/**",            // 内容根下 doc 目录里的全部文件
    "installer/*",       // 内容根下 installer 目录的直接子文件
    "**/.github/**",     // 任意一级名为 .github 的目录
    "**/test/**"         // 任意一级名为 test 的目录
  ]
}
```

`exclude_files`、`filter`、`exclude` 都是 gitignore 式模式，区分大小写：

| 模式 | 匹配 |
| --- | --- |
| 不含 `/`，如 `*.md`、`thumbfast.lua` | 任意深度下文件名匹配的文件 |
| 含 `/`，如 `doc/*`、`scripts/**/*.lua` | 从内容根（规则里是 `from`）起的整条相对路径；`*`、`?`、`[...]` 不跨 `/`，`**` 匹配任意层目录（含零层） |

不支持以 `!` 或 `/` 开头、以 `/` 结尾的模式，写了在加载配置时报错。

#### custom_install_rules 自定义安装规则

`custom_install_rules` 用于定义特殊的文件安装规则，参考 Node.js extraFiles 功能设计：

- `from`: 源目录或文件（相对于内容目录，可以为空，表示内容目录本身）
- `to`: 目标目录路径（相对于输出子目录 `<输出目录>/<name>/`，不是相对于 `portable_config/`）
- `filter`: 文件过滤器数组（可选，默认为 `["**/*"]`）
- `exclude`: 排除模式数组（可选）

规则只能写这四个字段，写了别的（比如把 `exclude` 拼成 `excludes`）加载配置时报错。模式见上面的模式表。

以下情况构建直接失败，报错写明依赖名和规则：
- `from` 在内容目录里不存在
- 某个 `filter` 在排除之后一个文件都没装进去（`install_to` 相当于一条 `filter: ["**/*"]` 的规则，所以内容目录全被排除掉也会失败）
- 两个依赖（或依赖与 `custom_config/base/`）要装同一个文件；`custom_config/<依赖项名>/` 替换依赖自带的文件是允许的

### 配置工作原理

1. **基础配置**: 清空 project 目录后，先把 `custom_config/base/` 复制进 `portable_config/`
2. **install_to**: 内容目录整个装到 `install_to`（如 mpv 的 `.` 是输出子目录根，与 `portable_config/` 同级），按 `exclude_files` 排除
3. **自定义规则**: 写了 `custom_install_rules` 的依赖只按规则安装文件，排除只看规则里的 `exclude`
4. **自定义配置**: 最后把 `custom_config/<依赖项名>/` 复制进 `portable_config/`

**安装路径处理**：
- 目标路径统一相对于输出子目录 `<输出目录>/<name>/` 处理
- 支持 `portable_config/` 前缀的完整路径
- 空目标路径安装到输出子目录根，与 `portable_config/` 同级
- `from` 不存在时构建失败

**配置规则示例**：
```json
{
  "from": "scripts",                    // 从内容目录的scripts目录
  "to": "portable_config/scripts",      // 安装到输出目录的portable_config/scripts
  "filter": ["**/*.lua"],               // 只包含lua文件
  "exclude": ["test/**"]                // 排除测试目录
}
```

### 配置示例详解

#### 简单插件（仅排除文档文件）

```json
{
  "uosc_danmaku": {
    "name": "uosc弹幕插件",
    "url": "https://github.com/Tony15246/uosc_danmaku/releases",
    "version": "v2.1.0",
    "exclude_files": [
      "*.md",              // 排除README.md等文档
      "LICENSE*"           // 排除许可证文件
    ]
  }
}
```

#### 复杂插件（自定义安装规则）

```json
{
  "uosc": {
    "name": "uosc插件", 
    "url": "https://github.com/tomasklaen/uosc/releases",
    "version": "5.13.0",
    "custom_install_rules": [
      {
        "from": "scripts",                    // 从内容目录的scripts目录
        "to": "portable_config/scripts",      // 安装到portable_config/scripts
        "filter": ["**/*"]                    // 包含所有文件
      },
      {
        "from": "fonts",                      // 从内容目录的fonts目录
        "to": "portable_config/fonts",       // 安装到portable_config/fonts
        "filter": ["**/*"]
      }
    ]
  }
}
```

**注意**：此配置会跳过默认安装，只按照自定义规则安装指定的文件。

#### MPV主程序（排除调试和文档文件）

```json
{
  "mpv": {
    "name": "mpv播放器",
    "url": "https://github.com/shinchiro/mpv-winbuild-cmake/releases",
    "version": "20261108",
    "exclude_files": [
      "doc/**"              // 排除文档目录
    ]
  }
}
```

这是 Windows 构建的 mpv，装到输出子目录根，只在 Windows 上被客户端使用。macOS 和 Linux 只用归档里的 `portable_config/`，见[平台差异](#平台差异)。

## 自定义配置

`custom_config/base/` 是基础配置：不属于任何依赖，每次构建都按原相对路径复制进 portable_config 目录。`custom_config/<依赖项名>/` 下放跟着某个依赖走的配置，安装该依赖后复制进去。两份配置要装到同一个路径时加载就报错，不会悄悄覆盖；依赖项也不能叫 `base`。没有对应依赖项的子目录不会被复制，`custom_config` 根目录下也不要放散文件（测试会检查）。

这些文件在三个平台上都会同步到用户的 mpv 配置目录，写法要兼容三个平台，见[平台差异](#平台差异)。新增文件默认归属 `config`（用户可改）；要托管或只放一次，在 `base_config_roles` 或依赖的 `config_roles` 里声明，见[归档清单](#归档清单-fntv-manifestjson)。

### 目录结构

```
custom_config/
├── base/                 # 基础配置
│   ├── input.conf        # 快捷键配置
│   ├── mpv.conf          # MPV主配置（薄文件，给用户改）
│   ├── fntv/
│   │   └── defaults.conf # 托管的默认值
│   └── shaders/          # Anime4K着色器
├── uosc/
│   └── script-opts/
│       └── uosc.conf     # UOSC插件配置
├── uosc_danmaku/
│   ├── script-opts/
│   │   └── uosc_danmaku.conf  # 弹幕插件配置
│   └── danmaku-history.json   # 弹幕历史的种子
└── thumbfast/
    └── script-opts/
        └── thumbfast.conf     # 缩略图插件配置
```

## GitHub Actions 自动化

项目包含GitHub Actions工作流，支持：

- **推送触发**: 推送到 `release` 分支时构建（没有定时触发）
- **手动触发**: 可以手动触发构建
- **自动发布**: 只在 `release` 分支上创建 Release；其他分支只上传构建产物

### 配置说明

工作流文件位于 `.github/workflows/daily-build.yml`，主要特性：

- 使用Windows环境进行构建，产出的同一个 zip 供三个平台使用
- 构建前先跑 `run_tests.py`，失败不构建
- `run.py --previous-release` 在下载依赖之前先取最新一版 Release 的 `fntv-manifest.json` 并入本次清单；那版没有清单、或清单的 `archiveVersion` 不是它的 tag 时构建失败
- `run.py --result-file` 写出构建结果（`build-result.json`）：归档版本、Release 标题、artifact 名、输出目录、安装包和清单资产的路径、Release 说明的路径。workflow 只读这些字段，不自行推导命名
- 时间戳是北京时间，Release tag 是 `fntv-mpv-v<时间>`，资产是 `mpv-package-<时间>.zip` 和 `fntv-manifest.json`
- Release 说明由 `src/release.py` 按 `templates/release-notes.md` 生成：本次处理的依赖、停用的依赖、目录树，以及从 `GITHUB_*` 环境变量取的分支、提交和链接
- 自动上传构建产物，保留 30 天

## 归档清单 fntv-manifest.json

归档根目录（与 `mpv.exe`、`portable_config/` 同级）带一份 `fntv-manifest.json`，客户端按它同步用户配置。格式和规则见 [JayYa/fntv-electron#219](https://github.com/JayYa/fntv-electron/issues/219)，格式和生成的代码在 `src/manifest.py`，契约测试在 `src/contract_test.py`。

- `files[]` 列出 `portable_config` 下的每个文件：相对路径、`sha256`、`role`、`knownHashes`。
- 归属（`role`）按文件的来源定：依赖装进来的文件都是 `managed`；`custom_config` 里的文件默认是 `config`，例外按模式声明在 `package_cfg.json` 顶层的 `base_config_roles`（基础配置）和各依赖的 `config_roles` 里，值只能是 `managed` 或 `seed`。现在声明的有：`fntv/defaults.conf`、`shaders/**` 是 `managed`，`danmaku-history.json` 是 `seed`。每个模式至少要命中一个文件；托管目录里的 custom_config 文件必须声明为 `managed`，否则加载配置时报错。
- `knownHashes` = 该路径在历史归档里出现过的全部哈希 + 本次哈希。历史来自两处：仓库里的 `manifest-history.json`（本 fork 早于清单的 5 个 Release 里每个路径的哈希和归属；这些 Release 不会再有，文件已冻结），以及上一版 Release 的 `fntv-manifest.json` 资产（CI 用 `--previous-release` 自动下载；本地可用 `--previous-manifest` 指定文件）。
- `obsolete`：历史里出现过、本次没有的托管路径，带它们的 `knownHashes`。删掉的 `config` 文件不进 `obsolete`，客户端一律保留。

### mpv.conf 分层

默认值放在托管的 `custom_config/base/fntv/defaults.conf`，**全部写在 `[fntv-defaults]` 段里**；`mpv.conf` 是给用户改的薄文件，前两个有效行固定为：

```
include="~~/fntv/defaults.conf"
profile=fntv-defaults
```

用户设置写在这两行后面，覆盖默认值。改默认值只改 `defaults.conf`。

不能只写 include、把默认值放在 `defaults.conf` 顶层：附带的 mpv（`55d3feb45`）把配置文件顶层选项先存进 default profile，读完整个文件才应用，include 进来的顶层选项被追加到最后，结果默认值覆盖了用户设置（已用附带 MPV 实测）。放进命名段再用 `profile=` 应用，默认值就在 include 行的位置生效。契约测试检查这两行的位置、`~~/` 前缀和 `[fntv-defaults]` 段。

### 契约测试

打包后 `run.py` 自动跑契约测试：清单和 zip 一一对应、哈希正确、`role` 合法、`managedDirs` 里的文件都是 `managed` 且每个托管目录含一个入口文件、每个依赖声明的 `entry`（含根目录的 `mpv.exe`）和基础配置的 `mpv.conf`、`fntv/defaults.conf` 都在、`provides` 和 `managedDirs` 齐全、`knownHashes` 只增不减、zip 旁边单独上传的 `fntv-manifest.json` 与 zip 里的相同。任何一条失败，构建就失败，不会发版。手工检查一个 zip（入口文件和托管目录默认从仓库的 `package_cfg.json` 读，`--config` 换别的配置）：

```bash
python check_archive.py mpv-package-<时间>.zip --archive-version fntv-mpv-v<时间> [--previous-manifest 上一版的fntv-manifest.json] [--config package_cfg.json]
```

## 配置架构说明

### 双层配置系统 (v1.0.0+)

本工具采用双层配置系统，将文件过滤和自定义安装规则分离：

#### 1. exclude_files - 文件排除层
- **目的**: 排除下载内容中不需要的文件
- **时机**: 按 `install_to` 安装时应用；和 `custom_install_rules` 一起写会报错
- **适用场景**: 排除文档、许可证、调试文件等

#### 2. custom_install_rules - 自定义安装层  
- **目的**: 定义精确的文件安装规则
- **时机**: 代替 `install_to`，两者二选一
- **适用场景**: 复杂的目录结构映射
- **设计理念**: 参考 Node.js extraFiles 功能，简洁的路径映射

### 处理流程

```
读取依赖布局 → 复制基础配置 → 下载文件 → 解压 → 过滤并复制文件 → 复制custom_config → 生成清单 → 打包 → 契约测试
```

1. **依赖布局**: 读取并校验所有依赖项的 `install_to`、`custom_install_rules`、`entry`、`managed_dir`，再复制 `custom_config/base/`
2. **下载解压**: 从GitHub下载并解压文件；本地文件夹跳过解压
3. **安装**:
   - 写了`install_to`: 整个内容目录装过去，按`exclude_files`过滤
   - 写了`custom_install_rules`: 按规则安装，按规则的`filter`和`exclude`过滤
4. **自定义配置**: 把`custom_config/<依赖项名>/`复制进`portable_config/`
5. **打包**: 生成`fntv-manifest.json`（`managedDirs` 来自各依赖的 `managed_dir`），打包zip并跑契约测试（必需路径来自各依赖的 `entry` 和基础配置）

### 配置优先级

- `install_to` 和 `custom_install_rules` 二选一
- `exclude_files` 只和 `install_to` 一起用
- 自定义规则中的 `exclude` > `filter`

## 开发指南

### 模块设计

项目采用模块化设计，各模块职责明确：

1. **package_config.py**: `load_package_config` 把 `package_cfg.json` 读成打包配置（构建设置、依赖布局、各依赖的来源），加载时校验全部字段
2. **dependency_source.py**: `DependencySource.fetch` 把一个依赖变成内容目录（本地文件夹原样返回，压缩包解压并去掉单一外层根目录），独占 `temp_dir` 的布局；内部用 `download_manager.py`（选出唯一的 Release 资产并下载，HTTP 会话可注入）和 `extract.py`（按扩展名解压）
3. **dependency_layout.py**: `load_layout` 从 `package_cfg.json` 读出依赖布局并校验：每个依赖装到哪、入口文件、托管目录、要复制的 custom_config 文件及其归属。安装、清单的归属和 `managedDirs`、契约测试的必需路径都从它来
4. **InstallManager**: 先清空 project 目录、装基础配置，再按依赖布局把内容目录和 custom_config 装进去
5. **log_setup.py**: `setup_logging` 把日志输出到标准输出
6. **package_archive.py**: `build_package_archive` 生成清单、打安装包并跑契约测试，不通过时抛 `ContractTestFailed`
7. **contract_test.py**: `contract_test(安装包, 已知哈希, 依赖布局)` 是契约测试的唯一入口，返回全部错误；`build_package_archive` 和 `check_archive.py` 都调用它
8. **manifest.py**: 清单的 JSON 格式只在这里：`Manifest.parse` 读入并一次报出全部结构错误，`Manifest.to_bytes` 写出；另有历史哈希（`load_history`）和已知哈希的合并。`build_manifest` 向依赖布局要每个文件的归属和 `managedDirs`
9. **previous_manifest.py**: `load_known_hashes` 读历史哈希、取上一版清单（`PreviousRelease` 从最新一版 Release 下载，`PreviousManifestFile` 读本地文件）、经 `Manifest.parse` 校验后合并成已知哈希；上一版清单拿不到或结构不对时抛 `PreviousManifestError`，历史哈希文件读不出或结构不对时抛 `ManifestError`。`build()` 和 `check_archive.py` 都经它取已知哈希
10. **build.py**: `build(打包配置, 构建范围)` 是构建流程的唯一入口：构建范围 `BuildScope` 决定只取依赖、取依赖并安装，还是完整打包；成功返回构建结果，任何失败都抛 `BuildFailed`，带上全部原因（契约测试的每条错误都在里面）。只处理部分依赖时不能完整打包。成功后删临时目录，失败时保留
11. **main.py**: 命令行只负责把参数翻译成 `build()` 的调用，把 `BuildFailed` 逐条打印并以退出码 1 结束；`--list`、`--clean` 是接收打包配置的普通函数

### 扩展性

- **添加新的依赖来源**: 在 `package_config.py` 加来源类型，在 `DependencySource.fetch` 里处理
- **支持新的压缩格式**: 在 `extract.py` 的 `_EXTRACTORS` 表里加一项（格式 → 解压函数），`ARCHIVE_FORMATS` 和加载时的校验都从这张表来
- **自定义安装规则**: 规则的解析和校验在 `dependency_layout.py`，按规则选文件、复制在 `install_manager.py`

### 调试技巧

```bash
# 启用详细日志（推荐用于排除模式调试）
python run.py --log-level DEBUG

# 离线重跑（用上次 --skip-cleanup 留下的压缩包，用于测试安装逻辑）
python run.py --skip-download

# 不清理临时文件（用于检查中间结果）
python run.py --skip-cleanup

# 只处理特定依赖项（空格分隔），不打包
python run.py --deps uosc uosc_danmaku --skip-package

# 检查 package_cfg.json：缺少或多余的字段、不存在的本地路径、不合法的安装规则，出错时退出码为 1
python run.py --list
```

#### 文件排除调试

当使用`--log-level DEBUG`时，可以看到每个复制的文件：

```
DEBUG - 已复制: temp\uosc\content\scripts\uosc\main.lua -> output\...
```

日志不列出被排除的文件。加上`--skip-cleanup`保留临时目录，对照解压结果和复制日志，就能看出哪些文件被排除了。

## 自定义配置规则详解

### 设计理念

自定义配置规则参考了 Node.js 的 extraFiles 功能，采用简洁明了的设计：

```json
{
  "from": "source_path",    // 源路径（相对于内容目录）
  "to": "target_path",      // 目标路径（相对于输出子目录）
  "filter": ["**/*"],       // 可选：包含过滤器
  "exclude": []             // 可选：排除过滤器
}
```

### 路径处理规则

1. **源路径 (`from`)**：
   - 相对于内容目录
   - 可以为空字符串（表示整个内容目录）
   - 示例：`"scripts"`、`"fonts"`、`""`

2. **目标路径 (`to`)**：
   - 统一相对于输出子目录 `<输出目录>/<name>/` 处理
   - 支持完整路径如 `"portable_config/scripts"`
   - 空字符串表示安装到输出子目录根，与 `portable_config/` 同级

### 实际应用示例

#### 示例1：标准插件安装
```json
{
  "from": "scripts/plugin_name",
  "to": "portable_config/scripts/plugin_name",
  "filter": ["**/*"]
}
```

#### 示例2：只复制特定文件类型
```json
{
  "from": "src", 
  "to": "portable_config/scripts/custom",
  "filter": ["**/*.lua", "**/*.js"],
  "exclude": ["test/**", "**/*.md"]
}
```

#### 示例3：整个目录重新映射
```json
{
  "from": "",  // 整个内容目录
  "to": "portable_config",
  "filter": ["**/*.lua"],
  "exclude": ["docs/**", "examples/**"]
}
```

`thumbfast` 就是这种用法：`"from": ""`、`"to": "portable_config/scripts"`、`"filter": ["thumbfast.lua"]`，只把一个文件装进 `scripts/`。

## 运行测试

项目包含单元测试，GitHub API 调用用 mock 替换，不需要网络。每个 PR 和推到 `main` 的提交都会在 CI（`.github/workflows/ci.yml`）里跑 `ruff check .` 和全部测试；本地先装开发依赖：

```bash
pip install -r requirements-dev.txt
ruff check .
```

### 推荐方式：使用内置测试运行器

```bash
# 运行所有测试（推荐）
python run_tests.py

# 输出示例：
# 运行MPV配置管理工具测试...
# test_list_shows_every_dependency_and_where_it_comes_from ... ok
# test_is_excluded ... ok
# ✅ 所有测试通过!
```

### 直接运行测试文件

```bash
# 运行测试文件
python -m unittest tests.test_download_manager -v
```

### 测试覆盖范围

- ✅ **package_config**: 三种依赖来源、字段校验、相对路径基准、输出目录优先级
- ✅ **命令行**: `--list`、`--clean`、`--deps` 的输出和退出码
- ✅ **DependencySource**: 本地文件夹、本地压缩包、下载后解压、离线模式命中和缺失缓存、清理
- ✅ **download_manager**: 选资产（精确名优先、唯一前缀、多个或没有时失败）、限流和缺 Release 的报错、按资产大小跳过或重下、下载不完整时失败、代理、`GITHUB_TOKEN` 认证、取最新 Release 的指定资产
- ✅ **previous_manifest**: 从 Release 或本地文件取上一版清单，缺清单、缺 `files`、不属于那版 Release 时失败
- ✅ **extract**: 格式识别、tar.gz 解压、拒绝越出目标目录的 tar 成员
- ✅ **InstallManager**: install_to 和自定义规则、模式匹配语义、规则对不上内容目录或两个依赖装同一文件时报错
- ✅ **manifest**: 清单解析与生成、历史哈希、完整打包流程（含上次构建的残留不进安装包）
- ✅ **contract_test**: 契约测试的每项检查和 `check_archive.py`
- ✅ **package_cfg.json**: 固定的依赖版本和下载地址

各测试文件的说明见 [tests/README.md](tests/README.md)。

## 常见问题

### Q: 解压失败，提示"无法找到 7-Zip 命令行工具"？
A: 这是因为系统缺少7-Zip工具。请按照以下步骤解决：
```bash
# 使用winget安装（推荐）
winget install --id 7zip.7zip

# 或者手动下载安装
# 1. 访问 https://7-zip.org/
# 2. 下载并安装7-Zip
# 3. 确保7z.exe在系统PATH中或安装在默认位置
```

macOS 和 Linux 上程序找不到 `7z`，这一步无法完成，在 Windows 上构建，见[平台差异](#平台差异)。

### Q: 下载失败怎么办？
A: 检查网络连接，确认GitHub访问正常。GitHub API 返回 403 时设置 `GITHUB_TOKEN`。国内网络可以把 `config.enable_proxy` 设为 `true`。可以使用`--log-level DEBUG`查看详细错误信息。

### Q: 如何添加新的插件？
A: 在`package_cfg.json`的`dependencies`中添加新的插件配置。对于简单插件，只需配置基本参数和排除规则；对于复杂插件，可以使用自定义配置规则精确控制文件安装位置。

示例：
```json
{
  "new_plugin": {
    "name": "新插件",
    "url": "https://github.com/author/plugin/releases",
    "version": "1.0.0",
    "filename_pattern": "plugin",
    "format": "zip",
    "custom_install_rules": [
      {
        "from": "src",
        "to": "portable_config/scripts/new_plugin",
        "filter": ["**/*.lua"]
      }
    ]
  }
}
```

### Q: 自定义配置不生效？
A: 确认配置文件放在正确的`custom_config`目录结构中，并且文件名和路径正确。

### Q: GitHub Actions构建失败？
A: 检查`package_cfg.json`中的版本号是否存在，网络访问是否正常，依赖项是否正确安装。日志里有“契约测试失败”时，按列出的条目改归档内容，常见原因是入口文件缺失或托管目录里的文件归属不对。

### Q: 排除模式不生效怎么办？
A: 
1. 使用`--log-level DEBUG`查看排除过程详细信息
2. 确认排除模式语法正确，对照[模式表](#exclude_files-排除模式)，使用正斜杠`/`作为路径分隔符
3. 注意大小写：模式在所有平台上都区分大小写
4. 确认排除的是相对于`from`目录的相对路径
5. 检查是否同时被`filter`包含和`exclude`排除（exclude优先）
6. 依赖项有`custom_install_rules`时不能写`exclude_files`（加载会报错），排除要写进规则的`exclude`

#### 排除模式语法示例：
```json
"exclude": [
  "*.md",           // ✅ 任意深度的 .md 文件
  "*.MD",           // ⚠️  区分大小写：只排除 .MD 文件
  "LICENSE*",       // ✅ 任意深度、文件名以 LICENSE 开头的文件
  ".git*",          // ✅ 任意深度、文件名以 .git 开头的文件，如 .gitignore
  "test/**",        // ✅ 内容根下 test 目录里的全部文件
  "**/test/**",     // ✅ 任意一级名为 test 的目录
  "docs/**/*.md",   // ✅ 内容根下 docs 目录里任意深度的 .md 文件
  "test/"           // ❌ 不支持以 / 结尾，加载配置时报错，应写 "test/**"
]
```

### Q: 如何验证排除模式是否正确？
A: 使用DEBUG模式运行特定依赖项：
```bash
python run.py --deps plugin_name --log-level DEBUG --skip-cleanup --skip-package
```
然后检查输出日志和生成的文件。

## 许可证

本项目采用MIT许可证，详见LICENSE文件。


## 更新日志

v1.0.1 之后不再维护版本号，每次发版的内容见 [GitHub Releases](https://github.com/JayYa/fntv-mpv-config/releases)（tag `fntv-mpv-v<时间>`）。

### v1.0.1 (2025-08-24)
- 🔧 **重构自定义配置规则处理**：参考 Node.js extraFiles 功能重新设计
- ✨ **简化路径处理逻辑**：统一目标路径处理，避免复杂的特殊情况判断
- 🐛 **修复路径重复问题**：解决 `portable_config/portable_config` 重复路径问题
- 📚 **改善文档说明**：添加更详细的配置规则说明和示例
- 🧹 **代码优化**：移除重复代码，提高代码可维护性

### v1.0.0 (2025-08-24)
- 🎉 初始版本发布
- 支持MPV、UOSC、UOSC_DANMAKU的自动下载和配置
- 实现GitHub Actions自动化构建
- 提供完整的配置管理功能
- fntv-electron配套mpv配置
