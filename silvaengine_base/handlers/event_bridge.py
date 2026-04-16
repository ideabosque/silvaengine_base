#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

from ..handler import Handler


class EventBridgeHandler(Handler):

    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        if all(key in event for key in ["funct", "endpoint_id", "params"]):
            return True
        return all(key in event for key in ["source", "detail-type", "detail"])

    def _extract_payload(self, event) -> Any:
        # EventBridge And Lambda Test
        return event.get("detail", event)
    
    def handle(self) -> Any:

        event_source = self.event.get("source", "unknown")
        detail_type = self.event.get("detail-type", "unknown")
        
        self.logger.info(
            f"EventBridge event received: source={event_source}, detail-type={detail_type}"
        )
        
        payload = self._extract_payload(self.event)
        
        if isinstance(payload, dict):
            self.logger.debug(f"EventBridge detail keys: {list(payload.keys())}")
        

        endpoint_id = payload.get("endpoint_id")
        funct = payload.get("funct")
        params = payload.get("params")
        setting, function = self._get_function_and_setting(
            endpoint_id,
            funct,
        )

        if hasattr(function, "area"):
            self._validate_function_area(function.area)

        if isinstance(setting, dict):
            self._merge_setting_to_default(setting)

        if (
            not hasattr(function.config, "module_name")
            or not hasattr(function.config, "class_name")
            or not hasattr(function, "function")
            or not hasattr(function, "aws_lambda_arn")
        ):
            raise ValueError("Missing function config")
        
        return self._get_proxied_callable(
            module_name=function.config.module_name,
            class_name=function.config.class_name,
            function_name=function.function,
        )(aws_lambda_arn=function.aws_lambda_arn, **params)
