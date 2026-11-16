"""
安装管理模块
负责将解压的文件按照规则安装到目标位置
"""
import shutil
import fnmatch
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging


class InstallManager:
    """安装管理器"""
    
    def __init__(self, output_dir: Path, custom_config_dir: Path, project_name: str):
        """
        初始化安装管理器
        
        Args:
            output_dir: 输出目录
            custom_config_dir: 自定义配置目录
            project_name: 项目名称，即 project 目录在输出目录下的名字

        Raises:
            ValueError: project_name 不是单独一级目录名（空、"."、".." 或含路径分隔符）
        """
        if project_name in ("", ".", "..") or Path(project_name).name != project_name:
            raise ValueError(f"项目名称必须是单独一级目录名: {project_name!r}")
        self.base_output_dir = Path(output_dir)
        self.output_dir = self.base_output_dir / project_name
        self.custom_config_dir = Path(custom_config_dir)
        self.project_name = project_name
        self.logger = logging.getLogger(__name__)
        self.portable_config_dir = self.output_dir / "portable_config"

    def remove_project_dir(self):
        """删掉 project 目录；输出目录里的其它东西不动"""
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
            self.logger.info(f"已删除 project 目录: {self.output_dir}")

    def reset_project_dir(self):
        """清空 project 目录，让这次构建只含本次安装的文件"""
        self.remove_project_dir()
        self.portable_config_dir.mkdir(parents=True)

    def install_dependency(self, name: str, config: Dict[str, Any], content_dir: Path):
        """
        把依赖的内容目录按规则装进 project 目录，再装 custom_config 下的同名配置

        Args:
            name: 依赖项名称
            config: 依赖项配置
            content_dir: 依赖的内容目录
        """
        self.logger.info(f"开始安装 {name}")

        custom_install_rules = config.get('custom_install_rules', [])
        if custom_install_rules:
            self.logger.info(f"{name} 使用自定义安装规则")
            for rule in custom_install_rules:
                self._apply_custom_config_rule(name, rule, content_dir)
        else:
            self._install_content_default(name, content_dir, config.get('exclude_files', []))

        self._install_custom_config(name)
        self.logger.info(f"{name} 安装完成")
    
    def _install_content_default(self, name: str, content_dir: Path, excludes: List[str]):
        # 根据依赖项类型决定默认安装位置
        if name == 'mpv':
            # MPV主程序安装到根目录
            target_path = self.output_dir
        else:
            # 其他插件默认安装到scripts目录下的子目录
            target_path = self.portable_config_dir / "scripts" / name
        
        self.logger.info(f"默认安装 {name}: {content_dir} -> {target_path}")
        if excludes:
            self.logger.debug(f"排除文件: {excludes}")
        
        # 创建目标目录
        target_path.mkdir(parents=True, exist_ok=True)
        
        # 复制所有文件，但排除指定模式
        self._copy_filtered_files(content_dir, target_path, "**/*", excludes)
    
    def _apply_custom_config_rule(self, name: str, rule: Dict[str, Any], source_base: Path):
        """
        应用自定义配置规则，参考 Node.js extraFiles 功能
        
        Args:
            name: 依赖项名称
            rule: 自定义配置规则，格式：
                  {
                      "from": "source_path",  # 源路径（相对于解压目录）
                      "to": "target_path",    # 目标路径（相对于输出目录）
                      "filter": ["**/*"],     # 可选：过滤模式
                      "exclude": []           # 可选：排除模式
                  }
            source_base: 源目录基础路径
        """
        source_rel = rule.get('from', '')
        target_rel = rule.get('to', '')
        filters = rule.get('filter', ['**/*'])
        excludes = rule.get('exclude', [])
        
        # 构建源路径
        if source_rel:
            source_path = source_base / source_rel
        else:
            source_path = source_base
        
        # 构建目标路径 - 简化逻辑，统一处理
        if target_rel:
            # 目标路径统一相对于输出目录处理
            target_path = self.output_dir / target_rel
        else:
            # 目标路径为空，默认复制到 output_dir 根目录
            target_path = self.output_dir
        
        self.logger.debug(f"应用自定义配置规则 [{name}]: {source_path} -> {target_path}")
        if filters != ['**/*']:
            self.logger.debug(f"过滤模式: {filters}")
        if excludes:
            self.logger.debug(f"排除模式: {excludes}")
        
        # 检查源路径是否存在
        if not source_path.exists():
            self.logger.warning(f"源路径不存在: {source_path}")
            return
        
        # 确保目标目录存在
        target_path.mkdir(parents=True, exist_ok=True)
        
        # 应用每个过滤器规则
        for filter_pattern in filters:
            self._copy_filtered_files(source_path, target_path, filter_pattern, excludes)
    
    def _copy_filtered_files(self, source_path: Path, target_path: Path, pattern: str, excludes: Optional[List[str]] = None):
        """
        根据模式复制文件，支持排除规则
        
        Args:
            source_path: 源路径
            target_path: 目标路径
            pattern: 文件模式
            excludes: 排除模式列表
        """
        if excludes is None:
            excludes = []
            
        if source_path.is_file():
            # 如果源是文件，直接检查是否匹配模式
            if fnmatch.fnmatch(source_path.name, pattern):
                # 检查是否被排除
                if not self._is_excluded(str(source_path.name), excludes):
                    target_file = target_path / source_path.name
                    self._copy_file(source_path, target_file)
        else:
            # 如果源是目录，遍历所有文件
            self._copy_directory_filtered(source_path, target_path, pattern, excludes)
    
    def _copy_directory_filtered(self, source_dir: Path, target_dir: Path, pattern: str, excludes: Optional[List[str]] = None):
        """
        递归复制目录中匹配模式的文件，支持排除规则
        
        Args:
            source_dir: 源目录
            target_dir: 目标目录
            pattern: 文件模式
            excludes: 排除模式列表
        """
        if excludes is None:
            excludes = []
            
        for item in source_dir.rglob('*'):
            if item.is_file():
                # 计算相对路径
                rel_path = item.relative_to(source_dir)
                
                # 检查文件是否匹配模式且未被排除
                if self._matches_pattern(str(rel_path), pattern) and not self._is_excluded(str(rel_path), excludes):
                    target_file = target_dir / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    self._copy_file(item, target_file)
    
    def _matches_pattern(self, file_path: str, pattern: str) -> bool:
        """
        检查文件路径是否匹配模式
        
        Args:
            file_path: 文件路径
            pattern: 模式
            
        Returns:
            是否匹配
        """
        import fnmatch
        
        # 将Windows路径分隔符统一为Unix格式进行匹配
        normalized_path = file_path.replace('\\', '/')
        normalized_pattern = pattern.replace('\\', '/')
        
        # 简单但有效的处理方式
        if pattern == '**/*':
            return True
        
        # 使用Python的fnmatch.fnmatch，它支持基本的glob模式
        # 但不支持**，所以我们需要手动处理
        if '**' in normalized_pattern:
            # 将**替换为*来进行近似匹配，或者使用更简单的包含检查
            if normalized_pattern.startswith('**/'):
                # **/pattern -> 检查文件名是否匹配
                sub_pattern = normalized_pattern[3:]
                return fnmatch.fnmatch(Path(file_path).name, sub_pattern)
            elif normalized_pattern.endswith('/**'):
                # pattern/** -> 检查路径是否包含该目录
                dir_name = normalized_pattern[:-3]
                return dir_name in normalized_path.split('/')
            elif '/**/' in normalized_pattern:
                # pattern/**/pattern -> 检查是否包含前后模式
                parts = normalized_pattern.split('/**/')
                if len(parts) == 2:
                    prefix, suffix = parts
                    return prefix in normalized_path and suffix in normalized_path
                return False
            else:
                # 其他**模式，简化处理
                simple_pattern = normalized_pattern.replace('**', '*')
                return fnmatch.fnmatch(normalized_path, simple_pattern)
        else:
            # 普通模式匹配
            return fnmatch.fnmatch(normalized_path, normalized_pattern)
    
    def _is_excluded(self, file_path: str, excludes: List[str]) -> bool:
        """
        检查文件路径是否被排除
        
        Args:
            file_path: 文件路径
            excludes: 排除模式列表
            
        Returns:
            是否被排除
        """
        for exclude_pattern in excludes:
            if self._matches_pattern(file_path, exclude_pattern):
                return True
        return False
    
    def _copy_file(self, source: Path, target: Path):
        """
        复制单个文件
        
        Args:
            source: 源文件
            target: 目标文件
        """
        try:
            # 确保目标目录存在
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # 复制文件
            shutil.copy2(source, target)
            self.logger.debug(f"已复制: {source} -> {target}")
            
        except Exception as e:
            self.logger.error(f"复制文件失败: {source} -> {target}, 错误: {e}")
            raise
    
    def _install_custom_config(self, name: str):
        """
        安装自定义配置文件
        
        Args:
            name: 依赖项名称
        """
        # 检查通用自定义配置目录
        custom_dir = self.custom_config_dir / name
        
        if custom_dir.exists():
            self.logger.info(f"安装 {name} 的自定义配置")
            
            try:
                # 递归复制自定义配置到portable_config
                for item in custom_dir.rglob('*'):
                    if item.is_file():
                        rel_path = item.relative_to(custom_dir)
                        target_file = self.portable_config_dir / rel_path
                        self._copy_file(item, target_file)
            
            except Exception as e:
                self.logger.error(f"安装 {name} 自定义配置失败: {e}")
                raise
