#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Fully Asynchronous Plugin Manager for silvaengine_base.

This module provides a completely non-blocking plugin loading and initialization
mechanism with support for:
- Asynchronous task scheduling
- Resource priority management
- Loading state monitoring
- Plugin dependency resolution
- Parallel loading capabilities
- Graceful degradation on loading failures
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from heapq import heappop, heappush
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    TypeVar,
    Union,
)

from .circuit_breaker import CircuitBreaker, get_circuit_breaker_registry
from .context import AbstractPluginContext, EagerPluginContext, PluginNotFoundError
from .dependency import DependencyResolver, PluginDependency
from .initializer_utils import PluginInitializationError, PluginInitializerUtils

T = TypeVar("T")


class PluginLoadingState(Enum):
    """State of plugin loading process."""
    PENDING = auto()
    SCHEDULED = auto()
    LOADING = auto()
    READY = auto()
    FAILED = auto()
    DEGRADED = auto()


@dataclass(order=True)
class PrioritizedPlugin:
    """Plugin with priority for loading queue."""
    priority: int
    plugin_type: str = field(compare=False)
    config: Dict[str, Any] = field(compare=False)
    dependencies: Set[str] = field(default_factory=set, compare=False)


@dataclass
class LoadingMetrics:
    """Metrics for plugin loading process."""
    total_plugins: int = 0
    loaded_plugins: int = 0
    failed_plugins: int = 0
    degraded_plugins: int = 0
    total_loading_time: float = 0.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    cache_hits: int = 0
    cache_misses: int = 0
    avg_response_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_plugins == 0:
            return 0.0
        return self.loaded_plugins / self.total_plugins

    @property
    def average_loading_time(self) -> float:
        if self.loaded_plugins == 0:
            return 0.0
        return self.total_loading_time / self.loaded_plugins

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def record_response_time(self, response_time_ms: float) -> None:
        """Record response time with exponential moving average."""
        if self.avg_response_time_ms == 0:
            self.avg_response_time_ms = response_time_ms
        else:
            self.avg_response_time_ms = 0.9 * self.avg_response_time_ms + 0.1 * response_time_ms


@dataclass
class PluginLoadResult:
    """Result of plugin loading operation."""
    plugin_type: str
    success: bool
    state: PluginLoadingState
    instance: Optional[Any] = None
    error: Optional[Exception] = None
    loading_time: float = 0.0
    degraded: bool = False


