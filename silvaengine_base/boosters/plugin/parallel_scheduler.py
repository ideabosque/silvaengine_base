#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Dependency-aware parallel initialization scheduler for silvaengine_base.

This module provides a parallel plugin initialization system with:
- Topological sorting for dependency resolution
- Parallel initialization of independent plugins
- Priority-based ordering within dependency levels
- Performance metrics collection
- Thread-safe operations
"""

import concurrent.futures
import heapq
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from .async_initializer import PluginFuture


@dataclass
class InitializationTask:
    """Represents a single plugin initialization task.
    
    Attributes:
        plugin_type: The type identifier of the plugin.
        config: Configuration dictionary for the plugin.
        dependencies: List of plugin types that must be initialized first.
        priority: Priority level (higher = initialize first within same level).
        timeout: Maximum time allowed for initialization in seconds.
    """
    
    plugin_type: str
    config: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    priority: int = 0
    timeout: float = 30.0


class InitializationMetrics:
    """Collect and track initialization performance metrics.
    
    This class provides thread-safe collection of initialization metrics
    including timing, success/failure counts, and parallel efficiency.
    """
    
    def __init__(self) -> None:
        """Initialize the metrics collector."""
        self._lock = threading.Lock()
        self._start_times: Dict[str, float] = {}
        self._end_times: Dict[str, float] = {}
        self._successes: Set[str] = set()
        self._failures: Dict[str, str] = {}
        self._global_start_time: Optional[float] = None
        self._global_end_time: Optional[float] = None
    
    def record_start(self, plugin_type: str) -> None:
        """Record the start time of a plugin initialization.
        
        Args:
            plugin_type: The type identifier of the plugin.
        """
        with self._lock:
            current_time = time.time()
            self._start_times[plugin_type] = current_time
            
            if self._global_start_time is None:
                self._global_start_time = current_time
    
    def record_success(self, plugin_type: str) -> None:
        """Record a successful plugin initialization.
        
        Args:
            plugin_type: The type identifier of the plugin.
        """
        with self._lock:
            self._end_times[plugin_type] = time.time()
            self._successes.add(plugin_type)
            self._global_end_time = time.time()
    
    def record_failure(self, plugin_type: str, error: str) -> None:
        """Record a failed plugin initialization.
        
        Args:
            plugin_type: The type identifier of the plugin.
            error: The error message describing the failure.
        """
        with self._lock:
            self._end_times[plugin_type] = time.time()
            self._failures[plugin_type] = error
            self._global_end_time = time.time()
    
    def get_plugin_duration(self, plugin_type: str) -> Optional[float]:
        """Get the initialization duration for a specific plugin.
        
        Args:
            plugin_type: The type identifier of the plugin.
            
        Returns:
            The duration in seconds, or None if not available.
        """
        with self._lock:
            start_time = self._start_times.get(plugin_type)
            end_time = self._end_times.get(plugin_type)
            
            if start_time is not None and end_time is not None:
                return end_time - start_time
            return None
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary including performance statistics.
        
        Returns:
            A dictionary containing:
            - total_plugins: Total number of plugins tracked.
            - successful: Number of successful initializations.
            - failed: Number of failed initializations.
            - total_time: Total elapsed time in seconds.
            - parallel_efficiency: Ratio of parallel time savings.
            - plugin_details: Per-plugin timing and status information.
        """
        with self._lock:
            total_plugins = len(self._start_times)
            successful = len(self._successes)
            failed = len(self._failures)
            
            total_time = 0.0
            if self._global_start_time is not None and self._global_end_time is not None:
                total_time = self._global_end_time - self._global_start_time
            
            sequential_time = 0.0
            plugin_details: Dict[str, Dict[str, Any]] = {}
            
            for plugin_type in self._start_times:
                duration = self.get_plugin_duration(plugin_type)
                if duration is not None:
                    sequential_time += duration
                
                status = "success" if plugin_type in self._successes else "failed"
                error = self._failures.get(plugin_type)
                
                plugin_details[plugin_type] = {
                    "status": status,
                    "duration": duration,
                    "error": error,
                }
            
            parallel_efficiency = 0.0
            if total_time > 0 and sequential_time > 0:
                parallel_efficiency = (sequential_time - total_time) / sequential_time
            
            return {
                "total_plugins": total_plugins,
                "successful": successful,
                "failed": failed,
                "total_time": total_time,
                "sequential_time": sequential_time,
                "parallel_efficiency": parallel_efficiency,
                "plugin_details": plugin_details,
            }
    
    def reset(self) -> None:
        """Reset all collected metrics."""
        with self._lock:
            self._start_times.clear()
            self._end_times.clear()
            self._successes.clear()
            self._failures.clear()
            self._global_start_time = None
            self._global_end_time = None


