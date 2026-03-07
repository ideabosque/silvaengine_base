#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Regression tests for silvaengine_base plugin system.

This module tests backward compatibility and ensures that
optimizations do not break existing functionality.

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

from silvaengine_base.boosters.plugin import (
    PluginManager,
    PluginConfiguration,
    DependencyResolver,
    PluginNotFoundError,
    PluginState,
)
from silvaengine_base.boosters.plugin.dependency import PluginDependency
from silvaengine_base.boosters.plugin.context import (
    EagerPluginContext,
    LazyPluginContext,
    get_plugin_context,
    PluginState,
)


class TestDependencyResolverBackwardCompatibility(unittest.TestCase):
    """Test DependencyResolver backward compatibility."""

    def test_resolve_dependencies_interface(self):
        """Test that resolve_dependencies interface remains compatible."""
        resolver = DependencyResolver()
        
        plugins = [
            PluginDependency(plugin_name="A", dependencies=["B"]),
            PluginDependency(plugin_name="B", dependencies=["C"]),
            PluginDependency(plugin_name="C", dependencies=[]),
        ]
        
        result = resolver.resolve_dependencies(plugins)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].plugin_name, "C")
        self.assertEqual(result[1].plugin_name, "B")
        self.assertEqual(result[2].plugin_name, "A")

    def test_detect_circular_dependencies_interface(self):
        """Test that detect_circular_dependencies interface remains compatible."""
        resolver = DependencyResolver()
        
        plugins_no_cycle = [
            PluginDependency(plugin_name="A", dependencies=["B"]),
            PluginDependency(plugin_name="B", dependencies=[]),
        ]
        
        result = resolver.detect_circular_dependencies(plugins_no_cycle)
        self.assertIsNone(result)
        
        plugins_with_cycle = [
            PluginDependency(plugin_name="A", dependencies=["B"]),
            PluginDependency(plugin_name="B", dependencies=["A"]),
        ]
        
        result = resolver.detect_circular_dependencies(plugins_with_cycle)
        self.assertIsNotNone(result)

    def test_validate_dependencies_interface(self):
        """Test that validate_dependencies interface remains compatible."""
        resolver = DependencyResolver()
        
        plugins = [
            PluginDependency(plugin_name="A", dependencies=["MISSING"]),
        ]
        
        result = resolver.validate_dependencies(plugins)
        
        self.assertIn("A", result)
        self.assertIn("MISSING", result["A"])


class TestPluginManagerBackwardCompatibility(unittest.TestCase):
    """Test PluginManager backward compatibility."""

    def setUp(self):
        """Set up test fixtures."""
        PluginManager.reset_instance()

    def tearDown(self):
        """Clean up after tests."""
        PluginManager.reset_instance()

    def test_singleton_pattern(self):
        """Test that singleton pattern still works."""
        manager1 = PluginManager()
        manager2 = PluginManager()
        
        self.assertIs(manager1, manager2)

    def test_initialize_interface(self):
        """Test that initialize interface remains compatible."""
        manager = PluginManager()
        
        with patch.object(manager, '_process_plugins_config'):
            result = manager.initialize({
                "plugins": [
                    {
                        "type": "test_plugin",
                        "module_name": "test_module",
                        "function_name": "init",
                    }
                ]
            })
        
        self.assertTrue(result)

    def test_get_context_interface(self):
        """Test that get_context interface remains compatible."""
        manager = PluginManager()
        manager._is_initialized = True
        
        context = manager.get_context()
        
        self.assertIsInstance(context, EagerPluginContext)

    def test_is_initialized_interface(self):
        """Test that is_initialized interface remains compatible."""
        manager = PluginManager()
        
        self.assertFalse(manager.is_initialized())
        
        manager._is_initialized = True
        
        self.assertTrue(manager.is_initialized())

    def test_reset_instance_interface(self):
        """Test that reset_instance interface remains compatible."""
        manager = PluginManager()
        manager._is_initialized = True
        
        PluginManager.reset_instance()
        
        new_manager = PluginManager()
        
        self.assertIsNot(manager, new_manager)
        self.assertFalse(new_manager.is_initialized())


