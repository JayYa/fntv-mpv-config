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

**依赖（dependency）**:
打进安装包的一个上游组件：mpv 本体或一个插件，来自 GitHub Release 或仓库内的本地包。
_Avoid_: 插件（指 mpv 本体时）, package

**内容目录（content dir）**:
一个依赖交给安装步骤的目录：压缩包解压后去掉单一外层根目录，本地文件夹则是它本身。
_Avoid_: 解压目录, extracted

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
