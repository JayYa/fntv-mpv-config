# 解压 7z 时给 py7zr 传文件对象，不传路径

`_extract_7z` 自己打开归档，把文件对象交给 `py7zr.SevenZipFile`。传路径时 py7zr 并行解压，会按文件名另开一个不关闭的句柄；解压报错（如 BCJ2）后这个句柄要等 GC 才释放，Windows 上 temp 目录就删不掉。传文件对象由我们的 `with` 关闭句柄，代价是放弃 py7zr 的并行解压。

## Consequences

- 不要为了提速把它改回传路径；除非 py7zr 修好了句柄泄漏，并在 Windows 上验证过报错后 temp 能删掉。
