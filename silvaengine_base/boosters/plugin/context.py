#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Plugin context manager for silvaengine_base."""

import logging
import threading
import time
from contextlib import contextmanager
from enum import Enum
from typing import Any, Dict, Optional

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


class PluginContext:
    """Context manager for plugin access."""

    def __init__(self, plugin_manager: "PluginManager") -> None:
        """Initialize plugin context."""
        self._plugin_manager = plugin_manager
        self._logger = logging.getLogger(__name__)
        self._lock = threading.RLock()

    def __enter__(self) -> "PluginContext":
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
        """Get plugin instance by name."""
        if not plugin_name:
            self._logger.warning("Attempted to get plugin with empty name")
            return None

        plugin_name = str(plugin_name).strip().lower()

        with self._lock:
            initialized_objects = self._plugin_manager.get_initialized_objects()
            plugin_data = initialized_objects.get(plugin_name)

            if plugin_data is None:
                self._logger.debug(
                    f"Plugin '{plugin_name}' not found or not initialized"
                )
                return None

            return plugin_data.get("manager")

    def get_or_raise(self, plugin_name: str) -> Any:
        """Get plugin instance or raise an exception."""
        if not plugin_name:
            raise PluginNotFoundError("Plugin name cannot be empty")

        plugin_name = str(plugin_name).strip().lower()

        with self._lock:
            initialized_objects = self._plugin_manager.get_initialized_objects()
            plugin_data = initialized_objects.get(plugin_name)

            if plugin_data is None:
                error_msg = f"Plugin '{plugin_name}' not found or not initialized"
                self._logger.error(error_msg)
                raise PluginNotFoundError(error_msg)

            return plugin_data.get("manager")

    def wait_for_plugin(self, plugin_name: str, timeout: float = 30.0) -> bool:
        """Wait for plugin to be initialized."""
        if not plugin_name:
            self._logger.warning("Attempted to wait for plugin with empty name")
            return False

        if timeout <= 0:
            self._logger.warning(
                f"Invalid timeout value: {timeout}, using default 30.0"
            )
            timeout = 30.0

        plugin_name = str(plugin_name).strip().lower()
        start_time = time.time()

        self._logger.debug(f"Waiting for plugin '{plugin_name}' (timeout: {timeout}s)")

        while True:
            with self._lock:
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

    def get_all_plugins(self) -> Dict[str, Any]:
        """Get all initialized plugins."""
        with self._lock:
            initialized_objects = self._plugin_manager.get_initialized_objects()
            result: Dict[str, Any] = {}

            for plugin_name, plugin_data in initialized_objects.items():
                result[plugin_name] = plugin_data.get("manager")

            self._logger.debug(f"Retrieved {len(result)} initialized plugins")
            return result

    def get_plugin_state(self, plugin_name: str) -> PluginState:
        """Get the state of a specific plugin."""
        if not plugin_name:
            return PluginState.FAILED

        plugin_name = str(plugin_name).strip().lower()

        with self._lock:
            initialized_objects = self._plugin_manager.get_initialized_objects()

            if plugin_name not in initialized_objects:
                return PluginState.INITIALIZING

            plugin_data = initialized_objects.get(plugin_name)
            if plugin_data is None:
                return PluginState.FAILED

            return PluginState.READY


@contextmanager
def get_plugin_context(
    plugin_manager: PluginManager,
    timeout: float = 30.0,
) -> "PluginContext":
    """Get a plugin context with optional timeout."""
    context = PluginContext(plugin_manager)

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
