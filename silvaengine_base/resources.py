#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
    _initialized = False
    _initializing = False
    _initializer_lock = threading.Lock()
    _executor = ThreadPoolExecutor()
    _reusable_resource_pool: List
    _lambda_context: Any
    _keep_alive_interval = int(os.getenv("KEEP_ALIVE_INTERVAL", 120))
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
    def _initialize(cls) -> None:
        with cls._initializer_lock:

            def _do_initialization():
                try:
                    # TODO: Asynchronous initialization + lazy loading mode
                    cls._warmup()
                except Exception as e:
                    Debugger.info(
                        variable=f"Error: {e}",
                        stage=f"{__name__}._initialize",
                    )

            cls._executor.submit(_do_initialization)

    @classmethod
    def _warmup(cls):
        if cls._keep_alive_interval < 60 or cls._keep_alive_interval > 300:
            cls._keep_alive_interval = 120

        while True:
            time.sleep(cls._keep_alive_interval)
            now = datetime.now(timezone.utc).isoformat()
            print(f">>> Service wake up at {now} ...")

            if cls._lambda_context:
                result = DefaultHandler.invoke_aws_lambda_function(
                    qualifier=cls._lambda_context.function_version,
                    function_name=cls._lambda_context.invoked_function_arn,
                    payload={"timestamp": now},
                )

                print(
                    f">>> Function name: `{cls._lambda_context.invoked_function_arn}`, qualifier: `{cls._lambda_context.function_version}`, response: {result}"
                )

    @classmethod
    def get_handler(cls, *args, **kwargs) -> Callable:
        """
        Generate a handler function for Lambda events.
        """
        cls._initialize()

        def handler(event: Dict[str, Any], context: Any):
            return cls(*args, **kwargs).handle(event, context)

        return handler

    def __init__(self, logger: Any) -> None:
        self.logger = logger

    def handle(self, event: Dict[str, Any], context: Any) -> Any:
        try:
            self.__class__._lambda_context = context
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
