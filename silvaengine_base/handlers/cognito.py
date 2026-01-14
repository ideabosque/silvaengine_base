#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Callable, Dict

from ..handler import Handler


class CognitoHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return all(
            key in event
            for key in ["triggerSource", "userPoolId", "request", "response"]
        )

    def handle(self) -> Any:
        """Handle Cognito triggers."""
        try:
            return self._get_proxied_callable(
                module_name=self.setting.get(
                    "cognito_hook_module_name",
                    "event_triggers",
                ),
                function_name=self.setting.get(
                    "cognito_hook_function_name",
                    "pre_token_generate",
                ),
                class_name=self.setting.get(
                    "cognito_hook_class_name",
                    "Cognito",
                ),
            )(self.event, self.context)

        except Exception as e:
            raise e