class PriorityInitializationQueue:
    """Priority queue for initialization tasks.
    
    This class provides a thread-safe priority queue that orders tasks
    by their priority (higher priority = processed first).
    """
    
    def __init__(self) -> None:
        """Initialize the priority queue."""
        self._lock = threading.Lock()
        self._heap: List[Tuple[int, int, InitializationTask]] = []
        self._counter = 0
    
    def push(self, task: InitializationTask) -> None:
        """Add a task to the priority queue.
        
        Higher priority tasks are processed first. Tasks with the same
        priority are processed in FIFO order.
        
        Args:
            task: The initialization task to add.
        """
        with self._lock:
            self._counter += 1
            heapq.heappush(
                self._heap,
                (-task.priority, self._counter, task)
            )
    
    def pop(self) -> Optional[InitializationTask]:
        """Remove and return the highest priority task.
        
        Returns:
            The highest priority task, or None if the queue is empty.
        """
        with self._lock:
            if not self._heap:
                return None
            
            _, _, task = heapq.heappop(self._heap)
            return task
    
    def peek(self) -> Optional[InitializationTask]:
        """Return the highest priority task without removing it.
        
        Returns:
            The highest priority task, or None if the queue is empty.
        """
        with self._lock:
            if not self._heap:
                return None
            
            _, _, task = self._heap[0]
            return task
    
    def is_empty(self) -> bool:
        """Check if the queue is empty.
        
        Returns:
            True if the queue is empty, False otherwise.
        """
        with self._lock:
            return len(self._heap) == 0
    
    def size(self) -> int:
        """Get the number of tasks in the queue.
        
        Returns:
            The number of tasks in the queue.
        """
        with self._lock:
            return len(self._heap)
    
    def clear(self) -> None:
        """Remove all tasks from the queue."""
        with self._lock:
            self._heap.clear()
            self._counter = 0


