#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import time
import traceback
from tkinter import EventType
from typing import Any, Callable, Dict, List, Optional, Set, Union

from silvaengine_dynamodb_base.models import GraphqlSchemaModel
from silvaengine_utility import Debugger

from ..handler import Handler


class LambdaInvocationHandler(Handler):
    _required_parameter_keys: Set[str] = {
        "__type",
        "context",
        "module_name",
        "class_name",
        "function_name",
    }

    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return (
            cls._required_parameter_keys.issubset(event.keys())
            and event.get("__type") == EventType.LAMBDA_INVOCATION
        )

    def _invoke_time_counter(self):
        started_at = self.event.get("__execution_start_time")

        if isinstance(started_at, (int, float, complex)):
            duration = time.time() - started_at
            self.logger.info(f"It takes {duration:.6f}s to invoke the lambda function.")

    def handle(self) -> Any:
        try:
            self._invoke_time_counter()

            context = self.event.get("context")
            module_name = self.event.get("module_name")
            function_name = self.event.get("function_name")
            class_name = self.event.get("class_name")
            parameters = self.event.get("parameters") or {}

            if not isinstance(context, dict) or not module_name or not function_name:
                raise TypeError("Invalid request")

            if "context" not in parameters:
                parameters.update(context=context)

            if "metadata" not in parameters:
                parameters.update(
                    metadata={
                        "aws_lambda_invoker": self.__class__.invoke_aws_lambda_function,
                        "aws_lambda_context": self.context,
                        "graphql_schema_picker": GraphqlSchemaModel.get_schema_picker(
                            endpoint_id=self._get_endpoint_id(context=context)
                        ),
                    }
                )

            return self._get_proxied_callable(
                module_name=module_name,
                function_name=function_name,
                class_name=class_name,
            )(**parameters)
        except Exception as e:
            Debugger.info(
                variable=f"Error: {e}, Trace: {traceback.format_exc()}",
                stage=f"{__file__}.handle",
            )
            raise

    def _get_api_area(self, context: Optional[Dict[str, Any]] = None) -> str:
        api_area = context.get("aws_api_area") if isinstance(context, dict) else ""

        if isinstance(api_area, str):
            api_area = api_area.strip()

            if api_area:
                return api_area.lower()

        return super()._get_api_area()

    def _get_api_stage(self, context: Optional[Dict[str, Any]] = None) -> str:
        api_stage = context.get("aws_api_stage") if isinstance(context, dict) else ""

        if isinstance(api_stage, str):
            api_stage = api_stage.strip()

            if api_stage:
                return api_stage.lower()

        return super()._get_api_stage()

    def _get_endpoint_id(self, context: Optional[Dict[str, Any]] = None) -> str:
        endpoint_id = context.get("endpoint_id") if isinstance(context, dict) else ""

        if isinstance(endpoint_id, str):
            endpoint_id = endpoint_id.strip()

            if endpoint_id:
                return endpoint_id.lower()

        return super()._get_endpoint_id()

    def _get_default_setting_index(self) -> str:
        context = self.event.get("context") or {}
        aws_api_stage = self._get_api_stage(context=context)
        aws_api_area = self._get_api_area(context=context)
        endpoint_id = self._get_endpoint_id(context=context)

        if not aws_api_stage or not aws_api_area or not endpoint_id:
            raise ValueError("Invalid required parameter(s)")

        return f"{aws_api_stage}_{aws_api_area}_{endpoint_id}"