class TestPluginContextBackwardCompatibility(unittest.TestCase):
    """Test PluginContext backward compatibility."""

    def test_eager_context_get_interface(self):
        """Test that EagerPluginContext.get interface remains compatible."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {
            "test_plugin": {"manager": {"result": "success"}}
        }
        
        context = EagerPluginContext(mock_manager)
        result = context.get("test_plugin")
        
        self.assertEqual(result, {"result": "success"})

    def test_eager_context_get_all_interface(self):
        """Test that EagerPluginContext.get_all_plugins interface remains compatible."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {
            "plugin_a": {"manager": {"result": "a"}},
            "plugin_b": {"manager": {"result": "b"}},
        }
        
        context = EagerPluginContext(mock_manager)
        result = context.get_all_plugins()
        
        self.assertEqual(len(result), 2)

    def test_lazy_context_get_interface(self):
        """Test that LazyPluginContext.get interface remains compatible."""
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
        
        with patch(
            "silvaengine_base.boosters.plugin.initializer_utils.PluginInitializerUtils.invoke_plugin_init",
            return_value=(True, {"result": "success"}, None),
        ):
            result = context.get("test_plugin")
        
        self.assertEqual(result, {"result": "success"})

    def test_context_state_interface(self):
        """Test that context get_plugin_state interface remains compatible."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {
            "ready_plugin": {"manager": {"result": "success"}}
        }
        
        context = EagerPluginContext(mock_manager)
        
        self.assertEqual(context.get_plugin_state("ready_plugin"), PluginState.READY)
        self.assertEqual(context.get_plugin_state("unknown_plugin"), PluginState.INITIALIZING)


class TestPluginConfigurationBackwardCompatibility(unittest.TestCase):
    """Test PluginConfiguration backward compatibility."""

    def test_configuration_creation(self):
        """Test that PluginConfiguration can be created with standard fields."""
        config = PluginConfiguration(
            plugin_type="test_plugin",
            module_name="test_module",
            function_name="init",
            config={"key": "value"},
        )
        
        self.assertEqual(config.plugin_type, "test_plugin")
        self.assertEqual(config.module_name, "test_module")
        self.assertEqual(config.function_name, "init")
        self.assertEqual(config.config, {"key": "value"})

    def test_configuration_with_class_name(self):
        """Test that PluginConfiguration supports class_name field."""
        config = PluginConfiguration(
            plugin_type="test_plugin",
            module_name="test_module",
            function_name="init",
            class_name="TestClass",
            config={"key": "value"},
        )
        
        self.assertEqual(config.class_name, "TestClass")


class TestExceptionBackwardCompatibility(unittest.TestCase):
    """Test exception classes backward compatibility."""

    def test_plugin_not_found_error(self):
        """Test that PluginNotFoundError can be raised and caught."""
        with self.assertRaises(PluginNotFoundError):
            raise PluginNotFoundError("Plugin not found")

    def test_exception_inheritance(self):
        """Test that exceptions inherit from correct base classes."""
        self.assertTrue(issubclass(PluginNotFoundError, Exception))


class TestInterfaceCompatibility(unittest.TestCase):
    """Test interface compatibility across the module."""

    def test_dependency_resolver_has_required_methods(self):
        """Test that DependencyResolver has all required methods."""
        resolver = DependencyResolver()
        
        self.assertTrue(hasattr(resolver, 'resolve_dependencies'))
        self.assertTrue(hasattr(resolver, 'detect_circular_dependencies'))
        self.assertTrue(hasattr(resolver, 'validate_dependencies'))
        
        self.assertTrue(callable(resolver.resolve_dependencies))
        self.assertTrue(callable(resolver.detect_circular_dependencies))
        self.assertTrue(callable(resolver.validate_dependencies))

    def test_plugin_manager_has_required_methods(self):
        """Test that PluginManager has all required methods."""
        manager = PluginManager()
        
        required_methods = [
            'initialize',
            'get_context',
            'is_initialized',
            'reset_instance',
            'get_initialized_objects',
            'set_parallel_enabled',
            'set_max_workers',
        ]
        
        for method in required_methods:
            self.assertTrue(hasattr(manager, method), f"Missing method: {method}")
            self.assertTrue(callable(getattr(manager, method)), f"Not callable: {method}")

    def test_context_has_required_methods(self):
        """Test that contexts have all required methods."""
        mock_manager = MagicMock()
        mock_manager.get_initialized_objects.return_value = {}
        
        eager_context = EagerPluginContext(mock_manager)
        lazy_context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={},
        )
        
        eager_required_methods = ['get', 'get_all_plugins', 'get_plugin_state']
        lazy_required_methods = ['get', 'get_all_plugins', 'get_plugin_state', 'is_initialized']
        
        for method in eager_required_methods:
            self.assertTrue(hasattr(eager_context, method), f"EagerContext missing: {method}")
        
        for method in lazy_required_methods:
            self.assertTrue(hasattr(lazy_context, method), f"LazyContext missing: {method}")


class TestConfigurationCompatibility(unittest.TestCase):
    """Test configuration format compatibility."""

    def test_plugins_config_format(self):
        """Test that plugins configuration format is accepted."""
        manager = PluginManager()
        
        config = {
            "plugins": [
                {
                    "type": "plugin_a",
                    "module_name": "module_a",
                    "function_name": "init",
                    "config": {"key": "value"},
                },
                {
                    "type": "plugin_b",
                    "module_name": "module_b",
                    "function_name": "init",
                    "class_name": "PluginB",
                    "dependencies": ["plugin_a"],
                },
            ]
        }
        
        with patch.object(manager, '_process_plugins_config'):
            result = manager.initialize(config)
        
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
