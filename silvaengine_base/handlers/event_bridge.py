#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

from ..handler import Handler


class EventBridgeHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return all(key in event for key in ["source", "detail-type", "detail"])

    def handle(self) -> Any:
        event_source = self.event.get("source", "unknown")
        detail_type = self.event.get("detail-type", "unknown")
        
        self.logger.info(
            f"EventBridge event received: source={event_source}, detail-type={detail_type}"
        )
        
        detail = self.event.get("detail", {})
        if isinstance(detail, dict):
            self.logger.debug(f"EventBridge detail keys: {list(detail.keys())}")
        
        self.logger.warning(
            "EventBridgeHandler.handle() is not implemented. "
            "Please extend this handler to process EventBridge events."
        )
        return {
            "status": "not_implemented",
            "source": event_source,
            "detail_type": detail_type,
        }
