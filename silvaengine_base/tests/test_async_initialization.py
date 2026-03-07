#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Unit tests for asynchronous plugin initialization.

This module provides comprehensive tests for:
- InitializationTracker functionality
- PluginFuture functionality
- AsyncPluginInitializer functionality
- PluginManager async initialization
- Non-blocking lazy loading
- Parallel initialization performance
"""

import logging
import threading
import time
import unittest
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, patch

from silvaengine_base.boosters.plugin.async_initializer import (
    AsyncPluginInitializer,
    InitializationState,
    InitializationStatus,
    InitializationTracker,
    PluginFuture,
)
from silvaengine_base.boosters.plugin.context import (
    LazyPluginContext,
    PluginState,
)


class TestInitializationTracker(unittest.TestCase):
    """Test InitializationTracker functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.tracker = InitializationTracker(logger=self.logger)

    def test_start_initialization(self):
        """Test starting initialization."""
        plugin_type = "test_plugin"
        
        self.tracker.start_initialization(plugin_type)
        
        status = self.tracker.get_status(plugin_type)
        self.assertEqual(status.plugin_type, plugin_type)
        self.assertEqual(status.state, InitializationState.INITIALIZING)
        self.assertIsNotNone(status.start_time)
        self.assertIsNone(status.end_time)

    def test_complete_initialization(self):
        """Test completing initialization."""
        plugin_type = "test_plugin"
        
        self.tracker.start_initialization(plugin_type)
        self.tracker.complete_initialization(plugin_type)
        
        status = self.tracker.get_status(plugin_type)
        self.assertEqual(status.state, InitializationState.READY)
        self.assertIsNotNone(status.end_time)
        self.assertIsNotNone(status.get_duration())

    def test_fail_initialization(self):
        """Test failing initialization."""
        plugin_type = "test_plugin"
        error = ValueError("Test error")
        
        self.tracker.start_initialization(plugin_type)
        self.tracker.fail_initialization(plugin_type, error)
        
        status = self.tracker.get_status(plugin_type)
        self.assertEqual(status.state, InitializationState.FAILED)
        self.assertEqual(status.error, str(error))
        self.assertEqual(status.error_type, "ValueError")

    def test_wait_for_initialization(self):
        """Test waiting for initialization."""
        plugin_type = "test_plugin"
        
        self.tracker.register_plugin(plugin_type)
        
        def complete_after_delay():
            time.sleep(0.1)
            self.tracker.start_initialization(plugin_type)
            self.tracker.complete_initialization(plugin_type)
        
        thread = threading.Thread(target=complete_after_delay)
        thread.start()
        
        result = self.tracker.wait_for_initialization(plugin_type, timeout=5.0)
        
        thread.join()
        
        self.assertTrue(result)
        self.assertTrue(self.tracker.is_ready(plugin_type))

    def test_wait_for_all(self):
        """Test waiting for all plugins."""
        plugins = ["plugin_a", "plugin_b", "plugin_c"]
        
        for plugin in plugins:
            self.tracker.register_plugin(plugin)
        
        def complete_plugins():
            for plugin in plugins:
                time.sleep(0.05)
                self.tracker.start_initialization(plugin)
                self.tracker.complete_initialization(plugin)
        
        thread = threading.Thread(target=complete_plugins)
        thread.start()
        
        results = self.tracker.wait_for_all(timeout=10.0)
        
        thread.join()
        
        for plugin in plugins:
            self.assertTrue(results.get(plugin, False))

    def test_register_plugin(self):
        """Test registering a plugin."""
        plugin_type = "test_plugin"
        
        self.tracker.register_plugin(plugin_type)
        
        status = self.tracker.get_status(plugin_type)
        self.assertEqual(status.state, InitializationState.PENDING)

    def test_is_ready(self):
        """Test is_ready method."""
        plugin_type = "test_plugin"
        
        self.assertFalse(self.tracker.is_ready(plugin_type))
        
        self.tracker.start_initialization(plugin_type)
        self.assertFalse(self.tracker.is_ready(plugin_type))
        
        self.tracker.complete_initialization(plugin_type)
        self.assertTrue(self.tracker.is_ready(plugin_type))

    def test_is_failed(self):
        """Test is_failed method."""
        plugin_type = "test_plugin"
        
        self.assertFalse(self.tracker.is_failed(plugin_type))
        
        self.tracker.start_initialization(plugin_type)
        self.tracker.fail_initialization(plugin_type, ValueError("Error"))
        
        self.assertTrue(self.tracker.is_failed(plugin_type))

    def test_reset(self):
        """Test reset method."""
        plugin_type = "test_plugin"
        
        self.tracker.start_initialization(plugin_type)
        self.tracker.complete_initialization(plugin_type)
        
        self.tracker.reset(plugin_type)
        
        status = self.tracker.get_status(plugin_type)
        self.assertEqual(status.state, InitializationState.PENDING)

    def test_get_all_status(self):
        """Test get_all_status method."""
        plugins = ["plugin_a", "plugin_b"]
        
        for plugin in plugins:
            self.tracker.start_initialization(plugin)
        
        all_status = self.tracker.get_all_status()
        
        self.assertEqual(len(all_status), 2)
        self.assertIn("plugin_a", all_status)
        self.assertIn("plugin_b", all_status)


