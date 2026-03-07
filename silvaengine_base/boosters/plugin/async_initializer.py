#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Asynchronous plugin initialization framework for silvaengine_base.

This module provides a non-blocking plugin initialization system with:
- Initialization state tracking and status management
- Thread-safe initialization tracker with event-based signaling
- PluginFuture for async-style result retrieval
- AsyncPluginInitializer for background plugin initialization
"""

import atexit
import concurrent.futures
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

if TYPE_CHECKING:
    from . import PluginManager


class InitializationState(Enum):
    """Enumeration of plugin initialization states."""

    PENDING = "pending"
    INITIALIZING = "initializing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class InitializationStatus:
    """Data class representing the initialization status of a plugin."""

    plugin_type: str
    state: InitializationState
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    error_type: Optional[str] = None

    def get_duration(self) -> Optional[float]:
        """Calculate the duration of initialization.

        Returns:
            The duration in seconds if both start and end times are available,
            None otherwise.
        """
        if self.start_time is not None and self.end_time is not None:
            return self.end_time - self.start_time
        return None

    def is_complete(self) -> bool:
        """Check if initialization is complete (either ready or failed).

        Returns:
            True if the initialization has completed, False otherwise.
        """
        return self.state in (InitializationState.READY, InitializationState.FAILED)


class InitializationTracker:
    """Thread-safe tracker for plugin initialization states.

    This class provides a centralized mechanism for tracking the initialization
    status of multiple plugins with event-based signaling for non-blocking
    wait operations.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        """Initialize the initialization tracker.

        Args:
            logger: Optional logger instance for logging.
        """
        self._logger = logger or logging.getLogger(__name__)
        self._statuses: Dict[str, InitializationStatus] = {}
        self._events: Dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def start_initialization(self, plugin_type: str) -> None:
        """Mark a plugin as starting initialization.

        Args:
            plugin_type: The type identifier of the plugin.
        """
        with self._lock:
            if plugin_type not in self._events:
                self._events[plugin_type] = threading.Event()

            self._statuses[plugin_type] = InitializationStatus(
                plugin_type=plugin_type,
                state=InitializationState.INITIALIZING,
                start_time=time.time(),
            )

        self._logger.debug(f"Started initialization for plugin '{plugin_type}'")

    def complete_initialization(self, plugin_type: str) -> None:
        """Mark a plugin as successfully initialized.

        Args:
            plugin_type: The type identifier of the plugin.
        """
        with self._lock:
            if plugin_type in self._statuses:
                status = self._statuses[plugin_type]
                status.state = InitializationState.READY
                status.end_time = time.time()

            if plugin_type in self._events:
                self._events[plugin_type].set()

        self._logger.debug(f"Completed initialization for plugin '{plugin_type}'")

    def fail_initialization(
        self, plugin_type: str, error: Exception
    ) -> None:
        """Mark a plugin as failed initialization.

        Args:
            plugin_type: The type identifier of the plugin.
            error: The exception that caused the failure.
        """
        with self._lock:
            if plugin_type in self._statuses:
                status = self._statuses[plugin_type]
                status.state = InitializationState.FAILED
                status.end_time = time.time()
                status.error = str(error)
                status.error_type = type(error).__name__

            if plugin_type in self._events:
                self._events[plugin_type].set()

        self._logger.error(
            f"Failed initialization for plugin '{plugin_type}': {error}"
        )

    def get_status(self, plugin_type: str) -> InitializationStatus:
        """Get the initialization status for a plugin.

        Args:
            plugin_type: The type identifier of the plugin.

        Returns:
            The initialization status, defaults to PENDING if not tracked.
        """
        with self._lock:
            if plugin_type in self._statuses:
                return self._statuses[plugin_type]

            return InitializationStatus(
                plugin_type=plugin_type,
                state=InitializationState.PENDING,
            )

    def get_all_status(self) -> Dict[str, InitializationStatus]:
        """Get all initialization statuses.

        Returns:
            A dictionary mapping plugin types to their initialization status.
        """
        with self._lock:
            return dict(self._statuses)

    def wait_for_initialization(
        self, plugin_type: str, timeout: float = 30.0
    ) -> bool:
        """Wait for a plugin to complete initialization.

        This method uses event-based signaling for efficient non-busy waiting.

        Args:
            plugin_type: The type identifier of the plugin.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if the plugin completed initialization (success or failure),
            False if timeout occurred.
        """
        event: Optional[threading.Event] = None

        with self._lock:
            if plugin_type in self._statuses:
                status = self._statuses[plugin_type]
                if status.is_complete():
                    return True

            if plugin_type not in self._events:
                self._events[plugin_type] = threading.Event()

            event = self._events[plugin_type]

        return event.wait(timeout=timeout)

    def wait_for_all(self, timeout: float = 120.0) -> Dict[str, bool]:
        """Wait for all tracked plugins to complete initialization.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            A dictionary mapping plugin types to their success status.
            True indicates successful initialization, False indicates failure or timeout.
        """
        results: Dict[str, bool] = {}
        plugin_types: List[str] = []

        with self._lock:
            plugin_types = list(self._statuses.keys())

        end_time = time.time() + timeout

        for plugin_type in plugin_types:
            remaining = end_time - time.time()
            if remaining <= 0:
                results[plugin_type] = False
                continue

            completed = self.wait_for_initialization(
                plugin_type, timeout=remaining
            )

            if not completed:
                results[plugin_type] = False
            else:
                with self._lock:
                    status = self._statuses.get(plugin_type)
                    results[plugin_type] = (
                        status.state == InitializationState.READY
                        if status else False
                    )

        return results

    def register_plugin(self, plugin_type: str) -> None:
        """Register a plugin for tracking before initialization starts.

        Args:
            plugin_type: The type identifier of the plugin.
        """
        with self._lock:
            if plugin_type not in self._statuses:
                self._statuses[plugin_type] = InitializationStatus(
                    plugin_type=plugin_type,
                    state=InitializationState.PENDING,
                )

            if plugin_type not in self._events:
                self._events[plugin_type] = threading.Event()

    def is_ready(self, plugin_type: str) -> bool:
        """Check if a plugin is ready.

        Args:
            plugin_type: The type identifier of the plugin.

        Returns:
            True if the plugin is ready, False otherwise.
        """
        with self._lock:
            if plugin_type in self._statuses:
                return self._statuses[plugin_type].state == InitializationState.READY
            return False

    def is_failed(self, plugin_type: str) -> bool:
        """Check if a plugin has failed initialization.

        Args:
            plugin_type: The type identifier of the plugin.

        Returns:
            True if the plugin failed, False otherwise.
        """
        with self._lock:
            if plugin_type in self._statuses:
                return self._statuses[plugin_type].state == InitializationState.FAILED
            return False

    def reset(self, plugin_type: str) -> None:
        """Reset the initialization status for a plugin.

        Args:
            plugin_type: The type identifier of the plugin.
        """
        with self._lock:
            if plugin_type in self._statuses:
                del self._statuses[plugin_type]

            if plugin_type in self._events:
                self._events[plugin_type].clear()


