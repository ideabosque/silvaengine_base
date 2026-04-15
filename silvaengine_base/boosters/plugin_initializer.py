#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Resources Handler for silvaengine_base.

This module provides the plugin management functionality that was previously
in the Resources class. All plugin-related operations are now centralized here.

[REFACTORED] This module now reuses AsyncPluginInitializer for all async
initialization functionality, eliminating code duplication.

Migration Notes:
- Internal async initialization is now delegated to AsyncPluginInitializer
- All public APIs remain unchanged for backward compatibility
"""

import logging
import threading
from typing import Any, Callable, Dict, Optional, Set

from .plugin import PluginContext, PluginManager
from .plugin.async_initializer import (
    AsyncPluginInitializer,
    InitializationState,
    InitializationTracker,
    PluginFuture,
)
from .plugin.config_manager import get_config_manager

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
    "private_key",
    "client_secret",
    "client_id",
    "bearer",
    "jwt",
    "session",
    "cookie",
    "signature",
    "hash",
    "salt",
    "encrypt",
    "decrypt",
    "certificate",
    "cert",
    "pem",
    "ssl",
    "tls",
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
        is_sensitive = any(pattern in key_lower for pattern in SENSITIVE_FIELD_PATTERNS)

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

    [REFACTORED] Now uses AsyncPluginInitializer internally for all async
    operations, eliminating duplicate code while maintaining the same public API.
    """

    _instance: Optional["PluginInitializer"] = None
    _lock = threading.Lock()
    _config: Dict[str, Any] = {}
    _plugin_manager: Optional[PluginManager] = None
    _plugin_context: Optional[PluginContext] = None
    _initialization_callback: Optional[Callable[[Dict[str, bool]], None]] = None
    _logger: Optional[logging.Logger] = None

    # [REFACTORED] Use AsyncPluginInitializer for async operations
    _async_initializer: Optional[AsyncPluginInitializer] = None

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
    def _get_async_initializer(cls) -> AsyncPluginInitializer:
        """Get or create the AsyncPluginInitializer instance.

        [REFACTORED] Centralized access to AsyncPluginInitializer.

        Returns:
            AsyncPluginInitializer instance.
        """
        if cls._async_initializer is None or cls._async_initializer.is_shutdown():
            if cls._plugin_manager is None:
                cls._plugin_manager = PluginManager(logger=cls.get_logger())

            cls._async_initializer = AsyncPluginInitializer(
                plugin_manager=cls._plugin_manager,
                logger=cls.get_logger(),
            )
        return cls._async_initializer

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

        This is the unified method for plugin initialization, supporting both
        synchronous and asynchronous initialization modes.

        Args:
            config: Configuration dictionary.
        """
        cls._config = config
        cls._logger.info(f"Setting up plugins: {sanitize_config(config)}")

        cls._apply_config_to_manager(config)

        config_manager = get_config_manager(config.get("plugin_settings", {}))

        if config_manager.get_async_initialization():
            cls._initialize_plugins_async(config)
        else:
            if cls._plugin_manager.initialize(setting=config):
                cls._plugin_context = cls._plugin_manager.get_context()

    @classmethod
    def _initialize_plugins_async(cls, config: Dict[str, Any]) -> None:
        """Initialize plugins asynchronously for non-blocking cold start.

        [FIXED] Removed immediate get_context() call to avoid timeout warning during
        async initialization startup. The context will be obtained lazily on first
        access via get_plugin_context().

        [FIXED v2] Set PluginManager initialization flags immediately after starting
        background initialization to prevent get_context() from waiting indefinitely.
        The _is_initialized flag indicates that initialization has STARTED (not completed),
        and _initialized_event is set to allow get_context() to proceed without timeout.

        Args:
            config: Configuration dictionary.
        """
        try:
            async_initializer = cls._get_async_initializer()
            plugins_config = config.get("plugins", [])
            timeout = config.get("plugin_settings", {}).get(
                "global_init_timeout", 120.0
            )

            async_initializer.initialize_background(
                plugins_config=plugins_config,
                timeout=timeout,
            )

            # [FIXED v2] Set initialization flags immediately after starting background init
            # This is critical: get_context() checks _is_initialized and waits on _initialized_event
            # Without setting these flags, get_context() would wait for the full timeout period
            # even though background initialization has already started.
            if cls._plugin_manager is not None:
                cls._plugin_manager._is_initialized = True
                cls._plugin_manager._initialized_event.set()

            # [FIXED] Don't get context immediately - it will be obtained on first access
            # via get_plugin_context(). This avoids the 10s timeout warning during async
            # startup when initialization is still in progress.
            cls._logger.info(
                "Plugin initialization started asynchronously (non-blocking)"
            )

        except Exception as e:
            cls._logger.error(f"Failed to start async initialization: {e}")
            # Fallback to synchronous initialization with timeout protection
            cls._fallback_to_sync_init(config)

    @classmethod
    def _fallback_to_sync_init(cls, config: Dict[str, Any]) -> None:
        """Fallback to synchronous initialization with timeout protection.

        Args:
            config: Configuration dictionary.
        """
        import concurrent.futures

        timeout = config.get("plugin_settings", {}).get("global_init_timeout", 30.0)

        def do_sync_init():
            return cls._plugin_manager.initialize(setting=config)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(do_sync_init)
                success = future.result(timeout=timeout)

                if success:
                    cls._plugin_context = cls._plugin_manager.get_context()
                    cls._logger.info("Synchronous fallback initialization succeeded")
                else:
                    cls._logger.error("Synchronous fallback initialization failed")

        except concurrent.futures.TimeoutError:
            cls._logger.error(f"Synchronous initialization timed out after {timeout}s")
        except Exception as e:
            cls._logger.error(f"Synchronous initialization error: {e}")

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

        [REFACTORED] Now retrieves status from AsyncPluginInitializer when available.

        Returns:
            Dictionary containing initialization status information.
        """
        if cls._async_initializer is not None:
            return cls._async_initializer.get_initialization_summary()

        if cls._plugin_manager is None:
            return {"initialized": False, "status": "not_started"}

        return cls._plugin_manager.get_initialization_status()

    @classmethod
    def wait_for_initialization(cls, timeout: float = 120.0) -> Dict[str, bool]:
        """Wait for all plugins to complete initialization.

        [REFACTORED] Now delegates to AsyncPluginInitializer.wait_all().

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Dictionary mapping plugin types to success status.
        """
        if cls._async_initializer is not None:
            return cls._async_initializer.wait_all(timeout=timeout)

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

        [FIXED] Added lazy initialization support for async initialization mode.
        If the context is None and async initialization is in progress,
        it will wait for the context to be ready with a proper timeout.

        Returns:
            PluginContext instance or None if not initialized.
        """
        # [FIXED] Lazy initialization for async mode - get context on first access
        if cls._plugin_context is None and cls._plugin_manager is not None:
            # Check if async initialization is active
            if cls._async_initializer is not None and not cls._async_initializer.is_shutdown():
                # Async initialization in progress - get context with longer timeout
                # to avoid false timeout warnings during normal async startup
                cls._plugin_context = cls._plugin_manager.get_context(timeout=30.0)
            elif cls._plugin_manager.is_initialized():
                # Synchronous initialization completed - get context normally
                cls._plugin_context = cls._plugin_manager.get_context(timeout=10.0)

        return cls._plugin_context

    @classmethod
    def wait_for_plugins_ready(cls, timeout: float = 30.0) -> bool:
        """Wait for plugins to be ready with detailed logging.

        This method ensures that critical plugins (like connection pool)
        are fully initialized. It provides detailed logging about
        initialization progress.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if all plugins are ready, False if timeout or error.
        """
        try:
            result = cls.wait_for_initialization(timeout=timeout)
            ready_count = sum(1 for v in result.values() if v)
            total_count = len(result)

            if ready_count == total_count:
                cls.get_logger().info(
                    f"All {total_count} plugins initialized successfully"
                )
                return True
            else:
                cls.get_logger().warning(
                    f"Plugin initialization incomplete: {ready_count}/{total_count} ready"
                )
                return False

        except Exception as e:
            cls.get_logger().error(f"Error waiting for plugins: {e}")
            return False

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
    def reset(cls, wait: bool = True, timeout: float = 5.0) -> None:
        """Reset the handler state with proper resource cleanup.

        Args:
            wait: Whether to wait for async operations to complete
            timeout: Maximum time to wait for cleanup in seconds
        """
        with cls._lock:
            # Shutdown async initializer with timeout
            if cls._async_initializer is not None:
                try:
                    cls._async_initializer.shutdown(wait=wait, timeout=timeout)
                except Exception as e:
                    cls._logger.warning(f"Error shutting down async initializer: {e}")
                finally:
                    cls._async_initializer = None

            cls._config = {}

            # Reset plugin manager with proper cleanup
            if cls._plugin_manager is not None:
                try:
                    cls._plugin_manager.reset_instance()
                except Exception as e:
                    cls._logger.warning(f"Error resetting plugin manager: {e}")
                finally:
                    cls._plugin_manager = None

            cls._plugin_context = None
            cls._initialization_callback = None
            cls._instance = None

            cls._logger.info("PluginInitializer reset completed")

    @classmethod
    def get_async_initializer(cls) -> Optional[AsyncPluginInitializer]:
        """Get the AsyncPluginInitializer instance.

        [NEW] Provides access to the underlying async initializer for advanced use cases.

        Returns:
            AsyncPluginInitializer instance or None.
        """
        return cls._async_initializer

    @classmethod
    def get_initialization_tracker(cls) -> Optional[InitializationTracker]:
        """Get the InitializationTracker instance.

        [NEW] Provides access to the initialization tracker for status monitoring.

        Returns:
            InitializationTracker instance or None.
        """
        if cls._async_initializer is not None:
            return cls._async_initializer.get_tracker()
        return None


__all__ = [
    "PluginInitializer",
    "sanitize_config",
    "SENSITIVE_FIELD_PATTERNS",
]
