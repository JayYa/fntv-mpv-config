# 默认值放在命名 profile 段里，薄 mpv.conf 先 include 再 profile=

默认值写在托管的 `fntv/defaults.conf` 的 `[fntv-defaults]` 段里；`mpv.conf` 是薄文件，前两个有效行是 `include="~~/fntv/defaults.conf"` 和 `profile=fntv-defaults`，用户设置写在后面。契约测试检查这两行的位置。

没有直接把默认值写在被 include 文件的顶层，是因为那样默认值会覆盖用户设置。MPV 55d3feb45 实测（见 `options/parse_configfile.c` 和 `m_config_frontend.c`）：配置文件顶层的选项先存进 default profile，读完整个文件才按顺序应用；include 在应用时才读入目标文件，目标文件的顶层选项追加到 default profile 末尾，排在外层文件所有行之后。放进命名段再用 `profile=` 立即应用，默认值就在 include 行的位置生效，后面的用户设置覆盖它。

## Consequences

- 托管的 `defaults.conf` 里不能有段外的顶层选项；新增默认值都写进 `[fntv-defaults]`。
- 升级 mpv 后如果 include 或 profile 的应用时机变了，要重新验证覆盖顺序。
