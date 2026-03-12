#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for Resources class methods.

This module provides comprehensive tests for the Resources class methods,
including logger management, configuration handling, and plugin context retrieval.
"""

import logging
import os
import unittest
from unittest.mock import MagicMock, patch

from silvaengine_base import Resources


class TestResourcesLoggerMethods(unittest.TestCase):
    """Tests for Resources logger methods."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._logger = None

    def tearDown(self):
        """Clean up after tests."""
        Resources._logger = None

    def test_get_logger_creates_new_instance(self):
        """Test that _get_logger creates a new logger instance."""
        logger = Resources._get_logger()

        self.assertIsNotNone(logger)
        self.assertIsInstance(logger, logging.Logger)

    def test_get_logger_returns_same_instance(self):
        """Test that _get_logger returns the same cached instance."""
        logger1 = Resources._get_logger()
        logger2 = Resources._get_logger()

        self.assertIs(logger1, logger2)

    def test_get_logger_default_level(self):
        """Test that logger has default INFO level."""
        original_level = os.environ.pop("LOGGING_LEVEL", None)

        try:
            Resources._logger = None
            logger = Resources._get_logger()

            self.assertEqual(logger.level, logging.INFO)
        finally:
            if original_level:
                os.environ["LOGGING_LEVEL"] = original_level

    def test_get_logger_custom_level(self):
        """Test that logger respects LOGGING_LEVEL environment variable."""
        os.environ["LOGGING_LEVEL"] = "DEBUG"

        try:
            Resources._logger = None
            logger = Resources._get_logger()

            self.assertEqual(logger.level, logging.DEBUG)
        finally:
            os.environ.pop("LOGGING_LEVEL", None)
            Resources._logger = None

    def test_get_logger_invalid_level_defaults_to_info(self):
        """Test that invalid LOGGING_LEVEL defaults to INFO."""
        os.environ["LOGGING_LEVEL"] = "INVALID_LEVEL"

        try:
            Resources._logger = None
            logger = Resources._get_logger()

            self.assertEqual(logger.level, logging.INFO)
        finally:
            os.environ.pop("LOGGING_LEVEL", None)
            Resources._logger = None


class TestResourcesRegionMethods(unittest.TestCase):
    """Tests for Resources region methods."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._runtime_region = ""

    def tearDown(self):
        """Clean up after tests."""
        Resources._runtime_region = ""
        os.environ.pop("REGION_NAME", None)

    def test_get_runtime_region_from_env(self):
        """Test that region is read from environment variable."""
        os.environ["REGION_NAME"] = "us-west-2"

        region = Resources._get_runtime_region()

        self.assertEqual(region, "us-west-2")

    def test_get_runtime_region_lowercase(self):
        """Test that region is converted to lowercase."""
        os.environ["REGION_NAME"] = "US-EAST-1"

        region = Resources._get_runtime_region()

        self.assertEqual(region, "us-east-1")

    def test_get_runtime_region_empty_default(self):
        """Test that region returns empty string when not set."""
        os.environ.pop("REGION_NAME", None)

        region = Resources._get_runtime_region()

        self.assertEqual(region, "")

    def test_get_runtime_region_cached(self):
        """Test that region is cached after first retrieval."""
        os.environ["REGION_NAME"] = "eu-west-1"

        region1 = Resources._get_runtime_region()

        os.environ["REGION_NAME"] = "ap-southeast-1"

        region2 = Resources._get_runtime_region()

        self.assertEqual(region1, "eu-west-1")
        self.assertEqual(region2, "eu-west-1")


class TestResourcesConfigIndexMethods(unittest.TestCase):
    """Tests for Resources config index methods."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._runtime_config_index = ""

    def tearDown(self):
        """Clean up after tests."""
        Resources._runtime_config_index = ""
        os.environ.pop("CONFIG_INDEX", None)

    def test_get_runtime_config_index_from_env(self):
        """Test that config index is read from environment variable."""
        os.environ["CONFIG_INDEX"] = "production-config"

        index = Resources._get_runtime_config_index()

        self.assertEqual(index, "production-config")

    def test_get_runtime_config_index_lowercase(self):
        """Test that config index is converted to lowercase."""
        os.environ["CONFIG_INDEX"] = "PRODUCTION-CONFIG"

        index = Resources._get_runtime_config_index()

        self.assertEqual(index, "production-config")

    def test_get_runtime_config_index_empty_default(self):
        """Test that config index returns empty string when not set."""
        os.environ.pop("CONFIG_INDEX", None)

        index = Resources._get_runtime_config_index()

        self.assertEqual(index, "")

    def test_get_runtime_config_index_cached(self):
        """Test that config index is cached after first retrieval."""
        os.environ["CONFIG_INDEX"] = "config-v1"

        index1 = Resources._get_runtime_config_index()

        os.environ["CONFIG_INDEX"] = "config-v2"

        index2 = Resources._get_runtime_config_index()

        self.assertEqual(index1, "config-v1")
        self.assertEqual(index2, "config-v1")


