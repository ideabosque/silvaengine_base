#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Plugin dependency management module."""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PluginDependency:
    """Plugin dependency data class."""
    plugin_name: str
    dependencies: List[str] = field(default_factory=list)
    version: str = ""
    optional: bool = False


class DependencyResolver:
    """Dependency resolver for plugin system."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the dependency resolver."""
        self._logger = logger or logging.getLogger(__name__)

    def resolve_dependencies(self, plugins: List[PluginDependency]) -> List[PluginDependency]:
        """Resolve plugin dependencies using topological sort."""
        if not plugins:
            self._logger.debug("No plugins provided for dependency resolution")
            return []

        plugin_map: Dict[str, PluginDependency] = {
            p.plugin_name: p for p in plugins
        }

        in_degree: Dict[str, int] = defaultdict(int)
        graph: Dict[str, List[str]] = defaultdict(list)

        for plugin in plugins:
            if plugin.plugin_name not in in_degree:
                in_degree[plugin.plugin_name] = 0

            for dep in plugin.dependencies:
                if dep in plugin_map:
                    graph[dep].append(plugin.plugin_name)
                    in_degree[plugin.plugin_name] += 1
                else:
                    self._logger.warning(
                        f"Plugin '{plugin.plugin_name}' depends on '{dep}' "
                        f"which is not defined"
                    )

        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        sorted_plugins: List[PluginDependency] = []

        while queue:
            current = queue.popleft()
            if current in plugin_map:
                sorted_plugins.append(plugin_map[current])

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_plugins) != len(plugins):
            self._logger.warning(
                "Not all plugins could be sorted - possible circular dependency detected"
            )

        self._logger.info(
            f"Resolved {len(sorted_plugins)} plugins in dependency order"
        )

        return sorted_plugins

    def detect_circular_dependencies(
        self, plugins: List[PluginDependency]
    ) -> Optional[List[str]]:
        """Detect circular dependencies in plugin configuration."""
        if not plugins:
            return None

        plugin_map: Dict[str, PluginDependency] = {
            p.plugin_name: p for p in plugins
        }

        visited: Dict[str, bool] = defaultdict(bool)
        rec_stack: Dict[str, bool] = defaultdict(bool)
        path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            visited[node] = True
            rec_stack[node] = True
            path.append(node)

            if node in plugin_map:
                for dependency in plugin_map[node].dependencies:
                    if dependency not in visited:
                        result = dfs(dependency)
                        if result:
                            return result
                    elif rec_stack[dependency]:
                        cycle_path = path + [dependency]
                        self._logger.error(
                            f"Circular dependency detected: {' -> '.join(cycle_path)}"
                        )
                        return cycle_path

            path.pop()
            rec_stack[node] = False
            return None

        for plugin in plugins:
            if plugin.plugin_name not in visited:
                cycle = dfs(plugin.plugin_name)
                if cycle:
                    return cycle

        self._logger.info("No circular dependencies detected")
        return None

    def validate_dependencies(
        self, plugins: List[PluginDependency]
    ) -> Dict[str, List[str]]:
        """Validate that all declared dependencies exist."""
        if not plugins:
            return {}

        plugin_names = {p.plugin_name for p in plugins}
        missing_deps: Dict[str, List[str]] = {}

        for plugin in plugins:
            missing = [
                dep for dep in plugin.dependencies
                if dep not in plugin_names
            ]
            if missing:
                missing_deps[plugin.plugin_name] = missing
                self._logger.warning(
                    f"Plugin '{plugin.plugin_name}' has missing dependencies: {missing}"
                )

        return missing_deps
