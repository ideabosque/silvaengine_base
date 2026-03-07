#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Error handling path tests for plugin initialization.

This module tests various error scenarios and exception handling
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

from silvaengine_base.boosters.plugin.initializer_utils import (
    PluginInitializationError,
    PluginInitializerUtils,
)


class TestPluginInitializerUtilsErrors(unittest.TestCase):
    """Test error handling in PluginInitializerUtils."""

    def test_invoke_plugin_init_module_not_found(self):
        """Test initialization with non-existent module."""
        mock_invoker = MagicMock()
        mock_invoker.resolve_proxied_callable.side_effect = ModuleNotFoundError(
            "No module named 'non_existent_module'"
        )
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.Invoker",
            mock_invoker,
        ):
            success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
                module_name="non_existent_module",
                function_name="init",
                plugin_config={},
            )
            
            self.assertFalse(success)
            self.assertIsNone(result)
            self.assertIsNotNone(error_msg)
            self.assertIn("non_existent_module", error_msg)

    def test_invoke_plugin_init_function_not_found(self):
        """Test initialization with non-existent function."""
        mock_invoker = MagicMock()
        mock_invoker.resolve_proxied_callable.side_effect = AttributeError(
            "Function not found"
        )
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.Invoker",
            mock_invoker,
        ):
            success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
                module_name="existing_module",
                function_name="non_existent_function",
                plugin_config={},
            )
            
            self.assertFalse(success)
            self.assertIsNone(result)
            self.assertIsNotNone(error_msg)

    def test_invoke_plugin_init_runtime_error(self):
        """Test initialization when plugin raises runtime error."""
        mock_invoker = MagicMock()
        mock_callable = MagicMock(side_effect=RuntimeError("Plugin failed"))
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
            
            self.assertFalse(success)
            self.assertIsNone(result)
            self.assertIn("Plugin failed", error_msg)

    def test_invoke_plugin_init_value_error(self):
        """Test initialization when plugin raises value error."""
        mock_invoker = MagicMock()
        mock_callable = MagicMock(side_effect=ValueError("Invalid config"))
        mock_invoker.resolve_proxied_callable.return_value = mock_callable
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.Invoker",
            mock_invoker,
        ):
            success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
                module_name="test_module",
                function_name="init",
                plugin_config={"invalid": "config"},
            )
            
            self.assertFalse(success)
            self.assertIn("Invalid config", error_msg)

    def test_invoke_plugin_init_timeout_error(self):
        """Test initialization when plugin raises timeout error."""
        mock_invoker = MagicMock()
        mock_callable = MagicMock(side_effect=TimeoutError("Plugin timed out"))
        mock_invoker.resolve_proxied_callable.return_value = mock_callable
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.Invoker",
            mock_invoker,
        ):
            success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
                module_name="test_module",
                function_name="init",
                plugin_config={},
                timeout=0.1,
            )
            
            self.assertFalse(success)

    def test_validate_plugin_config_invalid_type(self):
        """Test config validation with invalid type."""
        is_valid, error = PluginInitializerUtils.validate_plugin_config(
            "not_a_dict"
        )
        
        self.assertFalse(is_valid)
        self.assertIn("must be a dictionary", error)

    def test_validate_plugin_config_missing_fields(self):
        """Test config validation with missing required fields."""
        is_valid, error = PluginInitializerUtils.validate_plugin_config(
            {"some_field": "value"},
            required_fields=["module_name", "function_name"],
        )
        
        self.assertFalse(is_valid)
        self.assertIn("Missing required fields", error)
        self.assertIn("module_name", error)
        self.assertIn("function_name", error)

    def test_validate_plugin_config_valid(self):
        """Test config validation with valid config."""
        is_valid, error = PluginInitializerUtils.validate_plugin_config(
            {"module_name": "test", "function_name": "init"},
            required_fields=["module_name", "function_name"],
        )
        
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_extract_plugin_metadata_missing_type(self):
        """Test metadata extraction with missing type."""
        with self.assertRaises(PluginInitializationError) as context:
            PluginInitializerUtils.extract_plugin_metadata(
                {"module_name": "test"},
                index=0,
            )
        
        self.assertIn("missing 'type' field", str(context.exception))

    def test_extract_plugin_metadata_missing_module_name(self):
        """Test metadata extraction with missing module_name."""
        with self.assertRaises(PluginInitializationError) as context:
            PluginInitializerUtils.extract_plugin_metadata(
                {"type": "test_plugin"},
                index=0,
            )
        
        self.assertIn("missing 'module_name' field", str(context.exception))

    def test_extract_plugin_metadata_missing_function_name(self):
        """Test metadata extraction with missing function_name."""
        with self.assertRaises(PluginInitializationError) as context:
            PluginInitializerUtils.extract_plugin_metadata(
                {"type": "test_plugin", "module_name": "test_module"},
                index=0,
            )
        
        self.assertIn("missing 'function_name' field", str(context.exception))

    def test_extract_plugin_metadata_success(self):
        """Test successful metadata extraction."""
        result = PluginInitializerUtils.extract_plugin_metadata(
            {
                "type": "test_plugin",
                "module_name": "test_module",
                "function_name": "init",
                "class_name": "TestClass",
                "config": {"key": "value"},
            },
            index=0,
        )
        
        self.assertEqual(len(result), 5)
        plugin_type, module_name, function_name, class_name, config = result
        self.assertEqual(plugin_type, "test_plugin")
        self.assertEqual(module_name, "test_module")
        self.assertEqual(function_name, "init")
        self.assertEqual(class_name, "TestClass")
        self.assertEqual(config, {"key": "value"})

    def test_wait_with_timeout_condition_met(self):
        """Test wait_with_timeout when condition is met."""
        call_count = [0]
        
        def condition():
            call_count[0] += 1
            return call_count[0] >= 3
        
        result = PluginInitializerUtils.wait_with_timeout(
            condition_check=condition,
            timeout=5.0,
            poll_interval=0.01,
        )
        
        self.assertTrue(result)
        self.assertGreaterEqual(call_count[0], 3)

    def test_wait_with_timeout_timeout(self):
        """Test wait_with_timeout when timeout occurs."""
        result = PluginInitializerUtils.wait_with_timeout(
            condition_check=lambda: False,
            timeout=0.1,
            poll_interval=0.05,
        )
        
        self.assertFalse(result)


class TestPluginInitializationError(unittest.TestCase):
    """Test PluginInitializationError exception."""

    def test_error_message(self):
        """Test error message formatting."""
        error = PluginInitializationError("Test error message")
        self.assertEqual(str(error), "Test error message")

    def test_error_inheritance(self):
        """Test that error inherits from Exception."""
        error = PluginInitializationError("Test")
        self.assertIsInstance(error, Exception)

    def test_error_can_be_raised_and_caught(self):
        """Test that error can be raised and caught."""
        with self.assertRaises(PluginInitializationError):
            raise PluginInitializationError("Test error")


if __name__ == "__main__":
    unittest.main()
