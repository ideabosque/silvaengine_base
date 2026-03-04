#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Lazy plugin context for on-demand plugin initialization."""

import logging
import threading
import time
from typing import Any, Dict, Optional, Set

from silvaengine_utility import Invoker

from .context import PluginNotFoundError


class LazyPluginContext:
    """Lazy plugin context for on-demand initialization."""

    def __init__(
        self,
        plugin_manager: Any,
        plugin_configs: Dict[str, Dict[str, Any]],
        logger: Optional[logging.Logger] = None,
        initialization_timeout: float = 30.0,
    ):
        """Initialize lazy plugin context."""
        self._plugin_manager = plugin_manager
        self._plugin_configs = plugin_configs
        self._logger = logger or logging.getLogger(__name__)
        self._initialization_timeout = initialization_timeout

        self._initialized_plugins: Dict[str, Any] = {}
        self._initializing_plugins: Set[str] = set()
        self._failed_plugins: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._init_locks: Dict[str, threading.Lock] = {}

    def get(self, plugin_name: str) -> Optional[Any]:
        """Get plugin instance, initializing on first access."""
        if not plugin_name:
            self._logger.warning("Attempted to get plugin with empty name")
            return None

        plugin_name = str(plugin_name).strip().lower()

        with self._lock:
            if plugin_name in self._initialized_plugins:
                return self._initialized_plugins[plugin_name]

            if plugin_name in self._failed_plugins:
                self._logger.debug(
                    f"Plugin '{plugin_name}' previously failed initialization"
                )
                return None

        return self._initialize_on_demand(plugin_name)

    def _initialize_on_demand(self, plugin_name: str) -> Optional[Any]:
        """Initialize plugin on first access."""
        with self._lock:
            if plugin_name not in self._init_locks:
                self._init_locks[plugin_name] = threading.Lock()
            init_lock = self._init_locks[plugin_name]

        with init_lock:
            with self._lock:
                if plugin_name in self._initialized_plugins:
                    return self._initialized_plugins[plugin_name]

                if plugin_name in self._failed_plugins:
                    return None

            config = self._plugin_configs.get(plugin_name)
            if not config:
                self._logger.warning(f"Plugin '{plugin_name}' not found in configuration")
                return None

            self._logger.info(f"Lazy initializing plugin '{plugin_name}'")

            try:
                manager = self._do_initialize_plugin(plugin_name, config)

                with self._lock:
                    self._initialized_plugins[plugin_name] = manager

                self._logger.info(f"Plugin '{plugin_name}' lazy initialized successfully")
                return manager

            except Exception as e:
                error_msg = str(e)
                with self._lock:
                    self._failed_plugins[plugin_name] = error_msg

                self._logger.error(f"Failed to lazy initialize plugin '{plugin_name}': {error_msg}")
                return None

    def _do_initialize_plugin(
        self, plugin_name: str, config: Dict[str, Any]
    ) -> Any:
        """Perform actual plugin initialization."""
        module_name = config.get("module_name", "")
        function_name = config.get("function_name", "init")
        class_name = config.get("class_name")
        plugin_config = config.get("config", {})

        if not module_name:
            raise ValueError(f"Plugin '{plugin_name}' missing module_name")

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._invoke_initialization,
                module_name,
                function_name,
                class_name,
                plugin_config,
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
    ) -> Any:
        """Invoke plugin initialization function."""
        proxied_callable = Invoker.resolve_proxied_callable(
            module_name=module_name,
            function_name=function_name,
            class_name=class_name,
            constructor_parameters=None,
        )

        return proxied_callable(config)

    def get_or_raise(self, plugin_name: str) -> Any:
        """Get plugin instance or raise exception."""
        plugin = self.get(plugin_name)
        if plugin is None:
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' not found or failed to initialize"
            )
        return plugin

    def get_all_initialized(self) -> Dict[str, Any]:
        """Get all initialized plugins."""
        with self._lock:
            return self._initialized_plugins.copy()

    def is_initialized(self, plugin_name: str) -> bool:
        """Check if plugin is initialized."""
        plugin_name = str(plugin_name).strip().lower()
        with self._lock:
            return plugin_name in self._initialized_plugins

    def get_initialization_stats(self) -> Dict[str, Any]:
        """Get lazy initialization statistics."""
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

    def preload_plugin(self, plugin_name: str) -> bool:
        """Preload a specific plugin."""
        return self.get(plugin_name) is not None

    def preload_all(self) -> Dict[str, bool]:
        """Preload all configured plugins."""
        results = {}
        for plugin_name in self._plugin_configs.keys():
            results[plugin_name] = self.preload_plugin(plugin_name)
        return results
