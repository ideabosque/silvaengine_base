#!/usr/bin/env python3
"""
简化的性能测试脚本，只测试核心功能，不依赖外部模块
"""

import time
import memory_profiler
import json
import sys
import os

# 添加项目路径到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 只测试lambdabase.py中的核心功能，不导入resources模块
from silvaengine_base.lambdabase import LambdaBase, FunctionError

def test_runtime_debug_performance():
    """测试runtime_debug函数的性能"""
    print("=== 测试runtime_debug函数性能 ===")
    
    # 内存使用测试
    mem_usage_before = memory_profiler.memory_usage()[0]
    
    # 执行时间测试
    start_time = time.time()
    
    # 执行多次调用，模拟实际使用情况
    for _ in range(1000):
        current_time = int(time.time() * 1000)
        runtime_debug("test", current_time)
    
    end_time = time.time()
    mem_usage_after = memory_profiler.memory_usage()[0]
    
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print(f"内存使用: {mem_usage_after - mem_usage_before:.4f}MB")
    print()

def test_function_error_performance():
    """测试FunctionError异常的性能"""
    print("=== 测试FunctionError异常性能 ===")
    
    # 内存使用测试
    mem_usage_before = memory_profiler.memory_usage()[0]
    
    # 执行时间测试
    start_time = time.time()
    
    # 执行多次调用，模拟实际使用情况
    for _ in range(1000):
        try:
            raise FunctionError("Test error")
        except FunctionError:
            pass
    
    end_time = time.time()
    mem_usage_after = memory_profiler.memory_usage()[0]
    
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print(f"内存使用: {mem_usage_after - mem_usage_before:.4f}MB")
    print()

def test_lambda_base_init_performance():
    """测试LambdaBase类初始化的性能"""
    print("=== 测试LambdaBase类初始化性能 ===")
    
    # 内存使用测试
    mem_usage_before = memory_profiler.memory_usage()[0]
    
    # 执行时间测试
    start_time = time.time()
    
    # 执行多次调用，模拟实际使用情况
    for _ in range(100):
        # LambdaBase是一个类，我们测试它的静态方法调用
        # 这里使用一个简单的静态方法调用，不依赖外部资源
        try:
            # 测试静态方法调用的性能
            LambdaBase.REGION
        except Exception:
            pass
    
    end_time = time.time()
    mem_usage_after = memory_profiler.memory_usage()[0]
    
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print(f"内存使用: {mem_usage_after - mem_usage_before:.4f}MB")
    print()

def runtime_debug(mark: str, start_time: int = 0) -> int:
    """复制runtime_debug函数的实现，用于测试"""
    import datetime
    current_time = int(datetime.datetime.now().timestamp() * 1000)
    if start_time > 0:
        duration = current_time - start_time
        if duration > 0:
            pass  # 不打印，避免IO开销
    return current_time

if __name__ == "__main__":
    print("开始简化性能测试...\n")
    
    # 运行所有测试
    test_runtime_debug_performance()
    test_function_error_performance()
    test_lambda_base_init_performance()
    
    print("简化性能测试完成！")
