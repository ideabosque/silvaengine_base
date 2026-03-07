#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Edge case tests for plugin initialization.

This module tests edge cases and boundary conditions in the
plugin initialization system.

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

from silvaengine_base.boosters.plugin.initializer_utils import (
    PluginInitializationError,
    PluginInitializerUtils,
)
from silvaengine_base.boosters.plugin.context import (
    EagerPluginContext,
    LazyPluginContext,
    PluginState,
    PluginNotFoundError,
)
from silvaengine_base.boosters.plugin.async_initializer import (
    InitializationState,
    InitializationTracker,
    PluginFuture,
)


class TestPluginInitializerUtilsEdgeCases(unittest.TestCase):
    """Test edge cases in PluginInitializerUtils."""

    def test_invoke_plugin_init_empty_config(self):
        """Test initialization with empty config."""
        mock_invoker = MagicMock()
        mock_callable = MagicMock(return_value={"result": "success"})
        mock_invoker.resolve_proxied_callable.return_value = mock_callable
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.Invoker",
            mock_invoker,
        ):
            success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
                module_name="test_module",
                function_name="init",
                plugin_config={},
            )
            
            self.assertTrue(success)
            self.assertEqual(result, {"result": "success"})
            self.assertIsNone(error_msg)

    def test_invoke_plugin_init_none_config(self):
        """Test initialization with None config."""
        mock_invoker = MagicMock()
        mock_callable = MagicMock(return_value={"result": "success"})
        mock_invoker.resolve_proxied_callable.return_value = mock_callable
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.Invoker",
            mock_invoker,
        ):
            success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
                module_name="test_module",
                function_name="init",
                plugin_config=None,
            )
            
            self.assertTrue(success)

    def test_invoke_plugin_init_with_class_name(self):
        """Test initialization with class name."""
        mock_invoker = MagicMock()
        mock_callable = MagicMock(return_value={"result": "success"})
        mock_invoker.resolve_proxied_callable.return_value = mock_callable
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.Invoker",
            mock_invoker,
        ):
            success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
                module_name="test_module",
                function_name="init",
                plugin_config={},
                class_name="TestClass",
            )
            
            self.assertTrue(success)
            mock_invoker.resolve_proxied_callable.assert_called_once_with(
                module_name="test_module",
                function_name="init",
                class_name="TestClass",
                constructor_parameters=None,
            )

    def test_validate_plugin_config_empty_dict(self):
        """Test validation with empty dict."""
        is_valid, error = PluginInitializerUtils.validate_plugin_config({})
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_plugin_config_empty_required_fields(self):
        """Test validation with empty required fields list."""
        is_valid, error = PluginInitializerUtils.validate_plugin_config(
            {},
            required_fields=[],
        )
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_extract_plugin_metadata_minimal_config(self):
        """Test metadata extraction with minimal config."""
        result = PluginInitializerUtils.extract_plugin_metadata(
            {
                "type": "test",
                "module_name": "module",
                "function_name": "func",
            },
            index=0,
        )
        
        plugin_type, module_name, function_name, class_name, config = result
        self.assertEqual(plugin_type, "test")
        self.assertEqual(module_name, "module")
        self.assertEqual(function_name, "func")
        self.assertIsNone(class_name)
        self.assertEqual(config, {})

    def test_wait_with_timeout_immediate_condition(self):
        """Test wait when condition is immediately true."""
        result = PluginInitializerUtils.wait_with_timeout(
            condition_check=lambda: True,
            timeout=10.0,
        )
        self.assertTrue(result)

    def test_wait_with_timeout_zero_timeout(self):
        """Test wait with zero timeout."""
        result = PluginInitializerUtils.wait_with_timeout(
            condition_check=lambda: False,
            timeout=0.0,
        )
        self.assertFalse(result)

    def test_wait_with_timeout_negative_timeout(self):
        """Test wait with negative timeout."""
        result = PluginInitializerUtils.wait_with_timeout(
            condition_check=lambda: False,
            timeout=-1.0,
        )
        self.assertFalse(result)


