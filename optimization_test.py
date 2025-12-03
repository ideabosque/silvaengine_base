#!/usr/bin/env python3
"""
优化效果测试脚本，测试优化前后的核心功能性能差异
"""

import time
import memory_profiler
import sys
import os

# 添加项目路径到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试1：测试runtime_debug函数优化效果
def test_runtime_debug_optimization():
    """测试runtime_debug函数优化效果"""
    print("=== 测试runtime_debug函数优化效果 ===")
    
    # 模拟runtime_debug函数的优化前实现
    def runtime_debug_old(mark, start_time=0):
        from datetime import datetime
        current_time = int(datetime.now().timestamp() * 1000)
        if start_time > 0:
            duration = current_time - start_time
            if duration > 0:
                print(f"********** It took {duration} ms to execute `LambdaBase.{mark}`.")
        return current_time
    
    # 模拟runtime_debug函数的优化后实现
    def runtime_debug_new(mark, start_time=0):
        import time
        current_time = int(time.time() * 1000)
        if start_time > 0:
            duration = current_time - start_time
            if duration > 0:
                if os.environ.get('DEBUG', '').lower() == 'true':
                    print(f"********** It took {duration} ms to execute `LambdaBase.{mark}`.")
        return current_time
    
    # 测试优化前的性能
    mem_before = memory_profiler.memory_usage()[0]
    start_time = time.time()
    
    for _ in range(10000):
        current_time = int(time.time() * 1000)
        runtime_debug_old("test", current_time)
    
    old_time = time.time() - start_time
    mem_after = memory_profiler.memory_usage()[0]
    old_mem = mem_after - mem_before
    
    print(f"优化前 - 执行时间: {old_time:.4f}秒, 内存使用: {old_mem:.4f}MB")
    
    # 测试优化后的性能
    mem_before = memory_profiler.memory_usage()[0]
    start_time = time.time()
    
    for _ in range(10000):
        current_time = int(time.time() * 1000)
        runtime_debug_new("test", current_time)
    
    new_time = time.time() - start_time
    mem_after = memory_profiler.memory_usage()[0]
    new_mem = mem_after - mem_before
    
    print(f"优化后 - 执行时间: {new_time:.4f}秒, 内存使用: {new_mem:.4f}MB")
    
    # 计算优化效果
    time_improvement = ((old_time - new_time) / old_time) * 100
    mem_improvement = ((old_mem - new_mem) / old_mem) * 100 if old_mem > 0 else 0
    
    print(f"执行时间优化: {time_improvement:.2f}%")
    print(f"内存使用优化: {mem_improvement:.2f}%")
    print()

# 测试2：测试字典合并优化效果
def test_dict_merge_optimization():
    """测试字典合并优化效果"""
    print("=== 测试字典合并优化效果 ===")
    
    # 准备测试数据
    query_params = {f"key{i}": f"value{i}" for i in range(100)}
    endpoint_id = "1"
    area = "test-area"
    
    # 测试优化前的性能（使用字典合并运算符）
    mem_before = memory_profiler.memory_usage()[0]
    start_time = time.time()
    
    for _ in range(10000):
        params = {**query_params, "endpoint_id": endpoint_id, "area": area}
    
    old_time = time.time() - start_time
    mem_after = memory_profiler.memory_usage()[0]
    old_mem = mem_after - mem_before
    
    print(f"优化前 - 执行时间: {old_time:.4f}秒, 内存使用: {old_mem:.4f}MB")
    
    # 测试优化后的性能（使用字典推导）
    mem_before = memory_profiler.memory_usage()[0]
    start_time = time.time()
    
    for _ in range(10000):
        params = {k: v for k, v in query_params.items()}
        params["endpoint_id"] = endpoint_id
        params["area"] = area
    
    new_time = time.time() - start_time
    mem_after = memory_profiler.memory_usage()[0]
    new_mem = mem_after - mem_before
    
    print(f"优化后 - 执行时间: {new_time:.4f}秒, 内存使用: {new_mem:.4f}MB")
    
    # 计算优化效果
    time_improvement = ((old_time - new_time) / old_time) * 100
    mem_improvement = ((old_mem - new_mem) / old_mem) * 100 if old_mem > 0 else 0
    
    print(f"执行时间优化: {time_improvement:.2f}%")
    print(f"内存使用优化: {mem_improvement:.2f}%")
    print()

# 测试3：测试字符串操作优化效果
def test_string_operation_optimization():
    """测试字符串操作优化效果"""
    print("=== 测试字符串操作优化效果 ===")
    
    # 准备测试数据
    proxy = "test-function/path/to/resource"
    
    # 测试优化前的性能（使用partition方法）
    mem_before = memory_profiler.memory_usage()[0]
    start_time = time.time()
    
    for _ in range(10000):
        funct, _, path = proxy.partition("/")
        if path:
            pass  # 模拟后续操作
    
    old_time = time.time() - start_time
    mem_after = memory_profiler.memory_usage()[0]
    old_mem = mem_after - mem_before
    
    print(f"优化前 - 执行时间: {old_time:.4f}秒, 内存使用: {old_mem:.4f}MB")
    
    # 测试优化后的性能（使用split方法）
    mem_before = memory_profiler.memory_usage()[0]
    start_time = time.time()
    
    for _ in range(10000):
        funct = proxy.split("/")[0] if proxy else ""
        if "/" in proxy:
            path = proxy.split("/", 1)[1]
            pass  # 模拟后续操作
    
    new_time = time.time() - start_time
    mem_after = memory_profiler.memory_usage()[0]
    new_mem = mem_after - mem_before
    
    print(f"优化后 - 执行时间: {new_time:.4f}秒, 内存使用: {new_mem:.4f}MB")
    
    # 计算优化效果
    time_improvement = ((old_time - new_time) / old_time) * 100
    mem_improvement = ((old_mem - new_mem) / old_mem) * 100 if old_mem > 0 else 0
    
    print(f"执行时间优化: {time_improvement:.2f}%")
    print(f"内存使用优化: {mem_improvement:.2f}%")
    print()

if __name__ == "__main__":
    print("开始优化效果测试...\n")
    
    # 运行所有测试
    test_runtime_debug_optimization()
    test_dict_merge_optimization()
    test_string_operation_optimization()
    
    print("优化效果测试完成！")
