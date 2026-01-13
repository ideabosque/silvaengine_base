#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Callable, Dict, List, Optional, Union

from ..handler import Handler


class EventBridgeHandler(Handler):
    @classmethod
    def _is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return all(key in event for key in ["source", "detail-type", "detail"])

    def handle(self) -> Any:
        return {}
