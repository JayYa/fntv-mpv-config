#!/usr/bin/env python3
"""
自动化测试运行器
自动发现并运行tests目录下的所有测试
"""
import sys
import unittest
from pathlib import Path


def discover_and_run_tests():
    """
    自动发现并运行所有测试
    """
    # 确保能找到src模块
    project_root = Path(__file__).parent
    src_path = project_root / 'src'
    sys.path.insert(0, str(src_path))
    
    # 测试目录
    tests_dir = project_root / 'tests'
    
    print("运行MPV配置管理工具测试...")
    print("=" * 50)
    print(f"📁 测试目录: {tests_dir}")
    print(f"📁 源码目录: {src_path}")
    
    # 统计测试文件数量
    test_files = list(tests_dir.glob('test_*.py'))
    print(f"🔍 发现测试文件: {len(test_files)} 个")
    for test_file in test_files:
        print(f"   - {test_file.name}")
    
    print("=" * 50)
    
    # 使用unittest的自动发现功能
    loader = unittest.TestLoader()
    
    # 发现tests目录下的所有测试
    # 直接从项目根目录开始发现，指定tests目录的相对路径
    suite = loader.discover(
        start_dir='tests',
        pattern='test_*.py',
        top_level_dir='.'
    )
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出结果
    print("=" * 50)
    if result.wasSuccessful():
        print("🎉 所有测试通过!")
        print(f"✅ 运行了 {result.testsRun} 个测试")
        return 0
    else:
        print("❌ 测试失败!")
        print(f"📊 总测试数: {result.testsRun}")
        print(f"❌ 失败: {len(result.failures)}")
        print(f"💥 错误: {len(result.errors)}")
        
        if result.failures:
            print("\n失败的测试:")
            for test, _traceback in result.failures:
                print(f"  - {test}")
        
        if result.errors:
            print("\n出错的测试:")
            for test, _traceback in result.errors:
                print(f"  - {test}")
        
        return 1

if __name__ == '__main__':
    sys.exit(discover_and_run_tests())
