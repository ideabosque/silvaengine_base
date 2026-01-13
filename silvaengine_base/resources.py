#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

from silvaengine_constants import HttpStatus
from silvaengine_utility import Debugger, HttpResponse

from .handlers import (
    CloudwatchLogHandler,
    CognitoHandler,
    DynamodbHandler,
    EventBridgeHandler,
    HttpHandler,
    S3Handler,
    SNSHandler,
    SQSHandler,
    UnknownHandler,
    WebSocketHandler,
)


class Resources:
    _event_handlers = [
        HttpHandler,
        WebSocketHandler,
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
            Debugger.info(
                variable=event,
                stage="Lambda Handle",
                logger=self.logger,
                delimiter="#",
            )

            handle_parameters = {
                "event": event,
                "context": context,
                "logger": self.logger,
            }

            return next(
                (
                    handler
                    for handler in self._event_handlers
                    if handler.instantiate_handler(**handle_parameters)
                ),
                UnknownHandler(**handle_parameters),
            ).handle()
        except Exception as e:
            return HttpResponse.format_response(
                status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
                data={"error": str(e)},
            )
