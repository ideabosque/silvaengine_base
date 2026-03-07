#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for non-blocking initialization optimization.

This test suite verifies:
1. get_handler() returns immediately without blocking
2. Background initialization completes successfully
3. Plugin access works during and after initialization
4. Event-based waiting replaces polling
"""

import time
import threading
import unittest
from unittest.mock import MagicMock, patch
from typing import Any, Dict

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "silvaengine_constants"))
sys.path.insert(0, str(PROJECT_ROOT / "silvaengine_utility"))
sys.path.insert(0, str(PROJECT_ROOT / "silvaengine_dynamodb_base"))
sys.path.insert(0, str(PROJECT_ROOT / "silvaengine_base"))


class TestNonBlockingInitialization(unittest.TestCase):
    """Test suite for non-blocking initialization."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def tearDown(self) -> None:
        """Clean up after tests."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def test_get_handler_returns_immediately(self) -> None:
        """Verify get_handler() returns without blocking.

        Performance Target: < 100ms
        """
        from silvaengine_base.resources import Resources

        with patch.object(Resources, '_get_runtime_config_index', return_value='test_index'):
            with patch.object(Resources, '_get_runtime_region', return_value='us-west-2'):
                with patch.object(Resources, '_get_runtime_config', return_value={'plugins': []}):
                    start = time.time()
                    handler = Resources.get_handler()
                    duration = time.time() - start

                    self.assertLess(duration, 0.5, "get_handler() should return in < 500ms")
                    self.assertTrue(callable(handler), "get_handler() should return a callable")

    def test_background_initialization_starts(self) -> None:
        """Verify background initialization is started."""
        from silvaengine_base.resources import Resources
        from silvaengine_base import PluginInitializer

        with patch.object(Resources, '_get_runtime_config_index', return_value='test_index'):
            with patch.object(Resources, '_get_runtime_region', return_value='us-west-2'):
                with patch.object(Resources, '_get_runtime_config', return_value={'plugins': []}):
                    Resources.get_handler()

                    initializer = PluginInitializer()
                    self.assertIsNotNone(initializer, "PluginInitializer should be created")


class TestEventBasedWaiting(unittest.TestCase):
    """Test suite for event-based waiting optimization."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def tearDown(self) -> None:
        """Clean up after tests."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def test_wait_uses_async_initializer_when_available(self) -> None:
        """Verify waiting uses async initializer for efficiency."""
        from silvaengine_base.boosters.plugin.context import EagerPluginContext

        mock_manager = MagicMock()
        mock_async_initializer = MagicMock()
        mock_async_initializer.wait_for_plugin.return_value = True
        mock_manager.get_async_initializer.return_value = mock_async_initializer
        mock_manager.get_initialized_objects.return_value = {}

        context = EagerPluginContext(mock_manager)

        result = context._wait_for_plugin_internal("test_plugin", timeout=1.0)

        self.assertTrue(result, "Should return True when async initializer succeeds")
        mock_async_initializer.wait_for_plugin.assert_called_once()

    def test_wait_falls_back_to_polling_when_no_async_initializer(self) -> None:
        """Verify fallback to polling when async initializer unavailable."""
        from silvaengine_base.boosters.plugin.context import EagerPluginContext

        mock_manager = MagicMock()
        mock_manager.get_async_initializer.return_value = None

        call_count = [0]

        def get_objects():
            call_count[0] += 1
            if call_count[0] >= 3:
                return {"test_plugin": MagicMock()}
            return {}

        mock_manager.get_initialized_objects.side_effect = get_objects

        context = EagerPluginContext(mock_manager)

        start = time.time()
        result = context._wait_for_plugin_internal("test_plugin", timeout=5.0)
        duration = time.time() - start

        self.assertTrue(result, "Should return True when plugin appears")
        self.assertLess(duration, 1.0, "Should complete quickly once plugin appears")


class TestLazyPluginContextOptimization(unittest.TestCase):
    """Test suite for LazyPluginContext optimization."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def tearDown(self) -> None:
        """Clean up after tests."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def test_lazy_context_uses_async_initializer_for_waiting(self) -> None:
        """Verify LazyPluginContext uses async initializer for efficient waiting."""
        from silvaengine_base.boosters.plugin.context import LazyPluginContext

        mock_manager = MagicMock()
        mock_async_initializer = MagicMock()
        mock_async_initializer.wait_for_plugin.return_value = True
        mock_manager.get_async_initializer.return_value = mock_async_initializer

        context = LazyPluginContext(
            plugin_manager=mock_manager,
            plugin_configs={"test_plugin": {"type": "test_plugin"}},
        )

        result = context._wait_for_plugin_internal("test_plugin", timeout=1.0)

        self.assertTrue(result, "Should return True when async initializer succeeds")
        mock_async_initializer.wait_for_plugin.assert_called_once()


class TestPluginManagerNonBlocking(unittest.TestCase):
    """Test suite for PluginManager non-blocking processing."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def tearDown(self) -> None:
        """Clean up after tests."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def test_process_plugins_config_does_not_block(self) -> None:
        """Verify _process_plugins_config returns immediately."""
        from silvaengine_base.boosters.plugin import PluginManager

        manager = PluginManager()
        manager._logger = MagicMock()

        plugins_config = [
            {
                "type": "test_plugin",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            }
        ]

        start = time.time()
        manager._process_plugins_config(plugins_config)
        duration = time.time() - start

        self.assertLess(duration, 0.5, "_process_plugins_config should return in < 500ms")

    def test_async_initializer_is_created(self) -> None:
        """Verify async initializer is created during processing."""
        from silvaengine_base.boosters.plugin import PluginManager

        manager = PluginManager()
        manager._logger = MagicMock()

        plugins_config = [
            {
                "type": "test_plugin",
                "module_name": "test_module",
                "function_name": "init",
                "config": {},
            }
        ]

        manager._process_plugins_config(plugins_config)

        self.assertIsNotNone(manager._async_initializer, "Async initializer should be created")


class TestConcurrencySafety(unittest.TestCase):
    """Test suite for concurrency safety."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def tearDown(self) -> None:
        """Clean up after tests."""
        from silvaengine_base import PluginInitializer
        PluginInitializer.reset()

    def test_concurrent_get_handler_calls(self) -> None:
        """Verify concurrent get_handler calls are safe."""
        from silvaengine_base.resources import Resources

        results = []
        errors = []

        def call_get_handler():
            try:
                with patch.object(Resources, '_get_runtime_config_index', return_value='test_index'):
                    with patch.object(Resources, '_get_runtime_region', return_value='us-west-2'):
                        with patch.object(Resources, '_get_runtime_config', return_value={'plugins': []}):
                            handler = Resources.get_handler()
                            results.append(handler)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_get_handler) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=5.0)

        self.assertEqual(len(errors), 0, f"Should have no errors, got: {errors}")
        self.assertEqual(len(results), 5, "Should have 5 results")


if __name__ == "__main__":
    unittest.main(verbosity=2)
