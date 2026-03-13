#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Plugin manager for silvaengine_base.

This module provides a unified plugin management system with support for:
- Synchronous and asynchronous plugin initialization
- Parallel loading with dependency resolution
- Circuit breaker pattern for fault tolerance
- Lazy loading for on-demand initialization
- Comprehensive metrics and monitoring

Architecture:
    PluginManager (Singleton)
    ├── AsyncPluginInitializer (background initialization)
    ├── DependencyResolver (dependency management)
    ├── CircuitBreakerRegistry (fault tolerance)
    └── PluginContext (eager/lazy loading)

Example:
    >>> from silvaengine_base.boosters.plugin import PluginManager
    >>> manager = PluginManager()
    >>> manager.initialize({"plugins": [...]})
    >>> context = manager.get_context()
    >>> plugin = context.get("my_plugin")

@since 2.0.0
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol, Set, Union

if TYPE_CHECKING:
    from .async_initializer import AsyncPluginInitializer

from silvaengine_utility import Invoker

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    get_circuit_breaker_registry,
)
from .config_manager import (
    PluginConfigManager,
    get_config_manager,
    reset_config_manager,
)
from .config_validator import (
    ConfigValidator,
    ValidationResult,
    get_config_validator,
)
from .async_initializer import (
    AsyncPluginInitializer,
    InitializationState,
    InitializationStatus,
    InitializationTracker,
    PluginFuture,
)
from .context import (
    AbstractPluginContext,
    EagerPluginContext,
    LazyPluginContext,
    PluginContext,
    PluginInitializationTimeoutError,
    PluginNotFoundError,
    get_plugin_context,
)
from .dependency import (
    DependencyResolver,
    PluginDependency,
    UnifiedDependencyResolver,
)
from .initializer_utils import PluginInitializationError, PluginInitializerUtils
from .injector import (
    PluginContextDescriptor,
    PluginContextInjector,
    clear_current_plugin_context,
    get_current_plugin_context,
    inject_plugin_context,
    set_current_plugin_context,
)
from .parallel_scheduler import (
    InitializationMetrics,
    InitializationTask,
    ParallelInitializationScheduler,
)
from .thread_pool_manager import (
    ThreadPoolManager,
    get_thread_pool_manager,
    reset_thread_pool_manager,
)

# Default configuration constants
DEFAULT_WORKERS_PER_CPU = 4
DEFAULT_PLUGIN_INIT_TIMEOUT = 30.0
DEFAULT_GLOBAL_INIT_TIMEOUT = 120.0
DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
DEFAULT_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60.0





@dataclass
class PluginConfiguration:
    """Plugin configuration data class.
    
    Attributes:
        plugin_type: Unique identifier for the plugin type
        config: Plugin-specific configuration dictionary
        enabled: Whether the plugin is enabled
        module_name: Python module name containing the plugin
        class_name: Optional class name for class-based plugins
        function_name: Initialization function name (default: "init")
        dependencies: List of plugin types this plugin depends on
        priority: Loading priority (higher = loaded first within same level)
    """
    plugin_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    module_name: str = ""
    class_name: Optional[str] = None
    function_name: str = "init"
    dependencies: List[str] = field(default_factory=list)
    priority: int = 0

    @classmethod
    def from_dict(cls, plugin_type: str, data: Dict[str, Any]) -> PluginConfiguration:
        """Create PluginConfiguration from dictionary.
        
        Args:
            plugin_type: The plugin type identifier
            data: Configuration dictionary
            
        Returns:
            PluginConfiguration instance
        """
        plugin_config = data.get("config") or data.get("resources") or {}

        return cls(
            plugin_type=plugin_type,
            config=plugin_config,
            enabled=data.get("enabled", True),
            module_name=data.get("module_name", ""),
            class_name=data.get("class_name"),
            function_name=data.get("function_name", "init"),
            dependencies=data.get("dependencies", []),
            priority=data.get("priority", 0),
        )


