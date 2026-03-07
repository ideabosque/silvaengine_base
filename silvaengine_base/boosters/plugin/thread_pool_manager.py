#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unified Thread Pool Manager for silvaengine_base.

This module provides a centralized thread pool management system to:
- Avoid resource competition between multiple ThreadPoolExecutor instances
- Provide consistent thread pool configuration
- Enable efficient resource utilization
- Support graceful shutdown across all components

@since 2.0.0
"""

import atexit
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Set


DEFAULT_WORKERS_PER_CPU = 4
DEFAULT_MAX_WORKERS = (os.cpu_count() or 1) * DEFAULT_WORKERS_PER_CPU


class ThreadPoolManager:
    """Unified thread pool manager for plugin system.
    
    This class provides a centralized thread pool management system that:
    - Creates and manages thread pools for different components
    - Avoids resource competition between multiple executors
    - Provides consistent configuration across all pools
    - Ensures graceful shutdown on process exit
    
    Thread Safety:
        All operations are thread-safe using internal locks.
    
    Example:
        >>> manager = ThreadPoolManager.get_instance()
        >>> executor = manager.get_executor("plugin_init", max_workers=8)
        >>> # Use executor for plugin initialization
        >>> manager.shutdown_all()
    """
    
    _instance: Optional["ThreadPoolManager"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "ThreadPoolManager":
        """Create or return singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        """Initialize the thread pool manager."""
        if self._initialized:
            return
            
        self._executors: Dict[str, ThreadPoolExecutor] = {}
        self._executor_configs: Dict[str, int] = {}
        self._executor_locks: Dict[str, threading.Lock] = {}
        self._manager_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._logger = logging.getLogger(__name__)
        self._default_max_workers = DEFAULT_MAX_WORKERS
        self._initialized = True
        
        atexit.register(self._cleanup_on_exit)
    
    @classmethod
    def get_instance(cls) -> "ThreadPoolManager":
        """Get the singleton instance of ThreadPoolManager.
        
        Returns:
            The ThreadPoolManager singleton instance.
        """
        return cls()
    
    def get_executor(
        self,
        name: str,
        max_workers: Optional[int] = None,
    ) -> ThreadPoolExecutor:
        """Get or create a thread pool executor by name.
        
        This method returns an existing executor if one exists with the given
        name, or creates a new one if needed.
        
        Args:
            name: Unique name for the executor.
            max_workers: Maximum number of worker threads. None for default.
            
        Returns:
            A ThreadPoolExecutor instance.
            
        Raises:
            RuntimeError: If the manager has been shut down.
        """
        if self._shutdown_event.is_set():
            raise RuntimeError(
                "ThreadPoolManager has been shut down, cannot create new executors"
            )
        
        with self._manager_lock:
            if name not in self._executors:
                workers = max_workers or self._default_max_workers
                self._executors[name] = ThreadPoolExecutor(max_workers=workers)
                self._executor_configs[name] = workers
                self._executor_locks[name] = threading.Lock()
                self._logger.debug(
                    f"Created thread pool '{name}' with {workers} workers"
                )
            
            return self._executors[name]
    
    def get_max_workers(self, name: str) -> Optional[int]:
        """Get the max_workers configuration for a named executor.
        
        Args:
            name: The name of the executor.
            
        Returns:
            The max_workers value, or None if the executor doesn't exist.
        """
        with self._manager_lock:
            return self._executor_configs.get(name)
    
    def resize_executor(
        self,
        name: str,
        max_workers: int,
    ) -> bool:
        """Resize an executor by recreating it with new worker count.
        
        Note: This will wait for pending tasks to complete before resizing.
        
        Args:
            name: The name of the executor to resize.
            max_workers: New maximum worker count.
            
        Returns:
            True if resize was successful, False if executor doesn't exist.
        """
        with self._manager_lock:
            if name not in self._executors:
                return False
            
            old_executor = self._executors[name]
            old_executor.shutdown(wait=True)
            
            self._executors[name] = ThreadPoolExecutor(max_workers=max_workers)
            self._executor_configs[name] = max_workers
            
            self._logger.info(
                f"Resized thread pool '{name}' from to {max_workers} workers"
            )
            return True
    
    def shutdown_executor(self, name: str, wait: bool = True) -> bool:
        """Shutdown a specific executor.
        
        Args:
            name: The name of the executor to shutdown.
            wait: If True, wait for pending tasks to complete.
            
        Returns:
            True if shutdown was successful, False if executor doesn't exist.
        """
        with self._manager_lock:
            if name not in self._executors:
                return False
            
            executor = self._executors.pop(name)
            executor.shutdown(wait=wait)
            
            self._executor_configs.pop(name, None)
            self._executor_locks.pop(name, None)
            
            self._logger.debug(f"Shutdown thread pool '{name}'")
            return True
    
    def shutdown_all(self, wait: bool = True) -> None:
        """Shutdown all executors.
        
        Args:
            wait: If True, wait for pending tasks to complete.
        """
        self._shutdown_event.set()
        
        with self._manager_lock:
            for name, executor in list(self._executors.items()):
                try:
                    executor.shutdown(wait=wait)
                    self._logger.debug(f"Shutdown thread pool '{name}'")
                except Exception as e:
                    self._logger.error(f"Error shutting down thread pool '{name}': {e}")
            
            self._executors.clear()
            self._executor_configs.clear()
            self._executor_locks.clear()
        
        self._logger.info("All thread pools have been shut down")
    
    def is_shutdown(self) -> bool:
        """Check if the manager has been shut down.
        
        Returns:
            True if shutdown has been called, False otherwise.
        """
        return self._shutdown_event.is_set()
    
    def reset(self) -> None:
        """Reset the manager for reuse.
        
        This clears all executors and allows new ones to be created.
        """
        self.shutdown_all(wait=False)
        self._shutdown_event.clear()
        self._logger.debug("ThreadPoolManager has been reset")
    
    def get_active_executor_names(self) -> Set[str]:
        """Get the names of all active executors.
        
        Returns:
            A set of executor names.
        """
        with self._manager_lock:
            return set(self._executors.keys())
    
    def get_total_workers(self) -> int:
        """Get the total number of workers across all executors.
        
        Returns:
            Total worker count.
        """
        with self._manager_lock:
            return sum(self._executor_configs.values())
    
    def _cleanup_on_exit(self) -> None:
        """Cleanup all executors on process exit."""
        try:
            if not self._shutdown_event.is_set():
                self.shutdown_all(wait=False)
        except Exception:
            pass
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance."""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.shutdown_all(wait=False)
                except Exception:
                    pass
                cls._instance = None


def get_thread_pool_manager() -> ThreadPoolManager:
    """Get the ThreadPoolManager singleton instance.
    
    Returns:
        The ThreadPoolManager singleton instance.
    """
    return ThreadPoolManager.get_instance()


def reset_thread_pool_manager() -> None:
    """Reset the ThreadPoolManager singleton instance."""
    ThreadPoolManager.reset_instance()


__all__ = [
    "ThreadPoolManager",
    "get_thread_pool_manager",
    "reset_thread_pool_manager",
    "DEFAULT_MAX_WORKERS",
    "DEFAULT_WORKERS_PER_CPU",
]
