# 测试文档

## 测试覆盖范围

本项目包含了全面的单元测试，覆盖了所有核心功能模块。

### 测试文件结构

```
tests/
├── test_download_manager.py # 下载器：select_asset 直接用资产列表测，HTTP 行为经 download() 和假的会话测
├── test_extract.py      # 解压：格式识别、tar 解压和越界成员
├── test_package_config.py # 打包配置：经 load_package_config 测三种依赖来源和字段校验
├── test_main.py         # 命令行：经 main(argv) 测 --list、--clean、--deps 的输出和退出码
├── test_dependency_layout.py # 依赖布局：加载校验、入口文件、托管目录、基础配置
├── test_dependency_source.py # 依赖来源：每种依赖经 fetch 变成内容目录
├── test_install_core.py # 安装管理器核心功能测试
├── test_manifest.py     # 归档清单 fntv-manifest.json 的生成与契约测试
├── test_package_archive.py # 安装包构建：已知哈希、打包、命名、契约测试失败
├── test_package_defaults.py # 固定的依赖版本和首次安装的默认值
├── test_skip_window.py  # smart_skip 的跳过窗口 module（Lua，经 lupa 加载）
├── test_release.py      # 构建结果 JSON、Release 说明（含已停用的依赖）和 --result-file 参数
```

测试都不访问网络：下载器的测试给 `DownloadManager` 注入假的 HTTP 会话，依赖来源的测试用 mock 替换整个下载器。

`test_manifest.py` 覆盖清单生成（`build_manifest`）、经 `contract_test` 和根目录的 `check_archive.py` 对 zip 跑的契约测试，以及两个跑完整 `run()` 的端到端测试。`test_package_archive.py` 直接拿临时的 portable_config 目录测 `build_package_archive`，不用搭依赖配置。

### 测试模块详情

#### 0. test_package_config.py - 打包配置测试
- **TestLoadPackageConfig**: 全部经 `load_package_config` 测
  - GitHub Release、本地文件夹、本地压缩包三种来源；`local_path` 和 `config` 里的路径按配置文件所在目录解析
  - `enabled` 默认 `true`；停用的依赖（含 mpv）留在 `dependencies` 里，不进依赖布局，入口文件不再必需；停用的依赖照样校验，`enabled` 不是布尔值也报错
  - 不认识的字段、`url` 和 `local_path` 都写或都不写、`url` 不是 GitHub Release、缺 `filename_pattern` / `format` / `name` / `version`、本地来源写了 `format`、`format` 不是支持的压缩格式、本地压缩包的扩展名不认识都报 `ConfigError`
  - 顶层和 `config` 块的多余字段、缺必填项、`enable_proxy` 不是布尔值、文件不存在或不是 JSON 对象都报错；依赖布局的错误也作为 `ConfigError` 抛出
  - 输出目录优先级：`--output-dir` > `FNTV_MPV_OUTPUT_DIR` > `config.output_dir`，空环境变量视为未设置
  - 仓库的 `package_cfg.json` 能加载

#### 0b. test_main.py - 命令行测试
- **TestCommandLine**: 经 `main(argv)` 测
  - `--list` 列出每个依赖的显示名、版本和来源，停用的标"已停用"
  - 配置不合法时 `--list`、`--clean` 以退出码 1 结束；`--deps` 写了不存在或停用的依赖名也以 1 结束
  - `--enable` / `--disable` 已删除，传入时是参数错误（退出码 2）

#### 1. test_download_manager.py - 下载器测试
- **TestSelectAsset**: 直接拿资产列表调 `select_asset`
  - 名字等于 `<filename_pattern>.<format>` 的资产优先；没有时取唯一的前缀匹配
  - 前缀匹配不止一个、或一个都没有时报 `DownloadError`，报错里列出资产名
- **TestDownloadManager**: 经 `DownloadManager.download` 测，注入假的 HTTP 会话
  - 下载选中的资产；没有匹配的资产时不下载任何文件
  - API 返回 403 时报限流，返回 404 时报没有这个 Release，都不猜文件名
  - 已有文件大小等于资产大小时不重下，大小不同时重下
  - 下载的字节数和资产大小对不上、或连接中途断开时报错，不留下文件
  - 代理只加在资产下载地址上，不加在 API 上；设了 `GITHUB_TOKEN` 时 API 请求带认证头，没设时匿名

#### 1b. test_extract.py - 解压测试
- **TestExtractArchive**
  - 按扩展名认出格式（含 `.tar.gz`），认不出的返回 None，解压时报 `ExtractError`
  - tar.gz 能解压；成员路径越出目标目录时报 `ExtractError`，不写出文件

