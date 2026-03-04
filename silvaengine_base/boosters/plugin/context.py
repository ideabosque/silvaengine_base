#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Unified plugin context module for silvaengine_base.

This module provides a comprehensive plugin context system with:
- Abstract base class for plugin contexts with template method pattern
- Eager-loading plugin context for pre-initialized plugins
- Lazy-loading plugin context for on-demand initialization
- Thread-safe operations and state management
"""

import concurrent.futures
import logging
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

if TYPE_CHECKING:
    from . import PluginManager


class PluginState(Enum):
    """Plugin lifecycle states."""

    INITIALIZING = "initializing"
    READY = "ready"
    FAILED = "failed"
    DISABLED = "disabled"


class PluginNotFoundError(Exception):
    """Raised when a requested plugin is not found."""

    pass


class PluginInitializationTimeoutError(Exception):
    """Raised when plugin initialization times out."""

    pass


class AbstractPluginContext(ABC):
    """Abstract base class for plugin contexts with template method pattern.

    This class defines the common interface and shared functionality for
    different plugin context implementations. Subclasses must implement
    the abstract methods to provide specific loading behavior.
    """

    def __init__(
        self,
        plugin_manager: "PluginManager",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize the abstract plugin context.

        Args:
            plugin_manager: The plugin manager instance.
            logger: Optional logger instance for logging.
        """
        self._plugin_manager = plugin_manager
        self._logger = logger or logging.getLogger(__name__)
        self._lock = threading.RLock()

    def __enter__(self) -> "AbstractPluginContext":
        """Enter context manager."""
        self._logger.debug("Entering plugin context")
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Exit context manager."""
        self._logger.debug("Exiting plugin context")

    def get(self, plugin_name: str) -> Optional[Any]:
        """Get plugin instance by name.

        This is a template method that validates the plugin name and
        delegates to the subclass implementation.

        Args:
            plugin_name: The name of the plugin to retrieve.

        Returns:
            The plugin instance if found, None otherwise.
        """
        if not self._validate_plugin_name(plugin_name):
            self._logger.warning("Attempted to get plugin with empty name")
            return None

        normalized_name = self._normalize_plugin_name(plugin_name)
        return self._get_plugin_internal(normalized_name)

    def get_or_raise(self, plugin_name: str) -> Any:
        """Get plugin instance or raise exception.

        This is a template method that validates the plugin name and
        delegates to the subclass implementation.

        Args:
            plugin_name: The name of the plugin to retrieve.

        Returns:
            The plugin instance if found.

        Raises:
            PluginNotFoundError: If the plugin name is empty or plugin not found.
        """
        if not self._validate_plugin_name(plugin_name):
            raise PluginNotFoundError("Plugin name cannot be empty")

        normalized_name = self._normalize_plugin_name(plugin_name)
        plugin = self._get_plugin_internal(normalized_name)

        if plugin is None:
            error_msg = f"Plugin '{normalized_name}' not found or not initialized"
            self._logger.error(error_msg)
            raise PluginNotFoundError(error_msg)

        return plugin

    def get_all_plugins(self) -> Dict[str, Any]:
        """Get all initialized plugins.

        Returns:
            A dictionary mapping plugin names to their instances.
        """
        return self._get_all_plugins_internal()

    def get_plugin_state(self, plugin_name: str) -> PluginState:
        """Get the state of a specific plugin.

        Args:
            plugin_name: The name of the plugin to check.

        Returns:
            The current state of the plugin.
        """
        if not self._validate_plugin_name(plugin_name):
            return PluginState.FAILED

        normalized_name = self._normalize_plugin_name(plugin_name)
        return self._get_plugin_state_internal(normalized_name)

    def wait_for_plugin(self, plugin_name: str, timeout: float = 30.0) -> bool:
        """Wait for plugin to be initialized.

        Args:
            plugin_name: The name of the plugin to wait for.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if the plugin was initialized, False if timeout occurred.
        """
        if not self._validate_plugin_name(plugin_name):
            self._logger.warning("Attempted to wait for plugin with empty name")
            return False

        normalized_name = self._normalize_plugin_name(plugin_name)
        return self._wait_for_plugin_internal(normalized_name, timeout)

    def _normalize_plugin_name(self, plugin_name: str) -> str:
        """Normalize plugin name to lowercase and strip whitespace.

        Args:
            plugin_name: The plugin name to normalize.

        Returns:
            The normalized plugin name.
        """
        return str(plugin_name).strip().lower()

    def _validate_plugin_name(self, plugin_name: str) -> bool:
        """Validate plugin name is not empty.

        Args:
            plugin_name: The plugin name to validate.

        Returns:
            True if the name is valid, False otherwise.
        """
        if not plugin_name:
            return False
        return bool(str(plugin_name).strip())

    @abstractmethod
    def _get_plugin_internal(self, plugin_name: str) -> Optional[Any]:
        """Internal method to get plugin instance.

        Subclasses must implement this method to provide specific
        plugin retrieval behavior.

        Args:
            plugin_name: The normalized plugin name.

        Returns:
            The plugin instance if found, None otherwise.
        """
        pass

    @abstractmethod
    def _get_all_plugins_internal(self) -> Dict[str, Any]:
        """Internal method to get all plugins.

        Subclasses must implement this method to provide specific
        behavior for retrieving all plugins.

        Returns:
            A dictionary mapping plugin names to their instances.
        """
        pass

    @abstractmethod
    def _get_plugin_state_internal(self, plugin_name: str) -> PluginState:
        """Internal method to get plugin state.

        Subclasses must implement this method to provide specific
        state checking behavior.

        Args:
            plugin_name: The normalized plugin name.

        Returns:
            The current state of the plugin.
        """
        pass

    @abstractmethod
    def _wait_for_plugin_internal(self, plugin_name: str, timeout: float) -> bool:
        """Internal method to wait for plugin.

        Subclasses must implement this method to provide specific
        waiting behavior.

        Args:
            plugin_name: The normalized plugin name.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if the plugin was initialized, False if timeout occurred.
        """
        pass


class EagerPluginContext(AbstractPluginContext):
    """Eager-loading plugin context that accesses pre-initialized plugins.

    This context retrieves plugins that have been initialized at startup
    time by the PluginManager. It does not perform any lazy initialization.
    """

    def __init__(self, plugin_manager: "PluginManager") -> None:
        """Initialize the eager plugin context.

        Args:
            plugin_manager: The plugin manager instance.
        """
        super().__init__(plugin_manager=plugin_manager)

    def _get_plugin_internal(self, plugin_name: str) -> Optional[Any]:
        """Get plugin from pre-initialized objects.

        Args:
            plugin_name: The normalized plugin name.

        Returns:
            The plugin instance if found, None otherwise.
        """
        initialized_objects = self._plugin_manager.get_initialized_objects()
        plugin_data = initialized_objects.get(plugin_name)

        if plugin_data is None:
            self._logger.debug(
                f"Plugin '{plugin_name}' not found or not initialized"
            )
            return None

        return plugin_data.get("manager")

    def _get_all_plugins_internal(self) -> Dict[str, Any]:
        """Get all pre-initialized plugins.

        Returns:
            A dictionary mapping plugin names to their instances.
        """
        initialized_objects = self._plugin_manager.get_initialized_objects()
        result: Dict[str, Any] = {}

        for plugin_name, plugin_data in initialized_objects.items():
            result[plugin_name] = plugin_data.get("manager")

        self._logger.debug(f"Retrieved {len(result)} initialized plugins")
        return result

    def _get_plugin_state_internal(self, plugin_name: str) -> PluginState:
        """Get state from pre-initialized objects.

        Args:
            plugin_name: The normalized plugin name.

        Returns:
            The current state of the plugin.
        """
        initialized_objects = self._plugin_manager.get_initialized_objects()

        if plugin_name not in initialized_objects:
            return PluginState.INITIALIZING

        plugin_data = initialized_objects.get(plugin_name)
        if plugin_data is None:
            return PluginState.FAILED

        return PluginState.READY

    def _wait_for_plugin_internal(self, plugin_name: str, timeout: float) -> bool:
        """Wait for plugin to appear in initialized objects.

        Args:
            plugin_name: The normalized plugin name.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if the plugin was initialized, False if timeout occurred.
        """
        if timeout <= 0:
            self._logger.warning(
                f"Invalid timeout value: {timeout}, using default 30.0"
            )
            timeout = 30.0

        start_time = time.time()
        self._logger.debug(f"Waiting for plugin '{plugin_name}' (timeout: {timeout}s)")

        while True:
            initialized_objects = self._plugin_manager.get_initialized_objects()
            if plugin_name in initialized_objects:
                self._logger.debug(f"Plugin '{plugin_name}' is now initialized")
                return True

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                self._logger.warning(
                    f"Timeout waiting for plugin '{plugin_name}' after {elapsed:.2f}s"
                )
                return False

            remaining = timeout - elapsed
            sleep_time = min(0.1, remaining, 1.0)
            time.sleep(sleep_time)


class LazyPluginContext(AbstractPluginContext):
    """Lazy-loading plugin context with on-demand initialization.

    This context initializes plugins on first access rather than at startup.
    It maintains internal caches for initialized, initializing, and failed plugins.
    """

    def __init__(
        self,
        plugin_manager: Any,
        plugin_configs: Dict[str, Dict[str, Any]],
        logger: Optional[logging.Logger] = None,
        initialization_timeout: float = 30.0,
    ) -> None:
        """Initialize the lazy plugin context.

        Args:
            plugin_manager: The plugin manager instance.
            plugin_configs: Dictionary of plugin configurations.
            logger: Optional logger instance for logging.
            initialization_timeout: Timeout for plugin initialization in seconds.
        """
        super().__init__(plugin_manager=plugin_manager, logger=logger)

        self._plugin_configs = plugin_configs
        self._initialization_timeout = initialization_timeout

        self._initialized_plugins: Dict[str, Any] = {}
        self._initializing_plugins: Set[str] = set()
        self._failed_plugins: Dict[str, str] = {}
        self._init_locks: Dict[str, threading.Lock] = {}

    def _get_plugin_internal(self, plugin_name: str) -> Optional[Any]:
        """Get plugin, initializing on first access if needed.

        Args:
            plugin_name: The normalized plugin name.

        Returns:
            The plugin instance if found or initialized, None otherwise.
        """
        with self._lock:
            if plugin_name in self._initialized_plugins:
                return self._initialized_plugins[plugin_name]

            if plugin_name in self._failed_plugins:
                self._logger.debug(
                    f"Plugin '{plugin_name}' previously failed initialization"
                )
                return None

        return self._initialize_on_demand(plugin_name)

    def _get_all_plugins_internal(self) -> Dict[str, Any]:
        """Get all currently initialized plugins.

        Returns:
            A dictionary mapping plugin names to their instances.
        """
        with self._lock:
            return self._initialized_plugins.copy()

    def _get_plugin_state_internal(self, plugin_name: str) -> PluginState:
        """Get plugin state based on initialization status.

        Args:
            plugin_name: The normalized plugin name.

        Returns:
            The current state of the plugin.
        """
        with self._lock:
            if plugin_name in self._initialized_plugins:
                return PluginState.READY
            if plugin_name in self._failed_plugins:
                return PluginState.FAILED
            if plugin_name in self._initializing_plugins:
                return PluginState.INITIALIZING
            return PluginState.INITIALIZING

    def _wait_for_plugin_internal(self, plugin_name: str, timeout: float) -> bool:
        """Wait for lazy plugin initialization.

        Args:
            plugin_name: The normalized plugin name.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if the plugin was initialized, False if timeout occurred.
        """
        if timeout <= 0:
            timeout = 30.0

        start_time = time.time()

        while True:
            with self._lock:
                if plugin_name in self._initialized_plugins:
                    return True
                if plugin_name in self._failed_plugins:
                    return False

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return False

            time.sleep(min(0.1, timeout - elapsed))

    def _initialize_on_demand(self, plugin_name: str) -> Optional[Any]:
        """Initialize plugin on first access.

        Args:
            plugin_name: The normalized plugin name.

        Returns:
            The plugin instance if initialization succeeded, None otherwise.
        """
        with self._lock:
            if plugin_name in self._initialized_plugins:
                return self._initialized_plugins[plugin_name]

            if plugin_name in self._failed_plugins:
                self._logger.debug(
                    f"Plugin '{plugin_name}' previously failed initialization"
                )
                return None

            if plugin_name in self._initializing_plugins:
                self._logger.debug(
                    f"Plugin '{plugin_name}' is currently being initialized by another thread"
                )
                return None

            if plugin_name not in self._init_locks:
                self._init_locks[plugin_name] = threading.Lock()
            init_lock = self._init_locks[plugin_name]
            self._initializing_plugins.add(plugin_name)

        config = self._plugin_configs.get(plugin_name)
        if not config:
            self._logger.warning(f"Plugin '{plugin_name}' not found in configuration")
            with self._lock:
                self._initializing_plugins.discard(plugin_name)
            return None

        self._logger.info(f"Lazy initializing plugin '{plugin_name}'")

        try:
            manager = self._do_initialize_plugin(plugin_name, config)

            with self._lock:
                self._initialized_plugins[plugin_name] = manager
                self._initializing_plugins.discard(plugin_name)

            self._logger.info(f"Plugin '{plugin_name}' lazy initialized successfully")
            return manager

        except Exception as e:
            error_msg = str(e)
            with self._lock:
                self._failed_plugins[plugin_name] = error_msg
                self._initializing_plugins.discard(plugin_name)

            self._logger.error(
                f"Failed to lazy initialize plugin '{plugin_name}': {error_msg}"
            )
            return None

    def _do_initialize_plugin(
        self, plugin_name: str, config: Dict[str, Any]
    ) -> Any:
        """Perform actual plugin initialization.

        Args:
            plugin_name: The normalized plugin name.
            config: The plugin configuration dictionary.

        Returns:
            The initialized plugin manager instance.

        Raises:
            ValueError: If module_name is missing.
            TimeoutError: If initialization times out.
        """
        from silvaengine_utility import Invoker

        module_name = config.get("module_name", "")
        function_name = config.get("function_name", "init")
        class_name = config.get("class_name")
        plugin_config = config.get("config", {})

        if not module_name:
            raise ValueError(f"Plugin '{plugin_name}' missing module_name")

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._invoke_initialization,
                module_name,
                function_name,
                class_name,
                plugin_config,
                Invoker,
            )

            try:
                return future.result(timeout=self._initialization_timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"Plugin '{plugin_name}' initialization timed out after "
                    f"{self._initialization_timeout}s"
                )

    def _invoke_initialization(
        self,
        module_name: str,
        function_name: str,
        class_name: Optional[str],
        config: Dict[str, Any],
        invoker: Any,
    ) -> Any:
        """Invoke plugin initialization function.

        Args:
            module_name: The module name containing the plugin.
            function_name: The initialization function name.
            class_name: Optional class name for class-based plugins.
            config: The plugin configuration dictionary.
            invoker: The Invoker class for resolving callables.

        Returns:
            The initialized plugin instance.
        """
        proxied_callable = invoker.resolve_proxied_callable(
            module_name=module_name,
            function_name=function_name,
            class_name=class_name,
            constructor_parameters=None,
        )
        return proxied_callable(config)

    def preload_plugin(self, plugin_name: str) -> bool:
        """Preload a specific plugin.

        Args:
            plugin_name: The name of the plugin to preload.

        Returns:
            True if the plugin was successfully preloaded, False otherwise.
        """
        return self.get(plugin_name) is not None

    def preload_all(self) -> Dict[str, bool]:
        """Preload all configured plugins.

        Returns:
            A dictionary mapping plugin names to preload success status.
        """
        results = {}
        for plugin_name in self._plugin_configs.keys():
            results[plugin_name] = self.preload_plugin(plugin_name)
        return results

    def get_initialization_stats(self) -> Dict[str, Any]:
        """Get lazy initialization statistics.

        Returns:
            A dictionary containing initialization statistics.
        """
        with self._lock:
            return {
                "total_configured": len(self._plugin_configs),
                "initialized": len(self._initialized_plugins),
                "failed": len(self._failed_plugins),
                "not_initialized": len(self._plugin_configs)
                - len(self._initialized_plugins)
                - len(self._failed_plugins),
                "initialized_plugins": list(self._initialized_plugins.keys()),
                "failed_plugins": dict(self._failed_plugins),
            }

    def get_all_initialized(self) -> Dict[str, Any]:
        """Alias for get_all_plugins() for backward compatibility.

        Returns:
            A dictionary mapping plugin names to their instances.
        """
        return self.get_all_plugins()

    def is_initialized(self, plugin_name: str) -> bool:
        """Check if plugin is initialized.

        Args:
            plugin_name: The name of the plugin to check.

        Returns:
            True if the plugin is initialized, False otherwise.
        """
        return self.get_plugin_state(plugin_name) == PluginState.READY


@contextmanager
def get_plugin_context(
    plugin_manager: "PluginManager",
    timeout: float = 30.0,
) -> AbstractPluginContext:
    """Get a plugin context with optional timeout.

    Args:
        plugin_manager: The plugin manager instance.
        timeout: Maximum time to wait for initialization.

    Yields:
        A plugin context instance.
    """
    context = EagerPluginContext(plugin_manager)

    if not plugin_manager.is_initialized():
        initialized = False
        start_time = time.time()

        while time.time() - start_time < timeout:
            if plugin_manager.is_initialized():
                initialized = True
                break
            time.sleep(0.1)

        if not initialized:
            logging.getLogger(__name__).warning(
                f"PluginManager not initialized within {timeout}s timeout"
            )

    try:
        yield context
    finally:
        pass


PluginContext = AbstractPluginContext


__all__ = [
    "PluginState",
    "PluginNotFoundError",
    "PluginInitializationTimeoutError",
    "AbstractPluginContext",
    "EagerPluginContext",
    "LazyPluginContext",
    "PluginContext",
    "get_plugin_context",
]