class PluginFuture:
    """Future-like object for asynchronous plugin initialization.

    This class provides a non-blocking interface to check and retrieve
    plugin initialization results, similar to concurrent.futures.Future
    but specifically designed for plugin management.
    """

    def __init__(
        self,
        plugin_type: str,
        tracker: InitializationTracker,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize the plugin future.

        Args:
            plugin_type: The type identifier of the plugin.
            tracker: The initialization tracker instance.
            logger: Optional logger instance for logging.
        """
        self._plugin_type = plugin_type
        self._tracker = tracker
        self._logger = logger or logging.getLogger(__name__)
        self._done_callbacks: List[Callable[[Any], None]] = []
        self._callback_lock = threading.Lock()
        self._result: Optional[Any] = None
        self._result_lock = threading.Lock()
        self._completion_time: Optional[float] = None

    def is_done(self) -> bool:
        """Check if initialization is complete.

        Returns:
            True if initialization is complete (ready or failed), False otherwise.
        """
        status = self._tracker.get_status(self._plugin_type)
        return status.is_complete()

    def is_ready(self) -> bool:
        """Check if initialization succeeded.

        Returns:
            True if the plugin is ready, False otherwise.
        """
        return self._tracker.is_ready(self._plugin_type)

    def is_failed(self) -> bool:
        """Check if initialization failed.

        Returns:
            True if the plugin failed initialization, False otherwise.
        """
        return self._tracker.is_failed(self._plugin_type)

    def get(self, timeout: Optional[float] = None) -> Any:
        """Get the plugin result, optionally waiting for completion.

        Note: This method will block if the plugin is not yet initialized.
        Use is_done() to check completion status before calling this method
        for truly non-blocking operation.

        Args:
            timeout: Maximum time to wait in seconds. None means no timeout.

        Returns:
            The plugin result if initialization succeeded.

        Raises:
            TimeoutError: If timeout occurred while waiting.
            RuntimeError: If initialization failed.
        """
        if not self.is_done():
            if timeout is None:
                timeout = DEFAULT_PLUGIN_INIT_TIMEOUT

            completed = self._tracker.wait_for_initialization(
                self._plugin_type, timeout=timeout
            )

            if not completed:
                raise TimeoutError(
                    f"Timeout waiting for plugin '{self._plugin_type}' initialization"
                )

        status = self._tracker.get_status(self._plugin_type)

        if status.state == InitializationState.FAILED:
            raise RuntimeError(
                f"Plugin '{self._plugin_type}' initialization failed: "
                f"{status.error or 'Unknown error'}"
            )

        with self._result_lock:
            return self._result

    def get_or_none(self) -> Optional[Any]:
        """Get the plugin result without blocking.

        Returns:
            The plugin result if ready, None otherwise.
        """
        if not self.is_ready():
            return None

        with self._result_lock:
            return self._result

    def add_done_callback(self, callback: Callable[[Any], None]) -> None:
        """Add a callback to be executed when initialization completes.

        The callback will be invoked immediately if initialization is already
        complete, otherwise it will be stored for later invocation.

        Args:
            callback: A callable that accepts the plugin result.
        """
        with self._callback_lock:
            if self.is_done():
                try:
                    with self._result_lock:
                        callback(self._result)
                except Exception as exception:
                    self._logger.error(
                        f"Error executing done callback for "
                        f"plugin '{self._plugin_type}': {exception}"
                    )
            else:
                self._done_callbacks.append(callback)

    def set_result(self, result: Any) -> None:
        """Set the result of the plugin initialization.

        [OPTIMIZATION] Track completion time for memory cleanup
        
        This method is called internally by AsyncPluginInitializer.

        Args:
            result: The plugin initialization result.
        """
        import time
        
        with self._result_lock:
            self._result = result
            self._completion_time = time.time()

        with self._callback_lock:
            callbacks = list(self._done_callbacks)
            self._done_callbacks.clear()

        for callback in callbacks:
            try:
                with self._result_lock:
                    callback(self._result)
            except Exception as exception:
                self._logger.error(
                    f"Error executing done callback for "
                    f"plugin '{self._plugin_type}': {exception}"
                )

    @property
    def plugin_type(self) -> str:
        """Get the plugin type identifier.

        Returns:
            The plugin type string.
        """
        return self._plugin_type


class AsyncPluginInitializer:
    """Asynchronous plugin initializer with non-blocking operations.

    This class provides a framework for initializing plugins in background
    threads while maintaining non-blocking semantics for the caller.
    """

    def __init__(
        self,
        plugin_manager: "PluginManager",
        logger: Optional[logging.Logger] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        """Initialize the async plugin initializer.

        Args:
            plugin_manager: The plugin manager instance.
            logger: Optional logger instance for logging.
            max_workers: Maximum number of worker threads. None for auto.
        """
        self._plugin_manager = plugin_manager
        self._logger = logger or logging.getLogger(__name__)
        self._max_workers = max_workers

        self._tracker = InitializationTracker(logger=self._logger)
        self._futures: Dict[str, PluginFuture] = {}
        self._executor_name = "async_plugin_initializer"
        self._executor_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._active_tasks: Set[str] = set()
        self._active_tasks_lock = threading.Lock()

        _register_initializer(self)

    def initialize_background(
        self,
        plugins_config: List[Dict[str, Any]],
        timeout: float = 120.0,
    ) -> None:
        """Initialize plugins in background threads without blocking.

        This method starts background initialization for all configured plugins
        and returns immediately. Use wait_all() or individual futures to check
        completion status.

        Args:
            plugins_config: List of plugin configuration dictionaries.
            timeout: Maximum time for initialization in seconds (used per plugin).
        """
        if self._shutdown_event.is_set():
            self._logger.warning(
                "Cannot initialize plugins: initializer has been shut down"
            )
            return

        with self._executor_lock:
            from .thread_pool_manager import get_thread_pool_manager
            executor = get_thread_pool_manager().get_executor(
                self._executor_name,
                max_workers=self._max_workers,
            )

        for config in plugins_config:
            plugin_type = config.get("type", "")
            if not plugin_type:
                self._logger.warning("Skipping plugin config without 'type' field")
                continue

            self._tracker.register_plugin(plugin_type)

            future = PluginFuture(
                plugin_type=plugin_type,
                tracker=self._tracker,
                logger=self._logger,
            )
            self._futures[plugin_type] = future

            with self._active_tasks_lock:
                self._active_tasks.add(plugin_type)

            from .thread_pool_manager import get_thread_pool_manager
            executor = get_thread_pool_manager().get_executor(
                self._executor_name,
                max_workers=self._max_workers,
            )
            executor.submit(
                self._initialize_plugin_task,
                plugin_type,
                config,
                timeout,
            )

        self._logger.info(
            f"Started background initialization for {len(plugins_config)} plugins"
        )

    def initialize_async(
        self,
        plugins_config: List[Dict[str, Any]],
    ) -> Dict[str, PluginFuture]:
        """Initialize plugins asynchronously and return futures.

        This method starts background initialization and immediately returns
        PluginFuture objects for each plugin, allowing the caller to check
        status or wait for completion as needed.

        Args:
            plugins_config: List of plugin configuration dictionaries.

        Returns:
            A dictionary mapping plugin types to their PluginFuture objects.
        """
        if self._shutdown_event.is_set():
            self._logger.warning(
            "Cannot initialize plugins: initializer has been shut down"
        )
        return {}

        for config in plugins_config:
            plugin_type = config.get("type", "")
            if not plugin_type:
                self._logger.warning("Skipping plugin config without 'type' field")
                continue

            self._tracker.register_plugin(plugin_type)

            future = PluginFuture(
                plugin_type=plugin_type,
                tracker=self._tracker,
                logger=self._logger,
            )
            self._futures[plugin_type] = future

            with self._active_tasks_lock:
                self._active_tasks.add(plugin_type)

            from .thread_pool_manager import get_thread_pool_manager
            executor = get_thread_pool_manager().get_executor(
                self._executor_name,
                max_workers=self._max_workers,
            )
            executor.submit(
                self._initialize_plugin_task,
                plugin_type,
                config,
            )

        self._logger.info(
            f"Started async initialization for {len(plugins_config)} plugins"
        )

        return dict(self._futures)

    def get_future(self, plugin_type: str) -> Optional[PluginFuture]:
        """Get the PluginFuture for a specific plugin.

        Args:
            plugin_type: The type identifier of the plugin.

        Returns:
            The PluginFuture if the plugin was registered, None otherwise.
        """
        return self._futures.get(plugin_type)

    def get_all_futures(self) -> Dict[str, PluginFuture]:
        """Get all PluginFuture objects.

        Returns:
            A dictionary mapping plugin types to their PluginFuture objects.
        """
        return dict(self._futures)

    def wait_all(self, timeout: float = 120.0) -> Dict[str, bool]:
        """Wait for all plugins to complete initialization.

        Note: This method blocks until all plugins complete or timeout occurs.
        For truly non-blocking operation, use get_all_futures() and check
        individual future status.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            A dictionary mapping plugin types to their completion status.
        """
        return self._tracker.wait_for_all(timeout=timeout)

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the initializer and release resources.

        Args:
            wait: If True, wait for pending tasks to complete.
        """
        self._shutdown_event.set()

        with self._executor_lock:
            if self._executor is not None:
                self._executor.shutdown(wait=wait)
                self._executor = None

        _unregister_initializer(self)

        self._logger.info("AsyncPluginInitializer has been shut down")

    def is_shutdown(self) -> bool:
        """Check if the initializer has been shut down.

        Returns:
            True if shutdown has been called, False otherwise.
        """
        return self._shutdown_event.is_set()

    def get_tracker(self) -> InitializationTracker:
        """Get the initialization tracker.

        Returns:
            The InitializationTracker instance.
        """
        return self._tracker

    def get_active_tasks(self) -> Set[str]:
        """Get the set of currently active initialization tasks.

        Returns:
            A set of plugin types currently being initialized.
        """
        with self._active_tasks_lock:
            return set(self._active_tasks)

    def cleanup_completed_futures(self, max_age_seconds: float = 300.0) -> int:
        """Clean up completed futures to prevent memory growth.
        
        [OPTIMIZATION] Memory management for completed futures
        
        Problem: _futures dictionary grows indefinitely as plugins are initialized,
        potentially causing memory issues in long-running applications.
        
        Solution: Periodically clean up completed futures that are older than
        the specified age threshold.
        
        Performance Impact:
        - Memory usage: Prevents unbounded growth of _futures cache
        - CPU overhead: Minimal, only called when cleanup is needed
        
        Thread Safety: Uses existing locks for thread-safe access.
        
        Args:
            max_age_seconds: Maximum age in seconds for keeping completed futures.
                            Default is 300 seconds (5 minutes).
                            
        Returns:
            Number of futures cleaned up.
            
        @since 2.0.0
        """
        import time
        from .async_initializer import InitializationState
        
        cleaned = 0
        current_time = time.time()
        
        with self._executor_lock:
            to_remove = []
            
            for plugin_type, future in self._futures.items():
                status = self._tracker.get_status(plugin_type)
                
                if status.state in (InitializationState.READY, InitializationState.FAILED):
                    if hasattr(future, '_completion_time'):
                        if current_time - future._completion_time > max_age_seconds:
                            to_remove.append(plugin_type)
            
            for plugin_type in to_remove:
                del self._futures[plugin_type]
                cleaned += 1
        
        if cleaned > 0:
            self._logger.debug(f"Cleaned up {cleaned} completed futures")
        
        return cleaned

    def _initialize_plugin_task(
        self,
        plugin_type: str,
        config: Dict[str, Any],
        timeout: float,
    ) -> None:
        """Internal method to initialize a single plugin.

        This method is executed in a worker thread.

        Args:
            plugin_type: The type identifier of the plugin.
            config: The plugin configuration dictionary.
            timeout: Maximum time for initialization in seconds.
        """
        if self._shutdown_event.is_set():
            self._logger.warning(
                f"Skipping initialization for '{plugin_type}': initializer shut down"
            )
            return

        self._tracker.start_initialization(plugin_type)

        try:
            result = self._do_initialize(plugin_type, config, timeout)

            future = self._futures.get(plugin_type)
            if future is not None:
                future.set_result(result)

            self._tracker.complete_initialization(plugin_type)

            self._logger.info(
                f"Successfully initialized plugin '{plugin_type}'"
            )

        except Exception as exception:
            self._tracker.fail_initialization(plugin_type, exception)

            self._logger.error(
                f"Failed to initialize plugin '{plugin_type}': {exception}"
            )

        finally:
            with self._active_tasks_lock:
                self._active_tasks.discard(plugin_type)

    def _do_initialize(
        self,
        plugin_type: str,
        config: Dict[str, Any],
        timeout: float,
    ) -> Any:
        """Perform the actual plugin initialization.
        
        [OPTIMIZATION] Unified initialization logic using PluginInitializerUtils
        
        This method now uses the centralized PluginInitializerUtils for
        consistent initialization behavior across all modules.
        
        Args:
            plugin_type: The type identifier of the plugin.
            config: The plugin configuration dictionary.
            timeout: Maximum time for initialization in seconds.

        Returns:
            The initialized plugin instance.

        Raises:
            Exception: If initialization fails.
        """
        from .initializer_utils import PluginInitializerUtils, PluginInitializationError
        
        module_name = config.get("module_name", "")
        function_name = config.get("function_name", "init")
        class_name = config.get("class_name")
        plugin_config = config.get("config", {})

        if not module_name:
            raise ValueError(f"Plugin '{plugin_type}' missing module_name")

        success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
            module_name=module_name,
            function_name=function_name,
            plugin_config=plugin_config,
            class_name=class_name,
            timeout=timeout,
        )
        
        if success:
            return result
        
        if error_msg:
            raise PluginInitializationError(error_msg)
        
        raise PluginInitializationError(
            f"Plugin '{plugin_type}' initialization failed"
        )

    def get_initialization_summary(self) -> Dict[str, Any]:
        """Get a summary of initialization status.

        Returns:
            A dictionary containing initialization summary information.
        """
        all_status = self._tracker.get_all_status()

        pending_count = 0
        initializing_count = 0
        ready_count = 0
        failed_count = 0

        for status in all_status.values():
            if status.state == InitializationState.PENDING:
                pending_count += 1
            elif status.state == InitializationState.INITIALIZING:
                initializing_count += 1
            elif status.state == InitializationState.READY:
                ready_count += 1
            elif status.state == InitializationState.FAILED:
                failed_count += 1

        return {
            "total_plugins": len(all_status),
            "pending": pending_count,
            "initializing": initializing_count,
            "ready": ready_count,
            "failed": failed_count,
            "is_shutdown": self.is_shutdown(),
            "active_tasks": len(self.get_active_tasks()),
        }


_global_initializers: Set["AsyncPluginInitializer"] = set()
_global_initializers_lock = threading.Lock()


def _cleanup_global_initializers() -> None:
    """Cleanup all global async initializers on process exit."""
    with _global_initializers_lock:
        for initializer in list(_global_initializers):
            try:
                initializer.shutdown(wait=False)
            except Exception:
                pass
        _global_initializers.clear()


def _register_initializer(initializer: "AsyncPluginInitializer") -> None:
    """Register an initializer for cleanup on exit."""
    with _global_initializers_lock:
        _global_initializers.add(initializer)


def _unregister_initializer(initializer: "AsyncPluginInitializer") -> None:
    """Unregister an initializer from cleanup."""
    with _global_initializers_lock:
        _global_initializers.discard(initializer)


atexit.register(_cleanup_global_initializers)


__all__ = [
    "InitializationState",
    "InitializationStatus",
    "InitializationTracker",
    "PluginFuture",
    "AsyncPluginInitializer",
]
