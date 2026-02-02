#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import traceback
from typing import Any, Callable, Dict, List

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


class Resources:
    _reusable_resource_pool: List
    _keep_alive_interval = int(os.getenv("KEEP_ALIVE_INTERVAL", 59))
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
        """
        def handler(event: Dict[str, Any], context: Any):
            return cls(*args, **kwargs).handle(event, context)

        return handler

    def __init__(self, logger: Any) -> None:
        self.logger = logger

    def handle(self, event: Dict[str, Any], context: Any) -> Any:
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
