# 测试

## 运行

```bash
python run_tests.py                              # 全部测试，CI 也跑这个
python -m unittest tests.test_build              # 单个模块，从仓库根目录用 -m 运行
```

`run_tests.py` 自动发现 `tests/` 下所有 `test_*.py`，新增测试文件不用登记。

## 约定

- 测试都不访问网络：下载器、上一版清单和端到端 `build()` 的测试注入假的 HTTP 会话，依赖来源的测试用 mock 替换整个下载器。
- 测试经过各 module 的接口走（`load_package_config`、`load_layout`、`fetch`、`build()`、`main(argv)` 等），不去摆弄接口背后的暂存布局。
- 每个测试用自己的临时目录。

## 测试文件

每个文件测什么，看测试类名和测试名；这里只记从代码里看不出来的事。

- `test_build.py`：用本地假依赖跑完整的 `build()`，是构建流程唯一的端到端测试。
- `test_main.py`：经 `main(argv)` 测参数到构建范围的映射、输出和退出码。
- `test_package_archive.py`：直接拿临时的 portable_config 目录测 `build_package_archive`，不用搭依赖配置。
- `test_contract_test.py`：契约测试用从仓库 `package_cfg.json` 读出的依赖布局；也测根目录的 `check_archive.py`。
- `test_skip_window.py`：用 `lupa` 内嵌的 Lua 5.1 加载 `local_packages/smart_skip/skip_window.lua`，不需要装 Lua 或 mpv。
