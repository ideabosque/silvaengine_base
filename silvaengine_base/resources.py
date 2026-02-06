#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Resources module for silvaengine_base.

This module provides the core infrastructure for handling Lambda events
and managing plugin initialization. Pool management functionality has been
completely migrated to silvaengine_connections module.

Responsibilities:
- Lambda event handling and routing
- Handler selection and initialization
- Plugin initialization scheduling
- Context propagation to business modules
"""

from __future__ import print_function

import traceback
from typing import Any, Callable, Dict, List, Optional

from silvaengine_constants import HttpStatus
from silvaengine_utility import Debugger, HttpResponse

from .handlers import (
    CloudwatchLogHandler,
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
from .plugin_manager import PluginManager


class Resources:
    """
    Resources class for managing Lambda event handling and plugin initialization.

    This class is responsible for:
    - Routing Lambda events to appropriate handlers
    - Initializing plugins based on configuration
    - Propagating context to business modules

    Pool management is completely delegated to silvaengine_connections module.
    This class no longer contains any pool-related implementation.
    """

    _event_handlers: List = [
        HttpHandler,
        WebSocketHandler,
        LambdaInvocationHandler,
        CloudwatchLogHandler,
        CognitoHandler,
        DynamodbHandler,
        EventBridgeHandler,
        S3Handler,
        SNSHandler,
        SQSHandler,
    ]

    @classmethod
    def get_handler(cls, *args, **kwargs) -> Callable:
        """
        Generate a handler function for Lambda events.

        Args:
            *args: Positional arguments to pass to Resources constructor.
            **kwargs: Keyword arguments to pass to Resources constructor.

        Returns:
            Callable: Lambda handler function.
        """

        def handler(event: Dict[str, Any], context: Any):
            return cls(*args, **kwargs).handle(event, context)

        return handler

    def __init__(self, logger: Any) -> None:
        """
        Initialize Resources instance.

        Args:
            logger: Logger instance for logging.
        """
        self.logger = logger
        self._plugin_manager: Optional[PluginManager] = None

    def handle(self, event: Dict[str, Any], context: Any) -> Any:
        """
        Handle Lambda event.

        This method routes the event to the appropriate handler and
        initializes plugins based on configuration.

        Args:
            event: Lambda event dictionary.
            context: Lambda context object.

        Returns:
            Response from handler.
        """
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
                logger=self.logger,
            )

            if not handler:
                return HttpResponse.format_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    data={"error": f"Unrecognized request:{event}"},
                )

            # Initialize plugins based on handler configuration
            self._initialize_plugins(handler)

            # Pass Resources instance to handler for context access
            handler._resources_instance = self

            return handler.handle()
        except Exception as e:
            Debugger.info(
                variable=f"Error: {e}, Trace: {traceback.format_exc()}",
                stage=f"{__file__}.handle",
            )
            return HttpResponse.format_response(
                status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
                data={"error": str(e)},
            )

    def _initialize_plugins(self, handler: Any) -> None:
        """
        Initialize plugins based on handler configuration.

        This method extracts plugin configuration from the handler and
        initializes the PluginManager. PluginManager coordinates plugin
        registration but does not manage connection pools directly.

        Args:
            handler: Handler instance with configuration.
        """
        # Lazy initialization of plugin manager
        if self._plugin_manager is None:
            self._plugin_manager = PluginManager(logger=self.logger)

        # Initialize plugins
        self._plugin_manager.initialize(handler_setting=handler.setting)

    @property
    def plugin_manager(self) -> Optional[PluginManager]:
        """
        Get the plugin manager instance.

        Returns:
            PluginManager instance or None if not initialized.
        """
        return self._plugin_manager

    def get_context(self) -> Dict[str, Any]:
        """
        Get context with initialized plugins for business modules.

        This method provides context containing initialized plugin objects
        for passing to business modules through the handler.

        Returns:
            Context dictionary containing initialized plugin objects.
        """
        if self._plugin_manager:
            return self._plugin_manager.get_context()
        return {}
