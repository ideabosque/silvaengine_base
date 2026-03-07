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


mock_invoker_module = MagicMock()
mock_invoker_module.Invoker = MockInvoker
sys.modules['silvaengine_utility'] = mock_invoker_module

mock_dynamodb_module = MagicMock()
sys.modules['silvaengine_dynamodb_base'] = mock_dynamodb_module
sys.modules['silvaengine_dynamodb_base.models'] = MagicMock()

mock_constants_module = MagicMock()
sys.modules['silvaengine_constants'] = mock_constants_module