#### 2. test_dependency_source.py - 依赖来源测试
- **TestDependencySource**: 全部经 `DependencySource.fetch` / `clean` 测，下载器用 mock 替换
  - 本地文件夹原样作为内容目录，不碰 temp
  - 本地压缩包解压到 temp，单一外层根目录被去掉
  - 本地路径不存在时报 `FetchError`
  - 下载后解压，同一依赖之前下载的旧压缩包被删掉
  - 离线模式用 temp 里缓存的压缩包、不调用下载器；没有缓存时报 `FetchError`
  - `clean` 删掉整个 temp

#### 2b. test_dependency_layout.py - 依赖布局测试
- **TestLoadLayout**: 全部经 `load_layout` 测
  - `install_to` 和 `custom_install_rules` 必须且只能写一个；`exclude_files` 不能和规则一起写
  - 安装规则的未知字段、越出内容目录的 `from`、空或非列表的 `filter`、写错的 `[...]`、以 `!` / `/` 开头或以 `/` 结尾的模式、空的或不是对象列表的 `custom_install_rules` 都报错；`exclude_files` 按同样的规则校验
  - `managed_dir` 必须在 `portable_config/` 下并包含 `entry`；路径不能越出安装包
  - `custom_config/base/` 和 `custom_config/<依赖名>/` 的文件装进 portable_config，同一路径出现两次就报错，依赖不能叫 `base`
  - 仓库的 `package_cfg.json` 推导出的必需路径（含 `mpv.exe`）和托管目录

#### 3. test_install_core.py - 安装管理器功能测试
- **TestInstallManagerCore**: 安装管理器核心功能测试，规则都经 `load_layout` 和 `install_dependency` 走
  - `test_install_to_copies_the_content_dir_with_excludes`: 按 `install_to` 安装并排除 `exclude_files`
  - `test_install_to_dot_puts_the_content_at_the_archive_root`: `install_to: "."` 装到安装包根目录
    - 测试文件内容完整性
  - `test_custom_install_rule_basic`: 测试基本自定义安装规则
    - 测试 from/to 路径映射
    - 测试文件过滤器功能
    - 测试目标路径生成
  - `test_custom_install_rule_root_copy`: 测试根目录复制规则
    - 测试从根目录复制
    - 测试多种文件类型过滤
    - 测试子目录结构保持
  - `test_patterns_without_a_slash_match_file_names_at_any_depth` / `test_patterns_with_a_slash_are_anchored_at_the_rule_source`: gitignore 式匹配语义
  - `test_question_marks_classes_and_leading_double_stars`: `?`、`[...]`、`[!...]`、开头的 `**/` 和反斜杠写法
  - `test_a_rule_whose_source_is_missing_fails_the_install` / `test_a_filter_that_installs_nothing_fails_the_install`: 规则对不上内容目录时报 `InstallError`
  - `test_two_dependencies_installing_the_same_file_fail_the_install`: 两个依赖装同一个文件时报 `InstallError`
  - `test_paths_that_differ_only_in_case_are_the_same_file`: 只差大小写的路径算同一个文件
  - `test_custom_config_may_replace_a_file_the_dependency_ships`: `custom_config/<依赖名>/` 可以替换依赖自带的文件
- **TestPackageTimestampCli**: `--package-timestamp` 参数的解析和校验
- **TestRepositoryCustomConfig**: 用仓库里真实的 `package_cfg.json` 和 `custom_config` 测试
  - 不装任何依赖时基础配置 `custom_config/base/` 也装进 `portable_config/`
  - `custom_config/uosc_danmaku/` 下的文件装进 `portable_config/`
  - `custom_config` 根目录下没有散文件

#### 4. test_manifest.py - 归档清单测试
- **TestBuildManifest**: 清单列出每个文件的路径、哈希和 `role`，没有归属规则的文件让生成失败
- **TestCheckArchive**: 经 `contract_test`（传入从仓库 `package_cfg.json` 读出的依赖布局 `CLIENT_LAYOUT`）做的每项契约检查，含根目录缺 `mpv.exe`；清单资产与 zip 内清单的比对；`check_archive.py` 的退出码、`--manifest-asset` 和 `--config`
- **TestShippedMpvConf**: 仓库里的 `defaults.conf` 和薄 `mpv.conf` 符合分层约定
- **TestHistory**: 历史哈希的收集与合并、`obsolete`、`knownHashes` 只增不减
- **TestPackagingProducesManifest**: 端到端，用本地假 mpv 和假插件跑完整的 `run()`；mpv 装到根目录、基础配置进安装包，返回的构建结果指向实际的安装包和清单，上次构建留在 project 目录里的文件不进安装包，停用的插件不进安装包、`components` 和 `managedDirs`，它的托管文件进 `obsolete`，命令行 `--result-file` 写出构建结果和 Release 说明

