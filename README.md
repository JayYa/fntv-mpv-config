# MPV配置管理工具

一个用于自动下载、配置和打包MPV播放器及其插件的Python工具。支持版本管理、插件热插拔和GitHub Actions自动化构建。

## 功能特点

- 🎯 **自动化管理**: 自动下载MPV播放器和插件
- 🔧 **版本控制**: 通过配置文件管理所有组件版本
- 🔌 **插件热插拔**: 轻松启用/禁用插件
- 📦 **智能打包**: 自动创建便携式安装包
- 🗜️ **多格式支持**: 支持7z、zip、rar等多种压缩格式
- 🛠️ **自定义配置**: 支持自定义配置文件
- 🚀 **CI/CD支持**: GitHub Actions每日自动构建
- 🚫 **智能过滤**: 双层文件过滤系统，排除不需要的文件
- ⚙️ **灵活配置**: 分离式配置设计，清晰的文件排除和自定义安装规则

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
│   └── log_manager.py     # 日志管理
├── custom_config/         # 自定义配置目录
│   ├── mpv/
│   │   └── input.conf     # MPV快捷键配置
│   └── uosc/
│       └── script-opts/
│           └── uosc.conf  # UOSC插件配置
├── tests/                 # 测试目录
├── .github/workflows/     # GitHub Actions工作流
├── package_cfg.json          # 主配置文件
├── requirements.txt      # Python依赖
├── run.py               # 运行脚本
└── README.md           # 文档
```

## 快速开始

### 1. 环境准备

#### 系统要求
- Python 3.7+
- 7-Zip (用于解压某些压缩格式)

#### 安装7-Zip (必需)
```bash
# Windows (使用winget包管理器)
winget install --id 7zip.7zip

# 或者手动下载安装
# 访问 https://7-zip.org/ 下载并安装
```

#### 克隆项目并安装依赖
```bash
# 克隆仓库
git clone https://github.com/your-username/fntv-mpv-config.git
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
      "enabled": false
    }
  }
}
```

### 3. 基本使用

```bash
# 处理所有启用的依赖项
python run.py

# 只处理指定的依赖项
python run.py --deps mpv uosc

# 列出所有依赖项
python run.py --list

# 启用/禁用依赖项
python run.py --enable uosc_danmaku
python run.py --disable uosc_danmaku

# 跳过下载，只安装（用于调试）
python run.py --skip-download

# 只下载，不安装
python run.py --skip-install

# 使用本地包文件
python run.py --deps local_plugin  # 配置文件中指定了local_path的依赖项

# 输出到其它目录（不改 package_cfg.json；也可设环境变量 FNTV_MPV_OUTPUT_DIR）
python run.py --output-dir ./output

# 清理下载和构建目录
python run.py --clean temp      # 清理临时下载文件
python run.py --clean output    # 清理构建的安装包
python run.py --clean all       # 清理所有临时文件和构建产物
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
- **相对路径**：相对于项目根目录，如 `./local_packages/file.zip` 或 `./local_packages/folder`
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
- 本地文件会被复制到临时目录，保持一致的处理流程
- 文件夹方式会自动跳过解压步骤，提高处理效率

## 配置文件详解

### package_cfg.json 主配置文件

