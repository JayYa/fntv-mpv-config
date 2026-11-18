# 编码规范

审查时逐条对照。lint（`ruff check .`）和测试已经在 CI 里跑，这里只放需要判断的规则。

## 文档与代码一致

- diff 改了行为，就核对描述这个行为的每一处：README、GLOSSARY.md、`--help` 文字、docstring、报错文字。说法和新代码对不上的，都算违规。重点查"任何失败都抛 X"、"只会抛 Y"这类全称说法。
- 术语沿用 GLOSSARY.md 里的叫法，避开词条 _Avoid_ 里列的词。新引入的领域概念，要在 GLOSSARY.md 里加词条。
- README 写给使用者：怎么用、配置字段、清单格式。不要逐个列出 module 或测试。代码自己能说明的，不再抄一份。

## 分层

- 只有 `main.py` 知道命令行。`build()` 和更内层 module 的报错、日志、docstring 里不出现 `--skip-package` 这类参数名，要说的是构建范围或选项本身。
- 打包配置在加载时就把字段全部校验完。之后的 module 拿到的都是合法值，不再自己重新校验，也不会因为配置写错而抛出 `ValueError` 这类没人接的异常。
- 失败要带原因往外抛（`BuildFailed`、`ConfigError`、`FetchError` 等），原始异常用 `from` 接在异常链上。不要记一行日志就返回 `None`，也不要用 `except Exception` 兜底。

## 测试

- 测试经过 module 的接口去测（`load_package_config`、`load_layout`、`fetch`、`build()`、`main(argv)`），不去手工摆弄接口背后的暂存布局或私有属性。
- 一条测试只验证一条规则，测试名把这条规则说出来。

## 提交

- refactor 和 fix 分开提交。顺手做的结构调整（删参数、改函数归属）不要混进修 bug 的提交。
