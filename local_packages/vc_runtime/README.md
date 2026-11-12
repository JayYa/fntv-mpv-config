# VC++ 运行库（app-local）

mpv 官方 MSVC 构建（`mpv-<版本>-x86_64-pc-windows-msvc.zip`）动态链接 VC++ 运行库：`mpv.exe` 导入 `MSVCP140.dll`、`VCRUNTIME140.dll`、`VCRUNTIME140_1.dll`，`vulkan-1.dll` 导入 `VCRUNTIME140.dll`。Windows 不自带这几个 DLL，fntv-electron 安装包也不装 VC++ Redistributable，所以把它们放在 `mpv.exe` 旁边一起打包（Microsoft 文档里的 app-local 部署）。

## 来源

- 安装包：Microsoft Visual C++ v14 Redistributable (x64) 14.52.37029.0
  - 下载地址：<https://download.visualstudio.microsoft.com/download/pr/78d061c5-9ef3-42ab-98ed-3309d1095dc4/9C02C9ED120F671B900E6B9471D890E3B2414117A7E53F4AE2E855466FA2B7C9/VC_redist.x64.exe>（2026-11-12 由 <https://aka.ms/vc14/vc_redist.x64.exe> 跳转得到）
  - sha256：`9c02c9ed120f671b900e6b9471d890e3b2414117a7e53f4ae2e855466fa2b7c9`，Authenticode 签名者 Microsoft Corporation
- 取文件的方法（不运行安装包）：用 7-Zip 解开安装包末尾内嵌的 CAB，再从其中的 `a4`（x64 运行库 CAB）取 `msvcp140.dll_amd64`、`vcruntime140.dll_amd64`、`vcruntime140_1.dll_amd64`，去掉 `_amd64` 后缀。

| 文件 | 版本 | sha256 |
| --- | --- | --- |
| `msvcp140.dll` | 14.52.37029.0 | `59d325227321d52b9a523ea401ce6787a5d59f78229a0ff3a6f124e5d3445685` |
| `vcruntime140.dll` | 14.52.37029.0 | `eb1ee979bf02324712346e5bdbfc59c785388bc50d18cc2688aae4b0734915a0` |
| `vcruntime140_1.dll` | 14.52.37029.0 | `a14b4a42a2c6df04d6d53a8340816023d953406f7f3d94996c7cab30c414ff63` |

三个 DLL 都带有效的 Microsoft Authenticode 签名。

## 升级

升级 mpv 时，确认这里的运行库版本不低于新 `mpv.exe` 构建所用的 MSVC 工具集版本；不够新就按上面的方法从更新的 Redistributable 里重新取。`package_cfg.json` 里 `vc_runtime` 只把 `*.dll` 复制到归档根目录，本文件不进归档。
