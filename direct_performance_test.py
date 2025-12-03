#!/usr/bin/env python3
"""
直接测试脚本，从文件中直接导入需要的类和函数，避免通过__init__.py
"""

import time
import memory_profiler
import sys
import os

# 添加项目路径到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接从文件中导入，不通过__init__.py
import importlib.util

# 导入lambdabase.py中的类和函数
def load_module_from_file(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# 加载lambdabase模块
lambdabase_module = load_module_from_file(
    "silvaengine_base.lambdabase",
    os.path.join(os.path.dirname(__file__), "silvaengine_base", "lambdabase.py")
)

# 获取需要测试的类和函数
FunctionError = lambdabase_module.FunctionError
runtime_debug = lambdabase_module.runtime_debug

# 测试1：runtime_debug函数性能
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

# 测试2：FunctionError异常性能
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

# 测试3：模拟LambdaBase类的性能
def test_lambda_base_simulation():
    """模拟测试LambdaBase类的性能"""
    print("=== 模拟测试LambdaBase类性能 ===")
    
    # 内存使用测试
    mem_usage_before = memory_profiler.memory_usage()[0]
    
    # 执行时间测试
    start_time = time.time()
    
    # 模拟LambdaBase类的一些核心操作
    for _ in range(100):
        # 模拟JSON序列化和反序列化
        test_data = {"key": "value", "number": 123, "list": [1, 2, 3]}
        json_str = str(test_data)  # 简化的JSON序列化
        
        # 模拟条件判断
        if "key" in test_data:
            pass
        
        # 模拟异常处理
        try:
            raise ValueError("Test")
        except ValueError:
            pass
    
    end_time = time.time()
    mem_usage_after = memory_profiler.memory_usage()[0]
    
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print(f"内存使用: {mem_usage_after - mem_usage_before:.4f}MB")
    print()

if __name__ == "__main__":
    print("开始直接性能测试...\n")
    
    # 运行所有测试
    test_runtime_debug_performance()
    test_function_error_performance()
    test_lambda_base_simulation()
    
    print("直接性能测试完成！")
