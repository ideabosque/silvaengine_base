#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

from silvaengine_constants import HttpStatus
from silvaengine_utility import HttpResponse

from ..handler import Handler


class DefaultHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return True

    def handle(self) -> Any:
        event_type = type(self.event).__name__
        event_keys = list(self.event.keys()) if isinstance(self.event, dict) else []
        self.logger.warning(f"Unrecognized event: type={event_type}, keys={event_keys}")
        return HttpResponse.format_response(
            status_code=HttpStatus.BAD_REQUEST.value,
            data={"error": "Unrecognized request format"},
        )
