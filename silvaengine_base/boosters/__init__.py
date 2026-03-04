#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Hub module for silvaengine_base.

This module provides plugin management functionality including:
- Plugin registration and coordination
- Initialization scheduling with timeout control
- Context propagation
- Dependency resolution
- Configuration validation
- Circuit breaker pattern for fault tolerance
- Lazy loading for improved cold start performance
"""

from .plugin import (
    CircuitBreaker,
    ConfigValidator,
    DependencyResolver,
    LazyPluginContext,
    PluginConfiguration,
    PluginContext,
    PluginContextDescriptor,
    PluginContextInjector,
    PluginDependency,
    PluginManager,
    PluginNotFoundError,
    ValidationResult,
    get_current_plugin_context,
    set_current_plugin_context,
    clear_current_plugin_context,
    inject_plugin_context,
)
from .plugin.circuit_breaker import (
    CircuitBreakerRegistry,
    CircuitState,
    get_circuit_breaker_registry,
)
from .plugin.context import (
    AbstractPluginContext,
    EagerPluginContext,
    PluginState,
    PluginInitializationTimeoutError,
    get_plugin_context,
)

__all__ = [
    "PluginManager",
    "PluginConfiguration",
    "PluginContext",
    "PluginContextDescriptor",
    "PluginContextInjector",
    "LazyPluginContext",
    "DependencyResolver",
    "PluginDependency",
    "ConfigValidator",
    "ValidationResult",
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerRegistry",
    "PluginNotFoundError",
    "PluginInitializationTimeoutError",
    "PluginState",
    "AbstractPluginContext",
    "EagerPluginContext",
    "get_circuit_breaker_registry",
    "get_current_plugin_context",
    "set_current_plugin_context",
    "clear_current_plugin_context",
    "inject_plugin_context",
    "get_plugin_context",
]
