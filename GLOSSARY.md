# fntv-mpv-config

为飞牛影视（fntv）客户端打包的 mpv 播放器及其插件与配置。

## Language

### 智能跳过（smart_skip）

**跳过窗口**:
一个文件里要自动跳过的片头区间与片尾区间（绝对播放时间），每段至多一个，可以为空。
_Avoid_: 跳过时间点, skip time, skip config

**片头时长**:
从视频开头算起的片头长度（秒），与服务器 skipinfo 的 `skipStart` 同义。
_Avoid_: manual_intro_end, 片头结束时间

**片尾时长**:
从视频末尾倒数的片尾长度（秒），与服务器 skipinfo 的 `skipEnd` 同义；不是片尾的开始或结束时间点。
_Avoid_: manual_outro_start, 片尾开始时间

**检测模式**:
决定跳过窗口来源的用户设置：章节模式（只看章节）、手动模式（只看片头/片尾时长）、自动模式（每段先看章节，没有再看时长）。
_Avoid_: detect mode, 静音模式
