#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Resources module for silvaengine_base.

This module provides the core infrastructure for handling Lambda events
and managing plugin initialization. Pool management functionality has been
completely migrated to silvaengine_connections module.
"""

from __future__ import print_function

import os
import traceback
from typing import Any, Callable, Dict, List, Optional

from silvaengine_constants import HttpStatus
from silvaengine_utility import HttpResponse, Utility

from .boosters.plugin import PluginContext, PluginManager
from .boosters.plugin.injector import PluginContextInjector
from .handlers import (
    CloudWatchHandler,
    CognitoHandler,
    DefaultHandler,
    DynamodbHandler,
    EventBridgeHandler,
    HttpHandler,
    LambdaInvocationHandler,
    S3Handler,
    SNSHandler,
    SQSHandler,
    WebSocketHandler,
)


class Resources:
    """
    Resources class for managing Lambda event handling and plugin initialization.

    Pool management is completely delegated to silvaengine_connections module.
    """

    _event_handlers: List = [
        HttpHandler,
        WebSocketHandler,
        LambdaInvocationHandler,
        CloudWatchHandler,
        CognitoHandler,
        DynamodbHandler,
        EventBridgeHandler,
        S3Handler,
        SNSHandler,
        SQSHandler,
    ]

    @classmethod
    def get_handler(cls, *args, **kwargs) -> Callable:
        """Generate a handler function for Lambda events."""

        def handler(event: Dict[str, Any], context: Any):
            return cls(*args, **kwargs).handle(event, context)

        return handler

    def __init__(
        self,
        logger: Any,
        plugin_init_timeout: Optional[float] = None,
        global_init_timeout: Optional[float] = None,
        circuit_breaker_enabled: Optional[bool] = None,
        lazy_loading_enabled: Optional[bool] = None,
        parallel_enabled: Optional[bool] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        """Initialize Resources instance."""
        self._logger = logger
        self._plugin_manager: Optional[PluginManager] = None

        self._plugin_init_timeout = plugin_init_timeout
        self._global_init_timeout = global_init_timeout
        self._circuit_breaker_enabled = circuit_breaker_enabled
        self._lazy_loading_enabled = lazy_loading_enabled
        self._parallel_enabled = parallel_enabled
        self._max_workers = max_workers

    def handle(self, event: Dict[str, Any], context: Any) -> Any:
        """Handle Lambda event."""
        try:
            handler = next(
                (
                    handler
                    for handler in self._event_handlers
                    if handler.is_event_match_handler(event)
                ),
                DefaultHandler,
            ).new_handler(
                event=event,
                context=context,
                logger=self._logger,
            )

            plugin_context = self._initialize_plugins(handler)

            with PluginContextInjector(plugin_context):
                return handler.handle()
        except ValueError as e:
            self._logger.warning(f"Invalid request: {e}")
            return HttpResponse.format_response(
                status_code=HttpStatus.BAD_REQUEST.value,
                data={"error": "Invalid request parameters"},
            )
        except PermissionError as e:
            self._logger.warning(f"Permission denied: {e}")
            return HttpResponse.format_response(
                status_code=HttpStatus.FORBIDDEN.value,
                data={"error": "Permission denied"},
            )
        except Exception as e:
            self._logger.error(
                f"Internal error in {__file__}.handle: {e}\n{traceback.format_exc()}"
            )
            return HttpResponse.format_response(
                status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
                data={"error": "Internal server error"},
            )

    def _initialize_plugins(self, handler: Any) -> Optional[PluginContext]:
        """Initialize plugins based on handler configuration."""
        if self._plugin_manager is None:
            self._plugin_manager = PluginManager(logger=self._logger)
            self._configure_plugin_manager()

        if self._plugin_manager.initialize(setting=handler.setting):
            plugin_context = self._plugin_manager.get_context()

            handler.set_plugin_context(plugin_context)
            return plugin_context

    def _configure_plugin_manager(self) -> None:
        """Configure PluginManager with optimization settings."""
        if self._plugin_manager is None:
            return

        plugin_timeout = self._get_config_value(
            self._plugin_init_timeout,
            "PLUGIN_INIT_TIMEOUT",
            30.0,
        )
        self._plugin_manager.set_plugin_init_timeout(float(plugin_timeout))

        global_timeout = self._get_config_value(
            self._global_init_timeout,
            "PLUGIN_GLOBAL_INIT_TIMEOUT",
            120.0,
        )
        self._plugin_manager.set_global_init_timeout(float(global_timeout))

        circuit_breaker = self._get_config_value(
            self._circuit_breaker_enabled,
            "PLUGIN_CIRCUIT_BREAKER_ENABLED",
            True,
        )
        self._plugin_manager.set_circuit_breaker_enabled(
            Utility.parse_bool(circuit_breaker, True)
        )

        lazy_loading = self._get_config_value(
            self._lazy_loading_enabled,
            "PLUGIN_LAZY_LOADING_ENABLED",
            True,
        )
        self._plugin_manager.set_lazy_loading_enabled(
            Utility.parse_bool(lazy_loading, False)
        )

        parallel_enabled = self._get_config_value(
            self._parallel_enabled,
            "PLUGIN_PARALLEL_INIT_ENABLED",
            True,
        )
        self._plugin_manager.set_parallel_enabled(
            Utility.parse_bool(parallel_enabled, True)
        )

        max_workers = self._get_config_value(
            self._max_workers,
            "PLUGIN_MAX_WORKERS",
            None,
        )
        if max_workers is not None:
            self._plugin_manager.set_max_workers(int(max_workers))

        self._logger.info(
            "PluginManager configured with: "
            f"plugin_timeout={plugin_timeout}s, "
            f"global_timeout={global_timeout}s, "
            f"circuit_breaker={circuit_breaker}, "
            f"lazy_loading={lazy_loading}, "
            f"parallel={parallel_enabled}, "
            f"max_workers={max_workers or 'auto'}"
        )

    def _get_config_value(
        self,
        constructor_value: Optional[Any],
        env_var: str,
        default: Any,
    ) -> Any:
        """Get configuration value from constructor, environment, or default."""
        if constructor_value is not None:
            return constructor_value

        env_value = os.environ.get(env_var)

        if env_value is not None:
            return env_value

        return default

    def get_plugin_manager(self) -> Optional[PluginManager]:
        """Get the plugin manager instance."""
        return self._plugin_manager

    def reset_plugin_manager(self) -> None:
        """Reset the plugin manager instance."""
        if self._plugin_manager:
            PluginManager.reset_instance()
            self._plugin_manager = None
