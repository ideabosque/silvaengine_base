#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Callable, Dict, List, Optional, Union

from silvaengine_constants import AuthorizationAction
from silvaengine_dynamodb_base.models import FunctionModel
from silvaengine_utility import Authorizer, Debugger

from ..handler import Handler


class HttpHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return (
            "requestContext" in event
            and "http" in event["requestContext"]
            and "resourcePath" not in event["requestContext"]
        ) or (
            "requestContext" in event
            and "resourcePath" in event["requestContext"]
            and "httpMethod" in event["requestContext"]
        )

    def handle(self) -> Any:
        """
        Process regular HTTP API requests when the event is not related to WebSocket.
        """
        try:
            api_key, endpoint_id, function_name, parameters = (
                self._extract_core_parameters()
            )
            setting, function = self._get_function_and_setting(
                endpoint_id,
                function_name,
                api_key=api_key,
                method=self._get_request_method(),
            )

            if not isinstance(function, FunctionModel) or not hasattr(
                function, "config"
            ):
                raise ValueError("Invalid function")
            elif hasattr(function, "area"):
                self._validate_function_area(function.area)

            if isinstance(setting, dict):
                self._merge_setting_to_default(setting)

            self._merge_metadata_to_event(
                {
                    "function": function,
                    "endpoint_id": endpoint_id,
                }
            )

            # Add authorization for http event
            is_authorization_required = bool(
                hasattr(function.config, "auth_required")
                and bool(function.config.auth_required)
            )

            if self._is_authorization_event():
                if is_authorization_required:
                    try:
                        return self._invoke_authorization(
                            action=AuthorizationAction.AUTHORIZE
                        )
                    except Exception as e:
                        raise e

                return Authorizer(self.event).authorize(is_allow=True)
            elif self.event.get("body") and is_authorization_required:
                permission = self._invoke_authorization(
                    action=AuthorizationAction.VERIFY_PERMISSION
                )

                if isinstance(permission, dict):
                    self._merge_metadata_to_event(permission)

            if (
                not hasattr(function.config, "module_name")
                or not hasattr(function.config, "class_name")
                or not hasattr(function, "function")
                or not hasattr(function, "arn")
            ):
                raise ValueError("Missing function config")

            return self._get_proxied_callable(
                module_name=function.config.module_name,
                class_name=function.config.class_name,
                function_name=function.function,
            )(aws_lambda_arn=function.arn, **parameters)
        except Exception as e:
            raise e