@dataclass
class PluginMetrics:
    """Plugin initialization metrics.
    
    This class consolidates metrics collection that was previously
    scattered across multiple modules (AsyncPluginManager, InitializationTracker).
    
    Attributes:
        total_plugins: Total number of plugins registered
        loaded_plugins: Number of successfully loaded plugins
        failed_plugins: Number of failed plugin initializations
        degraded_plugins: Number of plugins in degraded mode
        total_loading_time: Cumulative loading time in seconds
        start_time: Global initialization start timestamp
        end_time: Global initialization end timestamp
        cache_hits: Number of plugin cache hits
        cache_misses: Number of plugin cache misses
    """
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
        """Calculate initialization success rate."""
        if self.total_plugins == 0:
            return 0.0
        return self.loaded_plugins / self.total_plugins

    @property
    def average_loading_time(self) -> float:
        """Calculate average loading time per plugin."""
        if self.loaded_plugins == 0:
            return 0.0
        return self.total_loading_time / self.loaded_plugins

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def record_response_time(self, response_time_ms: float) -> None:
        """Record response time with exponential moving average.
        
        Args:
            response_time_ms: Response time in milliseconds
        """
        if self.avg_response_time_ms == 0:
            self.avg_response_time_ms = response_time_ms
        else:
            self.avg_response_time_ms = 0.9 * self.avg_response_time_ms + 0.1 * response_time_ms

    def record_start(self) -> None:
        """Record initialization start time."""
        if self.start_time is None:
            self.start_time = time.time()

    def record_end(self) -> None:
        """Record initialization end time."""
        self.end_time = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary.
        
        Returns:
            Dictionary containing all metrics
        """
        return {
            "total_plugins": self.total_plugins,
            "loaded_plugins": self.loaded_plugins,
            "failed_plugins": self.failed_plugins,
            "degraded_plugins": self.degraded_plugins,
            "success_rate": self.success_rate,
            "average_loading_time": self.average_loading_time,
            "total_loading_time": self.total_loading_time,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": self.cache_hit_rate,
            "avg_response_time_ms": self.avg_response_time_ms,
        }


class IPluginManager(Protocol):
    """Protocol defining the plugin manager interface.
    
    This protocol defines the contract that all plugin manager
    implementations must follow, enabling better type checking
    and code documentation.
    """

    def initialize(self, setting: Dict[str, Any]) -> bool:
        """Initialize plugins from configuration."""
        ...

    def get_initialized_object(self, plugin_type: str) -> Optional[Any]:
        """Get an initialized plugin by type."""
        ...

    def get_initialized_objects(self) -> Dict[str, Any]:
        """Get all initialized plugins."""
        ...

    def get_context(self, timeout: float = 10.0) -> AbstractPluginContext:
        """Get plugin context."""
        ...

    def is_initialized(self) -> bool:
        """Check if manager is initialized."""
        ...


class PluginManager:
    """Unified plugin manager with comprehensive initialization support.
    
    This class provides a singleton plugin manager that supports:
    - Synchronous and asynchronous initialization
    - Parallel loading with dependency resolution
    - Circuit breaker pattern for fault tolerance
    - Lazy loading for on-demand initialization
    - Comprehensive metrics collection
    
    The manager uses a thread-safe singleton pattern and provides
    both blocking and non-blocking initialization options.
    
    Example:
        >>> manager = PluginManager()
        >>> success = manager.initialize({"plugins": [...]})
        >>> if success:
        ...     context = manager.get_context()
        ...     plugin = context.get("my_plugin")
    
    Attributes:
        _instance: Singleton instance
        _lock: Class-level lock for singleton creation
        _initialized_objects: Dictionary of initialized plugin instances
        _config: Current configuration dictionary
        _logger: Logger instance
        _manager_lock: Instance-level lock for thread safety
        _is_initialized: Initialization state flag
        _initialized_event: Event for initialization completion
        _parallel_enabled: Flag for parallel initialization
        _max_workers: Maximum worker threads for parallel init
        _dependency_resolver: Dependency resolver instance
        _config_validator: Configuration validator instance
        _validation_strict_mode: Strict validation flag
        _plugin_init_timeout: Timeout for individual plugin init
        _global_init_timeout: Timeout for global initialization
        _circuit_breaker_enabled: Circuit breaker flag
        _circuit_breaker_failure_threshold: Circuit breaker threshold
        _circuit_breaker_recovery_timeout: Circuit breaker recovery time
        _lazy_loading_enabled: Lazy loading flag
        _lazy_context: Lazy plugin context
        _async_initializer: Async initializer instance
        _stored_initialization_callback: Callback for init completion
        _metrics: Plugin initialization metrics
        _plugin_states: Dictionary tracking plugin states
    
    Thread Safety:
        All public methods are thread-safe. Internal state is protected
        by locks where necessary.
    
    @since 2.0.0
    """

    _instance: Optional[PluginManager] = None
    _lock = threading.Lock()

    def __new__(cls, logger: Optional[logging.Logger] = None) -> PluginManager:
        """Create or return singleton instance.
        
        Args:
            logger: Optional logger instance
            
        Returns:
            PluginManager singleton instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        """Initialize the plugin manager.
        
        Args:
            logger: Optional logger instance
        """
        with self._lock:
            if getattr(self, "_is_initialized", False):
                return

            self._initialized_objects: Dict[str, Any] = {}
            self._config: Dict[str, Any] = {}
            self._logger = logger or logging.getLogger(__name__)
            self._manager_lock = threading.RLock()
            self._is_initialized = False
            self._initialized_event = threading.Event()
            self._parallel_enabled = True
            self._max_workers = (os.cpu_count() or 1) * DEFAULT_WORKERS_PER_CPU
            self._dependency_resolver = DependencyResolver(self._logger)
            self._config_validator = get_config_validator()
            self._validation_strict_mode = False

            self._plugin_init_timeout = DEFAULT_PLUGIN_INIT_TIMEOUT
            self._global_init_timeout = DEFAULT_GLOBAL_INIT_TIMEOUT

            self._circuit_breaker_enabled = True
            self._circuit_breaker_failure_threshold = DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD
            self._circuit_breaker_recovery_timeout = DEFAULT_CIRCUIT_BREAKER_RECOVERY_TIMEOUT

            self._lazy_loading_enabled = False
            self._lazy_context: Optional[LazyPluginContext] = None
            self._async_initializer: Optional[AsyncPluginInitializer] = None
            self._stored_initialization_callback: Optional[Callable[[Dict[str, bool]], None]] = None

            # Initialize metrics and state tracking (merged from AsyncPluginManager)
            self._metrics = PluginMetrics()
            self._plugin_states: Dict[str, InitializationState] = {}

            self._logger.info(
                f"PluginManager initialized with max_workers={self._max_workers}, "
                f"plugin_timeout={self._plugin_init_timeout}s, "
                f"global_timeout={self._global_init_timeout}s"
            )

    def initialize(self, setting: Dict[str, Any]) -> bool:
        """Initialize plugins from handler settings.
        
        This method validates the configuration, resolves dependencies,
        and initializes all configured plugins. It supports both eager
        and lazy loading modes.
        
        Args:
            setting: Configuration dictionary containing plugins settings
            
        Returns:
            True if initialization succeeded, False otherwise
        """
        self._logger.debug(f"Setting: {setting}")
        
        if setting is None:
            self._logger.error("Invalid setting: setting cannot be None")
            return False

        if not isinstance(setting, dict):
            self._logger.error(
                f"Invalid setting: must be a dictionary, got {type(setting).__name__}"
            )
            return False

        plugins_config = setting.get("plugins")

        if not plugins_config:
            self._logger.warning("No plugins configuration found")
            return False

        # Validate configuration
        validation_result = self._config_validator.validate_plugins_config(plugins_config)

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
                self._metrics.record_start()
                self._metrics.total_plugins = len(plugins_config)

                if self._lazy_loading_enabled:
                    self._setup_lazy_loading(plugins_config)
                else:
                    self._process_plugins_config(plugins_config)

                self._is_initialized = True
                self._initialized_event.set()
                self._metrics.record_end()
                
                self._logger.info(
                    f"PluginManager initialized successfully: "
                    f"{self._metrics.loaded_plugins}/{self._metrics.total_plugins} plugins ready"
                )
                return True

            except Exception as e:
                self._logger.error(f"Failed to initialize PluginManager: {e}")
                return False

    def _setup_lazy_loading(self, plugins_config: List) -> None:
        """Setup lazy loading for plugins.
        
        Args:
            plugins_config: List of plugin configuration dictionaries
        """
        plugin_configs_dict = {}

        for plugin_item in plugins_config:
            if isinstance(plugin_item, dict):
                plugin_type = plugin_item.get("type", "").strip().lower()
                if plugin_type:
                    plugin_configs_dict[plugin_type] = plugin_item
                    self._plugin_states[plugin_type] = InitializationState.PENDING

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
        """Process plugins configuration without blocking.
        
        This method starts background initialization for all plugins
        and returns immediately. Use wait_for_initialization() to
        wait for completion.
        
        Args:
            plugins_config: List of plugin configuration dictionaries
        """
        if not isinstance(plugins_config, list) or not plugins_config:
            return

        from .async_initializer import AsyncPluginInitializer

        if self._async_initializer is None:
            self._async_initializer = AsyncPluginInitializer(
                plugin_manager=self,
                logger=self._logger,
                max_workers=self._max_workers,
            )

        if self._async_initializer.is_shutdown():
            self._async_initializer = AsyncPluginInitializer(
                plugin_manager=self,
                logger=self._logger,
                max_workers=self._max_workers,
            )

        # Initialize plugin states
        for config in plugins_config:
            plugin_type = config.get("type", "").strip().lower() if isinstance(config, dict) else ""
            if plugin_type:
                self._plugin_states[plugin_type] = InitializationState.PENDING

        self._async_initializer.initialize_background(plugins_config)

        self._logger.info(
            f"Started background initialization for {len(plugins_config)} plugins"
        )

    def _do_process_plugins_config(self, plugins_config: List) -> None:
        """Actual plugin configuration processing with dependency resolution.
        
        This method is called internally for synchronous processing.
        
        Args:
            plugins_config: List of plugin configuration dictionaries
        """
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

            resolved_order = self._dependency_resolver.resolve_dependencies(dependencies)
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
        """Extract plugin dependencies from configuration.
        
        Args:
            plugins_config: List of plugin configuration dictionaries
            
        Returns:
            List of PluginDependency objects
        """
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
        """Reorder plugins based on dependency resolution.
        
        Args:
            plugins_config: Original plugin configuration list
            resolved_order: Dependency-resolved plugin type order
            
        Returns:
            Reordered plugin configuration list
        """
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
        """Process plugins configuration sequentially.
        
        Args:
            plugins_config: List of plugin configuration dictionaries
        """
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
        """Process plugins configuration in parallel.
        
        Args:
            plugins_config: List of plugin configuration dictionaries
            
        Returns:
            Dictionary mapping plugin types to initialization results
        """
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

        from .thread_pool_manager import get_thread_pool_manager

        executor = get_thread_pool_manager().get_executor(
            "plugin_manager_parallel",
            max_workers=max_workers,
        )

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
                    self._metrics.loaded_plugins += 1
                    self._plugin_states[config.plugin_type] = InitializationState.READY
                    self._logger.debug(
                        f"Plugin {config.plugin_type} initialized successfully"
                    )
                else:
                    self._metrics.failed_plugins += 1
                    self._plugin_states[config.plugin_type] = InitializationState.FAILED
                    self._logger.warning(
                        f"Plugin {config.plugin_type} initialization failed: {result.get('error')}"
                    )

            except FutureTimeoutError:
                error_msg = f"Plugin {config.plugin_type} initialization timed out after {self._plugin_init_timeout}s"
                self._logger.error(error_msg)
                self._metrics.failed_plugins += 1
                self._plugin_states[config.plugin_type] = InitializationState.FAILED
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
                self._metrics.failed_plugins += 1
                self._plugin_states[config.plugin_type] = InitializationState.FAILED
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
        """Extract plugin configurations from a config item.
        
        Args:
            plugin_config: Plugin configuration dictionary
            index: Index in the configuration list
            
        Returns:
            List of PluginConfiguration objects
        """
        configs: List[PluginConfiguration] = []

        reserved_keys = {
            "config",
            "enabled",
            "module_name",
            "class_name",
            "function_name",
            "type",
            "dependencies",
            "priority",
        }

        for key, value in plugin_config.items():
            if isinstance(value, dict) and key not in reserved_keys:
                configs.append(PluginConfiguration.from_dict(key, value))

        if "config" in plugin_config and "type" in plugin_config:
            plugin_type = str(plugin_config.get("type")).strip().lower()
            configs.append(PluginConfiguration.from_dict(plugin_type, plugin_config))

        return configs

    def _process_single_plugin(self, plugin_config: Dict[str, Any], index: int) -> None:
        """Process a single plugin configuration.
        
        Args:
            plugin_config: Plugin configuration dictionary
            index: Index in the configuration list
        """
        configs = self._extract_plugin_configurations(plugin_config, index)

        for config in configs:
            self._logger.debug(
                f"Processing plugin {config.plugin_type} at index {index}"
            )
            result = self._initialize_plugin_safe(config)
            
            if result.get("success"):
                self._metrics.loaded_plugins += 1
                self._plugin_states[config.plugin_type] = InitializationState.READY
            else:
                self._metrics.failed_plugins += 1
                self._plugin_states[config.plugin_type] = InitializationState.FAILED

    def _initialize_plugin_safe(
        self, plugin_config: PluginConfiguration
    ) -> Dict[str, Any]:
        """Safely initialize a plugin with error handling.
        
        Args:
            plugin_config: Plugin configuration
            
        Returns:
            Dictionary containing initialization result
        """
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
        
        # Update state to initializing
        self._plugin_states[plugin_type] = InitializationState.INITIALIZING

        try:
            manager = self._execute_plugin_initialization(plugin_config, plugin_type)

            self._store_initialized_plugin(
                plugin_type=plugin_type,
                manager=manager,
                config={
                    "module_name": plugin_config.module_name,
                    "class_name": plugin_config.class_name,
                    "config": plugin_config.config,
                },
            )

            result["success"] = True
            result["manager"] = manager
            self._logger.info(f"Plugin {plugin_type} initialized successfully")

        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = type(e).__name__
            self._logger.error(f"Plugin {plugin_type}: {result['error']}")

        return result

    def _execute_plugin_initialization(
        self, plugin_config: PluginConfiguration, plugin_type: str
    ) -> Any:
        """Execute plugin initialization with optional circuit breaker protection.
        
        This method consolidates the initialization logic for both circuit breaker
        and non-circuit breaker scenarios, eliminating code duplication.
        
        Args:
            plugin_config: Plugin configuration
            plugin_type: Normalized plugin type identifier
            
        Returns:
            Initialized plugin instance
            
        Raises:
            Exception: If initialization fails
        """
        if self._circuit_breaker_enabled:
            circuit_breaker = get_circuit_breaker_registry().get_or_create(
                name=plugin_type,
                failure_threshold=self._circuit_breaker_failure_threshold,
                recovery_timeout=self._circuit_breaker_recovery_timeout,
            )
            return circuit_breaker.call(self._do_initialize_plugin, plugin_config)
        else:
            return self._do_initialize_plugin(plugin_config)

    def _do_initialize_plugin(self, plugin_config: PluginConfiguration) -> Any:
        """Perform actual plugin initialization with timeout protection.
        
        Args:
            plugin_config: Plugin configuration
            
        Returns:
            Initialized plugin instance
            
        Raises:
            PluginInitializationError: If initialization fails
        """
        success, result, error_msg = PluginInitializerUtils.invoke_plugin_init(
            module_name=plugin_config.module_name,
            function_name=plugin_config.function_name,
            plugin_config=plugin_config.config,
            class_name=plugin_config.class_name,
            timeout=self._plugin_init_timeout,
        )

        if success:
            return result

        if error_msg:
            raise PluginInitializationError(error_msg)

        raise PluginInitializationError(
            f"Plugin '{plugin_config.plugin_type}' initialization failed"
        )

    def _store_initialized_plugin(
        self,
        plugin_type: str,
        manager: Any,
        config: Dict[str, Any],
    ) -> None:
        """Store an initialized plugin.
        
        Args:
            plugin_type: Plugin type identifier
            manager: Plugin manager instance
            config: Plugin configuration
        """
        plugin_type = str(plugin_type).strip().lower()

        with self._manager_lock:
            self._initialized_objects[plugin_type] = {
                "manager": manager,
                "module_name": config.get("module_name"),
                "class_name": config.get("class_name"),
                "config": config.get("config"),
            }

        self._logger.debug(f"Stored initialized plugin: {plugin_type}")

    def get_initialized_objects(self) -> Dict[str, Any]:
        """Get all initialized plugin objects.
        
        Returns:
            Dictionary mapping plugin types to their data
        """
        return self._initialized_objects.copy()

    def get_initialized_object(self, plugin_type: str) -> Optional[Any]:
        """Get a specific initialized plugin.
        
        Args:
            plugin_type: Plugin type identifier
            
        Returns:
            Plugin instance or None
        """
        if not plugin_type:
            self._logger.warning(f"Invalid plugin type `{plugin_type}`")
            return None

        plugin_type = str(plugin_type).strip().lower()

        if self._lazy_loading_enabled and self._lazy_context:
            return self._lazy_context.get(plugin_type)

        return self._initialized_objects.get(plugin_type)

    def get_context(self, timeout: float = 10.0) -> AbstractPluginContext:
        """Get plugin context.
        
        Args:
            timeout: Maximum time to wait for initialization
            
        Returns:
            Plugin context instance
        """
        if self._lazy_loading_enabled and self._lazy_context:
            return self._lazy_context

        if not self._is_initialized and timeout > 0:
            if not self._initialized_event.wait(timeout=timeout):
                self._logger.warning(
                    f"PluginManager not initialized within {timeout}s timeout"
                )

        return EagerPluginContext(self)

    def is_initialized(self) -> bool:
        """Check if the manager is initialized.
        
        Returns:
            True if initialized, False otherwise
        """
        return self._is_initialized

    def get_plugin_state(self, plugin_type: str) -> InitializationState:
        """Get the initialization state of a specific plugin.

        Args:
            plugin_type: Plugin type identifier

        Returns:
            Current initialization state
        """
        plugin_type = str(plugin_type).strip().lower()
        return self._plugin_states.get(plugin_type, InitializationState.PENDING)

    def get_metrics(self) -> PluginMetrics:
        """Get initialization metrics.
        
        Returns:
            PluginMetrics instance
        """
        return self._metrics

    def get_async_initializer(self) -> Optional[AsyncPluginInitializer]:
        """Get the async initializer instance.
        
        Returns:
            AsyncPluginInitializer instance or None
        """
        return self._async_initializer

    def set_parallel_enabled(self, enabled: bool) -> None:
        """Enable or disable parallel initialization.
        
        Args:
            enabled: True to enable parallel initialization
        """
        self._parallel_enabled = enabled
        self._logger.debug(
            f"Parallel initialization {'enabled' if enabled else 'disabled'}"
        )

    def set_max_workers(self, max_workers: int) -> None:
        """Set maximum worker threads.
        
        Args:
            max_workers: Maximum number of worker threads
        """
        self._max_workers = max(1, max_workers)
        self._logger.debug(f"Max workers set to {self._max_workers}")

    def set_plugin_init_timeout(self, timeout: float) -> None:
        """Set plugin initialization timeout.
        
        Args:
            timeout: Timeout in seconds
        """
        self._plugin_init_timeout = max(1.0, timeout)
        self._logger.debug(
            f"Plugin initialization timeout set to {self._plugin_init_timeout}s"
        )

    def set_global_init_timeout(self, timeout: float) -> None:
        """Set global initialization timeout.
        
        Args:
            timeout: Timeout in seconds
        """
        self._global_init_timeout = max(1.0, timeout)
        self._logger.debug(
            f"Global initialization timeout set to {self._global_init_timeout}s"
        )

    def set_circuit_breaker_enabled(self, enabled: bool) -> None:
        """Enable or disable circuit breaker.
        
        Args:
            enabled: True to enable circuit breaker
        """
        self._circuit_breaker_enabled = enabled
        self._logger.debug(f"Circuit breaker {'enabled' if enabled else 'disabled'}")

    def set_lazy_loading_enabled(self, enabled: bool) -> None:
        """Enable or disable lazy loading.
        
        Args:
            enabled: True to enable lazy loading
        """
        self._lazy_loading_enabled = enabled
        self._logger.debug(f"Lazy loading {'enabled' if enabled else 'disabled'}")

    def set_validation_strict_mode(self, strict: bool) -> None:
        """Set validation strict mode.
        
        Args:
            strict: True for strict mode (fail on validation errors)
        """
        self._validation_strict_mode = strict
        self._logger.debug(
            f"Validation strict mode {'enabled' if strict else 'disabled'}"
        )

    def validate_configuration(
        self, plugins_config: List[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate plugins configuration without initializing.
        
        Args:
            plugins_config: List of plugin configurations
            
        Returns:
            ValidationResult with validation status
        """
        return self._config_validator.validate_plugins_config(plugins_config)

    def get_plugin_status(self, plugin_type: str) -> Dict[str, Any]:
        """Get the status of a specific plugin.
        
        Args:
            plugin_type: Plugin type identifier
            
        Returns:
            Dictionary containing plugin status
        """
        plugin_type = str(plugin_type).strip().lower()

        if self._lazy_loading_enabled and self._lazy_context:
            is_init = self._lazy_context.is_initialized(plugin_type)
            return {
                "plugin_type": plugin_type,
                "initialized": is_init,
                "lazy_loading": True,
            }

        initialized_object = self._initialized_objects.get(plugin_type)
        state = self._plugin_states.get(plugin_type, InitializationState.PENDING)

        if initialized_object:
            return {
                "plugin_type": plugin_type,
                "initialized": True,
                "state": state.value,
                "module_name": initialized_object.get("module_name"),
                "class_name": initialized_object.get("class_name"),
                "config_keys": list(initialized_object.get("config", {}).keys()),
            }

        return {
            "plugin_type": plugin_type,
            "initialized": False,
            "state": state.value,
        }

    def get_all_plugin_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all plugins.
        
        Returns:
            Dictionary mapping plugin types to their status
        """
        if self._lazy_loading_enabled and self._lazy_context:
            stats = self._lazy_context.get_initialization_stats()
            return {
                "lazy_loading_stats": stats,
            }

        return {
            plugin_type: self.get_plugin_status(plugin_type)
            for plugin_type in self._plugin_states.keys()
        }

    def initialize_async(self, setting: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize plugins asynchronously and return futures.
        
        Args:
            setting: Configuration dictionary
            
        Returns:
            Dictionary mapping plugin types to PluginFuture objects
        """
        self._logger.debug(f"Setting async: {setting}")
        
        if setting is None:
            self._logger.error("Invalid setting: setting cannot be None")
            return {}

        if not isinstance(setting, dict):
            self._logger.error(
                f"Invalid setting: must be a dictionary, got {type(setting).__name__}"
            )
            return {}

        plugins_config = setting.get("plugins")

        if not plugins_config:
            self._logger.warning("No plugins configuration found")
            return {}

        self._config = setting
        self._metrics.record_start()
        self._metrics.total_plugins = len(plugins_config)

        # Initialize the async initializer if needed
        if self._async_initializer is None:
            from .async_initializer import AsyncPluginInitializer

            self._async_initializer = AsyncPluginInitializer(
                plugin_manager=self,
                logger=self._logger,
                max_workers=self._max_workers,
            )

        # Initialize plugin states
        for config in plugins_config:
            plugin_type = config.get("type", "").strip().lower() if isinstance(config, dict) else ""
            if plugin_type:
                self._plugin_states[plugin_type] = InitializationState.PENDING

        # Start async initialization
        futures = self._async_initializer.initialize_async(plugins_config)

        self._is_initialized = True
        self._initialized_event.set()
        self._logger.info("PluginManager async initialization started")

        return futures

    def initialize_background(
        self,
        setting: Dict[str, Any],
        callback: Optional[Callable[[Dict[str, bool]], None]] = None,
    ) -> None:
        """Initialize plugins in background without blocking.
        
        Args:
            setting: Configuration dictionary
            callback: Optional callback for completion notification
        """
        self._logger.debug(f"Setting background: {setting}")

        if setting is None:
            self._logger.error("Invalid setting: setting cannot be None")
            return

        if not isinstance(setting, dict):
            self._logger.error(
                f"Invalid setting: must be a dictionary, got {type(setting).__name__}"
            )
            return

        plugins_config = setting.get("plugins")

        if not plugins_config:
            self._logger.warning("No plugins configuration found")
            return

        self._config = setting
        self._metrics.record_start()
        self._metrics.total_plugins = len(plugins_config)

        # Use lazy loading if enabled
        if self._lazy_loading_enabled:
            self._setup_lazy_loading(plugins_config)
            self._is_initialized = True
            self._initialized_event.set()
            self._logger.info("PluginManager lazy loading setup complete")
            return

        # Initialize the async initializer if needed
        if self._async_initializer is None:
            from .async_initializer import AsyncPluginInitializer

            self._async_initializer = AsyncPluginInitializer(
                plugin_manager=self,
                logger=self._logger,
                max_workers=self._max_workers,
            )

        # Initialize plugin states
        for config in plugins_config:
            plugin_type = config.get("type", "").strip().lower() if isinstance(config, dict) else ""
            if plugin_type:
                self._plugin_states[plugin_type] = InitializationState.PENDING

        # Start background initialization
        self._async_initializer.initialize_background(
            plugins_config=plugins_config,
            timeout=self._global_init_timeout,
        )

        # Store callback for later invocation
        if callback is not None:
            self._stored_initialization_callback = callback

        self._is_initialized = True
        self._initialized_event.set()
        self._logger.info("PluginManager background initialization started")

    def wait_for_initialization(self, timeout: float = 120.0) -> Dict[str, bool]:
        """Wait for all plugins to complete initialization.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            Dictionary mapping plugin types to success status
        """
        if self._async_initializer is not None:
            result = self._async_initializer.wait_all(timeout=timeout)
            
            # Update metrics based on results
            for plugin_type, success in result.items():
                if success:
                    self._plugin_states[plugin_type] = InitializationState.READY
                    if plugin_type not in [k for k, v in self._initialized_objects.items()]:
                        self._metrics.loaded_plugins += 1
                else:
                    self._plugin_states[plugin_type] = InitializationState.FAILED
                    self._metrics.failed_plugins += 1
            
            if self._stored_initialization_callback is not None:
                try:
                    self._stored_initialization_callback(result)
                except Exception as exception:
                    self._logger.error(f"Error in initialization callback: {exception}")
            return result

        return {plugin_type: True for plugin_type in self._initialized_objects.keys()}

    def get_initialization_status(self) -> Dict[str, Any]:
        """Get current initialization status.
        
        Returns:
            Dictionary containing initialization status
        """
        if self._async_initializer is not None:
            return self._async_initializer.get_initialization_summary()

        # Fallback: return basic status
        return {
            "initialized": self._is_initialized,
            "status": "ready" if self._is_initialized else "not_initialized",
            "total_plugins": len(self._initialized_objects),
            "metrics": self._metrics.to_dict(),
        }

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the PluginManager singleton instance with proper cleanup."""
        with cls._lock:
            if cls._instance:
                instance = cls._instance
                try:
                    if hasattr(instance, "_manager_lock"):
                        with instance._manager_lock:
                            if hasattr(instance, "_initialized_objects"):
                                for (
                                    plugin_type,
                                    plugin_data,
                                ) in instance._initialized_objects.items():
                                    try:
                                        manager = plugin_data.get("manager")
                                        if manager and hasattr(manager, "cleanup"):
                                            manager.cleanup()
                                    except Exception as e:
                                        if hasattr(instance, "_logger"):
                                            instance._logger.warning(
                                                f"Error cleaning up plugin {plugin_type}: {e}"
                                            )
                                instance._initialized_objects.clear()
                            instance._is_initialized = False
                            if hasattr(instance, "_initialized_event"):
                                instance._initialized_event.clear()
                            instance._config = {}
                            if hasattr(instance, "_lazy_context"):
                                instance._lazy_context = None
                            if hasattr(instance, "_async_initializer") and instance._async_initializer:
                                instance._async_initializer.shutdown(wait=False)
                                instance._async_initializer = None
                            if hasattr(instance, "_plugin_states"):
                                instance._plugin_states.clear()
                            if hasattr(instance, "_metrics"):
                                instance._metrics = PluginMetrics()
                except Exception as e:
                    if hasattr(instance, "_logger"):
                        instance._logger.error(f"Error during PluginManager reset: {e}")
                finally:
                    cls._instance = None


# Public API exports
__all__ = [
    # Core classes
    "PluginManager",
    "PluginConfiguration",
    "PluginMetrics",
    "IPluginManager",
    # Async initialization
    "AsyncPluginInitializer",
    "InitializationState",
    "InitializationStatus",
    "InitializationTracker",
    "PluginFuture",
    # Context classes
    "AbstractPluginContext",
    "PluginContext",
    "EagerPluginContext",
    "LazyPluginContext",
    # Dependency management
    "DependencyResolver",
    "PluginDependency",
    "UnifiedDependencyResolver",
    # Configuration
    "ConfigValidator",
    "ValidationResult",
    "PluginConfigManager",
    "get_config_manager",
    "reset_config_manager",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerRegistry",
    "get_circuit_breaker_registry",
    # Injection
    "PluginContextDescriptor",
    "PluginContextInjector",
    "inject_plugin_context",
    "get_current_plugin_context",
    "set_current_plugin_context",
    "clear_current_plugin_context",
    # Parallel scheduler
    "ParallelInitializationScheduler",
    "InitializationTask",
    "InitializationMetrics",
    # Thread pool management
    "ThreadPoolManager",
    "get_thread_pool_manager",
    "reset_thread_pool_manager",
    # Exceptions and states
    "PluginNotFoundError",
    "PluginInitializationTimeoutError",
    "PluginInitializationError",
    "PluginInitializerUtils",
    # Utilities
    "get_plugin_context",
]
