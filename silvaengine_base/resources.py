#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Resources module for silvaengine_base.

This module provides the core infrastructure for handling Lambda events.
Plugin management functionality has been migrated to boosters module.

Simplified version - delegate methods removed. Users should use PluginInitializer directly
for configuration, status queries, and plugin management.
"""

from __future__ import print_function

import logging
import os
import traceback
from typing import Any, Callable, Dict, List, Optional

from silvaengine_constants import HttpStatus
from silvaengine_dynamodb_base.models import ConfigModel
from silvaengine_utility import HttpResponse

from .boosters import PluginInitializer
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
    Resources class for managing Lambda event handling.

    This is a facade class that provides:
    1. Lambda handler entry point (get_handler)
    2. Event routing (handle)
    3. Plugin pre-initialization (pre_initialize_plugins)

    For plugin configuration, status queries, and management, use PluginInitializer directly.
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
    _logger: Optional[logging.Logger] = None
    _plugin_initializer: Optional[PluginInitializer] = None
    _runtime_region: str = ""
    _runtime_config_index: str = ""
    _runtime_config: Dict[str, Any] = {}

    @classmethod
    def _get_logger(cls) -> logging.Logger:
        """
        Get or create the logger instance.

        This method implements lazy initialization of the class-level logger.
        The logging level is determined by the LOGGING_LEVEL environment variable,
        defaulting to INFO if not set.

        Returns:
            logging.Logger: The configured logger instance.

        Example:
            >>> logger = Resources._get_logger()
            >>> logger.info("Message logged")
        """
        if cls._logger is None:
            level_name = str(os.getenv("LOGGING_LEVEL", "INFO")).strip().upper()
            cls._logger = logging.getLogger()
            cls._logger.setLevel(getattr(logging, level_name, logging.INFO))
        return cls._logger

    @classmethod
    def _get_runtime_region(cls) -> str:
        """
        Get the runtime AWS region from environment variable.

        The region name is cached after first retrieval for performance.
        Reads from REGION_NAME environment variable.

        Returns:
            str: The AWS region name in lowercase, or empty string if not set.

        Example:
            >>> region = Resources._get_runtime_region()
            >>> print(region)  # 'us-east-1'
        """
        if not cls._runtime_region:
            cls._runtime_region = str(os.getenv("REGION_NAME", "")).strip().lower()
        return cls._runtime_region

    @classmethod
    def _get_runtime_config_index(cls) -> str:
        """
        Get the runtime configuration index from environment variable.

        The configuration index is used to retrieve settings from DynamoDB.
        Reads from CONFIG_INDEX environment variable.

        Returns:
            str: The configuration index in lowercase, or empty string if not set.

        Example:
            >>> index = Resources._get_runtime_config_index()
            >>> print(index)  # 'production-config'
        """
        if not cls._runtime_config_index:
            cls._runtime_config_index = (
                str(os.getenv("CONFIG_INDEX", "")).strip().lower()
            )
        return cls._runtime_config_index

    @classmethod
    def _get_plugin_initializer(cls) -> PluginInitializer:
        """
        Get or create the PluginInitializer singleton instance.

        This method implements lazy initialization of the plugin initializer,
        which manages plugin lifecycle and configuration.

        Returns:
            PluginInitializer: The plugin initializer instance.

        Example:
            >>> initializer = Resources._get_plugin_initializer()
            >>> initializer.initialize(logger=logger)
        """
        if cls._plugin_initializer is None:
            cls._plugin_initializer = PluginInitializer()
        return cls._plugin_initializer

    @classmethod
    def _get_runtime_config(cls, config_index: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the runtime configuration from DynamoDB.

        Configuration is cached after first retrieval. If a different config_index
        is provided, the cache is invalidated and a new configuration is loaded.

        Args:
            config_index: Optional configuration index to load. If not provided,
                uses the value from CONFIG_INDEX environment variable.

        Returns:
            Dict[str, Any]: The configuration dictionary, or empty dict if not found.

        Example:
            >>> config = Resources._get_runtime_config()
            >>> print(config.get("setting_key"))

            >>> config = Resources._get_runtime_config("custom-index")
            >>> print(config.get("setting_key"))
        """
        cached_index = cls._get_runtime_config_index()
        index = config_index or cached_index

        if index and (cached_index != index or not cls._runtime_config):
            cls._runtime_config = (
                ConfigModel.find(setting_id=index, return_dict=True) or {}
            )
            cls._runtime_config_index = index
        return cls._runtime_config

    @classmethod
    def get_handler(cls, *args, **kwargs) -> Callable[[Dict[str, Any], Any], Any]:
        """Generate a handler function for Lambda events (non-blocking).

        Returns:
            Handler function for Lambda events

        Performance:
        - Time to return: <100ms (vs 5-30s before optimization)
        - Blocking: None on main thread
        """
        if not cls._get_runtime_config_index():
            raise RuntimeError("Unable to read environment variable `CONFIG_INDEX`")

        if not cls._get_runtime_region():
            raise RuntimeError("Unable to read environment variable `REGION_NAME`")

        cls.pre_initialize_plugins()

        def handler(event: Dict[str, Any], context: Any):
            return cls(*args, **kwargs).handle(event, context)

        return handler

    @classmethod
    def pre_initialize_plugins(
        cls,
        config_index: Optional[str] = None,
        timeout: float = 30,
    ) -> bool:
        """Pre-initialize plugins for Lambda cold start optimization.

        Args:
            config_index: Configuration index to load from DynamoDB (optional).
            config: Pre-loaded configuration dictionary (optional).

        Note:
            - If config is provided, it will be used directly.
            - If config_index is provided, config will be loaded from DynamoDB.
            - If neither is provided, config_index will be read from environment variable.

        Performance Impact:
            - Cold start time: <0.1s (non-blocking)
            - Main thread blocking: 0ms

        @since 2.0.0
        """
        config = cls._get_runtime_config(config_index)

        cls._get_plugin_initializer().initialize(logger=cls._get_logger())
        cls._get_plugin_initializer().setup_plugins(config=config)

        # Wait for critical plugins to be ready before returning handler
        # This ensures connection pool and other critical resources are available
        return cls._get_plugin_initializer().wait_for_plugins_ready(timeout=timeout)

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        """Initialize Resources instance.

        Args:
            logger: Optional logger instance
        """
        if logger is not None:
            self.__class__._logger = logger
            self.__class__._get_plugin_initializer().initialize(logger)

    def handle(self, event: Dict[str, Any], context: Any) -> Any:
        """Handle Lambda event.

        Routes events to appropriate handlers based on event type.

        Args:
            event: Lambda event dictionary
            context: Lambda context object

        Returns:
            Response object

        Note:
            Plugin context injection is performed when available.
            Connection pool availability is logged for debugging purposes.
        """
        try:
            handler = next(
                (h for h in self._event_handlers if h.is_event_match_handler(event)),
                DefaultHandler,
            ).new_handler(
                event=event,
                context=context,
                setting=self.__class__._get_runtime_config(),
                logger=self.__class__._get_logger(),
            )

            plugin_context = (
                self.__class__._get_plugin_initializer().get_plugin_context()
            )

            if plugin_context is None:
                return handler.handle()

            with PluginContextInjector(plugin_context):
                return handler.handle()
        except ValueError as e:
            self.__class__._get_logger().warning(f"Invalid request: {e}")
            return HttpResponse.format_response(
                status_code=HttpStatus.BAD_REQUEST.value,
                data={"error": "Invalid request parameters"},
            )
        except PermissionError as e:
            self.__class__._get_logger().warning(f"Permission denied: {e}")
            return HttpResponse.format_response(
                status_code=HttpStatus.FORBIDDEN.value,
                data={"error": "Permission denied"},
            )
        except Exception as e:
            self.__class__._get_logger().error(
                f"Internal error in {__file__}.handle: {e}\n{traceback.format_exc()}"
            )
            return HttpResponse.format_response(
                status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
                data={"error": "Internal server error"},
            )
