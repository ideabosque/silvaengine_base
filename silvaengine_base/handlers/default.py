#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Callable, Dict, List, Optional, Union

from ..handler import Handler


class DefaultHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        required_keys = {
            "module_name",
            "class_name",
            "function_name",
            "context",
            "parameters",
        }

        return required_keys.issubset(event.keys())

    def handle(self) -> Any:
        print("~UNKNOWN HANDLER~" * 10)

        context = self.event.get("context")
        module_name = self.event.get("module_name")
        function_name = self.event.get("function_name")
        class_name = self.event.get("class_name")
        parameters = self.event.get("parameters") or {}

        if not isinstance(context, dict) or not module_name or not function_name
            raise TypeError("Invalid request")

        parameters.update(context=context)

        return self._get_proxied_callable(
            module_name=module_name,
            function_name=function_name,
            class_name=class_name,
        )(**parameters)


    def _get_default_setting_index(self) -> str:
        context = self.event.get("context") or {}
        aws_api_stage = str(context.get("aws_api_stage") or "").strip().lower()
        aws_api_area = str(context.get("aws_api_area") or "").strip().lower()
        endpoint_id = str(context.get("endpoint_id") or "").strip().lower()

        if not aws_api_stage or not aws_api_area or not endpoint_id:
            raise ValueError("Invalid required parameter(s)")

        return f"{aws_api_stage}_{aws_api_area}_{endpoint_id}"
