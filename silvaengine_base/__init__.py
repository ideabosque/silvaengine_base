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
    # Core plugin management
    "PluginManager",
    "PluginConfiguration",
    "PluginMetrics",
    "IPluginManager",
    # Context management
    "PluginContext",
    "PluginContextDescriptor",
    "PluginContextInjector",
    "LazyPluginContext",
    "AbstractPluginContext",
    "EagerPluginContext",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerRegistry",
    # Exceptions and states
    "PluginNotFoundError",
    "PluginInitializationTimeoutError",
    "PluginInitializationError",
    # Configuration
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
    # Dependency management
    "DependencyResolver",
    "PluginDependency",
    "UnifiedDependencyResolver",
    # Thread pool management
    "ThreadPoolManager",
    "get_thread_pool_manager",
    "reset_thread_pool_manager",
    # Context injection utilities
    "get_current_plugin_context",
    "set_current_plugin_context",
    "clear_current_plugin_context",
    "inject_plugin_context",
    "get_plugin_context",
]

from .boosters import (
    AsyncPluginInitializer,
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    DependencyResolver,
    EagerPluginContext,
    InitializationMetrics,
    InitializationState,
    InitializationStatus,
    InitializationTask,
    InitializationTracker,
    LazyPluginContext,
    ParallelInitializationScheduler,
    PluginConfiguration,
    PluginContext,
    PluginContextDescriptor,
    PluginContextInjector,
    PluginDependency,
    PluginFuture,
    PluginInitializationError,
    PluginInitializationTimeoutError,
    PluginInitializer,
    PluginManager,
    PluginNotFoundError,
    ThreadPoolManager,
    UnifiedDependencyResolver,
    clear_current_plugin_context,
    get_config_manager,
    get_current_plugin_context,
    get_plugin_context,
    get_thread_pool_manager,
    inject_plugin_context,
    reset_config_manager,
    reset_thread_pool_manager,
    set_current_plugin_context,
)
from .boosters.plugin import (
    AbstractPluginContext,
    IPluginManager,
    PluginConfigManager,
    PluginMetrics,
)
from .resources import Resources
