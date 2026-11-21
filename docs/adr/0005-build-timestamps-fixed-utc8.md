# 构建时间戳固定用 UTC+8

安装包名里的构建时间戳一律用北京时间，用固定偏移 `timezone(timedelta(hours=8))` 表示，而不是 `zoneinfo.ZoneInfo("Asia/Shanghai")`。中国没有夏令时，固定偏移和时区库结果一致；而 Windows 上的 Python 默认没有 IANA 时区库，用 `zoneinfo` 就得额外依赖 `tzdata`。
