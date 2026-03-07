#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Concurrency tests for plugin initialization.

This module tests thread safety and concurrent access patterns
in the plugin initialization system.

@since 2.0.0
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import MagicMock

mock_invoker_module = MagicMock()
mock_invoker_module.Invoker = MagicMock()
sys.modules['silvaengine_utility'] = mock_invoker_module

mock_dynamodb_module = MagicMock()
sys.modules['silvaengine_dynamodb_base'] = mock_dynamodb_module
sys.modules['silvaengine_dynamodb_base.models'] = MagicMock()

mock_constants_module = MagicMock()
sys.modules['silvaengine_constants'] = mock_constants_module

import unittest
from unittest.mock import MagicMock, patch
import threading
import time
import concurrent.futures

from silvaengine_base.boosters.plugin.async_initializer import (
    AsyncPluginInitializer,
    InitializationTracker,
    InitializationState,
    PluginFuture,
)
from silvaengine_base.boosters.plugin.context import (
    LazyPluginContext,
    PluginState,
)


class TestInitializationTrackerConcurrency(unittest.TestCase):
    """Test InitializationTracker under concurrent access."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = InitializationTracker()

    def test_concurrent_registration(self):
        """Test concurrent plugin registration."""
        num_plugins = 100
        plugins = [f"plugin_{i}" for i in range(num_plugins)]
        
        def register_plugin(plugin_type):
            self.tracker.register_plugin(plugin_type)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_plugin, p) for p in plugins]
            concurrent.futures.wait(futures)
        
        for plugin in plugins:
            status = self.tracker.get_status(plugin)
            self.assertIn(status.state, [InitializationState.PENDING, InitializationState.READY])

    def test_concurrent_state_transitions(self):
        """Test concurrent state transitions."""
        num_plugins = 50
        
        for i in range(num_plugins):
            self.tracker.register_plugin(f"plugin_{i}")
        
        def transition_plugin(plugin_type):
            self.tracker.start_initialization(plugin_type)
            time.sleep(0.001)
            self.tracker.complete_initialization(plugin_type)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(transition_plugin, f"plugin_{i}")
                for i in range(num_plugins)
            ]
            concurrent.futures.wait(futures)
        
        for i in range(num_plugins):
            self.assertTrue(self.tracker.is_ready(f"plugin_{i}"))

    def test_concurrent_read_write(self):
        """Test concurrent read and write operations."""
        num_plugins = 50
        
        for i in range(num_plugins):
            self.tracker.register_plugin(f"plugin_{i}")
        
        read_results = []
        
        def read_status(plugin_type):
            for _ in range(10):
                status = self.tracker.get_status(plugin_type)
                read_results.append(status.state)
        
        def write_status(plugin_type):
            self.tracker.start_initialization(plugin_type)
            time.sleep(0.001)
            self.tracker.complete_initialization(plugin_type)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            read_futures = [
                executor.submit(read_status, f"plugin_{i}")
                for i in range(num_plugins)
            ]
            write_futures = [
                executor.submit(write_status, f"plugin_{i}")
                for i in range(num_plugins)
            ]
            concurrent.futures.wait(read_futures + write_futures)
        
        self.assertEqual(len(read_results), num_plugins * 10)

    def test_concurrent_failures(self):
        """Test concurrent failure handling."""
        num_plugins = 30
        
        for i in range(num_plugins):
            self.tracker.register_plugin(f"plugin_{i}")
        
        def fail_plugin(plugin_type):
            self.tracker.start_initialization(plugin_type)
            time.sleep(0.001)
            self.tracker.fail_initialization(
                plugin_type, Exception(f"Failed {plugin_type}")
            )
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(fail_plugin, f"plugin_{i}")
                for i in range(num_plugins)
            ]
            concurrent.futures.wait(futures)
        
        for i in range(num_plugins):
            self.assertTrue(self.tracker.is_failed(f"plugin_{i}"))


class TestPluginFutureConcurrency(unittest.TestCase):
    """Test PluginFuture under concurrent access."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = InitializationTracker()
        self.tracker.register_plugin("test_plugin")
        self.future = PluginFuture(
            plugin_type="test_plugin",
            tracker=self.tracker,
        )

    def test_concurrent_callback_registration(self):
        """Test concurrent callback registration."""
        callback_results = []
        
        def register_callback(index):
            def callback(result):
                callback_results.append((index, result))
            self.future.add_done_callback(callback)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_callback, i) for i in range(50)]
            concurrent.futures.wait(futures)
        
        self.tracker.start_initialization("test_plugin")
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization("test_plugin")
        
        time.sleep(0.1)
        self.assertEqual(len(callback_results), 50)

    def test_concurrent_get_operations(self):
        """Test concurrent get operations."""
        results = []
        
        def get_result():
            try:
                result = self.future.get(timeout=1.0)
                results.append(result)
            except TimeoutError:
                pass
        
        threads = [threading.Thread(target=get_result) for _ in range(10)]
        
        for t in threads:
            t.start()
        
        time.sleep(0.1)
        
        self.tracker.start_initialization("test_plugin")
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization("test_plugin")
        
        for t in threads:
            t.join(timeout=2.0)
        
        self.assertEqual(len(results), 10)


