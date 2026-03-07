#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Plugin dependency management module.

[OPTIMIZATION] Merged UnifiedDependencyResolver into this module

This module now contains all dependency resolution logic:
- DependencyNode: Data class for dependency graph nodes
- PluginDependency: Plugin dependency configuration
- UnifiedDependencyResolver: Static methods for dependency resolution
- DependencyResolver: High-level dependency resolver

This consolidation eliminates the need for unified_dependency.py and
simplifies the module structure.

@since 2.0.0
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class DependencyNode:
    """Node in a dependency graph."""
    name: str
    dependencies: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class PluginDependency:
    """Plugin dependency data class."""
    plugin_name: str
    dependencies: List[str] = field(default_factory=list)
    version: str = ""
    optional: bool = False


class UnifiedDependencyResolver:
    """Unified dependency resolver for plugin system.
    
    This class provides static methods for dependency resolution operations,
    eliminating code duplication across the codebase.
    
    Performance Characteristics:
        - detect_cycle: O(V + E) where V is vertices and E is edges
        - topological_sort: O(V + E)
        - validate_dependencies: O(V * D) where D is average dependencies
        
    Thread Safety:
        All methods are stateless and thread-safe.
    """
    
    @staticmethod
    def detect_cycle(
        nodes: Dict[str, List[str]],
        logger: Optional[logging.Logger] = None,
    ) -> Optional[List[str]]:
        """Detect circular dependencies using DFS.
        
        This unified method eliminates code duplication between:
        - DependencyResolver.detect_circular_dependencies()
        - ParallelInitializationScheduler._detect_cycle()
        
        Args:
            nodes: Dictionary mapping node names to their dependencies.
            logger: Optional logger for diagnostic messages.
            
        Returns:
            A list representing the cycle path if found, None otherwise.
            
        Performance:
            Time: O(V + E) where V is vertices and E is edges
            Space: O(V) for visited and recursion stack
            
        Thread Safety:
            Stateless operation, thread-safe.
        """
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []
        
        def dfs(node: str) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for dependent in nodes.get(node, []):
                if dependent not in visited:
                    result = dfs(dependent)
                    if result:
                        return result
                elif dependent in rec_stack:
                    cycle_start = path.index(dependent)
                    cycle = path[cycle_start:] + [dependent]
                    if logger:
                        logger.error(
                            f"Circular dependency detected: {' -> '.join(cycle)}"
                        )
                    return cycle
            
            path.pop()
            rec_stack.discard(node)
            return None
        
        for node in nodes:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    return cycle
        
        if logger:
            logger.info("No circular dependencies detected")
        return None
    
    @staticmethod
    def topological_sort(
        nodes: Dict[str, List[str]],
        logger: Optional[logging.Logger] = None,
    ) -> Tuple[bool, List[str]]:
        """Perform topological sort on dependency graph.
        
        This unified method eliminates code duplication between:
        - DependencyResolver.resolve_dependencies()
        - ParallelInitializationScheduler._topological_sort()
        
        Args:
            nodes: Dictionary mapping node names to their dependencies.
            logger: Optional logger for diagnostic messages.
            
        Returns:
            Tuple of (success, sorted_list).
            If there's a cycle, returns (False, partial_list).
            
        Performance:
            Time: O(V + E) where V is vertices and E is edges
            Space: O(V) for in-degree map and queue
            
        Thread Safety:
            Stateless operation, thread-safe.
        """
        in_degree: Dict[str, int] = defaultdict(int)
        graph: Dict[str, List[str]] = defaultdict(list)
        
        for node, deps in nodes.items():
            if node not in in_degree:
                in_degree[node] = 0
            
            for dep in deps:
                if dep in nodes:
                    graph[dep].append(node)
                    in_degree[node] += 1
                elif logger:
                    logger.warning(
                        f"Node '{node}' depends on '{dep}' which is not defined"
                    )
        
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        sorted_nodes: List[str] = []
        
        while queue:
            current = queue.popleft()
            sorted_nodes.append(current)
            
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        success = len(sorted_nodes) == len(nodes)
        
        if not success and logger:
            logger.warning(
                "Not all nodes could be sorted - possible circular dependency detected"
            )
        elif logger:
            logger.info(
                f"Resolved {len(sorted_nodes)} nodes in dependency order"
            )
        
        return (success, sorted_nodes)
    
    @staticmethod
    def validate_dependencies(
        nodes: Dict[str, List[str]],
        logger: Optional[logging.Logger] = None,
    ) -> Dict[str, List[str]]:
        """Validate that all declared dependencies exist.
        
        Args:
            nodes: Dictionary mapping node names to their dependencies.
            logger: Optional logger for diagnostic messages.
            
        Returns:
            Dictionary mapping node names to their missing dependencies.
        """
        node_names = set(nodes.keys())
        missing_deps: Dict[str, List[str]] = {}
        
        for node, deps in nodes.items():
            missing = [dep for dep in deps if dep not in node_names]
            if missing:
                missing_deps[node] = missing
                if logger:
                    logger.warning(
                        f"Node '{node}' has missing dependencies: {missing}"
                    )
        
        return missing_deps
    
    @staticmethod
    def build_dependency_graph(
        items: List[DependencyNode],
        logger: Optional[logging.Logger] = None,
    ) -> Dict[str, List[str]]:
        """Build dependency graph from list of nodes.
        
        Args:
            items: List of DependencyNode objects.
            logger: Optional logger for diagnostic messages.
            
        Returns:
            Dictionary mapping node names to their dependencies.
        """
        graph: Dict[str, List[str]] = {}
        item_names = {item.name for item in items}
        
        for item in items:
            valid_deps = []
            for dep in item.dependencies:
                if dep in item_names:
                    valid_deps.append(dep)
                elif logger:
                    logger.warning(
                        f"Item '{item.name}' depends on '{dep}' "
                        f"which is not in the item list"
                    )
            graph[item.name] = valid_deps
        
        return graph


