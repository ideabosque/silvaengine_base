#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Callable, Dict, List, Optional, Union

from ..handler import Handler


class CloudwatchLogHandler(Handler):
    @classmethod
    def _is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return "awslogs" in event

    def handle(self) -> Any:
        return {}
