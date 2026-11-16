"""
安装管理模块
按依赖布局把内容目录和 custom_config 装进 project 目录
"""
import logging
import shutil
from pathlib import Path
from typing import Dict, Iterable, NamedTuple

from .dependency_layout import ConfigFile, DependencyLayout, InstallRule, Placement, pattern_matcher


class InstallError(Exception):
    """安装规则与内容目录对不上，或两个依赖要装同一个文件"""


class _Installed(NamedTuple):
    archive_path: str
    owner: str


class InstallManager:

    def __init__(self, output_dir: Path, project_name: str):
        """
        Args:
            output_dir: 输出目录
            project_name: 项目名称，即 project 目录在输出目录下的名字

        Raises:
            ValueError: project_name 不是单独一级目录名（空、"."、".." 或含路径分隔符）
        """
        if project_name in ("", ".", "..") or Path(project_name).name != project_name:
            raise ValueError(f"项目名称必须是单独一级目录名: {project_name!r}")
        self.base_output_dir = Path(output_dir)
        self.output_dir = self.base_output_dir / project_name
        self.project_name = project_name
        self.logger = logging.getLogger(__name__)
        self.portable_config_dir = self.output_dir / "portable_config"
        # 按 casefold 后的安装包内路径记，Windows 上只差大小写的路径是同一个文件
        self._installed: Dict[str, _Installed] = {}

    def remove_project_dir(self):
        """删掉 project 目录；输出目录里的其它东西不动"""
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
            self.logger.info(f"已删除 project 目录: {self.output_dir}")
        self._installed.clear()

    def reset_project_dir(self):
        """清空 project 目录，让这次构建只含本次安装的文件"""
        self.remove_project_dir()
        self.portable_config_dir.mkdir(parents=True)

    def install_base_config(self, layout: DependencyLayout):
        self._install_config_files("基础配置", layout.base_config)

    def install_dependency(self, placement: Placement, content_dir: Path):
        """
        按安装规则把内容目录里的文件装进 project 目录，再装该依赖的 custom_config

        Raises:
            InstallError: 规则的 from 不存在、某个 filter 一个文件都没装进去，
                或要装的文件已由别的依赖或基础配置装过
        """
        name = placement.name
        self.logger.info(f"开始安装 {name}")
        for rule in placement.install_rules:
            target_dir = Path(rule.target)
            for rel, source in _select_files(name, rule, Path(content_dir)).items():
                self._install_content(name, source, (target_dir / rel).as_posix())
        self._install_config_files(name, placement.custom_config)
        self.logger.info(f"{name} 安装完成")

    def _install_content(self, name: str, source: Path, archive_path: str):
        earlier = self._installed.get(archive_path.casefold())
        if earlier is not None:
            who = f"{name} 的两条安装规则" if earlier.owner == name else f"{name} 和 {earlier.owner}"
            raise InstallError(f"{who}都要装 {earlier.archive_path}")
        self._copy(source, archive_path, name)

    def _install_config_files(self, owner: str, files: Iterable[ConfigFile]):
        for f in files:
            archive_path = f"{self.portable_config_dir.name}/{f.portable_config_path}"
            earlier = self._installed.get(archive_path.casefold())
            if earlier is not None:
                self.logger.info(f"{owner} 的配置替换了 {earlier.owner} 自带的 {earlier.archive_path}")
            self._copy(f.source, archive_path, owner)

    def _copy(self, source: Path, archive_path: str, owner: str):
        target = self.output_dir / archive_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        self._installed[archive_path.casefold()] = _Installed(archive_path, owner)
        self.logger.debug(f"已复制: {source} -> {target}")


def _select_files(name: str, rule: InstallRule, content_dir: Path) -> Dict[str, Path]:
    """返回规则选中的 {相对规则 to 的路径: 源文件}，每个 filter 至少选中一个"""
    source = content_dir / rule.source
    if source.is_file():
        candidates = [(source, source.name)]
    elif source.is_dir():
        candidates = [(p, p.relative_to(source).as_posix())
                      for p in sorted(source.rglob("*")) if p.is_file()]
    else:
        raise InstallError(f"{name} 的安装规则 from={rule.source!r} 在内容目录里不存在: {source}")

    excluded = [pattern_matcher(p) for p in rule.excludes]
    kept = {rel: path for path, rel in candidates if not any(m(rel) for m in excluded)}
    selected: Dict[str, Path] = {}
    for pattern in rule.filters:
        matches = pattern_matcher(pattern)
        hits = {rel: path for rel, path in kept.items() if matches(rel)}
        if not hits:
            raise InstallError(f"{name} 的安装规则 from={rule.source!r} 里 filter {pattern!r} "
                               f"排除 {list(rule.excludes)} 之后一个文件都没选中")
        selected.update(hits)
    return selected
