#!/usr/bin/env python3
"""
性能测试脚本，用于测量优化前后的执行时间和内存占用
"""

import time
import memory_profiler
import json
import sys
import os

# 添加项目路径到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from silvaengine_base.lambdabase import LambdaBase
from silvaengine_base.resources import Resources

class MockLogger:
    """模拟日志记录器"""
    def info(self, *args, **kwargs):
        pass
    
    def error(self, *args, **kwargs):
        pass
    
    def warning(self, *args, **kwargs):
        pass
    
    def exception(self, *args, **kwargs):
        pass

class MockContext:
    """模拟Lambda上下文"""
    def __init__(self):
        self.function_name = "test-function"
        self.function_version = "$LATEST"
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
        self.memory_limit_in_mb = 128
        self.aws_request_id = "test-request-id"
        self.log_group_name = "/aws/lambda/test-function"
        self.log_stream_name = "2023/01/01/[$LATEST]1234567890abcdef"

def test_get_function_performance():
    """测试get_function方法的性能"""
    print("=== 测试get_function方法性能 ===")
    
    # 内存使用测试
    mem_usage_before = memory_profiler.memory_usage()[0]
    
    # 执行时间测试
    start_time = time.time()
    
    # 执行多次调用，模拟实际使用情况
    for _ in range(100):
        try:
            # 这里使用模拟数据，实际运行时可能会失败
            # 我们主要关注方法的执行时间和内存占用
            LambdaBase.get_function("1", "test-function", "#####", "GET")
        except Exception:
            # 忽略异常，只关注执行时间和内存占用
            pass
    
    end_time = time.time()
    mem_usage_after = memory_profiler.memory_usage()[0]
    
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print(f"内存使用: {mem_usage_after - mem_usage_before:.4f}MB")
    print()

def test_resources_handle_performance():
    """测试Resources.handle方法的性能"""
    print("=== 测试Resources.handle方法性能 ===")
    
    # 创建测试数据
    test_event = {
        "pathParameters": {
            "area": "test-area",
            "endpoint_id": "1",
            "proxy": "test-function"
        },
        "requestContext": {
            "httpMethod": "GET",
            "identity": {
                "apiKey": "#####"
            },
            "stage": "beta"
        },
        "queryStringParameters": {
            "param1": "value1",
            "param2": "value2"
        },
        "headers": {
            "Content-Type": "application/json"
        }
    }
    
    mock_context = MockContext()
    mock_logger = MockLogger()
    resources = Resources(mock_logger)
    
    # 内存使用测试
    mem_usage_before = memory_profiler.memory_usage()[0]
    
    # 执行时间测试
    start_time = time.time()
    
    # 执行多次调用，模拟实际使用情况
    for _ in range(100):
        try:
            # 这里使用模拟数据，实际运行时可能会失败
            # 我们主要关注方法的执行时间和内存占用
            resources.handle(test_event, mock_context)
        except Exception:
            # 忽略异常，只关注执行时间和内存占用
            pass
    
    end_time = time.time()
    mem_usage_after = memory_profiler.memory_usage()[0]
    
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print(f"内存使用: {mem_usage_after - mem_usage_before:.4f}MB")
    print()

def test_invoke_performance():
    """测试invoke方法的性能"""
    print("=== 测试invoke方法性能 ===")
    
    # 内存使用测试
    mem_usage_before = memory_profiler.memory_usage()[0]
    
    # 执行时间测试
    start_time = time.time()
    
    # 执行多次调用，模拟实际使用情况
    for _ in range(100):
        try:
            # 这里使用模拟数据，实际运行时可能会失败
            # 我们主要关注方法的执行时间和内存占用
            LambdaBase.invoke(
                "test-function",
                {"test": "data"},
                "RequestResponse"
            )
        except Exception:
            # 忽略异常，只关注执行时间和内存占用
            pass
    
    end_time = time.time()
    mem_usage_after = memory_profiler.memory_usage()[0]
    
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print(f"内存使用: {mem_usage_after - mem_usage_before:.4f}MB")
    print()

if __name__ == "__main__":
    print("开始性能测试...\n")
    
    # 运行所有测试
    test_get_function_performance()
    test_resources_handle_performance()
    test_invoke_performance()
    
    print("性能测试完成！")
