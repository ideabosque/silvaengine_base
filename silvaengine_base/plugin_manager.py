#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Hot-pluggable plugin manager for silvaengine_base.

Provides plugin registration coordination and initialization scheduling.
Pool management functionality has been completely migrated to silvaengine_connections module.

This module is responsible for:
- Plugin registration coordination
- Initialization scheduling
- Context propagation to business modules
- Parallel plugin initialization for improved performance
"""

import importlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union


@dataclass
class PluginConfiguration:
    """
    Plugin configuration data class.

    Encapsulates all configuration parameters for a plugin,
    supporting both new standard format and legacy formats.

    Attributes:
        plugin_type: Plugin type identifier (e.g., "connection_pools", "cache")
        config: Plugin-specific configuration dictionary
        enabled: Whether the plugin is enabled
        module_name: Python module name for dynamic import
        class_name: Optional class name for instantiation
        function_name: Function or method name to call for initialization
    """

    plugin_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    module_name: str = ""
    class_name: Optional[str] = None
    function_name: str = "init"

    @classmethod
    def from_dict(cls, plugin_type: str, data: Dict[str, Any]) -> "PluginConfiguration":
        """
        Create PluginConfiguration from dictionary.

        Supports both new standard format (with 'config' key) and
        legacy format (with 'resources' key).

        Args:
            plugin_type: Plugin type identifier.
            data: Configuration dictionary.

        Returns:
            PluginConfiguration instance.
        """
        # Support both 'config' (new) and 'resources' (legacy) keys
        plugin_config = data.get("config") or data.get("resources") or {}

        return cls(
            plugin_type=plugin_type,
            config=plugin_config,
            enabled=data.get("enabled", True),
            module_name=data.get("module_name", ""),
            class_name=data.get("class_name"),
            function_name=data.get("function_name", "init"),
        )


class PluginManager:
    """
    Hot-pluggable plugin manager with parallel initialization support.

    This class coordinates plugin registration and initialization scheduling.
    It supports both sequential and parallel initialization modes for improved
    performance when multiple plugins are configured.

    Responsibilities:
    - Plugin registration coordination
    - Initialization scheduling (sequential or parallel)
    - Context propagation to business modules
    - Comprehensive error handling and logging

    The manager is implemented as a singleton to ensure consistent
    plugin management across the application.

    Supports standard configuration format (list with direct config):
        {
            "plugins": [
                {
                    "type": "connection_pools",
                    "config": {
                        "neo4j": {...},
                        "postgresql": {...}
                    },
                    "enabled": True,
                    "module_name": "silvaengine_connections",
                    "class_name": "PoolManager",
                    "function_name": "init"
                },
                ...
            ]
        }

    Also supports legacy formats for backward compatibility:
        - Legacy with 'resources' key
        - Legacy nested format (e.g., 'connection_pools': {...})

    Example:
        ```python
        # Get manager instance
        manager = PluginManager()

        # Initialize with standard configuration
        manager.initialize({
            "plugins": [
                {
                    "type": "connection_pools",
                    "config": {...},
                    "enabled": True,
                    "module_name": "silvaengine_connections",
                    "function_name": "init"
                }
            ]
        })

        # Get initialized plugin objects
        objects = manager.get_initialized_objects()

        # Get context for business modules
        context = manager.get_context()
        ```
    """

    _instance: Optional["PluginManager"] = None
    _lock = threading.Lock()

    def __new__(cls, logger: Optional[logging.Logger] = None):
        """
        Create or return the singleton instance.

        Args:
            logger: Optional logger instance.

        Returns:
            PluginManager: The singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, logger: Optional[logging.Logger] = None):
        if getattr(self, "_is_initialized", False):
            return

        self._initialized_objects: Dict[str, Any] = {}
        self._config: Dict[str, Any] = {}
        self._logger = logger or logging.getLogger(__name__)
        self._manager_lock = threading.RLock()
        self._is_initialized = False
        self._parallel_enabled = True  # Enable parallel initialization by default
        self._max_workers = 5  # Maximum concurrent threads for parallel initialization

    def initialize(self, handler_setting: Dict[str, Any]) -> bool:
        """
        Initialize plugin manager.

        This method coordinates plugin registration and initialization.
        Supports both sequential and parallel initialization modes.

        Args:
            handler_setting: Configuration dictionary with the following structure:
                # Standard format (list with type and config):
                {
                    "plugins": [
                        {
                            "type": "connection_pools",
                            "config": {
                                "neo4j": {...},
                                "postgresql": {...}
                            },
                            "enabled": True,
                            "module_name": "silvaengine_connections",
                            "class_name": "PoolManager",
                            "function_name": "init"
                        }
                    ]
                }

        Returns:
            bool: Whether initialization succeeded.
        """
        if not isinstance(handler_setting, dict):
            self._logger.error("Invalid handler_setting: must be a dictionary")
            return False

        plugins_config = handler_setting.get("plugins")

        if not plugins_config:
            self._logger.warning("No plugins configuration found")
            return False

        with self._manager_lock:
            # Check if configuration changed
            if self._is_initialized:
                if plugins_config != self._config.get("plugins"):
                    self._logger.info("Configuration changed, reinitializing plugins")
                    self._initialized_objects.clear()
                    self._config = handler_setting
                    self._process_plugins_config(plugins_config)
                return True

            try:
                self._config = handler_setting
                self._process_plugins_config(plugins_config)

                self._is_initialized = True
                self._logger.info("PluginManager initialized successfully")
                return True

            except Exception as e:
                self._logger.error(f"Failed to initialize PluginManager: {e}")
                return False

    def _process_plugins_config(self, plugins_config: Union[List, Dict]) -> None:
        """
        Process plugins configuration with optional parallelization.

        Automatically selects sequential or parallel processing based on
        configuration and number of plugins.

        Args:
            plugins_config: Plugins configuration, can be a list or dict.
        """
        # Determine if parallel processing should be used
        use_parallel = (
            self._parallel_enabled
            and isinstance(plugins_config, list)
            and len(plugins_config) > 1
        )

        if use_parallel:
            self._logger.debug("Using parallel initialization")
            self._process_plugins_config_parallel(plugins_config)
        else:
            self._logger.debug("Using sequential initialization")
            self._process_plugins_config_sequential(plugins_config)

    def _process_plugins_config_sequential(self, plugins_config: Union[List, Dict]) -> None:
        """
        Process plugins configuration sequentially.

        Args:
            plugins_config: Plugins configuration, can be a list or dict.
        """
        if isinstance(plugins_config, list):
            for index, plugin_item in enumerate(plugins_config):
                if isinstance(plugin_item, dict):
                    self._process_single_plugin(plugin_item, index)
                else:
                    self._logger.warning(f"Skipping invalid plugin item at index {index}: {plugin_item}")
        elif isinstance(plugins_config, dict):
            self._process_single_plugin(plugins_config, 0)
        else:
            self._logger.warning(f"Unsupported plugins config type: {type(plugins_config)}")

    def _process_plugins_config_parallel(self, plugins_config: List) -> Dict[str, Any]:
        """
        Process plugins configuration in parallel using ThreadPoolExecutor.

        This method initializes multiple plugins concurrently for improved
        performance. Each plugin is initialized in a separate thread.

        Args:
            plugins_config: List of plugin configurations.

        Returns:
            Dictionary containing initialization results for all plugins.
        """
        # Collect all plugin configurations
        all_configs: List[PluginConfiguration] = []
        
        for index, plugin_item in enumerate(plugins_config):
            if isinstance(plugin_item, dict):
                configs = self._extract_plugin_configurations(plugin_item, index)
                all_configs.extend(configs)
            else:
                self._logger.warning(f"Skipping invalid plugin item at index {index}: {plugin_item}")

        if not all_configs:
            self._logger.warning("No valid plugin configurations found for parallel processing")
            return {}

        # Execute initialization in parallel
        results: Dict[str, Any] = {}
        max_workers = min(len(all_configs), self._max_workers)

        self._logger.info(f"Initializing {len(all_configs)} plugins in parallel with {max_workers} workers")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all initialization tasks
            future_to_config = {
                executor.submit(self._initialize_plugin_safe, config): config
                for config in all_configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    result = future.result()
                    results[config.plugin_type] = result

                    if result["success"]:
                        self._logger.debug(f"Plugin {config.plugin_type} initialized successfully")
                    else:
                        self._logger.warning(f"Plugin {config.plugin_type} initialization failed: {result.get('error')}")

                except Exception as e:
                    self._logger.error(f"Unexpected error initializing {config.plugin_type}: {e}")
                    results[config.plugin_type] = {
                        "success": False,
                        "plugin_type": config.plugin_type,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }

        # Log summary
        success_count = sum(1 for r in results.values() if r.get("success"))
        total_count = len(results)
        self._logger.info(f"Parallel initialization complete: {success_count}/{total_count} plugins succeeded")

        return results

    def _extract_plugin_configurations(
        self, plugin_config: Dict[str, Any], index: int
    ) -> List[PluginConfiguration]:
        """
        Extract all plugin configurations from a plugin config dictionary.

        This method handles multiple configuration formats:
        1. New standard format with 'config' key
        2. Legacy format with 'resources' key
        3. Legacy nested format (e.g., 'connection_pools': {...})

        Args:
            plugin_config: Plugin configuration dictionary.
            index: Index for logging purposes.

        Returns:
            List of PluginConfiguration objects.
        """
        configs: List[PluginConfiguration] = []

        # Check for legacy nested format (e.g., "connection_pools", "cache", etc.)
        reserved_keys = {
            "config", "resources", "enabled", "module_name",
            "class_name", "function_name", "type"
        }

        for key, value in plugin_config.items():
            if isinstance(value, dict) and key not in reserved_keys:
                # This is likely a legacy nested format
                configs.append(PluginConfiguration.from_dict(key, value))

        # Check for direct config format (new standard)
        if "config" in plugin_config or "resources" in plugin_config:
            plugin_type = plugin_config.get("type", "connection_pools")
            configs.append(PluginConfiguration.from_dict(plugin_type, plugin_config))

        return configs

    def _process_single_plugin(self, plugin_config: Dict[str, Any], index: int) -> None:
        """
        Process a single plugin configuration.

        Args:
            plugin_config: Single plugin configuration dictionary.
            index: Index of the plugin in the list (for logging purposes).
        """
        configs = self._extract_plugin_configurations(plugin_config, index)

        for config in configs:
            self._logger.debug(f"Processing plugin {config.plugin_type} at index {index}")
            self._initialize_plugin_safe(config)

    def _initialize_plugin_safe(self, plugin_config: PluginConfiguration) -> Dict[str, Any]:
        """
        Safely initialize a plugin with comprehensive error handling.

        This method ensures that:
        1. Single plugin failure doesn't affect other plugins
        2. All errors are properly logged
        3. Partial results are returned for debugging

        Args:
            plugin_config: Plugin configuration.

        Returns:
            Result dictionary with success status and error details.
        """
        result = {
            "success": False,
            "plugin_type": plugin_config.plugin_type,
            "module_name": plugin_config.module_name,
            "class_name": plugin_config.class_name,
            "function_name": plugin_config.function_name,
            "manager": None,
            "error": None,
            "error_type": None,
        }

        # Validation
        if not plugin_config.enabled:
            result["error"] = "Plugin disabled by configuration"
            self._logger.debug(f"Plugin {plugin_config.plugin_type}: {result['error']}")
            return result

        if not plugin_config.module_name:
            result["error"] = "Missing required field: module_name"
            result["error_type"] = "ValidationError"
            self._logger.error(f"Plugin {plugin_config.plugin_type}: {result['error']}")
            return result

        try:
            # Attempt dynamic import
            try:
                module = importlib.import_module(plugin_config.module_name)
            except ImportError as import_error:
                result["error"] = f"Module import failed: {import_error}"
                result["error_type"] = "ImportError"
                self._logger.error(f"Plugin {plugin_config.plugin_type}: {result['error']}")
                return result

            # Get initialization callable
            try:
                if plugin_config.class_name:
                    plugin_class = getattr(module, plugin_config.class_name)
                    init_callable = getattr(plugin_class(), plugin_config.function_name)
                else:
                    init_callable = getattr(module, plugin_config.function_name)
            except AttributeError:
                target = plugin_config.class_name or plugin_config.function_name
                result["error"] = f"Attribute not found: {target}"
                result["error_type"] = "AttributeError"
                self._logger.error(f"Plugin {plugin_config.plugin_type}: {result['error']}")
                return result

            # Execute initialization
            try:
                manager = init_callable(plugin_config.config)
            except Exception as init_error:
                result["error"] = f"Initialization function failed: {init_error}"
                result["error_type"] = type(init_error).__name__
                self._logger.error(f"Plugin {plugin_config.plugin_type}: {result['error']}")
                return result

            # Store successful result
            self._initialized_objects[plugin_config.plugin_type] = {
                "manager": manager,
                "module_name": plugin_config.module_name,
                "class_name": plugin_config.class_name,
                "config": plugin_config.config,
            }

            result["success"] = True
            result["manager"] = manager
            self._logger.info(f"Plugin {plugin_config.plugin_type} initialized successfully")

        except Exception as unexpected_error:
            result["error"] = f"Unexpected error: {unexpected_error}"
            result["error_type"] = type(unexpected_error).__name__
            self._logger.exception(f"Plugin {plugin_config.plugin_type}: {result['error']}")

        return result

    def get_initialized_objects(self) -> Dict[str, Any]:
        """
        Get all initialized plugin objects.

        Returns:
            Dictionary mapping plugin names to initialized objects.
        """
        return self._initialized_objects.copy()

    def get_initialized_object(self, name: str) -> Optional[Any]:
        """
        Get initialized plugin object by name.

        Args:
            name: Plugin name.

        Returns:
            Initialized plugin object or None.
        """
        return self._initialized_objects.get(name)

    def get_connection_pool_manager(self) -> Optional[Any]:
        """
        Get the connection pool manager if initialized.

        Returns:
            ConnectionPoolManager instance or None.
        """
        connection_pools = self._initialized_objects.get("connection_pools")
        if connection_pools:
            return connection_pools.get("manager")
        return None

    def get_context(self) -> Dict[str, Any]:
        """
        Get context with initialized objects for passing to business modules.

        Returns:
            Context dictionary containing initialized plugin objects.
        """
        context = {
            "initialized_plugins": self._initialized_objects,
            "config": self._config,
        }

        # Add connection pool manager to context if available
        pool_manager = self.get_connection_pool_manager()
        if pool_manager:
            context["pool_manager"] = pool_manager
            context["pools"] = pool_manager.get_all_pools()

        return context

    def is_initialized(self) -> bool:
        """Check if initialized."""
        return self._is_initialized

    def set_parallel_enabled(self, enabled: bool) -> None:
        """
        Enable or disable parallel initialization.

        Args:
            enabled: True to enable parallel initialization, False for sequential.
        """
        self._parallel_enabled = enabled
        self._logger.debug(f"Parallel initialization {'enabled' if enabled else 'disabled'}")

    def set_max_workers(self, max_workers: int) -> None:
        """
        Set maximum number of worker threads for parallel initialization.

        Args:
            max_workers: Maximum number of concurrent threads.
        """
        self._max_workers = max(1, max_workers)
        self._logger.debug(f"Max workers set to {self._max_workers}")

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (mainly for testing)."""
        with cls._lock:
            if cls._instance:
                cls._instance = None