```json
{
  "name": "fntv-mpv-config",
  "version": "1.0.0",
  "config": {
    "output_dir": "./output",          // 输出目录
    "temp_dir": "./temp",              // 临时目录
    "custom_config_dir": "./custom_config"  // 自定义配置目录
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
        "doc/*",
        "installer/*", 
        "*.bat",
        "*.md",
        "LICENSE*"
      ]
    },
    "uosc": {
      "name": "uosc插件",
      "url": "https://github.com/tomasklaen/uosc/releases", 
      "version": "5.13.0",
      "filename_pattern": "uosc",
      "format": "zip",
      "enabled": true,
      "exclude_files": [                // 排除文档和许可证文件
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

- `exclude_files`: 排除文件数组，在安装时排除不需要的文件和目录
- `custom_install_rules`: 自定义配置安装规则数组（可选）

#### 输出目录

`config.output_dir` 是默认输出目录，可以按次覆盖，优先级从高到低：

1. 命令行 `--output-dir <目录>`
2. 环境变量 `FNTV_MPV_OUTPUT_DIR`（空值视为未设置）
3. `package_cfg.json` 的 `config.output_dir`

覆盖值只作用于本次运行，不会写回配置文件。`--clean output` 同样按这个顺序确定要清理的目录。

#### exclude_files 排除模式

`exclude_files` 用于排除下载内容中不需要的文件，支持glob模式：

```json
{
  "exclude_files": [
    "*.md",              // 排除所有markdown文档
    "LICENSE*",          // 排除许可证文件
    "doc/*",            // 排除doc目录下的所有文件
    "installer/*",      // 排除installer目录
    "*.bat",            // 排除批处理文件
    "**/.github/**",    // 排除GitHub工作流目录
    "**/test/**",       // 排除测试目录
    "**/docs/**"        // 排除文档目录
  ]
}
```

#### custom_install_rules 自定义安装规则

`custom_install_rules` 用于定义特殊的文件安装规则，参考 Node.js extraFiles 功能设计：

- `from`: 源目录路径（相对于解压后的根目录，可以为空）
- `to`: 目标目录路径（相对于输出根目录）
- `filter`: 文件过滤器数组，支持glob模式（可选，默认为 `["**/*"]`）
- `exclude`: 排除模式数组，支持glob模式（可选）

**设计理念**：
- 简洁的 `from` -> `to` 映射关系
- 统一的路径处理逻辑，避免复杂的特殊情况判断
- 灵活的过滤器和排除规则支持

**支持的文件模式**：
  - `**/*`: 所有文件
  - `*.lua`: 所有Lua文件
  - `**/script-opts/**`: script-opts目录下的所有文件
  - `*.md`: 排除所有Markdown文件

### 配置工作原理

1. **默认安装**: 所有文件默认会被安装到相应位置
2. **文件排除**: 应用 `exclude_files` 模式排除不需要的文件
3. **自定义规则**: 如果定义了 `custom_install_rules`，则按规则精确安装文件

**安装路径处理**：
- 目标路径统一相对于输出目录处理
- 支持 `portable_config/` 前缀的完整路径
- 空目标路径默认安装到 `portable_config` 根目录

**配置规则示例**：
```json
{
  "from": "scripts",                    // 从解压包的scripts目录
  "to": "portable_config/scripts",      // 安装到输出目录的portable_config/scripts
  "filter": ["**/*.lua"],               // 只包含lua文件
  "exclude": ["**/test/**"]             // 排除测试目录
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
      "doc/*",             // 排除文档目录
      "installer/*",       // 排除安装程序
      "*.bat",            // 排除批处理文件
      "*.md",             // 排除文档
      "LICENSE*"          // 排除许可证
    ]
  }
}
```

## 自定义配置

在 `custom_config` 目录下放置自定义配置文件，程序会自动将它们复制到最终的portable_config目录中。

### 目录结构示例

```
custom_config/
├── mpv/
│   ├── input.conf        # 快捷键配置
│   └── mpv.conf          # MPV主配置
├── uosc/
│   └── script-opts/
│       └── uosc.conf     # UOSC插件配置
└── scripts/
    └── custom.lua        # 自定义脚本
```

## GitHub Actions 自动化

项目包含GitHub Actions工作流，支持：

- **每日自动构建**: 每天自动检查更新并构建
- **手动触发**: 可以手动触发构建
- **自动发布**: 构建完成后自动创建Release

### 配置说明

工作流文件位于 `.github/workflows/daily-build.yml`，主要特性：

- 使用Windows环境进行构建
- 自动上传构建产物
- 创建带时间戳的Release
- 支持构建失败时的错误处理

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

打包后自动跑契约测试（`run.py` 内部一次，workflow 里再用 `check_archive.py` 带 tag 跑一次）：清单和 zip 一一对应、哈希正确、`role` 合法、各托管插件入口脚本存在、`provides` 和 `managedDirs` 齐全、`knownHashes` 只增不减。任何一条失败都不会发版。手工检查一个 zip：

```bash
python check_archive.py mpv-package-<时间>.zip --archive-version fntv-mpv-v<时间> [--previous-manifest 上一版的fntv-manifest.json]
```

## 配置架构说明

### 双层配置系统 (v1.0.0+)

本工具采用双层配置系统，将文件过滤和自定义安装规则分离：

#### 1. exclude_files - 文件排除层
- **目的**: 排除下载内容中不需要的文件
- **时机**: 在安装过程中应用
- **适用场景**: 排除文档、许可证、调试文件等

#### 2. custom_install_rules - 自定义安装层  
- **目的**: 定义精确的文件安装规则
- **时机**: 覆盖默认安装行为
- **适用场景**: 复杂的目录结构映射
- **设计理念**: 参考 Node.js extraFiles 功能，简洁的路径映射

### 处理流程

```
下载文件 → 解压 → 选择安装模式 → 应用exclude_files → 复制文件
```

1. **下载解压**: 从GitHub下载并解压文件
2. **安装模式选择**:
   - 如果定义了`custom_install_rules`: 使用自定义规则安装
   - 否则: 使用默认安装（直接复制到相应目录）
3. **文件过滤**: 在任何安装模式中都会应用`exclude_files`排除规则

### 配置优先级

- `custom_install_rules` > 默认安装
- `exclude_files` 在任何安装方式中都会被应用
- 自定义规则中的 `exclude` > `filter`

## 开发指南

### 模块设计

项目采用模块化设计，各模块职责明确：

1. **ConfigManager**: 配置文件的读取、验证和管理
2. **DownloadManager**: 处理各种下载源的文件下载
3. **ExtractManager**: 支持多种压缩格式的解压
4. **InstallManager**: 根据规则安装文件和配置
5. **LogManager**: 统一的日志管理

### 扩展性

- **添加新的下载源**: 在DownloadManager中扩展
- **支持新的压缩格式**: 在ExtractManager中添加处理器
- **自定义安装规则**: 修改InstallManager的规则处理逻辑

### 调试技巧

```bash
# 启用详细日志（推荐用于排除模式调试）
python run.py --log-level DEBUG

