#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Hub module for silvaengine_base.

This module provides plugin management functionality including:
- Plugin registration and coordination
- Initialization scheduling with timeout control
- Context propagation
- Dependency resolution
- Configuration validation
- Circuit breaker pattern for fault tolerance
- Lazy loading for improved cold start performance
- Centralized configuration management
"""

from .plugin import (
    AsyncPluginInitializer,
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    ConfigValidator,
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
    PluginManager,
    PluginMetrics,
    PluginNotFoundError,
    PluginInitializationError,
    PluginInitializationTimeoutError,
    PluginInitializerUtils,
    ThreadPoolManager,
    UnifiedDependencyResolver,
    ValidationResult,
    clear_current_plugin_context,
    get_circuit_breaker_registry,
    get_config_manager,
    get_current_plugin_context,
    get_plugin_context,
    get_thread_pool_manager,
    inject_plugin_context,
    reset_config_manager,
    reset_thread_pool_manager,
    set_current_plugin_context,
)
from .plugin_initializer import PluginInitializer

__all__ = [
    # Core plugin classes
    "PluginManager",
    "PluginConfiguration",
    "PluginMetrics",
    "PluginContext",
    "PluginContextDescriptor",
    "PluginContextInjector",
    "LazyPluginContext",
    "EagerPluginContext",
    "DependencyResolver",
    "PluginDependency",
    "UnifiedDependencyResolver",
    "ConfigValidator",
    "ValidationResult",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerRegistry",
    "get_circuit_breaker_registry",
    # Async initialization
    "AsyncPluginInitializer",
    "InitializationState",
    "InitializationStatus",
    "InitializationTracker",
    "PluginFuture",
    # Parallel scheduler
    "ParallelInitializationScheduler",
    "InitializationTask",
    "InitializationMetrics",
    # Thread pool management
    "ThreadPoolManager",
    "get_thread_pool_manager",
    "reset_thread_pool_manager",
    # Configuration management
    "get_config_manager",
    "reset_config_manager",
    # Plugin initializer
    "PluginInitializer",
    # Utility functions
    "get_current_plugin_context",
    "set_current_plugin_context",
    "clear_current_plugin_context",
    "inject_plugin_context",
    "get_plugin_context",
    # Exceptions
    "PluginNotFoundError",
    "PluginInitializationTimeoutError",
    "PluginInitializationError",
    "PluginInitializerUtils",
]
