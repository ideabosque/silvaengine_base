#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pytest configuration for silvaengine_base tests.

This module provides mock implementations for external dependencies
that are not available in the test environment.

IMPORTANT: This must be the first thing loaded by pytest, so we mock
the silvaengine_utility module before any other imports happen.

@since 2.0.0
"""

import sys
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


class MockModule:
    """Mock module that supports both attribute access and from imports."""
    
    Invoker = MockInvoker
    
    @staticmethod
    def HttpResponse():
        """Mock HttpResponse."""
        return MagicMock()


# Setup mocks BEFORE any imports happen
mock_invoker_module = MockModule()
sys.modules['silvaengine_utility'] = mock_invoker_module

mock_dynamodb_module = MagicMock()
mock_dynamodb_models = MagicMock()
mock_dynamodb_models.ConfigModel = MagicMock()
mock_dynamodb_models.ConfigModel.find = MagicMock(return_value={})
sys.modules['silvaengine_dynamodb_base'] = mock_dynamodb_module
sys.modules['silvaengine_dynamodb_base.models'] = mock_dynamodb_models

mock_constants_module = MagicMock()
mock_constants_module.HttpStatus = MagicMock()
mock_constants_module.HttpStatus.BAD_REQUEST = MagicMock(value=400)
mock_constants_module.HttpStatus.FORBIDDEN = MagicMock(value=403)
mock_constants_module.HttpStatus.INTERNAL_SERVER_ERROR = MagicMock(value=500)
sys.modules['silvaengine_constants'] = mock_constants_module


def pytest_configure(config):
    """Configure pytest with mocks before any tests are collected."""
    pass