class TestLazyPluginContextConcurrency(unittest.TestCase):
    """Test LazyPluginContext under concurrent access."""

    def test_concurrent_plugin_access(self):
        """Test concurrent access to the same plugin."""
        mock_manager = MagicMock()
        mock_manager.get_async_initializer.return_value = None
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={
                "test_plugin": {
                    "module_name": "test_module",
                    "function_name": "init",
                }
            },
        )
        
        init_count = [0]
        lock = threading.Lock()
        
        def mock_init(*args, **kwargs):
            with lock:
                init_count[0] += 1
            time.sleep(0.05)
            return (True, {"result": "success"}, None)
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.PluginInitializerUtils.invoke_plugin_init",
            side_effect=mock_init,
        ):
            def access_plugin():
                result = context.get("test_plugin")
                return result
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(access_plugin) for _ in range(20)]
                results = [f.result() for f in concurrent.futures.wait(futures)[0]]
            
            non_none_results = [r for r in results if r is not None]
            self.assertGreaterEqual(len(non_none_results), 1)
            self.assertEqual(init_count[0], 1)

    def test_concurrent_different_plugins(self):
        """Test concurrent access to different plugins."""
        mock_manager = MagicMock()
        mock_manager.get_async_initializer.return_value = None
        
        plugin_configs = {
            f"plugin_{i}": {
                "module_name": f"module_{i}",
                "function_name": "init",
            }
            for i in range(10)
        }
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs=plugin_configs,
        )
        
        results = {}
        lock = threading.Lock()
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.PluginInitializerUtils.invoke_plugin_init",
            return_value=(True, {"result": "success"}, None),
        ):
            def access_plugin(plugin_name):
                result = context.get(plugin_name)
                with lock:
                    results[plugin_name] = result
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(access_plugin, f"plugin_{i}")
                    for i in range(10)
                ]
                concurrent.futures.wait(futures)
        
        self.assertEqual(len(results), 10)


class TestDeadlockPrevention(unittest.TestCase):
    """Test deadlock prevention mechanisms."""

    def test_no_deadlock_on_concurrent_init(self):
        """Test that concurrent initialization doesn't cause deadlock."""
        mock_manager = MagicMock()
        mock_manager.get_async_initializer.return_value = None
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={
                "plugin_a": {"module_name": "module_a", "function_name": "init"},
                "plugin_b": {"module_name": "module_b", "function_name": "init"},
            },
        )
        
        init_order = []
        lock = threading.Lock()
        
        def mock_init(module_name, function_name, plugin_config, class_name=None, timeout=None):
            with lock:
                init_order.append(module_name)
            time.sleep(0.1)
            return (True, {"result": "success"}, None)
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.PluginInitializerUtils.invoke_plugin_init",
            side_effect=mock_init,
        ):
            def access_plugin(plugin_name):
                context.get(plugin_name)
            
            threads = [
                threading.Thread(target=access_plugin, args=("plugin_a",)),
                threading.Thread(target=access_plugin, args=("plugin_b",)),
            ]
            
            for t in threads:
                t.start()
            
            for t in threads:
                t.join(timeout=5.0)
            
            for t in threads:
                self.assertFalse(t.is_alive(), "Thread should have completed")

    def test_lock_timeout_prevents_deadlock(self):
        """Test that lock timeout prevents indefinite blocking."""
        mock_manager = MagicMock()
        mock_manager.get_async_initializer.return_value = None
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={
                "test_plugin": {
                    "module_name": "test_module",
                    "function_name": "init",
                }
            },
            initialization_timeout=0.5,
        )
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.PluginInitializerUtils.invoke_plugin_init",
            return_value=(True, {"result": "success"}, None),
        ):
            result = context.get("test_plugin")
            
            self.assertIsNotNone(result)


class TestHighConcurrencyStress(unittest.TestCase):
    """High concurrency stress tests."""

    def test_high_concurrency_plugin_access(self):
        """Test high concurrency plugin access."""
        mock_manager = MagicMock()
        mock_manager.get_async_initializer.return_value = None
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={
                "stress_plugin": {
                    "module_name": "stress_module",
                    "function_name": "init",
                }
            },
        )
        
        init_count = [0]
        lock = threading.Lock()
        
        def mock_init(*args, **kwargs):
            with lock:
                init_count[0] += 1
            time.sleep(0.02)
            return (True, {"result": "success"}, None)
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.PluginInitializerUtils.invoke_plugin_init",
            side_effect=mock_init,
        ):
            def access_plugin():
                result = context.get("stress_plugin")
                return result
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(access_plugin) for _ in range(100)]
                done, _ = concurrent.futures.wait(futures, timeout=10.0)
                results = [f.result() for f in done]
            
            non_none_results = [r for r in results if r is not None]
            self.assertGreaterEqual(len(non_none_results), 1)
            self.assertEqual(init_count[0], 1)  # Only one actual initialization


if __name__ == "__main__":
    unittest.main()
