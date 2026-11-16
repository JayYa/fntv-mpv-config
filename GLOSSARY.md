# fntv-mpv-config

为飞牛影视（fntv）客户端打包的 mpv 播放器及其插件与配置。

## Language

### 智能跳过（smart skip）

**跳过窗口（skip window）**:
一个文件里要自动跳过的片头区间与片尾区间（绝对播放时间），每段至多一个，可以为空。
_Avoid_: 跳过时间点, skip time, skip config

**片头时长（intro length）**:
从视频开头算起的片头长度（秒），与服务器 skipinfo 的 `skipStart` 同义。
_Avoid_: manual_intro_end, 片头结束时间

**片尾时长（outro length）**:
从视频末尾倒数的片尾长度（秒），与服务器 skipinfo 的 `skipEnd` 同义；不是片尾的开始或结束时间点。
_Avoid_: manual_outro_start, 片尾开始时间

**检测模式（detect mode）**:
决定跳过窗口来源的用户设置：章节模式（只看章节）、手动模式（只看片头/片尾时长）、自动模式（每段先看章节，没有再看时长）。
_Avoid_: 静音模式

### 构建与发布（build & release）

**打包配置（package config）**:
从 `package_cfg.json` 读出的整份值：构建设置（输出目录、临时目录、代理）、依赖布局和各依赖的来源，加载时一次校验完。
_Avoid_: 配置（单独使用时）, cfg

**依赖（dependency）**:
打包配置里列出的一个上游组件：mpv 本体或一个插件，来自 GitHub Release 或仓库内的本地包。默认启用，启用的依赖打进安装包。
_Avoid_: 插件（指 mpv 本体时）, package

**停用的依赖（disabled dependency）**:
留在打包配置里、但不打进安装包的依赖。它的入口文件不再是必需的，它装过的托管文件成为过时文件。
_Avoid_: 禁用插件, 删除的依赖

**依赖来源（dependency source）**:
一个依赖从哪来：GitHub Release、本地文件夹或本地压缩包，三者之一。
_Avoid_: 下载源, url（指本地路径时）

**内容目录（content dir）**:
一个依赖交给安装步骤的目录：压缩包解压后去掉单一外层根目录，本地文件夹则是它本身。
_Avoid_: 解压目录, extracted

**依赖布局（dependency layout）**:
各依赖在安装包里的位置：内容目录装到哪、入口文件是什么、哪个目录由客户端整体替换，外加与依赖无关的基础配置。
_Avoid_: 目录结构

**安装规则（install rule）**:
从一个依赖的内容目录里按 filter / exclude 选出文件、装到安装包内某个目录的一条规则；`install_to` 是它的简写。每个 filter 至少要装进一个文件，否则构建失败。
_Avoid_: 复制规则, extraFiles

**入口文件（entry）**:
一个依赖必须出现在安装包里的那个文件，例如 mpv 的 `mpv.exe`、uosc 的 `scripts/uosc/main.lua`；缺了它客户端就不能用这个依赖。
_Avoid_: 主文件, 必需文件

**托管目录（managed dir）**:
客户端整体替换的目录：更新时先删掉旧目录再放新的，用户放进去的文件不保留。
_Avoid_: 插件目录, 托管路径

**基础配置（base config）**:
不属于任何依赖、每次构建都装进 portable_config 的配置，如 mpv.conf、input.conf、fntv/defaults.conf 和着色器。
_Avoid_: mpv 配置（指这组文件时）, 默认配置

**安装包（package archive）**:
一次构建产出、发布给客户端下载的 zip，内含 mpv 和 portable_config。
_Avoid_: 产物, artifact, 归档

**归档版本（archive version）**:
一个安装包的唯一版本名，同时是它的 Release tag，由构建时间戳派生。
_Avoid_: 版本号, tag（单独使用时）

**清单（manifest）**:
随安装包发布的文件清单，列出 portable_config 下每个文件的哈希与归属，客户端据此同步用户配置。
_Avoid_: 文件列表, 索引

**归属（role）**:
清单里一个文件由谁负责：托管（managed，客户端整体替换）、配置（config，用户可改）、种子（seed，只在首次放置）。
_Avoid_: 类型, 分类

**已知哈希（known hashes）**:
某个路径在历次安装包里出现过的全部内容哈希，客户端据此判断用户是否改过该文件；只增不减。
_Avoid_: 历史版本

**过时文件（obsolete file）**:
曾在历史安装包里出现、本次已移除、客户端应删除的托管文件。
_Avoid_: 已删除文件, 废弃文件

**契约测试（contract test）**:
发版前对安装包与清单做的一致性检查；不通过就不发版。
_Avoid_: 校验, 验证脚本

**构建结果（build result）**:
一次构建交给发布步骤的全部事实：安装包与清单的位置、归档版本、构建时间戳、发布说明。发布步骤只读它，不自行推导任何命名。
_Avoid_: 发布契约, 构建输出, build output