class TestInitializationTrackerEdgeCases(unittest.TestCase):
    """Test edge cases in InitializationTracker."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = InitializationTracker()

    def test_get_status_unknown_plugin(self):
        """Test getting status for unknown plugin."""
        status = self.tracker.get_status("unknown_plugin")
        self.assertEqual(status.state, InitializationState.PENDING)

    def test_wait_for_unknown_plugin(self):
        """Test waiting for unknown plugin."""
        result = self.tracker.wait_for_initialization(
            "unknown_plugin",
            timeout=0.1,
        )
        self.assertFalse(result)

    def test_concurrent_initialization(self):
        """Test concurrent initialization tracking."""
        plugins = [f"plugin_{i}" for i in range(10)]
        
        def init_plugin(plugin_type):
            self.tracker.start_initialization(plugin_type)
            time.sleep(0.01)
            self.tracker.complete_initialization(plugin_type)
        
        threads = [
            threading.Thread(target=init_plugin, args=(p,))
            for p in plugins
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        for plugin in plugins:
            status = self.tracker.get_status(plugin)
            self.assertEqual(status.state, InitializationState.READY)

    def test_fail_then_retry(self):
        """Test failing then retrying initialization."""
        self.tracker.register_plugin("test_plugin")
        self.tracker.start_initialization("test_plugin")
        self.tracker.fail_initialization("test_plugin", Exception("Failed"))
        
        status = self.tracker.get_status("test_plugin")
        self.assertEqual(status.state, InitializationState.FAILED)
        
        self.tracker.reset("test_plugin")
        self.tracker.register_plugin("test_plugin")
        self.tracker.start_initialization("test_plugin")
        self.tracker.complete_initialization("test_plugin")
        
        status = self.tracker.get_status("test_plugin")
        self.assertEqual(status.state, InitializationState.READY)

    def test_double_complete(self):
        """Test double completion of initialization."""
        self.tracker.register_plugin("test_plugin")
        self.tracker.start_initialization("test_plugin")
        self.tracker.complete_initialization("test_plugin")
        self.tracker.complete_initialization("test_plugin")
        
        status = self.tracker.get_status("test_plugin")
        self.assertEqual(status.state, InitializationState.READY)

    def test_is_ready_unknown_plugin(self):
        """Test is_ready for unknown plugin."""
        self.assertFalse(self.tracker.is_ready("unknown_plugin"))

    def test_is_failed_unknown_plugin(self):
        """Test is_failed for unknown plugin."""
        self.assertFalse(self.tracker.is_failed("unknown_plugin"))


class TestPluginFutureEdgeCases(unittest.TestCase):
    """Test edge cases in PluginFuture."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = InitializationTracker()
        self.tracker.register_plugin("test_plugin")
        self.future = PluginFuture(
            plugin_type="test_plugin",
            tracker=self.tracker,
        )

    def test_get_before_complete(self):
        """Test getting result before completion."""
        with self.assertRaises(TimeoutError):
            self.future.get(timeout=0.1)

    def test_get_after_failure(self):
        """Test getting result after failure."""
        self.tracker.start_initialization("test_plugin")
        self.tracker.fail_initialization(
            "test_plugin",
            Exception("Test failure"),
        )
        
        with self.assertRaises(RuntimeError) as context:
            self.future.get(timeout=1.0)
        
        self.assertIn("Test failure", str(context.exception))

    def test_add_callback_before_complete(self):
        """Test adding callback before completion."""
        callback_results = []
        
        def callback(result):
            callback_results.append(result)
        
        self.future.add_done_callback(callback)
        
        self.tracker.start_initialization("test_plugin")
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization("test_plugin")
        
        self.assertEqual(len(callback_results), 1)
        self.assertEqual(callback_results[0], {"data": "test"})

    def test_add_callback_after_complete(self):
        """Test adding callback after completion."""
        callback_results = []
        
        def callback(result):
            callback_results.append(result)
        
        self.tracker.start_initialization("test_plugin")
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization("test_plugin")
        
        self.future.add_done_callback(callback)
        
        self.assertEqual(len(callback_results), 1)
        self.assertEqual(callback_results[0], {"data": "test"})

    def test_callback_exception_handling(self):
        """Test that callback exceptions are caught."""
        def bad_callback(result):
            raise ValueError("Bad callback")
        
        self.tracker.start_initialization("test_plugin")
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization("test_plugin")
        
        self.future.add_done_callback(bad_callback)

    def test_get_or_none_not_ready(self):
        """Test get_or_none when not ready."""
        result = self.future.get_or_none()
        self.assertIsNone(result)

    def test_get_or_none_ready(self):
        """Test get_or_none when ready."""
        self.tracker.start_initialization("test_plugin")
        self.future.set_result({"data": "test"})
        self.tracker.complete_initialization("test_plugin")
        
        result = self.future.get_or_none()
        self.assertEqual(result, {"data": "test"})


class TestEagerPluginContextEdgeCases(unittest.TestCase):
    """Test edge cases in EagerPluginContext."""

    def test_get_empty_name(self):
        """Test getting plugin with empty name."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {}
        
        context = EagerPluginContext(mock_manager)
        result = context.get("")
        
        self.assertIsNone(result)

    def test_get_whitespace_name(self):
        """Test getting plugin with whitespace name."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {}
        
        context = EagerPluginContext(mock_manager)
        result = context.get("   ")
        
        self.assertIsNone(result)

    def test_get_or_raise_not_found(self):
        """Test get_or_raise when plugin not found."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {}
        
        context = EagerPluginContext(mock_manager)
        
        with self.assertRaises(PluginNotFoundError):
            context.get_or_raise("nonexistent")

    def test_get_all_plugins_empty(self):
        """Test getting all plugins when empty."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {}
        
        context = EagerPluginContext(mock_manager)
        result = context.get_all_plugins()
        
        self.assertEqual(result, {})


class TestLazyPluginContextEdgeCases(unittest.TestCase):
    """Test edge cases in LazyPluginContext."""

    def test_get_nonexistent_plugin(self):
        """Test getting nonexistent plugin."""
        mock_manager = MagicMock()
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={},
        )
        
        result = context.get("nonexistent")
        self.assertIsNone(result)

    def test_preload_all_empty(self):
        """Test preloading all when empty."""
        mock_manager = MagicMock()
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={},
        )
        
        result = context.preload_all()
        self.assertEqual(result, {})

    def test_get_initialization_stats_empty(self):
        """Test getting stats when empty."""
        mock_manager = MagicMock()
        
        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={},
        )
        
        stats = context.get_initialization_stats()
        
        self.assertEqual(stats["total_configured"], 0)
        self.assertEqual(stats["initialized"], 0)
        self.assertEqual(stats["failed"], 0)


if __name__ == "__main__":
    unittest.main()
