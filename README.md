# MPV配置管理工具

一个用于自动下载、配置和打包MPV播放器及其插件的Python工具，产出 [fntv-electron](https://github.com/JayYa/fntv-electron) 在 Windows、macOS、Linux 上共用的 MPV 归档 `mpv-package-<时间>.zip`。三个平台用到归档的哪些部分不同，见[平台差异](#平台差异)。支持版本管理、插件热插拔和GitHub Actions自动化构建。

## 功能特点

- 🎯 **自动化管理**: 自动下载MPV播放器和插件
- 🔧 **版本控制**: 通过配置文件管理所有组件版本
- 🔌 **插件热插拔**: 轻松启用/禁用插件
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
- 文件排除模式用 Python 的 `fnmatch.fnmatch` 匹配，在 Windows 上不区分大小写，在 macOS 和 Linux 上区分。

## 项目结构

```
fntv-mpv-config/
├── src/                    # 源代码目录
│   ├── __init__.py
│   ├── main.py            # 主程序
│   ├── config_manager.py  # 配置管理
│   ├── download_manager.py # 下载管理
│   ├── extract_manager.py # 解压管理
│   ├── install_manager.py # 安装管理
│   ├── log_manager.py     # 日志管理
│   ├── package_archive.py # 安装包构建与契约测试的入口
│   ├── manifest.py        # 清单格式、归属规则、已知哈希和各项契约检查（package_archive 的实现）
│   └── release.py         # 构建结果 JSON 和 Release 说明
├── custom_config/         # 自定义配置目录，按依赖项名分子目录
│   ├── mpv/               # mpv.conf、input.conf、fntv/defaults.conf、shaders/
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
├── validate_config.py     # 检查 package_cfg.json
├── check_archive.py       # 对打包出的 zip 跑契约测试
├── build_manifest_history.py # 生成 manifest-history.json
└── README.md              # 文档
```

## 快速开始

### 1. 环境准备

#### 系统要求
- Python 3（CI 用 3.11）
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
      "version": "20261108",
      "enabled": true
    },
    "uosc": {
      "version": "5.13.0",
      "enabled": true
    },
    "uosc_danmaku": {
      "version": "v2.1.0",
      "enabled": true
    }
  }
}
```

### 3. 基本使用

一次完整运行会下载并安装所有启用的依赖项，生成 `fntv-manifest.json`，打包 `<输出目录>/mpv-package-<时间>.zip` 并跑契约测试，最后删除 `temp_dir`。安装内容放在 `<输出目录>/<package_cfg.json 的 name>/`，当前是 `fntv-mpv/`；这个目录每次安装前都会先清空，安装包里只有本次安装的文件。任何一个依赖项失败或契约测试失败，程序都以退出码 1 结束。

```bash
# 处理所有启用的依赖项
python run.py

# 只处理指定的依赖项（空格分隔）。只装一部分依赖打不出完整的安装包，必须同时带 --skip-package 或 --skip-install
python run.py --deps mpv uosc --skip-package

# 列出已启用的依赖项（禁用的不显示）
python run.py --list

# 启用/禁用依赖项（会按 2 空格缩进重写整个 package_cfg.json）
python run.py --enable uosc_danmaku
python run.py --disable uosc_danmaku

# 离线构建：不访问网络，网络依赖用 temp/<名称>/ 里上次下载的压缩包，没有就失败。
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

