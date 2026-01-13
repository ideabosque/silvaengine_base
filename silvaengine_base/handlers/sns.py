#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Callable, Dict, List, Optional, Union

from ..handler import Handler


class SNSHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return (
            "Records" in event
            and len(event["Records"]) > 0
            and "Sns" in event["Records"][0]
        )

    def handle(self) -> Any:
        return {}
