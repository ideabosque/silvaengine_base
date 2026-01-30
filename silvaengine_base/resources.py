#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import traceback
from typing import Any, Dict

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
    _event_handlers = [
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

    def __init__(self, logger: Any) -> None:
        self.logger = logger

    @classmethod
    def get_handler(cls, *args, **kwargs):
        """
        Generate a handler function for Lambda events.
        """

        def handler(event: Dict[str, Any], context: Any):
            return cls(*args, **kwargs).handle(event, context)

        return handler

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
            return HttpResponse.format_response(
                status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
                data={"error": str(e)},
            )