class AsyncPluginManager:
    """
    Fully asynchronous plugin manager with non-blocking loading.
    
    Features:
    - Asynchronous task scheduling with priority queue
    - Resource priority management
    - Loading state monitoring
    - Plugin dependency resolution
    - Parallel loading capabilities
    - Graceful degradation on failures
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        default_timeout: float = 30.0,
        logger: Optional[logging.Logger] = None,
    ):
        self._logger = logger or logging.getLogger(__name__)
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        
        # Async event loop and executor
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Plugin storage
        self._plugins: Dict[str, Any] = {}
        self._plugin_states: Dict[str, PluginLoadingState] = {}
        self._plugin_configs: Dict[str, Dict[str, Any]] = {}
        self._plugin_dependencies: Dict[str, Set[str]] = {}
        
        # Priority queue for loading
        self._loading_queue: List[PrioritizedPlugin] = []
        self._loading_tasks: Dict[str, asyncio.Task] = {}
        
        # State tracking
        self._metrics = LoadingMetrics()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._loading_event = asyncio.Event()
        self._plugin_events: Dict[str, asyncio.Event] = {}

        # Dependency resolver with caching
        self._dependency_resolver = DependencyResolver()
        self._dependency_cache: Dict[frozenset, List[List[str]]] = {}
    
    async def initialize(self) -> None:
        """Initialize the async plugin manager."""
        self._loop = asyncio.get_event_loop()
        self._logger.info("AsyncPluginManager initialized")
    
    async def shutdown(self) -> None:
        """Shutdown the async plugin manager gracefully."""
        # Cancel all pending tasks
        for task in self._loading_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._loading_tasks:
            await asyncio.gather(*self._loading_tasks.values(), return_exceptions=True)
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
        self._logger.info("AsyncPluginManager shutdown complete")
    
    def register_plugin(
        self,
        plugin_type: str,
        config: Dict[str, Any],
        priority: int = 5,
        dependencies: Optional[Set[str]] = None,
    ) -> None:
        """
        Register a plugin for asynchronous loading.
        
        Args:
            plugin_type: Unique identifier for the plugin
            config: Plugin configuration
            priority: Loading priority (lower = higher priority)
            dependencies: Set of plugin types this plugin depends on
        """
        self._plugin_configs[plugin_type] = config
        self._plugin_states[plugin_type] = PluginLoadingState.PENDING
        self._plugin_dependencies[plugin_type] = dependencies or set()
        
        prioritized = PrioritizedPlugin(
            priority=priority,
            plugin_type=plugin_type,
            config=config,
            dependencies=dependencies or set(),
        )
        heappush(self._loading_queue, prioritized)
        
        self._logger.debug(f"Registered plugin: {plugin_type} (priority: {priority})")
    
    async def load_plugin_async(
        self,
        plugin_type: str,
        timeout: Optional[float] = None,
    ) -> PluginLoadResult:
        """
        Load a single plugin asynchronously.
        
        Args:
            plugin_type: Type of plugin to load
            timeout: Loading timeout in seconds
            
        Returns:
            PluginLoadResult with loading status and instance
        """
        timeout = timeout or self._default_timeout
        start_time = time.time()
        
        if plugin_type not in self._plugin_configs:
            return PluginLoadResult(
                plugin_type=plugin_type,
                success=False,
                state=PluginLoadingState.FAILED,
                error=PluginNotFoundError(f"Plugin {plugin_type} not registered"),
            )
        
        self._plugin_states[plugin_type] = PluginLoadingState.LOADING
        config = self._plugin_configs[plugin_type]
        
        try:
            # Check circuit breaker
            if not await self._check_circuit_breaker(plugin_type):
                return await self._handle_degraded_loading(plugin_type, config)
            
            # Load dependencies first
            dependencies = self._plugin_dependencies.get(plugin_type, set())
            for dep in dependencies:
                if dep not in self._plugins:
                    dep_result = await self.load_plugin_async(dep, timeout)
                    if not dep_result.success:
                        raise PluginInitializationError(
                            f"Dependency {dep} failed to load"
                        )
            
            # Load the plugin
            instance = await self._load_plugin_instance(plugin_type, config, timeout)
            
            loading_time = time.time() - start_time
            self._plugins[plugin_type] = instance
            self._plugin_states[plugin_type] = PluginLoadingState.READY
            self._metrics.loaded_plugins += 1
            self._metrics.total_loading_time += loading_time
            
            self._logger.info(f"Successfully loaded plugin: {plugin_type} in {loading_time:.2f}s")
            
            return PluginLoadResult(
                plugin_type=plugin_type,
                success=True,
                state=PluginLoadingState.READY,
                instance=instance,
                loading_time=loading_time,
            )
            
        except Exception as e:
            loading_time = time.time() - start_time
            self._plugin_states[plugin_type] = PluginLoadingState.FAILED
            self._metrics.failed_plugins += 1
            
            self._logger.error(f"Failed to load plugin {plugin_type}: {e}")
            
            # Record failure in circuit breaker
            await self._record_failure(plugin_type)
            
            return PluginLoadResult(
                plugin_type=plugin_type,
                success=False,
                state=PluginLoadingState.FAILED,
                error=e,
                loading_time=loading_time,
            )
    
    async def load_all_plugins_parallel(
        self,
        timeout: Optional[float] = None,
    ) -> Dict[str, PluginLoadResult]:
        """
        Load all registered plugins in parallel with dependency resolution.
        
        Args:
            timeout: Global timeout for all loading operations
            
        Returns:
            Dictionary mapping plugin types to their load results
        """
        timeout = timeout or self._default_timeout * len(self._loading_queue)
        self._metrics.start_time = time.time()
        self._metrics.total_plugins = len(self._loading_queue)
        
        # Resolve dependency order
        ordered_plugins = self._resolve_loading_order()
        
        # Create loading tasks
        results: Dict[str, PluginLoadResult] = {}
        
        for batch in ordered_plugins:
            # Load plugins in the same batch in parallel
            tasks = [
                self.load_plugin_async(plugin_type, timeout)
                for plugin_type in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for plugin_type, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    results[plugin_type] = PluginLoadResult(
                        plugin_type=plugin_type,
                        success=False,
                        state=PluginLoadingState.FAILED,
                        error=result,
                    )
                else:
                    results[plugin_type] = result
        
        self._metrics.end_time = time.time()
        self._loading_event.set()
        
        return results
    
    async def get_plugin(self, plugin_type: str) -> Optional[Any]:
        """
        Get a loaded plugin instance with optimized fast path.

        Args:
            plugin_type: Type of plugin to retrieve

        Returns:
            Plugin instance or None if not loaded
        """
        import time
        start_time = time.perf_counter()

        # Fast path: already loaded
        if plugin_type in self._plugins:
            self._metrics.cache_hits += 1
            response_time = (time.perf_counter() - start_time) * 1000
            self._metrics.record_response_time(response_time)
            return self._plugins[plugin_type]

        self._metrics.cache_misses += 1

        # Wait for loading to complete if in progress
        if not self._loading_event.is_set():
            try:
                await asyncio.wait_for(
                    self._loading_event.wait(),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                response_time = (time.perf_counter() - start_time) * 1000
                self._metrics.record_response_time(response_time)
                return None

        response_time = (time.perf_counter() - start_time) * 1000
        self._metrics.record_response_time(response_time)

        return self._plugins.get(plugin_type)
    
    async def wait_for_plugin(
        self,
        plugin_type: str,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Wait for a specific plugin to be loaded using event-driven approach.

        Args:
            plugin_type: Type of plugin to wait for
            timeout: Maximum time to wait

        Returns:
            True if plugin is ready, False if timeout
        """
        timeout = timeout or self._default_timeout

        # Fast check
        if self._plugin_states.get(plugin_type) == PluginLoadingState.READY:
            return True

        # Create per-plugin event if not exists
        if plugin_type not in self._plugin_events:
            self._plugin_events[plugin_type] = asyncio.Event()

        try:
            await asyncio.wait_for(
                self._plugin_events[plugin_type].wait(),
                timeout=timeout
            )
            return self._plugin_states.get(plugin_type) == PluginLoadingState.READY
        except asyncio.TimeoutError:
            return False
    
    def get_plugin_state(self, plugin_type: str) -> PluginLoadingState:
        """Get the current loading state of a plugin."""
        return self._plugin_states.get(plugin_type, PluginLoadingState.PENDING)
    
    def get_metrics(self) -> LoadingMetrics:
        """Get loading metrics."""
        return self._metrics
    
    def is_ready(self) -> bool:
        """Check if all plugins are loaded."""
        return all(
            state == PluginLoadingState.READY
            for state in self._plugin_states.values()
        )
    
    async def _load_plugin_instance(
        self,
        plugin_type: str,
        config: Dict[str, Any],
        timeout: float,
    ) -> Any:
        """Load a plugin instance asynchronously."""
        # Run the synchronous loading in executor
        loop = asyncio.get_event_loop()
        
        def load_sync():
            return PluginInitializerUtils.invoke_plugin_init(
                module_name=config.get("module_name"),
                function_name=config.get("function_name", "init"),
                plugin_config=config.get("config", {}),
                class_name=config.get("class_name"),
                timeout=timeout,
            )
        
        result = await asyncio.wait_for(
            loop.run_in_executor(self._executor, load_sync),
            timeout=timeout,
        )
        
        if not result[0]:  # success flag
            raise PluginInitializationError(result[2])
        
        return result[1]
    
    async def _check_circuit_breaker(self, plugin_type: str) -> bool:
        """Check if circuit breaker allows loading."""
        if plugin_type not in self._circuit_breakers:
            self._circuit_breakers[plugin_type] = get_circuit_breaker_registry().get_or_create(
                name=f"plugin_{plugin_type}",
                failure_threshold=3,
                recovery_timeout=60.0,
            )
        
        breaker = self._circuit_breakers[plugin_type]
        return breaker.allow_request()
    
    async def _record_failure(self, plugin_type: str) -> None:
        """Record a loading failure in circuit breaker."""
        if plugin_type in self._circuit_breakers:
            self._circuit_breakers[plugin_type].record_failure()
    
    async def _handle_degraded_loading(
        self,
        plugin_type: str,
        config: Dict[str, Any],
    ) -> PluginLoadResult:
        """Handle degraded loading when circuit breaker is open."""
        self._logger.warning(f"Circuit breaker open for plugin {plugin_type}, using degraded mode")
        
        self._metrics.degraded_plugins += 1
        
        return PluginLoadResult(
            plugin_type=plugin_type,
            success=True,
            state=PluginLoadingState.DEGRADED,
            instance=None,
            degraded=True,
        )
    
    def _resolve_loading_order(self) -> List[List[str]]:
        """Resolve plugin loading order based on dependencies with caching."""
        # Check cache
        cache_key = frozenset(self._plugin_dependencies.keys())
        if cache_key in self._dependency_cache:
            return self._dependency_cache[cache_key]

        # Build dependency graph
        graph: Dict[str, Set[str]] = {}
        for plugin_type, deps in self._plugin_dependencies.items():
            graph[plugin_type] = deps

        # Topological sort with batching (Kahn's algorithm)
        in_degree = {node: 0 for node in graph}
        for deps in graph.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        batches: List[List[str]] = []
        visited = set()

        while len(visited) < len(graph):
            batch = [
                node for node in graph
                if node not in visited and in_degree[node] == 0
            ]

            if not batch:
                # Circular dependency detected
                remaining = set(graph.keys()) - visited
                raise PluginInitializationError(
                    f"Circular dependency detected: {remaining}"
                )

            batches.append(batch)
            visited.update(batch)

            for node in batch:
                for dependent in graph:
                    if node in graph[dependent]:
                        in_degree[dependent] -= 1

        # Cache result
        self._dependency_cache[cache_key] = batches
        return batches


