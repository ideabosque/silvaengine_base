#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

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
            if cls._initialized or cls._initializing:
                return

            cls._initializing = True

            def _do_initialization():
                try:
                    # Asynchronous initialization + lazy loading mode
                    while True:
                        time.sleep(123)
                        DefaultHandler.invoke_aws_lambda_function(
                            function_name="gpt_silvaengine_microcore",
                            payload={
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "source": "boto3_invoke",
                            },
                        )

                    cls._initialized = True
                except Exception as e:
                    Debugger.info(
                        variable=f"Error: {e}",
                        stage=f"{__name__}._initialize",
                    )
                finally:
                    cls._initializing = False

            cls._executor.submit(_do_initialization)

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
