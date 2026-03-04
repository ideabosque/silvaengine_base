#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Plugin context injector for automatic plugin injection."""

import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Optional

from .context import PluginContext

_context_storage: Optional["PluginContextStorage"] = None
_storage_lock = threading.Lock()


class PluginContextStorage:
    """Thread-local storage for plugin context."""

    def __init__(self):
        self._local = threading.local()

    def set(self, context: Optional["PluginContext"]) -> None:
        """Set the plugin context for current thread."""
        self._local.context = context

    def get(self) -> Optional["PluginContext"]:
        """Get the plugin context for current thread."""
        return getattr(self._local, "context", None)

    def clear(self) -> None:
        """Clear the plugin context for current thread."""
        if hasattr(self._local, "context"):
            del self._local.context

    def has_context(self) -> bool:
        """Check if context is set for current thread."""
        return hasattr(self._local, "context") and self._local.context is not None


class PluginContextDescriptor:
    """Descriptor for automatic plugin context injection."""

    def __get__(
        self, obj: Any, objtype: Optional[type] = None
    ) -> Optional["PluginContext"]:
        """Get the plugin context from thread-local storage."""
        if obj is None:
            return self

        storage = _get_context_storage()
        return storage.get()

    def __set__(self, obj: Any, value: Optional["PluginContext"]) -> None:
        """Set the plugin context in thread-local storage."""
        storage = _get_context_storage()
        storage.set(value)

    def __delete__(self, obj: Any) -> None:
        """Delete the plugin context from thread-local storage."""
        storage = _get_context_storage()
        storage.clear()


class PluginContextInjector:
    """Context manager for automatic plugin context injection and cleanup."""

    def __init__(self, context: Optional["PluginContext"] = None):
        """Initialize the plugin context injector."""
        self.context = context
        self._previous_context: Optional["PluginContext"] = None
        self._storage = _get_context_storage()

    def __enter__(self) -> "PluginContextInjector":
        """Enter the context and inject the plugin context."""
        self._previous_context = self._storage.get()
        self._storage.set(self.context)
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Exit the context and restore previous state."""
        self._storage.set(self._previous_context)


@contextmanager
def inject_plugin_context(context: Optional["PluginContext"] = None):
    """Context manager for plugin context injection."""
    storage = _get_context_storage()
    previous_context = storage.get()

    try:
        storage.set(context)
        yield
    finally:
        storage.set(previous_context)


def get_current_plugin_context() -> Optional["PluginContext"]:
    """Get the current plugin context from thread-local storage."""
    storage = _get_context_storage()
    return storage.get()


def set_current_plugin_context(context: Optional["PluginContext"]) -> None:
    """Set the current plugin context in thread-local storage."""
    storage = _get_context_storage()
    storage.set(context)


def clear_current_plugin_context() -> None:
    """Clear the current plugin context from thread-local storage."""
    storage = _get_context_storage()
    storage.clear()


def _get_context_storage() -> PluginContextStorage:
    """Get or create the global context storage."""
    global _context_storage
    if _context_storage is None:
        with _storage_lock:
            if _context_storage is None:
                _context_storage = PluginContextStorage()
    return _context_storage


__all__ = [
    "PluginContextStorage",
    "PluginContextDescriptor",
    "PluginContextInjector",
    "inject_plugin_context",
    "get_current_plugin_context",
    "set_current_plugin_context",
    "clear_current_plugin_context",
]
