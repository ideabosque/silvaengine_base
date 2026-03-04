#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

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
        records = self.event.get("Records") or []
        self.logger.info(f"SNS event received with {len(records)} record(s)")
        
        for index, record in enumerate(records):
            sns_data = record.get("Sns", {})
            message_id = sns_data.get("MessageId", "unknown")
            subject = sns_data.get("Subject", "")
            self.logger.debug(
                f"SNS record {index}: MessageId={message_id}, Subject={subject}"
            )
        
        self.logger.warning(
            "SNSHandler.handle() is not implemented. "
            "Please extend this handler to process SNS events."
        )
        return {"status": "not_implemented", "records_received": len(records)}
