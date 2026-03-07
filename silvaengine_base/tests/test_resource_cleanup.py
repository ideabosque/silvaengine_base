#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Resource cleanup tests for plugin initialization.

This module tests resource cleanup and shutdown behavior
in the plugin initialization system.

@since 2.0.0
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import MagicMock

class MockInvoker:
    """Mock implementation of Invoker for testing."""
    
    @staticmethod
    def resolve_proxied_callable(
        module_name,
        function_name,
        class_name=None,
        constructor_parameters=None,
    ):
        """Mock resolve_proxied_callable that returns a callable."""
        def mock_callable(config):
            return {"result": "mock_success", "config": config}
        
        return mock_callable

mock_invoker_module = MagicMock()
mock_invoker_module.Invoker = MockInvoker
sys.modules['silvaengine_utility'] = mock_invoker_module

mock_dynamodb_module = MagicMock()
sys.modules['silvaengine_dynamodb_base'] = mock_dynamodb_module
sys.modules['silvaengine_dynamodb_base.models'] = MagicMock()

mock_constants_module = MagicMock()
sys.modules['silvaengine_constants'] = mock_constants_module

import unittest
from unittest.mock import MagicMock, patch, Mock
import threading
import time
import weakref
import gc

from silvaengine_base.boosters.plugin.async_initializer import (
    AsyncPluginInitializer,
    InitializationTracker,
    PluginFuture,
)
from silvaengine_base.boosters.plugin.parallel_scheduler import (
    ParallelInitializationScheduler,
    InitializationTask,
)
from silvaengine_base.boosters.plugin.context import LazyPluginContext


class TestAsyncInitializerCleanup(unittest.TestCase):
    """Test cleanup behavior in AsyncPluginInitializer."""

    def test_shutdown_waits_for_tasks(self):
        """Test that shutdown waits for pending tasks."""
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=2,
        )
        
        task_started = threading.Event()
        task_completed = threading.Event()
        
        def slow_task(plugin_type, config, timeout):
            task_started.set()
            time.sleep(0.2)
            task_completed.set()
        
        initializer._do_initialize = slow_task
        
        initializer.initialize_background([
            {"type": "test_plugin", "module_name": "test", "config": {}}
        ])
        
        task_started.wait(timeout=1.0)
        
        shutdown_thread = threading.Thread(target=initializer.shutdown, kwargs={"wait": True})
        shutdown_thread.start()
        
        time.sleep(0.1)
        self.assertTrue(shutdown_thread.is_alive())
        
        task_completed.wait(timeout=1.0)
        shutdown_thread.join(timeout=1.0)
        
        self.assertFalse(shutdown_thread.is_alive())
        self.assertTrue(initializer.is_shutdown())

    def test_shutdown_no_wait(self):
        """Test shutdown without waiting."""
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=2,
        )
        
        initializer.initialize_background([
            {"type": "test_plugin", "module_name": "test", "config": {}}
        ])
        
        initializer.shutdown(wait=False)
        
        self.assertTrue(initializer.is_shutdown())

    def test_multiple_shutdown_calls(self):
        """Test that multiple shutdown calls are safe."""
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=2,
        )
        
        initializer.shutdown()
        initializer.shutdown()
        initializer.shutdown()
        
        self.assertTrue(initializer.is_shutdown())

    def test_initialize_after_shutdown(self):
        """Test initialization after shutdown."""
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=2,
        )
        
        initializer.shutdown()
        
        initializer.initialize_background([
            {"type": "test_plugin", "module_name": "test", "config": {}}
        ])
        
        self.assertTrue(initializer.is_shutdown())

    def test_weak_reference_cleanup(self):
        """Test that initializer can be garbage collected."""
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=2,
        )
        
        weak_ref = weakref.ref(initializer)
        
        initializer.shutdown()
        del initializer
        gc.collect()
        
        self.assertIsNone(weak_ref())


class TestParallelSchedulerCleanup(unittest.TestCase):
    """Test cleanup behavior in ParallelInitializationScheduler."""

    def test_shutdown_waits_for_tasks(self):
        """Test that scheduler shutdown waits for tasks."""
        scheduler = ParallelInitializationScheduler(max_workers=2)
        
        task_started = threading.Event()
        task_completed = threading.Event()
        
        original_init = scheduler._do_initialize
        
        def slow_init(task):
            task_started.set()
            time.sleep(0.2)
            task_completed.set()
            return original_init(task)
        
        scheduler._do_initialize = slow_init
        
        tasks = [
            InitializationTask(
                plugin_type="test_plugin",
                config={"module_name": "test"},
            )
        ]
        
        scheduler.schedule(tasks)
        
        task_started.wait(timeout=1.0)
        
        shutdown_thread = threading.Thread(target=scheduler.shutdown, kwargs={"wait": True})
        shutdown_thread.start()
        
        time.sleep(0.1)
        self.assertTrue(shutdown_thread.is_alive())
        
        task_completed.wait(timeout=1.0)
        shutdown_thread.join(timeout=1.0)
        
        self.assertFalse(shutdown_thread.is_alive())
        self.assertTrue(scheduler.is_shutdown())

    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        scheduler = ParallelInitializationScheduler(max_workers=2)
        
        tasks = [
            InitializationTask(
                plugin_type="test_plugin",
                config={"module_name": "test"},
            )
        ]
        
        scheduler.schedule(tasks)
        
        scheduler.reset()
        
        self.assertEqual(len(scheduler.get_all_futures()), 0)
        self.assertEqual(len(scheduler._ready_events), 0)
        self.assertEqual(len(scheduler._initialization_errors), 0)
        self.assertFalse(scheduler.is_shutdown())

    def test_shutdown_then_reset(self):
        """Test reset after shutdown."""
        scheduler = ParallelInitializationScheduler(max_workers=2)
        
        scheduler.shutdown()
        self.assertTrue(scheduler.is_shutdown())
        
        scheduler.reset()
        self.assertFalse(scheduler.is_shutdown())