class AsyncPluginContext(AbstractPluginContext):
    """Async-aware plugin context implementation."""
    
    def __init__(
        self,
        plugin_manager: AsyncPluginManager,
        logger: Optional[logging.Logger] = None,
    ):
        self._plugin_manager = plugin_manager
        self._logger = logger or logging.getLogger(__name__)
    
    def get(self, plugin_name: str) -> Optional[Any]:
        """Get plugin synchronously (for compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If in async context, use run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(
                    self._plugin_manager.get_plugin(plugin_name),
                    loop,
                )
                return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(
                    self._plugin_manager.get_plugin(plugin_name)
                )
        except Exception as e:
            self._logger.error(f"Error getting plugin {plugin_name}: {e}")
            return None
    
    async def get_async(self, plugin_name: str) -> Optional[Any]:
        """Get plugin asynchronously."""
        return await self._plugin_manager.get_plugin(plugin_name)
    
    def _get_plugin_internal(self, plugin_name: str) -> Optional[Any]:
        """Internal method for plugin retrieval."""
        return self.get(plugin_name)
    
    def _get_all_plugins_internal(self) -> Dict[str, Any]:
        """Get all loaded plugins."""
        return self._plugin_manager._plugins
    
    def get_plugin_state(self, plugin_name: str) -> PluginLoadingState:
        """Get plugin loading state."""
        return self._plugin_manager.get_plugin_state(plugin_name)
    
    def wait_for_plugin(self, plugin_name: str, timeout: float = 30.0) -> bool:
        """Wait for plugin to be ready."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._plugin_manager.wait_for_plugin(plugin_name, timeout),
                    loop,
                )
                return future.result(timeout=timeout)
            else:
                return loop.run_until_complete(
                    self._plugin_manager.wait_for_plugin(plugin_name, timeout)
                )
        except Exception:
            return False


# Global async plugin manager instance
_global_async_manager: Optional[AsyncPluginManager] = None
_manager_lock = asyncio.Lock()


async def get_async_plugin_manager(
    max_workers: int = 4,
    logger: Optional[logging.Logger] = None,
) -> AsyncPluginManager:
    """Get or create global async plugin manager."""
    global _global_async_manager
    
    if _global_async_manager is None:
        async with _manager_lock:
            if _global_async_manager is None:
                _global_async_manager = AsyncPluginManager(
                    max_workers=max_workers,
                    logger=logger,
                )
                await _global_async_manager.initialize()
    
    return _global_async_manager


async def reset_async_plugin_manager() -> None:
    """Reset global async plugin manager."""
    global _global_async_manager
    
    if _global_async_manager is not None:
        await _global_async_manager.shutdown()
        _global_async_manager = None


__all__ = [
    "AsyncPluginManager",
    "AsyncPluginContext",
    "PluginLoadingState",
    "PluginLoadResult",
    "LoadingMetrics",
    "PrioritizedPlugin",
    "get_async_plugin_manager",
    "reset_async_plugin_manager",
]