# 并入上一版 Release 的清单（默认只用仓库里的 manifest-history.json，可用 --manifest-history 换文件）
python run.py --previous-manifest ./fntv-manifest.json

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
    "enabled": true,
    "local_path": "./local_packages/plugin.zip",
    "version": "local",
    "format": "zip",
    "exclude_files": ["*.md", "LICENSE*"],
    "custom_install_rules": [
      {
        "from": "scripts",
        "to": "portable_config/scripts",
        "filter": ["**/*"]
      }
    ]
  }
}
```

#### 方式2：使用 local_path 字段（文件夹）
```json
{
  "my_folder_plugin": {
    "name": "本地文件夹插件",
    "enabled": true,
    "local_path": "./local_packages/extracted_plugin",
    "version": "folder",
    "exclude_files": ["*.md", "test/**"],
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

#### 方式3：将 url 设置为本地路径
```json
{
  "my_local_mpv": {
    "name": "本地MPV",
    "enabled": true,
    "url": "./local_packages/mpv-local.7z",
    "version": "local",
    "filename_pattern": "mpv-local",
    "format": "7z"
  }
}
```

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
- 安装规则（exclude_files、custom_install_rules）完全相同
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
      "enabled": true,
      "exclude_files": [                // 排除不需要的文件
        "doc/*"
      ]
    },
    "uosc": {
      "name": "uosc插件",
      "url": "https://github.com/tomasklaen/uosc/releases", 
      "version": "5.13.0",
      "filename_pattern": "uosc",
      "format": "zip",
      "enabled": true,
      "exclude_files": [                // 有 custom_install_rules 时不生效
        "*.md",
        "LICENSE*"
      ],
      "custom_install_rules": [          // 自定义安装规则
        {
          "from": "scripts",            // 从解压包的scripts目录
          "to": "portable_config/scripts", // 安装到portable_config/scripts
          "filter": ["**/*"]            // 包含所有文件
        },
        {
          "from": "fonts",              // 从解压包的fonts目录
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

- `exclude_files`: 排除文件数组，在默认安装时排除不需要的文件和目录。依赖项有 `custom_install_rules` 时不生效
- `custom_install_rules`: 自定义配置安装规则数组（可选）
- `url`、`version`、`filename_pattern`、`format`: 网络依赖项必填。程序用 GitHub API 读 `version` 这个 tag 的 Release，按以下顺序找资产：名字等于 `<filename_pattern>.<format>`；以 `filename_pattern` 开头、以 `.<format>` 结尾；含 `filename_pattern` 的全部关键词；该格式的唯一资产。`filename_pattern` 可含 `{version}` 占位符
- `version` 也写进清单的 `components`

#### 输出目录

`config.output_dir` 是默认输出目录，可以按次覆盖，优先级从高到低：

1. 命令行 `--output-dir <目录>`
2. 环境变量 `FNTV_MPV_OUTPUT_DIR`（空值视为未设置）
3. `package_cfg.json` 的 `config.output_dir`

覆盖值只作用于本次运行，不会写回配置文件。`--clean output` 同样按这个顺序确定要清理的目录。

#### exclude_files 排除模式

`exclude_files` 用于排除下载内容中不需要的文件，模式作用于相对内容根的路径：

```json
{
  "exclude_files": [
    "*.md",              // 排除任意深度的markdown文档（* 也匹配 /）
    "LICENSE*",          // 排除许可证文件
    "doc/*",            // 排除doc目录下的所有文件
    "installer/*",      // 排除installer目录
    "*.bat",            // 排除批处理文件
    ".github/**",       // 排除任意一级名为.github的目录
    "test/**",          // 排除任意一级名为test的目录
    "docs/**"           // 排除任意一级名为docs的目录
  ]
}
```

模式不是完整的 glob，`exclude_files`、`filter`、`exclude` 都按下表匹配（`InstallManager._matches_pattern`）：

| 模式 | 匹配 |
| --- | --- |
| `**/*` | 所有文件 |
| `**/<文件名模式>` | 任意深度下文件名匹配的文件，如 `**/*.lua`。`**/test/**` 这种只比较文件名，匹配不到任何文件 |
| `<目录>/**` | 路径中任意一级目录名等于 `<目录>` 的文件 |
| `<前缀>/**/<后缀>` | 路径同时含 `<前缀>` 和 `<后缀>` 两个子串的文件 |
| 其他 | `fnmatch.fnmatch` 匹配整个相对路径，`*` 也匹配 `/` |

`fnmatch.fnmatch` 在 Windows 上不区分大小写，在 macOS 和 Linux 上区分。

#### custom_install_rules 自定义安装规则

`custom_install_rules` 用于定义特殊的文件安装规则，参考 Node.js extraFiles 功能设计：

- `from`: 源目录路径（相对于解压后的根目录，可以为空）
- `to`: 目标目录路径（相对于输出子目录 `<输出目录>/<name>/`，不是相对于 `portable_config/`）
- `filter`: 文件过滤器数组，支持glob模式（可选，默认为 `["**/*"]`）
- `exclude`: 排除模式数组，支持glob模式（可选）

**设计理念**：
- 简洁的 `from` -> `to` 映射关系
- 统一的路径处理逻辑，避免复杂的特殊情况判断
- 灵活的过滤器和排除规则支持

**支持的文件模式**：
  - `**/*`: 所有文件
  - `*.lua`: 所有Lua文件
  - `script-opts/**`: script-opts目录下的所有文件
  - `*.md`: 排除所有Markdown文件
  - 完整规则见上面的模式表

### 配置工作原理

1. **默认安装**: 没有 `custom_install_rules` 时，`mpv` 装到输出子目录根（与 `portable_config/` 同级），其他依赖项装到 `portable_config/scripts/<依赖项名>/`
2. **文件排除**: 默认安装时应用 `exclude_files` 模式排除不需要的文件
3. **自定义规则**: 如果定义了 `custom_install_rules`，则只按规则安装文件，排除只看规则里的 `exclude`
4. **自定义配置**: 最后把 `custom_config/<依赖项名>/` 复制进 `portable_config/`

**安装路径处理**：
- 目标路径统一相对于输出子目录 `<输出目录>/<name>/` 处理
- 支持 `portable_config/` 前缀的完整路径
- 空目标路径安装到输出子目录根，与 `portable_config/` 同级
- `from` 不存在时记一条警告并跳过该规则

**配置规则示例**：
```json
{
  "from": "scripts",                    // 从解压包的scripts目录
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
    "exclude_files": [
      "*.md",
      "LICENSE*"
    ],
    "custom_install_rules": [
      {
        "from": "scripts",                    // 从解压包的scripts目录
        "to": "portable_config/scripts",      // 安装到portable_config/scripts
        "filter": ["**/*"]                    // 包含所有文件
      },
      {
        "from": "fonts",                      // 从解压包的fonts目录
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
      "doc/*"              // 排除文档目录
    ]
  }
}
```

这是 Windows 构建的 mpv，装到输出子目录根，只在 Windows 上被客户端使用。macOS 和 Linux 只用归档里的 `portable_config/`，见[平台差异](#平台差异)。

## 自定义配置

在 `custom_config/<依赖项名>/` 下放置自定义配置文件。安装某个依赖项后，程序把对应子目录里的文件按原相对路径复制进最终的portable_config目录，覆盖同名文件。没有对应依赖项的子目录不会被复制，`custom_config` 根目录下也不要放散文件（测试会检查）。

这些文件在三个平台上都会同步到用户的 mpv 配置目录，写法要兼容三个平台，见[平台差异](#平台差异)。新增文件还要先在 `src/manifest.py` 的 `ROLE_RULES` 里有归属，见[归档清单](#归档清单-fntv-manifestjson)。

### 目录结构

```
custom_config/
├── mpv/
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
- 下载上一版 Release 的 `fntv-manifest.json`，通过 `--previous-manifest` 并入本次清单
- `run.py --result-file` 写出构建结果（`build-result.json`）：归档版本、时间戳、输出目录、安装包和清单资产的路径、Release 说明的路径。workflow 只读这些字段，不自行推导命名
- 时间戳是北京时间，Release tag 是 `fntv-mpv-v<时间>`，资产是 `mpv-package-<时间>.zip` 和 `fntv-manifest.json`
- Release 说明由 `src/release.py` 按 `templates/release-notes.md` 生成：启用的插件、目录树，以及从 `GITHUB_*` 环境变量取的分支、提交和链接
- 自动上传构建产物，保留 30 天

## 归档清单 fntv-manifest.json

归档根目录（与 `mpv.exe`、`portable_config/` 同级）带一份 `fntv-manifest.json`，客户端按它同步用户配置。格式和规则见 [JayYa/fntv-electron#219](https://github.com/JayYa/fntv-electron/issues/219)，生成和检查的代码在 `src/manifest.py`。

- `files[]` 列出 `portable_config` 下的每个文件：相对路径、`sha256`、`role`、`knownHashes`。
- 归属（`role`）：`scripts/**`、`fonts/**`、`shaders/**`、`fntv/defaults.conf` 是 `managed`；`mpv.conf`、`input.conf`、`script-opts/*.conf` 是 `config`；`danmaku-history.json` 是 `seed`。新增文件如果不在这些规则里，打包会失败，要先在 `src/manifest.py` 的 `ROLE_RULES` 里给它定归属。
- `knownHashes` = 该路径在历史归档里出现过的全部哈希 + 本次哈希。历史来自两处：仓库里的 `manifest-history.json`（本 fork 早于清单的 5 个 Release，由 `build_manifest_history.py` 生成，复现方法见脚本开头），以及上一版 Release 的 `fntv-manifest.json` 资产（CI 自动下载，`--previous-manifest`）。
- `obsolete`：历史里出现过、本次没有的托管路径，带它们的 `knownHashes`。删掉的 `config` 文件不进 `obsolete`，客户端一律保留。

### mpv.conf 分层

默认值放在托管的 `custom_config/mpv/fntv/defaults.conf`，**全部写在 `[fntv-defaults]` 段里**；`mpv.conf` 是给用户改的薄文件，前两个有效行固定为：

```
include="~~/fntv/defaults.conf"
profile=fntv-defaults
```

用户设置写在这两行后面，覆盖默认值。改默认值只改 `defaults.conf`。

不能只写 include、把默认值放在 `defaults.conf` 顶层：附带的 mpv（`55d3feb45`）把配置文件顶层选项先存进 default profile，读完整个文件才应用，include 进来的顶层选项被追加到最后，结果默认值覆盖了用户设置（已用附带 MPV 实测）。放进命名段再用 `profile=` 应用，默认值就在 include 行的位置生效。契约测试检查这两行的位置、`~~/` 前缀和 `[fntv-defaults]` 段。

### 契约测试

打包后 `run.py` 自动跑契约测试：清单和 zip 一一对应、哈希正确、`role` 合法、各托管插件入口脚本存在、`provides` 和 `managedDirs` 齐全、`knownHashes` 只增不减、zip 旁边单独上传的 `fntv-manifest.json` 与 zip 里的相同。任何一条失败，构建就失败，不会发版。手工检查一个 zip：

```bash
python check_archive.py mpv-package-<时间>.zip --archive-version fntv-mpv-v<时间> [--previous-manifest 上一版的fntv-manifest.json]
```

## 配置架构说明

### 双层配置系统 (v1.0.0+)

本工具采用双层配置系统，将文件过滤和自定义安装规则分离：

#### 1. exclude_files - 文件排除层
- **目的**: 排除下载内容中不需要的文件
- **时机**: 在默认安装过程中应用；有 `custom_install_rules` 时不生效
- **适用场景**: 排除文档、许可证、调试文件等

#### 2. custom_install_rules - 自定义安装层  
- **目的**: 定义精确的文件安装规则
- **时机**: 覆盖默认安装行为
- **适用场景**: 复杂的目录结构映射
- **设计理念**: 参考 Node.js extraFiles 功能，简洁的路径映射

### 处理流程

```
下载文件 → 解压 → 选择安装模式 → 过滤并复制文件 → 复制custom_config → 生成清单 → 打包 → 契约测试
```

1. **下载解压**: 从GitHub下载并解压文件；本地文件夹跳过解压
2. **安装模式选择**:
   - 如果定义了`custom_install_rules`: 使用自定义规则安装，按规则的`filter`和`exclude`过滤
   - 否则: 使用默认安装（直接复制到相应目录），按`exclude_files`过滤
3. **自定义配置**: 把`custom_config/<依赖项名>/`复制进`portable_config/`
4. **打包**: 生成`fntv-manifest.json`，打包zip并跑契约测试

### 配置优先级

- `custom_install_rules` > 默认安装
- `exclude_files` 只在默认安装中应用
- 自定义规则中的 `exclude` > `filter`

## 开发指南

### 模块设计

项目采用模块化设计，各模块职责明确：

1. **ConfigManager**: 配置文件的读取、验证和管理
2. **dependency_source.py**: `DependencySource.fetch` 把一个依赖变成内容目录（本地文件夹原样返回，压缩包解压并去掉单一外层根目录），独占 `temp_dir` 的布局；内部用 DownloadManager（GitHub Release 下载）和 ExtractManager（多种压缩格式的解压）
3. **InstallManager**: 先清空 project 目录，再按规则把内容目录和 custom_config 装进去
4. **LogManager**: 统一的日志管理
5. **package_archive.py**: 调用方唯一的入口。`build_package_archive` 生成清单、打安装包并跑契约测试；`contract_test` 是契约测试的唯一入口；`KnownHashes.load` 读取并合并已知哈希（类定义在 `manifest.py`，从这里导出）
6. **manifest.py**: 清单格式、归属规则、已知哈希的合并（含默认的 `manifest-history.json` 路径）和各项契约检查，只被 `package_archive.py` 使用

### 扩展性

- **添加新的下载源**: 在DownloadManager中扩展
- **支持新的压缩格式**: 在ExtractManager中添加处理器
- **自定义安装规则**: 修改InstallManager的规则处理逻辑

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

# 检查 package_cfg.json：缺少的字段、不存在的本地路径、不完整的安装规则
python validate_config.py
```

#### 文件排除调试

当使用`--log-level DEBUG`时，可以看到每条规则的源和目标路径，以及每个复制的文件：

```
DEBUG - 排除文件: ['doc/*']
DEBUG - 应用自定义配置规则 [uosc]: temp\uosc\content\scripts -> output\fntv-mpv\portable_config\scripts
DEBUG - 已复制: temp\uosc\content\scripts\uosc\main.lua -> output\...
```

日志不列出被排除的文件。加上`--skip-cleanup`保留临时目录，对照解压结果和复制日志，就能看出哪些文件被排除了。

## 自定义配置规则详解

### 设计理念

自定义配置规则参考了 Node.js 的 extraFiles 功能，采用简洁明了的设计：

```json
{
  "from": "source_path",    // 源路径（相对于解压目录）
  "to": "target_path",      // 目标路径（相对于输出子目录）
  "filter": ["**/*"],       // 可选：包含过滤器
  "exclude": []             // 可选：排除过滤器
}
```

### 路径处理规则

1. **源路径 (`from`)**：
   - 相对于解压后的根目录
   - 可以为空字符串（表示整个解压目录）
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
  "from": "",  // 整个解压目录
  "to": "portable_config",
  "filter": ["**/*.lua"],
  "exclude": ["docs/**", "examples/**"]
}
```

`thumbfast` 就是这种用法：`"from": ""`、`"to": "portable_config/scripts"`、`"filter": ["thumbfast.lua"]`，只把一个文件装进 `scripts/`。

## 运行测试

项目包含单元测试，GitHub API 调用用 mock 替换，不需要网络：

### 推荐方式：使用内置测试运行器

```bash
# 运行所有测试（推荐）
python run_tests.py

# 输出示例：
# 运行MPV配置管理工具测试...
# test_config_validation ... ok  
# test_is_excluded ... ok
# ✅ 所有测试通过!
```

### 直接运行测试文件

```bash
# 运行测试文件
python tests/test_all.py
```

### 测试覆盖范围

- ✅ **ConfigManager**: 配置加载、验证、依赖项管理、输出目录优先级
- ✅ **DependencySource**: 本地文件夹、本地压缩包、下载后解压、离线模式命中和缺失缓存、清理
- ✅ **DownloadManager**: `GITHUB_TOKEN` 认证
- ✅ **ExtractManager**: 格式识别
- ✅ **InstallManager**: 模式匹配、排除功能、默认安装和自定义规则、安装包命名
- ✅ **manifest**: 清单生成、契约测试、历史哈希、完整打包流程（含上次构建的残留不进安装包）
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
A: 检查`package_cfg.json`中的版本号是否存在，网络访问是否正常，依赖项是否正确安装。日志里有“契约测试失败”时，按列出的条目改归档内容，常见原因是新增文件没有在 `ROLE_RULES` 里定归属。

### Q: 排除模式不生效怎么办？
A: 
1. 使用`--log-level DEBUG`查看排除过程详细信息
2. 确认排除模式语法正确，对照[模式表](#exclude_files-排除模式)，使用正斜杠`/`作为路径分隔符
3. 注意大小写：Windows 上不区分，macOS 和 Linux 上区分
4. 确认排除的是相对于`from`目录的相对路径
5. 检查是否同时被`filter`包含和`exclude`排除（exclude优先）
6. 依赖项有`custom_install_rules`时，`exclude_files`不生效，要写进规则的`exclude`

#### 排除模式语法示例：
```json
"exclude": [
  "*.md",           // ✅ 正确：排除所有.md文件
  "*.MD",           // ⚠️  注意：Windows 上同 *.md；macOS 和 Linux 上只排除.MD文件
  "LICENSE*",       // ✅ 正确：排除以LICENSE开头的文件
  "**/.git*",       // ✅ 正确：排除任意深度下文件名以.git开头的文件，如.gitignore
  "test/**",        // ✅ 正确：排除任意一级名为test的目录
  "**/test/**",     // ❌ 错误：只比较文件名，匹配不到任何文件，应写 "test/**"
  "docs/**/*.md"    // ❌ 错误：按子串比较 "docs" 和 "*.md"，匹配不到；可用 "*.md" 加规则的 from 限定目录
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
