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
        return HttpResponse.format_response(
            status_code=HttpStatus.BAD_REQUEST.value,
            data={"error": f"Unrecognized request:{self.event}"},
        )
