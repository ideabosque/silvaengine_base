#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Plugin manager for silvaengine_base."""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from silvaengine_utility import Invoker

from .circuit_breaker import (
    CircuitBreaker,
    get_circuit_breaker_registry,
)
from .config_validator import (
    ConfigValidator,
    ValidationResult,
    get_config_validator,
)
from .context import PluginContext, PluginNotFoundError
from .dependency import (
    DependencyResolver,
    PluginDependency,
)
from .injector import (
    PluginContextDescriptor,
    PluginContextInjector,
    clear_current_plugin_context,
    get_current_plugin_context,
    inject_plugin_context,
    set_current_plugin_context,
)
from .lazy_context import LazyPluginContext

__all__ = [
    "PluginContext",
    "PluginManager",
    "PluginConfiguration",
    "DependencyResolver",
    "PluginDependency",
    "ConfigValidator",
    "ValidationResult",
    "CircuitBreaker",
    "LazyPluginContext",
    "PluginContextDescriptor",
    "PluginContextInjector",
    "PluginNotFoundError",
    "get_current_plugin_context",
    "set_current_plugin_context",
    "clear_current_plugin_context",
    "inject_plugin_context",
]


@dataclass
class PluginConfiguration:
    """Plugin configuration data class."""

    plugin_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    module_name: str = ""
    class_name: Optional[str] = None
    function_name: str = "init"
    dependencies: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, plugin_type: str, data: Dict[str, Any]) -> "PluginConfiguration":
        plugin_config = data.get("config") or data.get("resources") or {}

        return cls(
            plugin_type=plugin_type,
            config=plugin_config,
            enabled=data.get("enabled", True),
            module_name=data.get("module_name", ""),
            class_name=data.get("class_name"),
            function_name=data.get("function_name", "init"),
            dependencies=data.get("dependencies", []),
        )


