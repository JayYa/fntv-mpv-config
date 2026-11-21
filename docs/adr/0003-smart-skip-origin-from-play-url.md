# smart_skip 的 skipinfo 请求发往播放地址所在的 Proxy

smart_skip 从播放地址取 scheme、主机和端口（a5e1137 起），skipinfo 的读写都发往这个 origin，而不是写死的地址或单独的配置项。播放地址本来就指向客户端的 Proxy，用同一个 origin 就不需要另外配置或发现服务器地址。

客户端要依赖这个行为，所以清单的 `provides` 里声明能力 `smart-skip.origin-from-play-url`，版本 1；契约测试检查安装包里有这项能力。

## Consequences

- 改变请求目标的方式（比如改回固定地址）要同时去掉或升级这项能力，否则客户端会按旧约定接入。
