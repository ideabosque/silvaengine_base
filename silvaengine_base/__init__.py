#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Silvaengine base module for plugin management and initialization scheduling.

This module provides the core infrastructure for:
- Plugin registration and coordination
- Initialization scheduling with timeout control
- Event handling and routing
- Context propagation to business modules
- Circuit breaker pattern for fault tolerance
- Lazy loading for improved cold start performance
- Centralized configuration management
- Asynchronous plugin initialization framework

Pool management functionality has been migrated to silvaengine_connections module.
"""

__all__ = [
    "Resources",
    "PluginManager",
    "PluginConfiguration",
    "PluginContext",
    "PluginContextDescriptor",
    "PluginContextInjector",
    "LazyPluginContext",
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerRegistry",
    "PluginNotFoundError",
    "PluginInitializationTimeoutError",
    "PluginState",
    "AbstractPluginContext",
    "EagerPluginContext",
    "PluginConfigManager",
    "PluginInitializer",
    "get_config_manager",
    "reset_config_manager",
    # Async initialization framework
    "AsyncPluginInitializer",
    "InitializationState",
    "InitializationStatus",
    "InitializationTracker",
    "PluginFuture",
    # Parallel scheduler
    "ParallelInitializationScheduler",
    "InitializationTask",
    "InitializationMetrics",
    # New async plugin manager
    "AsyncPluginManager",
    "AsyncPluginContext",
    "PluginLoadingState",
    "PluginLoadResult",
    "LoadingMetrics",
    "get_async_plugin_manager",
    "reset_async_plugin_manager",
]

from .boosters import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    LazyPluginContext,
    PluginConfiguration,
    PluginContext,
    PluginContextDescriptor,
    PluginContextInjector,
    PluginManager,
    PluginNotFoundError,
    PluginInitializationTimeoutError,
    PluginState,
    AbstractPluginContext,
    EagerPluginContext,
    PluginConfigManager,
    PluginInitializer,
    get_config_manager,
    reset_config_manager,
    get_current_plugin_context,
    set_current_plugin_context,
    clear_current_plugin_context,
    inject_plugin_context,
    get_plugin_context,
)
from .boosters.plugin.async_initializer import (
    AsyncPluginInitializer,
    InitializationState,
    InitializationStatus,
    InitializationTracker,
    PluginFuture,
)
from .boosters.plugin.parallel_scheduler import (
    ParallelInitializationScheduler,
    InitializationTask,
    InitializationMetrics,
)
from .boosters.plugin.async_plugin_manager import (
    AsyncPluginManager,
    AsyncPluginContext,
    PluginLoadingState,
    PluginLoadResult,
    LoadingMetrics,
    get_async_plugin_manager,
    reset_async_plugin_manager,
)
from .resources import Resources
