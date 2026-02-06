#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Silvaengine base module for plugin management and initialization scheduling.

This module provides the core infrastructure for:
- Plugin registration and coordination
- Initialization scheduling
- Event handling and routing
- Context propagation to business modules

Pool management functionality has been migrated to silvaengine_connections module.
"""

__all__ = ["Resources", "PluginManager"]

from .plugin_manager import PluginManager
from .resources import Resources
