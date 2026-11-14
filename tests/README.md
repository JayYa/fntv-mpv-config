# 测试文档

## 测试覆盖范围

本项目包含了全面的单元测试，覆盖了所有核心功能模块。

### 测试文件结构

```
tests/
├── test_all.py          # 原有的基础功能测试
├── test_local_core.py   # 本地包功能核心测试
├── test_install_core.py # 安装管理器核心功能测试
├── test_manifest.py     # 归档清单 fntv-manifest.json 的生成与契约测试
```

`test_manifest.py` 覆盖清单生成（`build_manifest`）、对 zip 的契约测试（`check_archive` 和根目录的 `check_archive.py`），以及用本地假插件跑完整打包流程后 zip 带清单、契约失败时打包失败。

### 测试模块详情

#### 1. test_all.py - 基础功能测试
- **TestConfigManager**: 配置管理器测试
  - `test_load_config`: 测试配置文件加载
  - `test_config_validation`: 测试配置验证
  - `test_get_enabled_dependencies`: 测试获取已启用依赖项

- **TestDownloadManager**: 下载管理器测试
  - `test_init`: 测试下载管理器初始化
  - `test_parse_github_url`: 测试GitHub URL解析

- **TestExtractManager**: 解压管理器测试
  - `test_get_format`: 测试文件格式识别

- **TestInstallManager**: 安装管理器测试
  - `test_matches_pattern`: 测试文件模式匹配
  - `test_is_excluded`: 测试文件排除功能

#### 2. test_local_core.py - 本地包功能测试
- **TestLocalPackageCore**: 本地包核心功能测试
  - `test_is_local_file_detection`: 测试本地文件检测
    - 测试 local_path 配置检测
    - 测试 url 为本地路径的检测
    - 测试网络URL的排除
  - `test_local_directory_handling`: 测试本地文件夹处理
    - 测试文件夹复制到临时目录
    - 测试文件结构保持完整
    - 测试路径生成正确性

#### 3. test_install_core.py - 安装管理器功能测试
- **TestInstallManagerCore**: 安装管理器核心功能测试
  - `test_default_installation`: 测试默认安装规则
    - 测试插件安装到正确的目录结构
    - 测试文件排除功能
    - 测试文件内容完整性
  - `test_custom_install_rule_basic`: 测试基本自定义安装规则
    - 测试 from/to 路径映射
    - 测试文件过滤器功能
    - 测试目标路径生成
  - `test_custom_install_rule_root_copy`: 测试根目录复制规则
    - 测试从根目录复制
    - 测试多种文件类型过滤
    - 测试子目录结构保持

## 新增功能测试

### 本地包支持测试

1. **本地文件检测** (test_is_local_file_detection)
   - ✅ 检测 `local_path` 配置项
   - ✅ 检测 `url` 为本地路径
   - ✅ 排除网络URL (http/https/ftp)
   - ✅ 处理空配置

2. **本地文件夹处理** (test_local_directory_handling)
   - ✅ 复制文件夹到临时目录
   - ✅ 保持文件夹结构完整
   - ✅ 生成正确的提取路径名
   - ✅ 验证文件内容正确

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
# 基础功能测试
python tests/test_all.py

# 本地包功能测试
python tests/test_local_core.py

# 安装管理器功能测试
python tests/test_install_core.py
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
test_config_validation (tests.test_all.TestConfigManager)
测试配置验证 ... ok
test_get_enabled_dependencies (tests.test_all.TestConfigManager)
测试获取已启用的依赖项 ... ok
...
test_default_installation (tests.test_install_core.TestInstallManagerCore)
测试默认安装功能 ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.057s

OK
==================================================
✅ 所有测试通过!
```

## 测试覆盖的修改内容

### 1. 本地包支持功能
- ✅ `DownloadManager._is_local_file()` - 本地文件检测
- ✅ `DownloadManager._handle_local_directory()` - 本地文件夹处理
- ✅ `DownloadManager._get_directory_name_from_config()` - 目录名生成
- ✅ `DownloadManager._directory_is_newer()` - 目录时间比较

### 2. 安装管理器重构
- ✅ `InstallManager._install_extracted_files_default()` - 默认安装逻辑
- ✅ `InstallManager._apply_custom_config_rule()` - 自定义规则应用
- ✅ 移除硬编码的插件特定逻辑
- ✅ 简化路径处理逻辑

### 3. 主流程改进
- ✅ `main.py` 中本地文件夹检测逻辑
- ✅ 跳过解压步骤的条件判断
- ✅ 配置驱动的安装流程

## 测试质量保证

1. **隔离性**: 每个测试使用独立的临时目录
2. **完整性**: 测试覆盖正常情况和边界情况
3. **可重复性**: 测试可以多次运行且结果一致
4. **清理**: 所有测试后自动清理临时文件
5. **可读性**: 测试名称和注释说明功能目的

所有测试都通过，确保了代码重构和新功能的正确性。