class DependencyResolver:
    """Dependency resolver for plugin system.
    
    [OPTIMIZATION] Uses UnifiedDependencyResolver for all operations
    
    This class delegates all dependency resolution operations to
    UnifiedDependencyResolver, providing a high-level interface
    for plugin dependency management.
    
    Performance Characteristics:
        - resolve_dependencies: O(V + E)
        - detect_circular_dependencies: O(V + E)
        - validate_dependencies: O(V * D)
    
    Thread Safety:
        All operations are delegated to stateless methods in UnifiedDependencyResolver.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the dependency resolver."""
        self._logger = logger or logging.getLogger(__name__)

    def resolve_dependencies(self, plugins: List[PluginDependency]) -> List[PluginDependency]:
        """Resolve plugin dependencies using topological sort.
        
        Uses UnifiedDependencyResolver.topological_sort()
        
        Args:
            plugins: List of PluginDependency objects to resolve.
            
        Returns:
            List of PluginDependency objects in dependency order.
        """
        if not plugins:
            self._logger.debug("No plugins provided for dependency resolution")
            return []

        plugin_map: Dict[str, PluginDependency] = {
            p.plugin_name: p for p in plugins
        }
        
        nodes: Dict[str, List[str]] = {
            p.plugin_name: p.dependencies for p in plugins
        }
        
        success, sorted_names = UnifiedDependencyResolver.topological_sort(
            nodes, self._logger
        )
        
        sorted_plugins: List[PluginDependency] = [
            plugin_map[name] for name in sorted_names if name in plugin_map
        ]
        
        return sorted_plugins

    def detect_circular_dependencies(
        self, plugins: List[PluginDependency]
    ) -> Optional[List[str]]:
        """Detect circular dependencies in plugin configuration.
        
        Uses UnifiedDependencyResolver.detect_cycle()
        
        Args:
            plugins: List of PluginDependency objects to check.
            
        Returns:
            A list representing the cycle path if found, None otherwise.
        """
        if not plugins:
            return None
        
        nodes: Dict[str, List[str]] = {
            p.plugin_name: p.dependencies for p in plugins
        }
        
        return UnifiedDependencyResolver.detect_cycle(nodes, self._logger)

    def validate_dependencies(
        self, plugins: List[PluginDependency]
    ) -> Dict[str, List[str]]:
        """Validate that all declared dependencies exist.
        
        Uses UnifiedDependencyResolver.validate_dependencies()
        
        Args:
            plugins: List of PluginDependency objects to validate.
            
        Returns:
            Dictionary mapping plugin names to their missing dependencies.
        """
        if not plugins:
            return {}

        nodes: Dict[str, List[str]] = {
            p.plugin_name: p.dependencies for p in plugins
        }
        
        return UnifiedDependencyResolver.validate_dependencies(nodes, self._logger)


__all__ = [
    "DependencyNode",
    "PluginDependency",
    "UnifiedDependencyResolver",
    "DependencyResolver",
]
