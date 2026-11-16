#!/usr/bin/env python3
"""
配置验证脚本
检查package.json配置文件的有效性
"""

import sys
import json
from pathlib import Path

# 添加src目录到Python路径
current_dir = Path(__file__).parent
src_dir = current_dir / 'src'
sys.path.insert(0, str(src_dir))

from config_manager import ConfigManager, ConfigError


def validate_config(config_path="package_cfg.json"):
    """
    验证配置文件
    
    Args:
        config_path: 配置文件路径
    """
    print(f"验证配置文件: {config_path}")
    print("=" * 50)
    
    try:
        # 检查文件是否存在
        if not Path(config_path).exists():
            print(f"❌ 配置文件不存在: {config_path}")
            return False
        
        # 尝试加载配置
        manager = ConfigManager(config_path)
        config = manager.load_config()
        
        print(f"✅ 配置文件格式正确")
        print(f"   项目名称: {config['name']}")
        print(f"   版本: {config['version']}")
        
        # 验证目录配置
        print("\n📁 目录配置:")
        dirs = config['config']
        for key, value in dirs.items():
            print(f"   {key}: {value}")
        
        # 验证依赖项
        print("\n📦 依赖项配置:")
        dependencies = config['dependencies']
        
        for name, dep_config in dependencies.items():
            status = "启用" if dep_config.get('enabled', True) else "禁用"
            print(f"   {name}: {dep_config['name']} {dep_config['version']} ({status})")
            
            # 检查必需字段
            has_url = 'url' in dep_config
            has_local_path = 'local_path' in dep_config
            
            if not has_url and not has_local_path:
                print(f"      ⚠️  缺少下载源: 需要 'url' 或 'local_path' 字段")
            
            basic_fields = ['name', 'version', 'filename_pattern', 'format']
            missing_fields = [field for field in basic_fields if field not in dep_config]
            
            if missing_fields:
                print(f"      ⚠️  缺少字段: {', '.join(missing_fields)}")
            
            # 检查本地路径
            if has_local_path:
                local_path = Path(dep_config['local_path'])
                if not local_path.is_absolute():
                    local_path = Path(config_path).resolve().parent / local_path
                
                if local_path.exists():
                    if local_path.is_file():
                        print(f"      📁 本地文件: {dep_config['local_path']}")
                    elif local_path.is_dir():
                        print(f"      📁 本地文件夹: {dep_config['local_path']}")
                else:
                    print(f"      ⚠️  本地路径不存在: {dep_config['local_path']}")
            
            # 检查自定义安装规则
            if 'custom_install_rules' in dep_config:
                rules_count = len(dep_config['custom_install_rules'])
                print(f"      📋 自定义安装规则: {rules_count} 条")
                
                for i, rule in enumerate(dep_config['custom_install_rules']):
                    required_rule_fields = ['from', 'to']
                    missing_rule_fields = [field for field in required_rule_fields if field not in rule]
                    if missing_rule_fields:
                        print(f"         ⚠️  规则 {i+1} 缺少字段: {', '.join(missing_rule_fields)}")
                    else:
                        filter_info = f" (过滤器: {len(rule.get('filter', []))} 条)" if 'filter' in rule else ""
                        exclude_info = f" (排除: {len(rule.get('exclude', []))} 条)" if 'exclude' in rule else ""
                        print(f"         ✅ 规则 {i+1}: {rule['from']} -> {rule['to']}{filter_info}{exclude_info}")
            
            # 检查文件排除规则
            if 'exclude_files' in dep_config:
                exclude_count = len(dep_config['exclude_files'])
                print(f"      🚫 文件排除规则: {exclude_count} 条")
                for exclude in dep_config['exclude_files']:
                    print(f"         - {exclude}")
        
        # 验证启用的依赖项
        enabled_deps = manager.get_enabled_dependencies()
        print(f"\n✅ 共有 {len(enabled_deps)} 个启用的依赖项")
        
        # 检查自定义配置目录
        custom_config_dir = manager.get_custom_config_dir()
        if custom_config_dir.exists():
            print(f"✅ 自定义配置目录存在: {custom_config_dir}")
            
            # 列出自定义配置文件
            config_files = list(custom_config_dir.rglob('*'))
            config_files = [f for f in config_files if f.is_file()]
            
            if config_files:
                print(f"   📄 找到 {len(config_files)} 个自定义配置文件:")
                for config_file in config_files:
                    rel_path = config_file.relative_to(custom_config_dir)
                    print(f"      - {rel_path}")
            else:
                print(f"   ℹ️  自定义配置目录为空")
        else:
            print(f"ℹ️  自定义配置目录不存在: {custom_config_dir}")
        
        print(f"\n🎉 配置验证完成，未发现严重错误！")
        return True
        
    except ConfigError as e:
        print(f"❌ 配置错误: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ JSON格式错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 验证过程中出现错误: {e}")
        return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="验证MPV配置文件")
    parser.add_argument(
        'config',
        nargs='?',
        default='package_cfg.json',
        help='配置文件路径 (默认: package_cfg.json)'
    )
    
    args = parser.parse_args()
    
    success = validate_config(args.config)
    
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()