class PluginManager:
    _instance: Optional["PluginManager"] = None
    _lock = threading.Lock()

    def __new__(cls, logger: Optional[logging.Logger] = None):
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
        self._parallel_enabled = True
        self._max_workers = (os.cpu_count() or 1) * 4
        self._dependency_resolver = DependencyResolver(self._logger)
        self._config_validator = get_config_validator()
        self._validation_strict_mode = False

        # Timeout configuration
        self._plugin_init_timeout = 30.0
        self._global_init_timeout = 120.0

        # Circuit breaker configuration
        self._circuit_breaker_enabled = True
        self._circuit_breaker_failure_threshold = 3
        self._circuit_breaker_recovery_timeout = 60.0

        # Lazy loading configuration
        self._lazy_loading_enabled = False
        self._lazy_context: Optional[LazyPluginContext] = None

        self._logger.info(
            f"PluginManager initialized with max_workers={self._max_workers}, "
            f"plugin_timeout={self._plugin_init_timeout}s, "
            f"global_timeout={self._global_init_timeout}s"
        )

    def initialize(self, setting: Dict[str, Any]) -> bool:
        """Initialize plugins from handler settings."""
        if not setting:
            self._logger.error("Invalid setting: must be a dictionary")
            return False

        plugins_config = setting.get("plugins")

        if not plugins_config:
            self._logger.warning("No plugins configuration found")
            return False

        # Validate plugins configuration before processing
        validation_result = self._config_validator.validate_plugins_config(
            plugins_config
        )

        if not validation_result.is_valid:
            for error in validation_result.errors:
                self._logger.error(
                    f"Configuration validation error [{error.code}]: {error.field} - {error.message}"
                )

            if self._validation_strict_mode:
                self._logger.error(
                    "Configuration validation failed in strict mode, aborting initialization"
                )
                return False
            else:
                self._logger.warning(
                    "Configuration validation failed, continuing with warnings"
                )

        for warning in validation_result.warnings:
            self._logger.warning(
                f"Configuration validation warning [{warning.code}]: {warning.field} - {warning.message}"
            )

        with self._manager_lock:
            if self._is_initialized:
                if plugins_config != self._config.get("plugins"):
                    self._logger.info("Configuration changed, reinitializing plugins")
                    self._initialized_objects.clear()
                    self._config = setting
                    self._process_plugins_config(plugins_config)
                return True

            try:
                self._config = setting

                # If lazy loading is enabled, store configs and defer initialization
                if self._lazy_loading_enabled:
                    self._setup_lazy_loading(plugins_config)
                else:
                    self._process_plugins_config(plugins_config)

                self._is_initialized = True
                self._logger.info("PluginManager initialized successfully")
                return True

            except Exception as e:
                self._logger.error(f"Failed to initialize PluginManager: {e}")
                return False

    def _setup_lazy_loading(self, plugins_config: List) -> None:
        """Setup lazy loading for plugins."""
        plugin_configs_dict = {}

        for plugin_item in plugins_config:
            if isinstance(plugin_item, dict):
                plugin_type = plugin_item.get("type", "").strip().lower()
                if plugin_type:
                    plugin_configs_dict[plugin_type] = plugin_item

        self._lazy_context = LazyPluginContext(
            plugin_manager=self,
            plugin_configs=plugin_configs_dict,
            logger=self._logger,
            initialization_timeout=self._plugin_init_timeout,
        )

        self._logger.info(
            f"Lazy loading enabled for {len(plugin_configs_dict)} plugins"
        )

    def _process_plugins_config(self, plugins_config: List) -> None:
        """Process plugins configuration with global timeout."""
        if not isinstance(plugins_config, list) and not plugins_config:
            return

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._do_process_plugins_config, plugins_config)

            try:
                future.result(timeout=self._global_init_timeout)
            except FutureTimeoutError:
                self._logger.error(
                    f"Global plugin initialization timed out after {self._global_init_timeout}s"
                )
                raise TimeoutError(
                    f"Plugin initialization exceeded global timeout of {self._global_init_timeout}s"
                )

    def _do_process_plugins_config(self, plugins_config: List) -> None:
        """Actual plugin configuration processing."""
        dependencies = self._extract_plugin_dependencies(plugins_config)

        if dependencies:
            circular_deps = self._dependency_resolver.detect_circular_dependencies(
                dependencies
            )
            if circular_deps:
                error_msg = (
                    f"Circular dependency detected in plugin configuration: "
                    f"{' -> '.join(circular_deps)}"
                )
                self._logger.error(error_msg)
                raise ValueError(error_msg)

            resolved_order = self._dependency_resolver.resolve_dependencies(
                dependencies
            )
            resolved_plugin_names = [p.plugin_name for p in resolved_order]
            self._logger.info(
                f"Plugin dependency order resolved: {resolved_plugin_names}"
            )

            plugins_config = self._reorder_plugins_by_dependencies(
                plugins_config, resolved_plugin_names
            )

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

    def _extract_plugin_dependencies(
        self, plugins_config: List
    ) -> List[PluginDependency]:
        dependencies: List[PluginDependency] = []

        for plugin_item in plugins_config:
            if isinstance(plugin_item, dict):
                plugin_type = plugin_item.get("type", "").strip().lower()

                if plugin_type:
                    deps = plugin_item.get("dependencies", [])

                    if deps:
                        dependencies.append(
                            PluginDependency(plugin_name=plugin_type, dependencies=deps)
                        )

        return dependencies

    def _reorder_plugins_by_dependencies(
        self, plugins_config: List, resolved_order: List[str]
    ) -> List:
        plugin_map: Dict[str, Any] = {}

        for plugin in plugins_config:
            if isinstance(plugin, dict):
                plugin_type = plugin.get("type", "").strip().lower()

                if plugin_type:
                    plugin_map[plugin_type] = plugin

        reordered: List[Any] = []

        for plugin_name in resolved_order:
            if plugin_name in plugin_map:
                reordered.append(plugin_map[plugin_name])

        for plugin in plugins_config:
            if isinstance(plugin, dict):
                plugin_type = plugin.get("type", "").strip().lower()

                if plugin_type not in resolved_order:
                    reordered.append(plugin)

        return reordered

    def _process_plugins_config_sequential(self, plugins_config: List) -> None:
        if isinstance(plugins_config, list):
            for index, plugin_item in enumerate(plugins_config):
                if isinstance(plugin_item, dict):
                    self._process_single_plugin(plugin_item, index)
                else:
                    self._logger.warning(
                        f"Skipping invalid plugin item at index {index}: {plugin_item}"
                    )
        else:
            self._logger.warning(
                f"Unsupported plugins config type: {type(plugins_config)}"
            )

    def _process_plugins_config_parallel(self, plugins_config: List) -> Dict[str, Any]:
        all_configs: List[PluginConfiguration] = []

        for index, plugin_item in enumerate(plugins_config):
            if isinstance(plugin_item, dict):
                configs = self._extract_plugin_configurations(plugin_item, index)
                all_configs.extend(configs)
            else:
                self._logger.warning(
                    f"Skipping invalid plugin item at index {index}: {plugin_item}"
                )

        if not all_configs:
            self._logger.warning(
                "No valid plugin configurations found for parallel processing"
            )
            return {}

        results: Dict[str, Any] = {}
        max_workers = min(len(all_configs), self._max_workers)

        self._logger.info(
            f"Initializing {len(all_configs)} plugins in parallel with {max_workers} workers"
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_config = {
                executor.submit(self._initialize_plugin_safe, config): config
                for config in all_configs
            }

            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    result = future.result(timeout=self._plugin_init_timeout)
                    results[config.plugin_type] = result

                    if result["success"]:
                        self._logger.debug(
                            f"Plugin {config.plugin_type} initialized successfully"
                        )
                    else:
                        self._logger.warning(
                            f"Plugin {config.plugin_type} initialization failed: {result.get('error')}"
                        )

                except FutureTimeoutError:
                    error_msg = f"Plugin {config.plugin_type} initialization timed out after {self._plugin_init_timeout}s"
                    self._logger.error(error_msg)
                    results[config.plugin_type] = {
                        "success": False,
                        "plugin_type": config.plugin_type,
                        "error": error_msg,
                        "error_type": "TimeoutError",
                    }

                except Exception as e:
                    self._logger.error(
                        f"Unexpected error initializing {config.plugin_type}: {e}"
                    )
                    results[config.plugin_type] = {
                        "success": False,
                        "plugin_type": config.plugin_type,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }

        success_count = sum(1 for r in results.values() if r.get("success"))
        total_count = len(results)
        self._logger.info(
            f"Parallel initialization complete: {success_count}/{total_count} plugins succeeded"
        )

        return results

    def _extract_plugin_configurations(
        self, plugin_config: Dict[str, Any], index: int
    ) -> List[PluginConfiguration]:
        configs: List[PluginConfiguration] = []

        reserved_keys = {
            "config",
            "enabled",
            "module_name",
            "class_name",
            "function_name",
            "type",
        }

        for key, value in plugin_config.items():
            if isinstance(value, dict) and key not in reserved_keys:
                configs.append(PluginConfiguration.from_dict(key, value))

        if "config" in plugin_config and "type" in plugin_config:
            plugin_type = str(plugin_config.get("type")).strip().lower()
            configs.append(PluginConfiguration.from_dict(plugin_type, plugin_config))

        return configs

    def _process_single_plugin(self, plugin_config: Dict[str, Any], index: int) -> None:
        configs = self._extract_plugin_configurations(plugin_config, index)

        for config in configs:
            self._logger.debug(
                f"Processing plugin {config.plugin_type} at index {index}"
            )
            self._initialize_plugin_safe(config)

    def _initialize_plugin_safe(
        self, plugin_config: PluginConfiguration
    ) -> Dict[str, Any]:
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

        if not plugin_config.plugin_type:
            result["error"] = "Invalid plugin type"
            self._logger.debug(f"Plugin {plugin_config.plugin_type}: {result['error']}")
            return result

        if not plugin_config.enabled:
            result["error"] = "Plugin disabled by configuration"
            self._logger.debug(f"Plugin {plugin_config.plugin_type}: {result['error']}")
            return result

        if not plugin_config.module_name:
            result["error"] = "Missing required field: module_name"
            result["error_type"] = "ValidationError"
            self._logger.error(f"Plugin {plugin_config.plugin_type}: {result['error']}")
            return result

        plugin_type = str(plugin_config.plugin_type).strip().lower()

        # Use circuit breaker if enabled
        if self._circuit_breaker_enabled:
            circuit_breaker = get_circuit_breaker_registry().get_or_create(
                name=plugin_type,
                failure_threshold=self._circuit_breaker_failure_threshold,
                recovery_timeout=self._circuit_breaker_recovery_timeout,
            )

            try:
                manager = circuit_breaker.call(
                    self._do_initialize_plugin,
                    plugin_config,
                )

                self._initialized_objects[plugin_type] = {
                    "manager": manager,
                    "module_name": plugin_config.module_name,
                    "class_name": plugin_config.class_name,
                    "config": plugin_config.config,
                }

                result["success"] = True
                result["manager"] = manager
                self._logger.info(f"Plugin {plugin_type} initialized successfully")

            except Exception as e:
                result["error"] = str(e)
                result["error_type"] = type(e).__name__
                self._logger.error(f"Plugin {plugin_type}: {result['error']}")

        else:
            try:
                manager = self._do_initialize_plugin(plugin_config)

                self._initialized_objects[plugin_type] = {
                    "manager": manager,
                    "module_name": plugin_config.module_name,
                    "class_name": plugin_config.class_name,
                    "config": plugin_config.config,
                }

                result["success"] = True
                result["manager"] = manager
                self._logger.info(f"Plugin {plugin_type} initialized successfully")

            except Exception as e:
                result["error"] = str(e)
                result["error_type"] = type(e).__name__
                self._logger.error(f"Plugin {plugin_type}: {result['error']}")

        return result

    def _do_initialize_plugin(self, plugin_config: PluginConfiguration) -> Any:
        """Perform actual plugin initialization with timeout."""
        proxied_callable = Invoker.resolve_proxied_callable(
            module_name=plugin_config.module_name,
            function_name=plugin_config.function_name,
            class_name=plugin_config.class_name,
            constructor_parameters=None,
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(proxied_callable, plugin_config.config)

            try:
                return future.result(timeout=self._plugin_init_timeout)
            except FutureTimeoutError:
                raise TimeoutError(
                    f"Plugin '{plugin_config.plugin_type}' initialization timed out "
                    f"after {self._plugin_init_timeout}s"
                )

    def get_initialized_objects(self) -> Dict[str, Any]:
        return self._initialized_objects.copy()

    def get_initialized_object(self, plugin_type: str) -> Optional[Any]:
        if not plugin_type:
            self._logger.exception(f"Invalid plugin type `{plugin_type}`")
            return None

        plugin_type = str(plugin_type).strip().lower()

        # If lazy loading is enabled, use lazy context
        if self._lazy_loading_enabled and self._lazy_context:
            return self._lazy_context.get(plugin_type)

        return self._initialized_objects.get(plugin_type)

    def get_context(self, timeout: float = 30.0) -> PluginContext:
        # If lazy loading is enabled, return lazy context wrapper
        if self._lazy_loading_enabled and self._lazy_context:
            return LazyPluginContextWrapper(self._lazy_context)

        if not self._is_initialized and timeout > 0:
            start_time = time.time()
            while not self._is_initialized:
                if time.time() - start_time >= timeout:
                    self._logger.warning(
                        f"PluginManager not initialized within {timeout}s timeout"
                    )
                    break
                time.sleep(0.1)

        return PluginContext(self)

    def is_initialized(self) -> bool:
        return self._is_initialized

    def set_parallel_enabled(self, enabled: bool) -> None:
        self._parallel_enabled = enabled
        self._logger.debug(
            f"Parallel initialization {'enabled' if enabled else 'disabled'}"
        )

    def set_max_workers(self, max_workers: int) -> None:
        self._max_workers = max(1, max_workers)
        self._logger.debug(f"Max workers set to {self._max_workers}")

    def set_plugin_init_timeout(self, timeout: float) -> None:
        """Set timeout for individual plugin initialization."""
        self._plugin_init_timeout = max(1.0, timeout)
        self._logger.debug(
            f"Plugin initialization timeout set to {self._plugin_init_timeout}s"
        )

    def set_global_init_timeout(self, timeout: float) -> None:
        """Set global timeout for entire initialization process."""
        self._global_init_timeout = max(1.0, timeout)
        self._logger.debug(
            f"Global initialization timeout set to {self._global_init_timeout}s"
        )

    def set_circuit_breaker_enabled(self, enabled: bool) -> None:
        """Enable or disable circuit breaker."""
        self._circuit_breaker_enabled = enabled
        self._logger.debug(f"Circuit breaker {'enabled' if enabled else 'disabled'}")

    def set_lazy_loading_enabled(self, enabled: bool) -> None:
        """Enable or disable lazy loading."""
        self._lazy_loading_enabled = enabled
        self._logger.debug(f"Lazy loading {'enabled' if enabled else 'disabled'}")

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the PluginManager singleton instance."""
        with cls._lock:
            if cls._instance:
                cls._instance = None

    def set_validation_strict_mode(self, strict: bool) -> None:
        """Set the validation strict mode."""
        self._validation_strict_mode = strict
        self._logger.debug(
            f"Validation strict mode {'enabled' if strict else 'disabled'}"
        )

    def validate_configuration(
        self, plugins_config: List[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate plugins configuration without initializing."""
        return self._config_validator.validate_plugins_config(plugins_config)

    def get_plugin_status(self, plugin_type: str) -> Dict[str, Any]:
        """Get the status of a specific plugin."""
        plugin_type = str(plugin_type).strip().lower()

        # Check lazy context if enabled
        if self._lazy_loading_enabled and self._lazy_context:
            is_init = self._lazy_context.is_initialized(plugin_type)
            return {
                "plugin_type": plugin_type,
                "initialized": is_init,
                "lazy_loading": True,
            }

        initialized_object = self._initialized_objects.get(plugin_type)

        if initialized_object:
            return {
                "plugin_type": plugin_type,
                "initialized": True,
                "module_name": initialized_object.get("module_name"),
                "class_name": initialized_object.get("class_name"),
                "config_keys": list(initialized_object.get("config", {}).keys()),
            }

        return {
            "plugin_type": plugin_type,
            "initialized": False,
        }

    def get_all_plugin_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all plugins."""
        if self._lazy_loading_enabled and self._lazy_context:
            stats = self._lazy_context.get_initialization_stats()
            return {
                "lazy_loading_stats": stats,
            }

        return {
            plugin_type: self.get_plugin_status(plugin_type)
            for plugin_type in self._initialized_objects.keys()
        }


class LazyPluginContextWrapper:
    """Wrapper to make LazyPluginContext compatible with PluginContext interface."""

    def __init__(self, lazy_context: LazyPluginContext):
        self._lazy_context = lazy_context

    def get(self, plugin_name: str) -> Optional[Any]:
        return self._lazy_context.get(plugin_name)

    def get_or_raise(self, plugin_name: str) -> Any:
        return self._lazy_context.get_or_raise(plugin_name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