class TestResourcesPluginInitializerMethods(unittest.TestCase):
    """Tests for Resources plugin initializer methods."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._plugin_initializer = None

    def tearDown(self):
        """Clean up after tests."""
        Resources._plugin_initializer = None

    def test_get_plugin_initializer_creates_instance(self):
        """Test that _get_plugin_initializer creates a new instance."""
        from silvaengine_base.boosters import PluginInitializer

        initializer = Resources._get_plugin_initializer()

        self.assertIsNotNone(initializer)
        self.assertIsInstance(initializer, PluginInitializer)

    def test_get_plugin_initializer_returns_same_instance(self):
        """Test that _get_plugin_initializer returns the same cached instance."""
        initializer1 = Resources._get_plugin_initializer()
        initializer2 = Resources._get_plugin_initializer()

        self.assertIs(initializer1, initializer2)


class TestResourcesPluginContextMethods(unittest.TestCase):
    """Tests for Resources plugin context methods."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._plugin_initializer = None
        Resources._logger = None

    def tearDown(self):
        """Clean up after tests."""
        Resources._plugin_initializer = None
        Resources._logger = None

    def test_get_plugin_context_returns_none_when_not_initialized(self):
        """Test that _get_plugin_context returns None when not initialized."""
        context = Resources._get_plugin_context()

        self.assertIsNone(context)

    def test_get_plugin_context_safe_returns_none_on_error(self):
        """Test that _get_plugin_context_safe returns None on error."""
        context = Resources._get_plugin_context_safe()

        self.assertIsNone(context)

    def test_get_plugin_context_safe_logs_warning_on_error(self):
        """Test that _get_plugin_context_safe logs warning on error."""
        mock_logger = MagicMock()
        Resources._logger = mock_logger

        Resources._get_plugin_context_safe()

        mock_logger.warning.assert_called()


class TestResourcesRuntimeConfigMethods(unittest.TestCase):
    """Tests for Resources runtime config methods."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._runtime_config = {}
        Resources._runtime_config_index = ""

    def tearDown(self):
        """Clean up after tests."""
        Resources._runtime_config = {}
        Resources._runtime_config_index = ""
        os.environ.pop("CONFIG_INDEX", None)

    def test_get_runtime_config_returns_empty_dict_when_not_set(self):
        """Test that _get_runtime_config returns empty dict when not configured."""
        config = Resources._get_runtime_config()

        self.assertEqual(config, {})

    def test_get_runtime_config_caches_result(self):
        """Test that _get_runtime_config caches the result."""
        config1 = Resources._get_runtime_config()
        config2 = Resources._get_runtime_config()

        self.assertIs(config1, config2)


class TestResourcesInit(unittest.TestCase):
    """Tests for Resources __init__ method."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._logger = None
        Resources._plugin_initializer = None

    def tearDown(self):
        """Clean up after tests."""
        Resources._logger = None
        Resources._plugin_initializer = None

    def test_init_with_logger(self):
        """Test that __init__ sets the logger."""
        mock_logger = MagicMock()

        Resources(logger=mock_logger)

        self.assertIs(Resources._logger, mock_logger)

    def test_init_without_logger(self):
        """Test that __init__ works without logger."""
        Resources()

        self.assertIsNone(Resources._logger)


class TestResourcesPreInitialize(unittest.TestCase):
    """Tests for Resources pre_initialize method."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._plugin_initializer = None
        Resources._logger = None
        Resources._runtime_config = {}
        Resources._runtime_config_index = ""

    def tearDown(self):
        """Clean up after tests."""
        Resources._plugin_initializer = None
        Resources._logger = None
        Resources._runtime_config = {}
        Resources._runtime_config_index = ""
        os.environ.pop("CONFIG_INDEX", None)

    def test_pre_initialize_calls_plugin_initializer(self):
        """Test that pre_initialize calls plugin initializer."""
        mock_logger = MagicMock()
        Resources._logger = mock_logger

        Resources.pre_initialize()

        self.assertIsNotNone(Resources._plugin_initializer)


class TestResourcesGetHandler(unittest.TestCase):
    """Tests for Resources get_handler method."""

    def setUp(self):
        """Set up test fixtures."""
        Resources._plugin_initializer = None
        Resources._logger = None
        Resources._runtime_config = {}
        Resources._runtime_config_index = ""
        Resources._runtime_region = ""

    def tearDown(self):
        """Clean up after tests."""
        Resources._plugin_initializer = None
        Resources._logger = None
        Resources._runtime_config = {}
        Resources._runtime_config_index = ""
        Resources._runtime_region = ""
        os.environ.pop("CONFIG_INDEX", None)
        os.environ.pop("REGION_NAME", None)

    def test_get_handler_raises_error_without_config_index(self):
        """Test that get_handler raises RuntimeError without CONFIG_INDEX."""
        os.environ.pop("CONFIG_INDEX", None)
        os.environ["REGION_NAME"] = "us-east-1"

        with self.assertRaises(RuntimeError) as context:
            Resources.get_handler()

        self.assertIn("CONFIG_INDEX", str(context.exception))

    def test_get_handler_raises_error_without_region(self):
        """Test that get_handler raises RuntimeError without REGION_NAME."""
        os.environ["CONFIG_INDEX"] = "test-config"
        os.environ.pop("REGION_NAME", None)

        with self.assertRaises(RuntimeError) as context:
            Resources.get_handler()

        self.assertIn("REGION_NAME", str(context.exception))

    def test_get_handler_returns_callable(self):
        """Test that get_handler returns a callable."""
        os.environ["CONFIG_INDEX"] = "test-config"
        os.environ["REGION_NAME"] = "us-east-1"

        handler = Resources.get_handler()

        self.assertTrue(callable(handler))


if __name__ == "__main__":
    unittest.main()