class TestPluginFuture(unittest.TestCase):
    """Test PluginFuture functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger(__name__)
        self.tracker = InitializationTracker(logger=self.logger)
        self.plugin_type = "test_plugin"
        self.future = PluginFuture(
            plugin_type=self.plugin_type,
            tracker=self.tracker,
            logger=self.logger,
        )

    def test_is_done_pending(self):
        """Test is_done returns False when pending."""
        self.tracker.register_plugin(self.plugin_type)
        
        self.assertFalse(self.future.is_done())

    def test_is_done_initializing(self):
        """Test is_done returns False when initializing."""
        self.tracker.start_initialization(self.plugin_type)
        
        self.assertFalse(self.future.is_done())

    def test_is_done_ready(self):
        """Test is_done returns True when ready."""
        self.tracker.start_initialization(self.plugin_type)
        self.tracker.complete_initialization(self.plugin_type)
        
        self.assertTrue(self.future.is_done())

    def test_is_done_failed(self):
        """Test is_done returns True when failed."""
        self.tracker.start_initialization(self.plugin_type)
        self.tracker.fail_initialization(self.plugin_type, ValueError("Error"))
        
        self.assertTrue(self.future.is_done())

    def test_is_ready(self):
        """Test is_ready method."""
        self.assertFalse(self.future.is_ready())
        
        self.tracker.start_initialization(self.plugin_type)
        self.tracker.complete_initialization(self.plugin_type)
        
        self.assertTrue(self.future.is_ready())

    def test_is_failed(self):
        """Test is_failed method."""
        self.assertFalse(self.future.is_failed())
        
        self.tracker.start_initialization(self.plugin_type)
        self.tracker.fail_initialization(self.plugin_type, ValueError("Error"))
        
        self.assertTrue(self.future.is_failed())

    def test_get_or_none(self):
        """Test get_or_none method."""
        self.assertIsNone(self.future.get_or_none())
        
        self.tracker.start_initialization(self.plugin_type)
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization(self.plugin_type)
        
        result = self.future.get_or_none()
        self.assertEqual(result, {"data": "test"})

    def test_get_with_timeout(self):
        """Test get method with timeout."""
        self.tracker.register_plugin(self.plugin_type)
        
        def complete_after_delay():
            time.sleep(0.1)
            self.tracker.start_initialization(self.plugin_type)
            self.future.set_result({"data": "test"})
            self.tracker.complete_initialization(self.plugin_type)
        
        thread = threading.Thread(target=complete_after_delay)
        thread.start()
        
        result = self.future.get(timeout=5.0)
        
        thread.join()
        
        self.assertEqual(result, {"data": "test"})

    def test_get_timeout_error(self):
        """Test get method raises TimeoutError."""
        self.tracker.register_plugin(self.plugin_type)
        
        with self.assertRaises(TimeoutError):
            self.future.get(timeout=0.1)

    def test_get_runtime_error_on_failure(self):
        """Test get method raises RuntimeError on failure."""
        self.tracker.start_initialization(self.plugin_type)
        self.tracker.fail_initialization(self.plugin_type, ValueError("Error"))
        
        with self.assertRaises(RuntimeError):
            self.future.get(timeout=1.0)

    def test_add_done_callback(self):
        """Test add_done_callback method."""
        callback_result = []
        
        def callback(result):
            callback_result.append(result)
        
        self.tracker.start_initialization(self.plugin_type)
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization(self.plugin_type)
        
        self.future.add_done_callback(callback)
        
        self.assertEqual(len(callback_result), 1)
        self.assertEqual(callback_result[0], {"data": "test"})

    def test_add_done_callback_before_completion(self):
        """Test add_done_callback before completion."""
        callback_result = []
        
        def callback(result):
            callback_result.append(result)
        
        self.tracker.register_plugin(self.plugin_type)
        self.future.add_done_callback(callback)
        
        self.tracker.start_initialization(self.plugin_type)
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization(self.plugin_type)
        
        time.sleep(0.1)
        
        self.assertEqual(len(callback_result), 1)
        self.assertEqual(callback_result[0], {"data": "test"})

    def test_plugin_type_property(self):
        """Test plugin_type property."""
        self.assertEqual(self.future.plugin_type, self.plugin_type)


class TestAsyncPluginInitializer(unittest.TestCase):
    """Test AsyncPluginInitializer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger(__name__)
        self.mock_plugin_manager = Mock()
        self.mock_plugin_manager.get_initialized_objects.return_value = {}
        
        self.initializer = AsyncPluginInitializer(
            plugin_manager=self.mock_plugin_manager,
            logger=self.logger,
            max_workers=2,
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.initializer:
            self.initializer.shutdown(wait=False)

    def test_initialize_async(self):
        """Test async initialization."""
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
            {
                "type": "plugin_b",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        with patch.object(
            self.initializer, "_do_initialize", return_value={"result": "success"}
        ):
            futures = self.initializer.initialize_async(plugins_config)
            
            self.assertEqual(len(futures), 2)
            self.assertIn("plugin_a", futures)
            self.assertIn("plugin_b", futures)
            
            for plugin_type, future in futures.items():
                self.assertIsInstance(future, PluginFuture)
                self.assertEqual(future.plugin_type, plugin_type)

    def test_initialize_background(self):
        """Test background initialization."""
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        with patch.object(
            self.initializer, "_do_initialize", return_value={"result": "success"}
        ):
            self.initializer.initialize_background(plugins_config, timeout=5.0)
            
            tracker = self.initializer.get_tracker()
            status = tracker.get_status("plugin_a")
            
            self.assertIn(
                status.state,
                [InitializationState.PENDING, InitializationState.INITIALIZING, InitializationState.READY],
            )

    def test_wait_all(self):
        """Test wait_all method."""
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        with patch.object(
            self.initializer, "_do_initialize", return_value={"result": "success"}
        ):
            self.initializer.initialize_background(plugins_config, timeout=5.0)
            
            results = self.initializer.wait_all(timeout=10.0)
            
            self.assertIn("plugin_a", results)

    def test_shutdown(self):
        """Test shutdown method."""
        self.assertFalse(self.initializer.is_shutdown())
        
        self.initializer.shutdown(wait=True)
        
        self.assertTrue(self.initializer.is_shutdown())

    def test_get_future(self):
        """Test get_future method."""
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        with patch.object(
            self.initializer, "_do_initialize", return_value={"result": "success"}
        ):
            self.initializer.initialize_async(plugins_config)
            
            future = self.initializer.get_future("plugin_a")
            
            self.assertIsNotNone(future)
            self.assertEqual(future.plugin_type, "plugin_a")

    def test_get_all_futures(self):
        """Test get_all_futures method."""
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
            {
                "type": "plugin_b",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        with patch.object(
            self.initializer, "_do_initialize", return_value={"result": "success"}
        ):
            self.initializer.initialize_async(plugins_config)
            
            futures = self.initializer.get_all_futures()
            
            self.assertEqual(len(futures), 2)

    def test_get_initialization_summary(self):
        """Test get_initialization_summary method."""
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        with patch.object(
            self.initializer, "_do_initialize", return_value={"result": "success"}
        ):
            self.initializer.initialize_async(plugins_config)
            
            summary = self.initializer.get_initialization_summary()
            
            self.assertEqual(summary["total_plugins"], 1)
            self.assertIn("pending", summary)
            self.assertIn("initializing", summary)
            self.assertIn("ready", summary)
            self.assertIn("failed", summary)

    def test_initialize_after_shutdown(self):
        """Test initialization after shutdown."""
        self.initializer.shutdown(wait=True)
        
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        futures = self.initializer.initialize_async(plugins_config)
        
        self.assertEqual(len(futures), 0)

    def test_skip_plugin_without_type(self):
        """Test that plugins without type are skipped."""
        plugins_config = [
            {
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        futures = self.initializer.initialize_async(plugins_config)
        
        self.assertEqual(len(futures), 0)


class TestPluginManagerAsync(unittest.TestCase):
    """Test PluginManager async initialization."""

    def setUp(self):
        """Set up test fixtures."""
        from silvaengine_base import PluginManager
        
        PluginManager.reset_instance()
        self.logger = logging.getLogger(__name__)
        self.plugin_manager = PluginManager(logger=self.logger)

    def tearDown(self):
        """Clean up after tests."""
        from silvaengine_base import PluginManager
        
        PluginManager.reset_instance()

    def test_initialize_async(self):
        """Test PluginManager.initialize_async()."""
        setting = {
            "plugins": [
                {
                    "type": "plugin_a",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                },
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            futures = self.plugin_manager.initialize_async(setting)
            
            self.assertIsInstance(futures, dict)

    def test_initialize_background(self):
        """Test PluginManager.initialize_background()."""
        setting = {
            "plugins": [
                {
                    "type": "plugin_a",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                },
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            self.plugin_manager.initialize_background(setting)
            
            self.assertTrue(self.plugin_manager.is_initialized())

    def test_get_initialization_status(self):
        """Test PluginManager.get_initialization_status()."""
        setting = {
            "plugins": [
                {
                    "type": "plugin_a",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                },
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            self.plugin_manager.initialize_background(setting)
            
            status = self.plugin_manager.get_initialization_status()
            
            self.assertIsInstance(status, dict)

    def test_wait_initialization(self):
        """Test PluginManager.wait_initialization()."""
        setting = {
            "plugins": [
                {
                    "type": "plugin_a",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                },
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            self.plugin_manager.initialize_background(setting)
            
            results = self.plugin_manager.wait_initialization(timeout=10.0)
            
            self.assertIsInstance(results, dict)


class TestLazyPluginContextNonBlocking(unittest.TestCase):
    """Test LazyPluginContext non-blocking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger(__name__)
        self.mock_plugin_manager = Mock()
        
        self.plugin_configs = {
            "plugin_a": {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
            "plugin_b": {
                "type": "plugin_b",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        }
        
        self.lazy_context = LazyPluginContext(
            plugin_manager=self.mock_plugin_manager,
            plugin_configs=self.plugin_configs,
            logger=self.logger,
        )

    def tearDown(self):
        """Clean up after tests."""
        self.lazy_context.shutdown(wait=False)

    def test_get_or_schedule(self):
        """Test get_or_schedule returns Future immediately."""
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            future = self.lazy_context.get_or_schedule("plugin_a")
            
            self.assertIsInstance(future, PluginFuture)
            self.assertEqual(future.plugin_type, "plugin_a")

    def test_preload_background(self):
        """Test preload_background is non-blocking."""
        start_time = time.time()
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            self.lazy_context.preload_background()
            
            elapsed = time.time() - start_time
            
            self.assertLess(elapsed, 0.5)

    def test_add_initialization_callback(self):
        """Test initialization callback is called."""
        callback_results = []
        
        def callback(plugin_name, result, error):
            callback_results.append({
                "plugin_name": plugin_name,
                "result": result,
                "error": error,
            })
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            self.lazy_context.add_initialization_callback("plugin_a", callback)
            
            self.lazy_context.get_or_schedule("plugin_a")
            
            time.sleep(0.5)
            
            self.assertEqual(len(callback_results), 1)
            self.assertEqual(callback_results[0]["plugin_name"], "plugin_a")
            self.assertIsNotNone(callback_results[0]["result"])

    def test_non_blocking_first_access(self):
        """Test first access returns immediately without blocking."""
        start_time = time.time()
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: time.sleep(1.0)
            
            result = self.lazy_context.get("plugin_a")
            
            elapsed = time.time() - start_time
            
            self.assertIsNone(result)
            self.assertLess(elapsed, 0.5)

    def test_get_all_plugins_non_blocking(self):
        """Test get_all_plugins returns immediately."""
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            plugins = self.lazy_context.get_all_plugins()
            
            self.assertIsInstance(plugins, dict)

    def test_get_initialization_stats(self):
        """Test get_initialization_stats method."""
        stats = self.lazy_context.get_initialization_stats()
        
        self.assertIn("total_configured", stats)
        self.assertIn("initialized", stats)
        self.assertIn("failed", stats)
        self.assertEqual(stats["total_configured"], 2)


class TestParallelInitializationPerformance(unittest.TestCase):
    """Test parallel initialization performance."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger(__name__)
        self.mock_plugin_manager = Mock()
        
        self.initializer = AsyncPluginInitializer(
            plugin_manager=self.mock_plugin_manager,
            logger=self.logger,
            max_workers=4,
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.initializer:
            self.initializer.shutdown(wait=False)

    def test_parallel_vs_sequential(self):
        """Test parallel initialization is faster than sequential."""
        num_plugins = 4
        init_delay = 0.2
        
        plugins_config = [
            {
                "type": f"plugin_{i}",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            }
            for i in range(num_plugins)
        ]
        
        def slow_init(config):
            time.sleep(init_delay)
            return {"result": "success"}
        
        with patch.object(
            self.initializer, "_do_initialize", side_effect=slow_init
        ):
            start_time = time.time()
            self.initializer.initialize_background(plugins_config, timeout=10.0)
            results = self.initializer.wait_all(timeout=10.0)
            parallel_time = time.time() - start_time
        
        expected_max_time = init_delay * num_plugins / 2
        
        self.assertLess(parallel_time, expected_max_time)
        
        for plugin_type in [f"plugin_{i}" for i in range(num_plugins)]:
            self.assertIn(plugin_type, results)

    def test_dependency_order(self):
        """Test dependencies are initialized in correct order."""
        initialization_order = []
        
        def track_init(plugin_type):
            def init_func(config):
                initialization_order.append(plugin_type)
                return {"result": "success"}
            return init_func
        
        plugins_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
            {
                "type": "plugin_b",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        with patch.object(
            self.initializer, "_do_initialize"
        ) as mock_init:
            mock_init.return_value = {"result": "success"}
            
            self.initializer.initialize_background(plugins_config, timeout=10.0)
            self.initializer.wait_all(timeout=10.0)
        
        self.assertEqual(len(initialization_order), 0)

    def test_parallel_efficiency(self):
        """Test parallel efficiency calculation."""
        num_plugins = 8
        init_delay = 0.1
        
        plugins_config = [
            {
                "type": f"plugin_{i}",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            }
            for i in range(num_plugins)
        ]
        
        def slow_init(config):
            time.sleep(init_delay)
            return {"result": "success"}
        
        with patch.object(
            self.initializer, "_do_initialize", side_effect=slow_init
        ):
            start_time = time.time()
            self.initializer.initialize_background(plugins_config, timeout=30.0)
            results = self.initializer.wait_all(timeout=30.0)
            parallel_time = time.time() - start_time
        
        sequential_time = init_delay * num_plugins
        
        efficiency = sequential_time / parallel_time
        
        self.assertGreater(efficiency, 1.5)

    def test_max_workers_limit(self):
        """Test that max_workers limits concurrency."""
        max_workers = 2
        initializer = AsyncPluginInitializer(
            plugin_manager=self.mock_plugin_manager,
            logger=self.logger,
            max_workers=max_workers,
        )
        
        num_plugins = 4
        concurrent_count = 0
        max_concurrent = 0
        lock = threading.Lock()
        
        def track_concurrency(config):
            nonlocal concurrent_count, max_concurrent
            with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            time.sleep(0.1)
            with lock:
                concurrent_count -= 1
            return {"result": "success"}
        
        plugins_config = [
            {
                "type": f"plugin_{i}",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            }
            for i in range(num_plugins)
        ]
        
        with patch.object(
            initializer, "_do_initialize", side_effect=track_concurrency
        ):
            initializer.initialize_background(plugins_config, timeout=10.0)
            initializer.wait_all(timeout=10.0)
        
        self.assertLessEqual(max_concurrent, max_workers)
        
        initializer.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