class ParallelInitializationScheduler:
    """Dependency-aware parallel initialization scheduler.
    
    This class provides a sophisticated plugin initialization system that:
    - Resolves dependencies using topological sorting
    - Initializes independent plugins in parallel
    - Respects priority ordering within dependency levels
    - Collects detailed performance metrics
    - Ensures thread-safe operations
    
    Example:
        >>> scheduler = ParallelInitializationScheduler(logger=logger, max_workers=8)
        >>> tasks = [
        ...     InitializationTask(plugin_type="database", config={...}, priority=10),
        ...     InitializationTask(plugin_type="cache", config={...}, dependencies=["database"]),
        ... ]
        >>> futures = scheduler.schedule(tasks)
        >>> metrics = scheduler.get_metrics()
        >>> scheduler.shutdown()
    """
    
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        """Initialize the parallel initialization scheduler.
        
        Args:
            logger: Optional logger instance for logging.
            max_workers: Maximum number of parallel workers. None for auto.
        """
        self._logger = logger or logging.getLogger(__name__)
        self._max_workers = max_workers
        
        self._metrics = InitializationMetrics()
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._executor_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        
        self._futures: Dict[str, "PluginFuture"] = {}
        self._futures_lock = threading.Lock()
        
        self._ready_events: Dict[str, threading.Event] = {}
        self._ready_events_lock = threading.Lock()
        
        self._initialization_errors: Dict[str, str] = {}
        self._errors_lock = threading.Lock()
    
    def schedule(
        self,
        tasks: List[InitializationTask],
    ) -> Dict[str, "PluginFuture"]:
        """Schedule all initialization tasks.
        
        This method analyzes dependencies, performs topological sorting,
        and starts parallel initialization. It returns immediately with
        PluginFuture objects for each task.
        
        Args:
            tasks: List of initialization tasks to schedule.
            
        Returns:
            A dictionary mapping plugin types to their PluginFuture objects.
            
        Raises:
            ValueError: If circular dependencies are detected.
        """
        if self._shutdown_event.is_set():
            self._logger.warning(
                "Cannot schedule tasks: scheduler has been shut down"
            )
            return {}
        
        if not tasks:
            self._logger.debug("No tasks provided for scheduling")
            return {}
        
        task_map = {task.plugin_type: task for task in tasks}
        
        dependency_graph = self._build_dependency_graph(tasks)
        
        cycle = self._detect_cycle(dependency_graph)
        if cycle:
            raise ValueError(
                f"Circular dependency detected: {' -> '.join(cycle)}"
            )
        
        levels = self._topological_sort(dependency_graph, tasks)
        
        self._initialize_executor()
        
        self._create_futures(tasks)
        
        self._schedule_levels(levels, task_map)
        
        self._logger.info(
            f"Scheduled {len(tasks)} tasks across {len(levels)} levels"
        )
        
        with self._futures_lock:
            return dict(self._futures)
    
    def _build_dependency_graph(
        self,
        tasks: List[InitializationTask],
    ) -> Dict[str, List[str]]:
        """Build dependency graph from tasks.
        
        [OPTIMIZATION] Uses UnifiedDependencyResolver for dependency operations
        
        The graph maps each plugin type to the list of plugins that depend on it.
        This is the reverse of the dependency relationship, needed for topological sort.
        
        Args:
            tasks: List of initialization tasks.
            
        Returns:
            A dictionary mapping plugin types to their dependents (plugins that depend on this one).
        """
        from .dependency import UnifiedDependencyResolver
        
        graph: Dict[str, List[str]] = {}
        task_types = {task.plugin_type for task in tasks}
        
        for task in tasks:
            if task.plugin_type not in graph:
                graph[task.plugin_type] = []
            
            for dep in task.dependencies:
                if dep in task_types:
                    if dep not in graph:
                        graph[dep] = []
                    graph[dep].append(task.plugin_type)
                else:
                    self._logger.warning(
                        f"Task '{task.plugin_type}' depends on '{dep}' "
                        f"which is not in the task list"
                    )
        
        return graph
    
    def _detect_cycle(
        self,
        graph: Dict[str, List[str]],
    ) -> Optional[List[str]]:
        """Detect circular dependencies in the dependency graph.
        
        [OPTIMIZATION] Delegates to UnifiedDependencyResolver.detect_cycle()
        
        Args:
            graph: The dependency graph (node -> dependencies).
            
        Returns:
            A list representing the cycle path if found, None otherwise.
        """
        from .dependency import UnifiedDependencyResolver
        
        return UnifiedDependencyResolver.detect_cycle(graph, self._logger)
    
    def _topological_sort(
        self,
        graph: Dict[str, List[str]],
        tasks: List[InitializationTask],
    ) -> List[List[str]]:
        """Perform topological sort returning levels.
        
        [OPTIMIZATION] Uses UnifiedDependencyResolver for core sorting logic
        
        Each level contains plugins that can be initialized in parallel.
        Plugins within the same level are sorted by priority (descending).
        
        Args:
            graph: The dependency graph (node -> dependencies).
            tasks: List of initialization tasks.
            
        Returns:
            A list of levels, where each level is a list of plugin types.
        """
        from .dependency import UnifiedDependencyResolver
        
        success, sorted_nodes = UnifiedDependencyResolver.topological_sort(
            graph, self._logger
        )
        
        if not success:
            self._logger.warning(
                "Topological sort incomplete - possible circular dependency"
            )
            return []
        
        priority_map = {task.plugin_type: task.priority for task in tasks}
        
        in_degree: Dict[str, int] = defaultdict(int)
        task_types = {task.plugin_type for task in tasks}
        
        for task in tasks:
            if task.plugin_type not in in_degree:
                in_degree[task.plugin_type] = 0
            
            for dependency in task.dependencies:
                if dependency in task_types:
                    in_degree[task.plugin_type] += 1
        
        levels: List[List[str]] = []
        remaining = set(task_types)
        
        while remaining:
            current_level = [
                plugin_type for plugin_type in remaining
                if in_degree[plugin_type] == 0
            ]
            
            if not current_level:
                break
            
            current_level.sort(key=lambda x: -priority_map.get(x, 0))
            
            levels.append(current_level)
            
            for plugin_type in current_level:
                remaining.remove(plugin_type)
                for dependent in graph.get(plugin_type, []):
                    in_degree[dependent] -= 1
        
        return levels
    
    def _initialize_executor(self) -> None:
        """Initialize the thread pool executor if not already created.
        
        [OPTIMIZATION] Uses ThreadPoolManager for unified thread pool management
        """
        from .thread_pool_manager import get_thread_pool_manager
        
        with self._executor_lock:
            if self._executor is None:
                self._executor = get_thread_pool_manager().get_executor(
                    "parallel_scheduler",
                    max_workers=self._max_workers,
                )
    
    def _create_futures(self, tasks: List[InitializationTask]) -> None:
        """Create PluginFuture objects for all tasks.
        
        Args:
            tasks: List of initialization tasks.
        """
        from .async_initializer import (
            InitializationTracker,
            PluginFuture,
        )
        
        tracker = InitializationTracker(logger=self._logger)
        
        for task in tasks:
            tracker.register_plugin(task.plugin_type)
            
            future = PluginFuture(
                plugin_type=task.plugin_type,
                tracker=tracker,
                logger=self._logger,
            )
            
            with self._futures_lock:
                self._futures[task.plugin_type] = future
            
            with self._ready_events_lock:
                self._ready_events[task.plugin_type] = threading.Event()
    
    def _schedule_levels(
        self,
        levels: List[List[str]],
        task_map: Dict[str, InitializationTask],
    ) -> None:
        """Schedule initialization by levels.
        
        [OPTIMIZATION] Changed from recursive to iterative implementation
        
        Each level is initialized in parallel after the previous level completes.
        This prevents stack overflow for large numbers of levels.
        
        Args:
            levels: List of plugin type levels.
            task_map: Mapping of plugin types to their tasks.
        """
        def initialize_all_levels() -> None:
            # Iterative implementation instead of recursive
            for level_index, level in enumerate(levels):
                if self._shutdown_event.is_set():
                    self._logger.warning("Scheduler shutdown - stopping level initialization")
                    break
                
                self._logger.debug(
                    f"Initializing level {level_index} with {len(level)} plugins"
                )
                
                self._initialize_level(level, task_map)
        
        with self._executor_lock:
            if self._executor is not None:
                self._executor.submit(initialize_all_levels)
    
    def _initialize_level(
        self,
        level: List[str],
        task_map: Dict[str, InitializationTask],
    ) -> None:
        """Initialize all plugins in a level in parallel.
        
        This method blocks until all plugins in the level are initialized.
        
        Args:
            level: List of plugin types in this level.
            task_map: Mapping of plugin types to their tasks.
        """
        if self._shutdown_event.is_set():
            self._logger.warning("Scheduler shutdown - skipping level initialization")
            return
        
        futures_list: List[concurrent.futures.Future] = []
        
        for plugin_type in level:
            task = task_map.get(plugin_type)
            if task is None:
                self._logger.warning(f"No task found for plugin type '{plugin_type}'")
                continue
            
            with self._executor_lock:
                if self._executor is None:
                    continue
                
                future = self._executor.submit(
                    self._initialize_single_task,
                    task,
                )
                futures_list.append(future)
        
        for future in concurrent.futures.as_completed(futures_list):
            try:
                future.result()
            except Exception as exception:
                self._logger.error(f"Error in level initialization: {exception}")
    
    def _initialize_single_task(self, task: InitializationTask) -> None:
        """Initialize a single plugin task.
        
        This method is executed in a worker thread.
        
        Args:
            task: The initialization task to execute.
        """
        if self._shutdown_event.is_set():
            self._logger.warning(
                f"Skipping initialization for '{task.plugin_type}': scheduler shut down"
            )
            return
        
        for dependency in task.dependencies:
            if not self._wait_for_dependency(dependency, task.timeout):
                error_msg = (
                    f"Dependency '{dependency}' failed or timed out "
                    f"for plugin '{task.plugin_type}'"
                )
                self._record_failure(task.plugin_type, error_msg)
                return
        
        self._metrics.record_start(task.plugin_type)
        
        try:
            result = self._do_initialize(task)
            
            with self._futures_lock:
                future = self._futures.get(task.plugin_type)
                if future is not None:
                    future.set_result(result)
            
            self._metrics.record_success(task.plugin_type)
            
            with self._ready_events_lock:
                if task.plugin_type in self._ready_events:
                    self._ready_events[task.plugin_type].set()
            
            self._logger.info(
                f"Successfully initialized plugin '{task.plugin_type}'"
            )
            
        except Exception as exception:
            error_msg = str(exception)
            self._record_failure(task.plugin_type, error_msg)
            
            self._logger.error(
                f"Failed to initialize plugin '{task.plugin_type}': {exception}"
            )
    
    def _wait_for_dependency(self, dependency: str, timeout: float) -> bool:
        """Wait for a dependency to be initialized.
        
        Args:
            dependency: The plugin type to wait for.
            timeout: Maximum time to wait in seconds.
            
        Returns:
            True if the dependency is ready, False if it failed or timed out.
        """
        with self._errors_lock:
            if dependency in self._initialization_errors:
                return False
        
        with self._ready_events_lock:
            event = self._ready_events.get(dependency)
        
        if event is None:
            return True
        
        return event.wait(timeout=timeout)
    
    def _record_failure(self, plugin_type: str, error: str) -> None:
        """Record a plugin initialization failure.
        
        Args:
            plugin_type: The type identifier of the plugin.
            error: The error message.
        """
        self._metrics.record_failure(plugin_type, error)
        
        with self._errors_lock:
            self._initialization_errors[plugin_type] = error
        
        with self._ready_events_lock:
            if plugin_type in self._ready_events:
                self._ready_events[plugin_type].set()
    
    def _do_initialize(self, task: InitializationTask) -> Any:
        """Perform the actual plugin initialization.
        
        [OPTIMIZATION] Unified initialization logic using PluginInitializerUtils
        
        This method now uses the centralized PluginInitializerUtils for
        consistent initialization behavior across all modules.
        
        Args:
            task: The initialization task.
            
        Returns:
            The initialized plugin instance.
            
        Raises:
            Exception: If initialization fails.
        """
        from .initializer_utils import PluginInitializerUtils, PluginInitializationError
        
        config = task.config
        module_name = config.get("module_name", "")
        function_name = config.get("function_name", "init")
        class_name = config.get("class_name")
        plugin_config = config.get("config", {})
        
        if not module_name:
            raise ValueError(f"Plugin '{task.plugin_type}' missing module_name")

        success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
            module_name=module_name,
            function_name=function_name,
            plugin_config=plugin_config,
            class_name=class_name,
            timeout=task.timeout,
        )
        
        if success:
            return result
        
        if error_msg:
            raise PluginInitializationError(error_msg)
        
        raise PluginInitializationError(
            f"Plugin '{task.plugin_type}' initialization failed"
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get initialization performance metrics.
        
        Returns:
            A dictionary containing performance metrics and statistics.
        """
        return self._metrics.get_summary()
    
    def get_future(self, plugin_type: str) -> Optional["PluginFuture"]:
        """Get the PluginFuture for a specific plugin.
        
        Args:
            plugin_type: The type identifier of the plugin.
            
        Returns:
            The PluginFuture if available, None otherwise.
        """
        with self._futures_lock:
            return self._futures.get(plugin_type)
    
    def get_all_futures(self) -> Dict[str, "PluginFuture"]:
        """Get all PluginFuture objects.
        
        Returns:
            A dictionary mapping plugin types to their PluginFuture objects.
        """
        with self._futures_lock:
            return dict(self._futures)
    
    def wait_for_completion(self, timeout: float = 120.0) -> Dict[str, bool]:
        """Wait for all scheduled tasks to complete.
        
        Args:
            timeout: Maximum time to wait in seconds.
            
        Returns:
            A dictionary mapping plugin types to their completion status.
        """
        results: Dict[str, bool] = {}
        end_time = time.time() + timeout
        
        with self._ready_events_lock:
            events = dict(self._ready_events)
        
        for plugin_type, event in events.items():
            remaining = end_time - time.time()
            if remaining <= 0:
                results[plugin_type] = False
                continue
            
            results[plugin_type] = event.wait(timeout=remaining)
        
        return results
    
    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler and release resources.
        
        Args:
            wait: If True, wait for pending tasks to complete.
        """
        self._shutdown_event.set()
        
        with self._executor_lock:
            if self._executor is not None:
                self._executor.shutdown(wait=wait)
                self._executor = None
        
        self._logger.info("ParallelInitializationScheduler has been shut down")
    
    def is_shutdown(self) -> bool:
        """Check if the scheduler has been shut down.
        
        Returns:
            True if shutdown has been called, False otherwise.
        """
        return self._shutdown_event.is_set()
    
    def reset(self) -> None:
        """Reset the scheduler for reuse.
        
        This method clears all futures, events, and metrics.
        The executor is not affected.
        """
        with self._futures_lock:
            self._futures.clear()
        
        with self._ready_events_lock:
            self._ready_events.clear()
        
        with self._errors_lock:
            self._initialization_errors.clear()
        
        self._metrics.reset()
        
        self._shutdown_event.clear()
        
        self._logger.debug("Scheduler has been reset")


__all__ = [
    "InitializationTask",
    "InitializationMetrics",
    "PriorityInitializationQueue",
    "ParallelInitializationScheduler",
]