#### 5. test_package_archive.py - 安装包构建测试
- **TestKnownHashes**: 合并历史哈希文件与上一版清单，默认读仓库里的 `manifest-history.json`
- **TestBuildPackageArchive**: 时间戳决定归档版本、zip 名和清单资产位置；已知哈希进清单；契约测试失败抛 `ContractTestFailed`；默认用北京时间，格式错误的时间戳在写任何文件前被拒绝；`is_package_archive_name` 只认自己产出的 zip 名

#### 6. test_package_defaults.py - 发版输入测试
- **TestPackageDefaults**: 固定 `mpv`、`uosc`、`uosc_danmaku` 的版本和下载地址；`danmaku-history.json` 只含 `{"show_danmaku": true}`。升级依赖项时要同时改这里的期望值

#### 7. test_skip_window.py - 跳过窗口测试
用 `lupa` 内嵌的 Lua 5.1 加载 `local_packages/smart_skip/skip_window.lua`，不需要装 Lua 或 mpv。
- **TestManualWindows**: 服务器的片头/片尾时长换成区间，片尾超过一半、片头与片尾重叠、时长未知时丢弃
- **TestChapterWindows** / **TestAutoWindows**: 章节检测；自动模式每段先取章节，没有再取时长；已删除的静音模式按自动模式处理
- **TestEdits**: 菜单里输入时长和「设为当前位置」的校验与换算

## 新增功能测试

### 安装规则重构测试

1. **默认安装规则** (test_default_installation)
   - ✅ 插件安装到 `portable_config/scripts/` 目录
   - ✅ 文件排除功能正常工作
   - ✅ 保持原有文件结构
   - ✅ 文件内容完整复制

2. **自定义安装规则** (test_custom_install_rule_*)
   - ✅ 基本 from/to 路径映射
   - ✅ 文件过滤器 (filter) 功能
   - ✅ 根目录复制 (from: ".")
   - ✅ 多种文件类型过滤

## 运行测试

### 自动发现并运行所有测试（推荐）
```bash
python run_tests.py
```

测试运行器会自动：
- 🔍 发现 `tests/` 目录下所有 `test_*.py` 文件
- 📊 显示发现的测试文件统计信息
- 🚀 自动运行所有测试用例
- 📈 提供详细的测试结果报告

### 运行特定测试模块
```bash
# 下载器测试
python -m unittest tests.test_download_manager

# 依赖来源测试（导入 src 包，从仓库根目录用 -m 运行）
python -m unittest tests.test_dependency_source

# 安装管理器功能测试
python tests/test_install_core.py

# 归档清单测试
python tests/test_manifest.py

# 发版输入测试
python tests/test_package_defaults.py
```

### 添加新测试

只需要在 `tests/` 目录下创建新的 `test_*.py` 文件，测试运行器会自动发现并执行：

```python
# tests/test_new_feature.py
import unittest

class TestNewFeature(unittest.TestCase):
    def test_something(self):
        self.assertTrue(True)
```

运行 `python run_tests.py` 就会自动包含新测试！

### 测试结果示例
```
运行MPV配置管理工具测试...
==================================================
test_formats_are_recognised_by_extension (tests.test_extract.TestExtractArchive) ... ok
...
test_default_installation (tests.test_install_core.TestInstallManagerCore)
测试默认安装功能 ... ok

----------------------------------------------------------------------
Ran 60 tests in 2.585s

OK
==================================================
🎉 所有测试通过!
✅ 运行了 60 个测试
```

## 测试覆盖的修改内容

### 1. 依赖来源
- ✅ `DependencySource.fetch()` - 本地文件夹、本地压缩包、下载、离线缓存
- ✅ `DependencySource.clean()` - 删除临时目录

### 2. 安装管理器重构
- ✅ `InstallManager.install_dependency()` - 按依赖布局的 `install_to` 或自定义规则安装
- ✅ `InstallManager.install_base_config()` - 基础配置
- ✅ 移除硬编码的插件特定逻辑
- ✅ 简化路径处理逻辑

### 3. 主流程改进
- ✅ 安装前清空 project 目录，上次构建的残留不进安装包
- ✅ `--deps` 不带 `--skip-package` / `--skip-install` 时拒绝运行
- ✅ 配置驱动的安装流程

## 测试质量保证

1. **隔离性**: 每个测试使用独立的临时目录
2. **完整性**: 测试覆盖正常情况和边界情况
3. **可重复性**: 测试可以多次运行且结果一致
4. **清理**: 所有测试后自动清理临时文件
5. **可读性**: 测试名称和注释说明功能目的

所有测试都通过，确保了代码重构和新功能的正确性。
