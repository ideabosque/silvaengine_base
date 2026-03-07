#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unified Plugin Initialization Utilities.

This module provides unified plugin initialization logic to eliminate code
duplication across multiple modules (__init__.py, async_initializer.py,
context.py, parallel_scheduler.py).

@since 2.0.0
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

from silvaengine_utility import Invoker

logger = logging.getLogger(__name__)


class PluginInitializationError(Exception):
    """Exception raised when plugin initialization fails."""
    pass


class PluginInitializerUtils:
    """Unified utilities for plugin initialization.
    
    This class provides static methods for common plugin initialization
    operations, eliminating code duplication across the codebase.
    
    Performance Characteristics:
        - invoke_plugin_init: O(1) for resolution + O(n) for execution
        - validate_plugin_config: O(1)
        - extract_plugin_metadata: O(1)
    
    Thread Safety:
        All methods are stateless and thread-safe.
    """
    
    @staticmethod
    def invoke_plugin_init(
        module_name: str,
        function_name: str,
        plugin_config: Dict[str, Any],
        class_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[bool, Any, Optional[str]]:
        """Invoke plugin initialization function.
        
        This unified method eliminates code duplication across 4 locations:
        - PluginManager._do_initialize_plugin()
        - AsyncPluginInitializer._do_initialize()
        - PluginContext._do_initialize_plugin()
        - ParallelInitializationScheduler._do_initialize()
        
        Args:
            module_name: Module containing the plugin.
            function_name: Initialization function name.
            plugin_config: Plugin configuration dictionary.
            class_name: Optional class name for class-based plugins.
            timeout: Optional timeout for initialization (not enforced here).
            
        Returns:
            Tuple of (success, result, error_message).
            
        Performance:
            - Time: O(1) for resolution + O(n) for plugin execution
            - Space: O(1) for local variables
            
        Thread Safety:
            Stateless operation, thread-safe.
        """
        try:
            proxied_callable = Invoker.resolve_proxied_callable(
                module_name=module_name,
                function_name=function_name,
                class_name=class_name,
                constructor_parameters=None,
            )
            
            result = proxied_callable(plugin_config)
            return (True, result, None)
            
        except Exception as e:
            error_msg = f"Plugin initialization failed: {module_name}.{function_name}"
            if class_name:
                error_msg += f".{class_name}"
            error_msg += f" - {str(e)}"
            
            logger.error(error_msg, exc_info=True)
            return (False, None, error_msg)
    
    @staticmethod
    def validate_plugin_config(
        plugin_config: Dict[str, Any],
        required_fields: Optional[list] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate plugin configuration.
        
        Args:
            plugin_config: Plugin configuration dictionary.
            required_fields: List of required field names.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not isinstance(plugin_config, dict):
            return (False, "Plugin config must be a dictionary")
        
        if required_fields:
            missing = [f for f in required_fields if f not in plugin_config]
            if missing:
                return (False, f"Missing required fields: {missing}")
        
        return (True, None)
    
    @staticmethod
    def extract_plugin_metadata(
        plugin_item: Dict[str, Any],
        index: int,
    ) -> Tuple[str, str, Optional[str], Dict[str, Any]]:
        """Extract plugin metadata from configuration item.
        
        Args:
            plugin_item: Plugin configuration item.
            index: Plugin index for error messages.
            
        Returns:
            Tuple of (plugin_type, module_name, function_name, config).
            
        Raises:
            PluginInitializationError: If required fields are missing.
        """
        plugin_type = plugin_item.get("type")
        module_name = plugin_item.get("module_name")
        function_name = plugin_item.get("function_name")
        class_name = plugin_item.get("class_name")
        config = plugin_item.get("config", {})
        
        if not plugin_type:
            raise PluginInitializationError(
                f"Plugin at index {index} missing 'type' field"
            )
        
        if not module_name:
            raise PluginInitializationError(
                f"Plugin '{plugin_type}' missing 'module_name' field"
            )
        
        if not function_name:
            raise PluginInitializationError(
                f"Plugin '{plugin_type}' missing 'function_name' field"
            )
        
        return (plugin_type, module_name, function_name, class_name, config)
    
    @staticmethod
    def wait_with_timeout(
        condition_check: callable,
        timeout: float,
        poll_interval: float = 0.1,
    ) -> bool:
        """Wait for condition with timeout using polling.
        
        Note: This is a fallback for cases where Event-based waiting
        is not available. Prefer threading.Event.wait() when possible.
        
        Args:
            condition_check: Callable that returns True when condition is met.
            timeout: Maximum time to wait in seconds.
            poll_interval: Time between checks in seconds.
            
        Returns:
            True if condition was met, False if timeout.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition_check():
                return True
            time.sleep(poll_interval)
        return False


__all__ = [
    "PluginInitializationError",
    "PluginInitializerUtils",
]