# 跳过下载步骤（用于测试安装逻辑）
python run.py --skip-download

# 不清理临时文件（用于检查中间结果）
python run.py --skip-cleanup

# 只处理特定依赖项
python run.py --deps uosc,uosc_danmaku
```

#### 文件排除调试

当使用`--log-level DEBUG`时，可以看到文件排除过程的详细信息：

```
DEBUG - 应用exclude_files: ['*.md', 'LICENSE*']
DEBUG - 应用自定义配置规则 [uosc]: temp\uosc_extracted\scripts -> output\fntv-mpv-config\portable_config\scripts
DEBUG - 已复制: temp\uosc_extracted\scripts\uosc\main.lua -> output\...
DEBUG - 排除文件: README.md (匹配模式: *.md)
DEBUG - 排除文件: LICENSE (匹配模式: LICENSE*)
```

这有助于验证排除规则和自定义配置规则是否按预期工作。

## 自定义配置规则详解

### 设计理念

自定义配置规则参考了 Node.js 的 extraFiles 功能，采用简洁明了的设计：

```json
{
  "from": "source_path",    // 源路径（相对于解压目录）
  "to": "target_path",      // 目标路径（相对于输出目录）
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
   - 统一相对于输出目录处理
   - 支持完整路径如 `"portable_config/scripts"`
   - 空字符串表示默认安装到 `portable_config` 根目录

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
  "exclude": ["**/test/**", "**/*.md"]
}
```

#### 示例3：整个目录重新映射
```json
{
  "from": "",  // 整个解压目录
  "to": "portable_config",
  "filter": ["**/*.lua"],
  "exclude": ["**/docs/**", "**/examples/**"]
}
```

## 运行测试

项目包含完整的单元测试，支持多种运行方式：

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

### 使用pytest（如果遇到卡死问题，请使用上述方式）

```bash
# 使用pytest（可能在某些环境中卡死）
python -m pytest tests/ -v
```

### 测试覆盖范围

- ✅ **ConfigManager**: 配置加载、验证、依赖项管理
- ✅ **DownloadManager**: URL解析、初始化测试  
- ✅ **ExtractManager**: 格式识别
- ✅ **InstallManager**: 模式匹配、排除功能测试

### 故障排除

如果`pytest`命令卡死或无响应：
1. 使用`python run_tests.py`代替
2. 或直接运行`python tests/test_all.py`
3. 检查网络连接（某些测试可能需要访问GitHub API）

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

### Q: 下载失败怎么办？
A: 检查网络连接，确认GitHub访问正常。可以使用`--log-level DEBUG`查看详细错误信息。

### Q: 如何添加新的插件？
A: 在`package_cfg.json`的`dependencies`中添加新的插件配置。对于简单插件，只需配置基本参数和排除规则；对于复杂插件，可以使用自定义配置规则精确控制文件安装位置。

示例：
```json
{
  "new_plugin": {
    "name": "新插件",
    "url": "https://github.com/author/plugin/releases",
    "version": "1.0.0",
    "exclude_files": ["*.md", "LICENSE*"],
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
A: 检查`package_cfg.json`中的版本号是否存在，网络访问是否正常，依赖项是否正确安装。

### Q: 排除模式不生效怎么办？
A: 
1. 使用`--log-level DEBUG`查看排除过程详细信息
2. 确认排除模式语法正确，使用正斜杠`/`作为路径分隔符
3. 注意排除模式区分大小写
4. 确认排除的是相对于`from`目录的相对路径
5. 检查是否同时被`filter`包含和`exclude`排除（exclude优先）

#### 排除模式语法示例：
```json
"exclude": [
  "*.md",           // ✅ 正确：排除所有.md文件
  "*.MD",           // ⚠️  注意：区分大小写，只排除.MD文件
  "LICENSE*",       // ✅ 正确：排除以LICENSE开头的文件
  "**/.git*",       // ✅ 正确：排除任意深度的.git相关文件
  "test\\**",       // ❌ 错误：应使用正斜杠 "test/**"
  "docs/**/*.md"    // ✅ 正确：排除docs目录下的所有.md文件
]
```

### Q: 如何验证排除模式是否正确？
A: 使用DEBUG模式运行特定依赖项：
```bash
python run.py --deps plugin_name --log-level DEBUG --skip-cleanup
```
然后检查输出日志和生成的文件。

## 许可证

本项目采用MIT许可证，详见LICENSE文件。


## 更新日志

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