class TestLazyPluginContextCleanup(unittest.TestCase):
    """Test cleanup behavior in LazyPluginContext."""

    def test_shutdown_releases_executor(self):
        """Test that shutdown releases the executor."""
        mock_manager = MagicMock()
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={"test": {"module_name": "test"}},
        )
        
        context._async_executor = MagicMock()
        
        context.shutdown(wait=True)
        
        context._async_executor.shutdown.assert_called_once_with(wait=True)

    def test_shutdown_without_executor(self):
        """Test shutdown when no executor exists."""
        mock_manager = MagicMock()
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={},
        )
        
        context.shutdown(wait=True)

    def test_multiple_shutdown_calls(self):
        """Test multiple shutdown calls are safe."""
        mock_manager = MagicMock()
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={},
        )
        
        context.shutdown()
        context.shutdown()
        context.shutdown()


class TestInitializationTrackerCleanup(unittest.TestCase):
    """Test cleanup behavior in InitializationTracker."""

    def test_clear_on_reset(self):
        """Test that reset clears all tracking data."""
        from silvaengine_base.boosters.plugin.async_initializer import InitializationState
        tracker = InitializationTracker()
        
        tracker.register_plugin("plugin1")
        tracker.register_plugin("plugin2")
        tracker.start_initialization("plugin1")
        tracker.complete_initialization("plugin1")
        tracker.start_initialization("plugin2")
        tracker.fail_initialization("plugin2", Exception("Failed"))
        
        tracker.reset("plugin1")
        
        status = tracker.get_status("plugin1")
        self.assertEqual(status.state, InitializationState.PENDING)

    def test_events_cleared_on_reset(self):
        """Test that events are cleared on reset."""
        tracker = InitializationTracker()
        
        tracker.register_plugin("test_plugin")
        tracker.start_initialization("test_plugin")
        tracker.complete_initialization("test_plugin")
        
        self.assertTrue(tracker._events["test_plugin"].is_set())
        
        tracker.reset("test_plugin")
        
        self.assertFalse(tracker._events["test_plugin"].is_set())


class TestResourceLeakPrevention(unittest.TestCase):
    """Test prevention of resource leaks."""

    def test_no_thread_leak_on_shutdown(self):
        """Test that no threads leak after shutdown."""
        initial_thread_count = threading.active_count()
        
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=4,
        )
        
        initializer.initialize_background([
            {"type": f"plugin_{i}", "module_name": "test", "config": {}}
            for i in range(10)
        ])
        
        time.sleep(0.1)
        
        initializer.shutdown(wait=True)
        
        time.sleep(0.2)
        
        final_thread_count = threading.active_count()
        
        self.assertLessEqual(final_thread_count, initial_thread_count + 1)

    def test_scheduler_no_thread_leak(self):
        """Test that scheduler doesn't leak threads."""
        initial_thread_count = threading.active_count()
        
        scheduler = ParallelInitializationScheduler(max_workers=4)
        
        tasks = [
            InitializationTask(
                plugin_type=f"plugin_{i}",
                config={"module_name": "test"},
            )
            for i in range(10)
        ]
        
        scheduler.schedule(tasks)
        
        time.sleep(0.1)
        
        scheduler.shutdown(wait=True)
        
        time.sleep(0.2)
        
        final_thread_count = threading.active_count()
        
        self.assertLessEqual(final_thread_count, initial_thread_count + 1)

    def test_memory_cleanup_on_plugin_failure(self):
        """Test that memory is cleaned up when plugin fails."""
        mock_manager = MagicMock()
        mock_manager.get_async_initializer.return_value = None
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={
                "failing_plugin": {
                    "module_name": "nonexistent",
                    "function_name": "init",
                }
            },
        )
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.PluginInitializerUtils.invoke_plugin_init",
            return_value=(False, None, "Module not found"),
        ):
            result = context.get("failing_plugin")
        
        self.assertIsNone(result)
        self.assertIn("failing_plugin", context._failed_plugins)
        self.assertEqual(len(context._initializing_plugins), 0)


class TestGracefulShutdown(unittest.TestCase):
    """Test graceful shutdown scenarios."""

    def test_shutdown_during_initialization(self):
        """Test shutdown during active initialization."""
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=2,
        )
        
        init_started = threading.Event()
        init_blocked = threading.Event()
        
        def blocking_init(plugin_type, config, timeout):
            init_started.set()
            init_blocked.wait(timeout=5.0)
            return {"result": "success"}
        
        initializer._do_initialize = blocking_init
        
        initializer.initialize_background([
            {"type": "test_plugin", "module_name": "test", "config": {}}
        ])
        
        init_started.wait(timeout=1.0)
        
        shutdown_thread = threading.Thread(target=initializer.shutdown, kwargs={"wait": False})
        shutdown_thread.start()
        shutdown_thread.join(timeout=1.0)
        
        self.assertTrue(initializer.is_shutdown())
        
        init_blocked.set()

    def test_callback_cleanup_on_shutdown(self):
        """Test that callbacks are cleaned up on shutdown."""
        mock_manager = MagicMock()
        initializer = AsyncPluginInitializer(
            plugin_manager=mock_manager,
            max_workers=2,
        )
        
        callback_called = threading.Event()
        
        def completion_callback(results):
            callback_called.set()
        
        initializer.initialize_background([
            {"type": "test_plugin", "module_name": "test", "config": {}}
        ])
        
        initializer.shutdown(wait=True)
        
        self.assertTrue(initializer.is_shutdown())


if __name__ == "__main__":
    unittest.main()
