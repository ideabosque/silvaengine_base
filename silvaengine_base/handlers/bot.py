#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

from silvaengine_dynamodb_base.models import FunctionModel

from ..handler import Handler


class BotHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return "bot" in event

    def handle(self) -> Any:
        try:
            endpoint_id = self.event.get("bot", {}).get("id")
            bot_name = str(self.event.get("bot", {}).get("name")).strip().lower()
            function_name = f"{bot_name}_lex_dispatch"

            if not endpoint_id:
                endpoint_id = self._get_endpoint_id()

            parameters = {
                **self._extract_additional_parameters(self.event),
                "logger": self.logger,
            }
            setting, function = self._get_function_and_setting(
                endpoint_id=endpoint_id,
                function_name=function_name,
            )

            if (
                not isinstance(function, FunctionModel)
                or not hasattr(function, "config")
                or not hasattr(function.config, "module_name")
                or not hasattr(function.config, "class_name")
                or not hasattr(function, "function")
                or not hasattr(function, "arn")
            ):
                raise ValueError("Invalid function")

            self._merge_setting_to_default(setting=setting)

            return self._get_proxied_callable(
                module_name=function.config.module_name,
                function_name=function.function,
                class_name=function.config.class_name,
            )(aws_lambda_arn=function.arn, **parameters)
        except Exception as e:
            raise e
