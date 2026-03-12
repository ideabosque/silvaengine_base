#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Resources Handler for silvaengine_base.

This module provides the plugin management functionality that was previously
in the Resources class. All plugin-related operations are now centralized here.
"""

import logging
import os
import threading
from typing import Any, Callable, Dict, Optional, Set

from .plugin import PluginContext, PluginManager
from .plugin.config_manager import get_config_manager
from .plugin.injector import PluginContextInjector

SENSITIVE_FIELD_PATTERNS: Set[str] = {
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "auth",
    "api_key",
    "apikey",
    "private",
    "access_key",
    "secret_key",
}


def sanitize_config(config: Dict[str, Any], mask: str = "***") -> Dict[str, Any]:
    """Sanitize configuration by masking sensitive fields.

    Args:
        config: Configuration dictionary to sanitize.
        mask: Mask string to replace sensitive values.

    Returns:
        Sanitized configuration dictionary.
    """
    if not isinstance(config, dict):
        return config

    sanitized = {}
    for key, value in config.items():
        key_lower = str(key).lower().replace("-", "_")
        is_sensitive = any(
            pattern in key_lower for pattern in SENSITIVE_FIELD_PATTERNS
        )

        if is_sensitive:
            sanitized[key] = mask
        elif isinstance(value, dict):
            sanitized[key] = sanitize_config(value, mask)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_config(item, mask) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


class PluginInitializer:
    """Handler for plugin-related resources operations.

    This class encapsulates all plugin initialization and management logic,
    keeping the Resources class clean and focused on event handling.
    """

    _instance: Optional["PluginInitializer"] = None
    _lock = threading.Lock()
    _config: Dict[str, Any] = {}
    _plugin_manager: Optional[PluginManager] = None
    _plugin_context: Optional[PluginContext] = None
    _initialization_callback: Optional[Callable[[Dict[str, bool]], None]] = None
    _logger: Optional[logging.Logger] = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    cls._instance = instance
        return cls._instance
    
    @classmethod
    def initialize(cls, logger: Optional[logging.Logger] = None) -> None:
        """Initialize the handler with logger.
        
        Args:
            logger: Logger instance.
        """
        if logger is not None:
            cls._logger = logger
        elif cls._logger is None:
            cls._logger = logging.getLogger(__name__)
    
    @classmethod
    def _apply_config_to_manager(cls, setting: Dict[str, Any]) -> None:
        """Apply configuration to plugin manager.
        
        This unified method eliminates code duplication between setup_plugins
        and pre_initialize methods.
        
        Args:
            setting: Plugin configuration dictionary.
        """
        if cls._plugin_manager is None:
            cls._plugin_manager = PluginManager(logger=cls.get_logger())
        
        config_manager = get_config_manager(setting.get("plugin_settings", {}))
        config_manager.apply_to_plugin_manager(cls._plugin_manager)
    
    @classmethod
    def get_logger(cls) -> logging.Logger:
        """Get the logger instance.
        
        Returns:
            Logger instance.
        """
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger
    
    @classmethod
    def setup_plugins(cls, config: Dict[str, Any]) -> None:
        """Setup plugins with configuration.
        
        Args:
            config: Configuration dictionary.
        """
        cls._config = config
        cls._logger.info(f"Setting: {sanitize_config(config)}")
        
        cls._apply_config_to_manager(config)
        
        config_manager = get_config_manager(config.get("plugin_settings", {}))
        
        if config_manager.get_async_initialization():
            cls._initialize_plugins_async()
        else:
            if cls._plugin_manager.initialize(setting=config):
                cls._plugin_context = cls._plugin_manager.get_context()
    
    @classmethod
    def _initialize_plugins_async(cls) -> None:
        """Initialize plugins asynchronously for non-blocking cold start."""
        try:
            cls._plugin_manager.initialize_background(
                setting=cls._config,
                callback=cls._on_initialization_complete,
            )
            cls._plugin_context = cls._plugin_manager.get_context()
            cls._logger.info(
                "Plugin initialization started asynchronously (non-blocking)"
            )
        except Exception as e:
            cls._logger.error(f"Failed to start async initialization: {e}")
            # Fallback to synchronous initialization
            if cls._plugin_manager.initialize(setting=cls._config):
                cls._plugin_context = cls._plugin_manager.get_context()
    
    @classmethod
    def _on_initialization_complete(cls, status: Dict[str, bool]) -> None:
        """Handle initialization completion callback.
        
        Args:
            status: Dictionary mapping plugin_type to success status.
        """
        cls._logger.info("Plugin initialization completed")
        for plugin_type, success in status.items():
            status_str = "SUCCESS" if success else "FAILED"
            cls._logger.info(f"  {plugin_type}: {status_str}")
        
        # Call user-provided callback if set
        if cls._initialization_callback is not None:
            try:
                cls._initialization_callback(status)
            except Exception as e:
                cls._logger.error(f"Error in initialization callback: {e}")
    
    @classmethod
    def pre_initialize(cls, setting: Dict[str, Any]) -> None:
        """Pre-initialize plugins for Lambda cold start optimization.
        
        Args:
            setting: Plugin configuration dictionary.
        """
        cls._config = setting
        cls._logger.info(f"Pre-initializing plugins: {sanitize_config(setting)}")
        
        cls._apply_config_to_manager(setting)
        
        cls._plugin_manager.initialize_background(
            setting=setting,
            callback=cls._on_initialization_complete,
        )
        
        cls._plugin_context = cls._plugin_manager.get_context()
    
    @classmethod
    def set_initialization_callback(
        cls, callback: Optional[Callable[[Dict[str, bool]], None]]
    ) -> None:
        """Set callback for initialization completion.
        
        Args:
            callback: Function to call when initialization completes.
        """
        cls._initialization_callback = callback
    
    @classmethod
    def get_initialization_status(cls) -> Dict[str, Any]:
        """Get current initialization status.
        
        Returns:
            Dictionary containing initialization status information.
        """
        if cls._plugin_manager is None:
            return {"initialized": False, "status": "not_started"}
        return cls._plugin_manager.get_initialization_status()
    
    @classmethod
    def wait_for_initialization(cls, timeout: float = 120.0) -> Dict[str, bool]:
        """Wait for all plugins to complete initialization.
        
        Args:
            timeout: Maximum time to wait in seconds.
            
        Returns:
            Dictionary mapping plugin types to success status.
        """
        if cls._plugin_manager is None:
            return {}
        return cls._plugin_manager.wait_for_initialization(timeout=timeout)
    
    @classmethod
    def get_plugin_manager(cls) -> Optional[PluginManager]:
        """Get the plugin manager instance.
        
        Returns:
            PluginManager instance or None if not initialized.
        """
        return cls._plugin_manager
    
    @classmethod
    def get_plugin_context(cls) -> Optional[PluginContext]:
        """Get the plugin context.
        
        Returns:
            PluginContext instance or None if not initialized.
        """
        return cls._plugin_context
    
    @classmethod
    def configure(
        cls,
        async_initialization: bool = True,
        lazy_loading_enabled: bool = False,
        parallel_enabled: bool = True,
        plugin_init_timeout: float = 30.0,
        global_init_timeout: float = 120.0,
        circuit_breaker_enabled: bool = True,
        max_workers: Optional[int] = None,
    ) -> None:
        """Configure plugin settings.
        
        Args:
            async_initialization: Enable async initialization.
            lazy_loading_enabled: Enable lazy loading.
            parallel_enabled: Enable parallel initialization.
            plugin_init_timeout: Plugin initialization timeout.
            global_init_timeout: Global initialization timeout.
            circuit_breaker_enabled: Enable circuit breaker.
            max_workers: Maximum worker threads.
        """
        config = {
            "async_initialization": async_initialization,
            "lazy_loading": lazy_loading_enabled,
            "parallel_enabled": parallel_enabled,
            "plugin_init_timeout": plugin_init_timeout,
            "global_init_timeout": global_init_timeout,
            "circuit_breaker_enabled": circuit_breaker_enabled,
            "max_workers": max_workers,
        }
        get_config_manager(config)
        logger = cls.get_logger()
        logger.info(f"Plugin configuration updated: {config}")
    
    @classmethod
    def reset(cls) -> None:
        """Reset the handler state."""
        with cls._lock:
            cls._config = {}
            if cls._plugin_manager is not None:
                cls._plugin_manager.reset_instance()
            cls._plugin_manager = None
            cls._plugin_context = None
            cls._initialization_callback = None
            cls._instance = None


__all__ = ["PluginInitializer"]
