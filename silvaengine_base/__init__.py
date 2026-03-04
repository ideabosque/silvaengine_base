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
    "PluginNotFoundError",
]

from .boosters.plugin import (
    CircuitBreaker,
    LazyPluginContext,
    PluginConfiguration,
    PluginContext,
    PluginContextDescriptor,
    PluginContextInjector,
    PluginManager,
    PluginNotFoundError,
    get_current_plugin_context,
    inject_plugin_context,
)
from .boosters.plugin.circuit_breaker import CircuitState
from .resources import Resources
