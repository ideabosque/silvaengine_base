#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Integration tests for async plugin initialization.

This module provides comprehensive integration tests for:
- Resources async initialization
- Pre-initialization mode
- Callback mechanism
- Backward compatibility with sync mode
"""

import logging
import threading
import time
import unittest
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, patch

from silvaengine_base import PluginManager, Resources
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


class TestIntegration(unittest.TestCase):
    """Integration tests for async plugin initialization."""

    def setUp(self):
        """Set up test fixtures."""
        PluginManager.reset_instance()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        """Clean up after tests."""
        PluginManager.reset_instance()

    def test_resources_async_initialization(self):
        """Test Resources async initialization."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
            plugin_init_timeout=5.0,
            global_init_timeout=10.0,
        )
        
        setting = {
            "plugins": [
                {
                    "type": "plugin_a",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {"key": "value"},
                },
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            resources.pre_initialize(setting)
            
            self.assertTrue(resources.is_pre_initialized())
            
            status = resources.get_initialization_status()
            
            self.assertIn("status", status)
            self.assertIn("summary", status)
            self.assertIn("is_pre_initialized", status)

    def test_pre_initialization(self):
        """Test pre-initialization mode."""
        callback_results = []
        
        def callback(status):
            callback_results.append(status)
        
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
            pre_initialization_callback=callback,
        )
        
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
            
            resources.pre_initialize(setting)
            
            time.sleep(0.5)
            
            self.assertTrue(resources.is_pre_initialized())

    def test_callback_mechanism(self):
        """Test initialization callback."""
        callback_results = []
        
        def init_callback(status):
            callback_results.append(status)
        
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
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
            
            resources.pre_initialize(setting)
            
            resources.set_initialization_callback(init_callback)
            
            time.sleep(0.5)

    def test_backward_compatibility(self):
        """Test backward compatibility with sync mode."""
        mock_logger = Mock()
        
        resources = Resources(logger=mock_logger)
        
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
            
            resources.pre_initialize(setting)
            
            plugin_context = PluginInitializer.get_plugin_context()
            
            self.assertIsNotNone(plugin_context)

    def test_multiple_plugin_initialization(self):
        """Test multiple plugins initialization."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
            max_workers=4,
        )
        
        setting = {
            "plugins": [
                {
                    "type": f"plugin_{i}",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {"id": i},
                }
                for i in range(5)
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            resources.pre_initialize(setting)
            
            results = resources.wait_for_initialization(timeout=10.0)
            
            self.assertEqual(len(results), 5)

    def test_plugin_failure_handling(self):
        """Test plugin failure handling."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
        setting = {
            "plugins": [
                {
                    "type": "failing_plugin",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                },
            ]
        }
        
        def failing_init(config):
            raise ValueError("Intentional test failure")
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = failing_init
            
            resources.pre_initialize(setting)
            
            results = resources.wait_for_initialization(timeout=10.0)
            
            self.assertIn("failing_plugin", results)
            self.assertFalse(results["failing_plugin"])

    def test_initialization_status_tracking(self):
        """Test initialization status tracking."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
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
            
            resources.pre_initialize(setting)
            
            status = resources.get_initialization_status()
            
            self.assertIn("summary", status)
            
            summary = status["summary"]
            self.assertIn("total", summary)
            self.assertIn("ready", summary)
            self.assertIn("failed", summary)

    def test_lazy_loading_integration(self):
        """Test lazy loading integration."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
            lazy_loading_enabled=True,
        )
        
        setting = {
            "plugins": [
                {
                    "type": "lazy_plugin",
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
            
            resources.pre_initialize(setting)
            
            plugin_manager = resources.get_plugin_manager()
            
            self.assertIsNotNone(plugin_manager)

    def test_circuit_breaker_integration(self):
        """Test circuit breaker integration."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
            circuit_breaker_enabled=True,
        )
        
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
            
            resources.pre_initialize(setting)
            
            results = resources.wait_for_initialization(timeout=10.0)
            
            self.assertTrue(results.get("plugin_a", False))

    def test_concurrent_access(self):
        """Test concurrent access to plugin manager."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
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
        
        access_results = []
        
        def access_status():
            status = resources.get_initialization_status()
            access_results.append(status)
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            resources.pre_initialize(setting)
            
            threads = [
                threading.Thread(target=access_status)
                for _ in range(5)
            ]
            
            for thread in threads:
                thread.start()
            
            for thread in threads:
                thread.join()
            
            self.assertEqual(len(access_results), 5)

    def test_reset_and_reinitialize(self):
        """Test reset and reinitialize."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
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
            
            resources.pre_initialize(setting)
            
            self.assertTrue(resources.is_pre_initialized())
            
            resources.reset_plugin_manager()
            
            self.assertFalse(resources.is_pre_initialized())
            
            resources.pre_initialize(setting)
            
            self.assertTrue(resources.is_pre_initialized())

    def test_timeout_handling(self):
        """Test timeout handling."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
            plugin_init_timeout=0.1,
        )
        
        setting = {
            "plugins": [
                {
                    "type": "slow_plugin",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                },
            ]
        }
        
        def slow_init(config):
            time.sleep(5.0)
            return {"result": "success"}
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = slow_init
            
            resources.pre_initialize(setting)
            
            results = resources.wait_for_initialization(timeout=1.0)

    def test_empty_plugins_config(self):
        """Test empty plugins configuration."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
        setting = {
            "plugins": []
        }
        
        resources.pre_initialize(setting)
        
        status = resources.get_initialization_status()
        
        self.assertEqual(status["summary"]["total"], 0)

    def test_disabled_plugin(self):
        """Test disabled plugin handling."""
        mock_logger = Mock()
        
        resources = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
        setting = {
            "plugins": [
                {
                    "type": "disabled_plugin",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                    "enabled": False,
                },
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            resources.pre_initialize(setting)

    def test_async_initialization_flag(self):
        """Test async initialization flag."""
        mock_logger = Mock()
        
        resources_async = Resources(
            logger=mock_logger,
            async_initialization=True,
        )
        
        self.assertTrue(resources_async.is_async_initialization_enabled())
        
        resources_sync = Resources(
            logger=mock_logger,
            async_initialization=False,
        )
        
        self.assertFalse(resources_sync.is_async_initialization_enabled())


class TestPluginManagerIntegration(unittest.TestCase):
    """Integration tests for PluginManager."""

    def setUp(self):
        """Set up test fixtures."""
        PluginManager.reset_instance()
        self.logger = logging.getLogger(__name__)

    def tearDown(self):
        """Clean up after tests."""
        PluginManager.reset_instance()

    def test_singleton_pattern(self):
        """Test singleton pattern."""
        from silvaengine_base import PluginManager
        
        manager1 = PluginManager(logger=self.logger)
        manager2 = PluginManager(logger=self.logger)
        
        self.assertIs(manager1, manager2)

    def test_configuration_validation(self):
        """Test configuration validation."""
        manager = PluginManager(logger=self.logger)
        
        valid_config = [
            {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        ]
        
        result = manager.validate_configuration(valid_config)
        
        self.assertTrue(result.is_valid)

    def test_plugin_status_retrieval(self):
        """Test plugin status retrieval."""
        manager = PluginManager(logger=self.logger)
        
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
            
            manager.initialize_background(setting)
            
            status = manager.get_plugin_status("plugin_a")
            
            self.assertIn("plugin_type", status)

    def test_all_plugin_status(self):
        """Test getting all plugin status."""
        manager = PluginManager(logger=self.logger)
        
        setting = {
            "plugins": [
                {
                    "type": f"plugin_{i}",
                    "module_name": "test_module",
                    "function_name": "init",
                    "config": {},
                }
                for i in range(3)
            ]
        }
        
        with patch(
            "silvaengine_utility.Invoker.resolve_proxied_callable"
        ) as mock_resolve:
            mock_resolve.return_value = lambda config: {"result": "success"}
            
            manager.initialize_background(setting)
            
            all_status = manager.get_all_plugin_status()
            
            self.assertIsInstance(all_status, dict)


class TestLazyPluginContextIntegration(unittest.TestCase):
    """Integration tests for LazyPluginContext."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger(__name__)
        self.mock_plugin_manager = Mock()

    def test_full_initialization_lifecycle(self):
        """Test full initialization lifecycle."""
        plugin_configs = {
            "plugin_a": {
                "type": "plugin_a",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            },
        }
        
        lazy_context = LazyPluginContext(
            plugin_manager=self.mock_plugin_manager,
            plugin_configs=plugin_configs,
            logger=self.logger,
        )
        
        try:
            with patch(
                "silvaengine_utility.Invoker.resolve_proxied_callable"
            ) as mock_resolve:
                mock_resolve.return_value = lambda config: {"result": "success"}
                
                future = lazy_context.get_or_schedule("plugin_a")
                
                self.assertIsInstance(future, PluginFuture)
                
                time.sleep(0.5)
                
                stats = lazy_context.get_initialization_stats()
                
                self.assertEqual(stats["initialized"], 1)
        finally:
            lazy_context.shutdown(wait=False)

    def test_multiple_plugin_preload(self):
        """Test preloading multiple plugins."""
        plugin_configs = {
            f"plugin_{i}": {
                "type": f"plugin_{i}",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            }
            for i in range(5)
        }
        
        lazy_context = LazyPluginContext(
            plugin_manager=self.mock_plugin_manager,
            plugin_configs=plugin_configs,
            logger=self.logger,
        )
        
        try:
            with patch(
                "silvaengine_utility.Invoker.resolve_proxied_callable"
            ) as mock_resolve:
                mock_resolve.return_value = lambda config: {"result": "success"}
                
                lazy_context.preload_background()
                
                time.sleep(1.0)
                
                stats = lazy_context.get_initialization_stats()
                
                self.assertEqual(stats["initialized"], 5)
        finally:
            lazy_context.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
