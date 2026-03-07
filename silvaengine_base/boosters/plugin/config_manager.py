#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Plugin Configuration Manager for silvaengine_base.

This module provides centralized configuration management for plugin system,
including async initialization settings, timeouts, and feature flags.
All configuration is read from the plugin config dictionary.
"""

import logging
import os
from typing import Any, Dict, Optional


class PluginConfigManager:
    """Centralized configuration manager for plugin system.
    
    This class manages all plugin-related configuration settings,
    reading from config dictionary with environment variable overrides.
    
    Uses a module-level singleton pattern for efficient access.
    """
    
    _instance: Optional["PluginConfigManager"] = None
    
    DEFAULT_ASYNC_INITIALIZATION = True
    DEFAULT_LAZY_LOADING = False
    DEFAULT_PARALLEL_ENABLED = True
    DEFAULT_PLUGIN_INIT_TIMEOUT = 30.0
    DEFAULT_GLOBAL_INIT_TIMEOUT = 120.0
    DEFAULT_CIRCUIT_BREAKER_ENABLED = True
    DEFAULT_MAX_WORKERS = None
    
    def __new__(cls, config: Optional[Dict[str, Any]] = None) -> "PluginConfigManager":
        """Create or return the singleton instance.
        
        Args:
            config: Optional configuration dictionary.
            
        Returns:
            The singleton PluginConfigManager instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = config or {}
            cls._instance._logger = logging.getLogger(__name__)
        elif config is not None:
            cls._instance._config = config
        return cls._instance
    
    def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration.
        
        Args:
            config: New configuration dictionary.
        """
        self._config = config
    
    def get_async_initialization(self) -> bool:
        """Get async initialization setting.
        
        Returns:
            True if async initialization is enabled.
        """
        # Check environment variable first
        env_value = os.getenv("PLUGIN_ASYNC_INITIALIZATION")
        if env_value is not None:
            return env_value.lower() in ("true", "1", "yes")
        
        # Check config
        return self._config.get(
            "async_initialization",
            self.DEFAULT_ASYNC_INITIALIZATION
        )
    
    def get_lazy_loading(self) -> bool:
        """Get lazy loading setting.
        
        Returns:
            True if lazy loading is enabled.
        """
        env_value = os.getenv("PLUGIN_LAZY_LOADING_ENABLED")
        if env_value is not None:
            return env_value.lower() in ("true", "1", "yes")
        
        return self._config.get(
            "lazy_loading",
            self.DEFAULT_LAZY_LOADING
        )
    
    def get_parallel_enabled(self) -> bool:
        """Get parallel initialization setting.
        
        Returns:
            True if parallel initialization is enabled.
        """
        env_value = os.getenv("PLUGIN_PARALLEL_ENABLED")
        if env_value is not None:
            return env_value.lower() in ("true", "1", "yes")
        
        return self._config.get(
            "parallel_enabled",
            self.DEFAULT_PARALLEL_ENABLED
        )
    
    def get_plugin_init_timeout(self) -> float:
        """Get plugin initialization timeout.
        
        Returns:
            Timeout in seconds.
        """
        env_value = os.getenv("PLUGIN_INIT_TIMEOUT")
        if env_value is not None:
            try:
                return float(env_value)
            except ValueError:
                pass
        
        return self._config.get(
            "plugin_init_timeout",
            self.DEFAULT_PLUGIN_INIT_TIMEOUT
        )
    
    def get_global_init_timeout(self) -> float:
        """Get global initialization timeout.
        
        Returns:
            Timeout in seconds.
        """
        env_value = os.getenv("PLUGIN_GLOBAL_INIT_TIMEOUT")
        if env_value is not None:
            try:
                return float(env_value)
            except ValueError:
                pass
        
        return self._config.get(
            "global_init_timeout",
            self.DEFAULT_GLOBAL_INIT_TIMEOUT
        )
    
    def get_circuit_breaker_enabled(self) -> bool:
        """Get circuit breaker setting.
        
        Returns:
            True if circuit breaker is enabled.
        """
        env_value = os.getenv("PLUGIN_CIRCUIT_BREAKER_ENABLED")
        if env_value is not None:
            return env_value.lower() in ("true", "1", "yes")
        
        return self._config.get(
            "circuit_breaker_enabled",
            self.DEFAULT_CIRCUIT_BREAKER_ENABLED
        )
    
    def get_max_workers(self) -> Optional[int]:
        """Get maximum worker threads.
        
        Returns:
            Number of workers or None for auto-detect.
        """
        env_value = os.getenv("PLUGIN_MAX_WORKERS")
        if env_value is not None:
            try:
                return int(env_value)
            except ValueError:
                pass
        
        return self._config.get("max_workers", self.DEFAULT_MAX_WORKERS)
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all configuration settings.
        
        Returns:
            Dictionary containing all settings.
        """
        return {
            "async_initialization": self.get_async_initialization(),
            "lazy_loading": self.get_lazy_loading(),
            "parallel_enabled": self.get_parallel_enabled(),
            "plugin_init_timeout": self.get_plugin_init_timeout(),
            "global_init_timeout": self.get_global_init_timeout(),
            "circuit_breaker_enabled": self.get_circuit_breaker_enabled(),
            "max_workers": self.get_max_workers(),
        }
    
    def apply_to_plugin_manager(self, plugin_manager: Any) -> None:
        """Apply all settings to a plugin manager instance.
        
        Args:
            plugin_manager: PluginManager instance to configure.
        """
        plugin_manager.set_parallel_enabled(self.get_parallel_enabled())
        plugin_manager.set_plugin_init_timeout(self.get_plugin_init_timeout())
        plugin_manager.set_global_init_timeout(self.get_global_init_timeout())
        plugin_manager.set_circuit_breaker_enabled(self.get_circuit_breaker_enabled())
        plugin_manager.set_lazy_loading_enabled(self.get_lazy_loading())
        
        max_workers = self.get_max_workers()
        if max_workers is not None:
            plugin_manager.set_max_workers(max_workers)
        
        self._logger.debug(f"Applied configuration to plugin manager: {self.get_all_settings()}")


def get_config_manager(config: Optional[Dict[str, Any]] = None) -> PluginConfigManager:
    """Get or create global configuration manager.
    
    Args:
        config: Optional configuration dictionary.
        
    Returns:
        PluginConfigManager instance.
    """
    return PluginConfigManager(config)


def reset_config_manager() -> None:
    """Reset global configuration manager."""
    PluginConfigManager._instance = None


__all__ = [
    "PluginConfigManager",
    "get_config_manager",
    "reset_config_manager",
]
