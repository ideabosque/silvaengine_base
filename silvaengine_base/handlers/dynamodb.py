#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import os
from typing import Any, Dict, List, Optional

from silvaengine_dynamodb_base.models import ConfigModel, FunctionModel

from ..handler import Handler


class DynamodbHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return (
            "Records" in event
            and len(event["Records"]) > 0
            and event["Records"][0].get("eventSource") == "aws:dynamodb"
        )

    def _extract_table_name(self, arn: str) -> Optional[str]:
        """Extract the DynamoDB table name from its ARN."""
        parts = arn.split("/")

        for i, part in enumerate(parts):
            if ":table" in part:
                return str(parts[i + 1]).strip()
        return None

    def _invoke(
        self,
        endpoint_id: str,
        function_name: str,
        parameters: Dict[str, Any],
    ) -> Any:
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
        ):
            raise ValueError("Invalid function")

        self._merge_setting_to_default(setting=setting)

        return self._get_proxied_callable(
            module_name=function.config.module_name,
            function_name=function.function,
            class_name=function.config.class_name,
        )(**parameters)

    def handle(self) -> Any:
        records = self.event.get("Records") or []
        
        if len(records) < 1:
            self.logger.warning("No records found in DynamoDB stream event")
            return {}
        
        self.logger.info(f"Processing {len(records)} DynamoDB stream records")
        
        endpoint_id = self.setting.get(
            "dynamodb_stream_endpoint_id",
            os.getenv("DYNAMODB_STREAM_ENDPOINTID", self._get_endpoint_id()),
        )
        
        table_name = self._extract_table_name(records[0].get("eventSourceARN"))
        
        if not table_name:
            self.logger.warning(f"Could not extract table name from ARN: {records[0].get('eventSourceARN')}")
            return {}
        
        function_name = self.setting.get("dynamodb_stream_handler", "stream_handle")
        parameters = {
            "records": records,
            "logger": self.logger,
        }
        
        try:
            dynamodb_stream_config = ConfigModel.find(
                setting_id=self.setting.get(
                    "dynamodb_stream_config",
                    "dynamodb_stream_config",
                )
            )
        except Exception:
            dynamodb_stream_config = {}
            self.logger.debug("Failed to load dynamodb_stream_config, using default handler")
        
        results: List[Dict[str, Any]] = []
        
        if not dynamodb_stream_config.get(table_name):
            self.logger.info(f"Processing table {table_name} with default handler")
            result = self._invoke(
                endpoint_id=str(endpoint_id).strip(),
                function_name=str(function_name).strip(),
                parameters=parameters,
            )
            results.append({
                "table_name": table_name,
                "status": "success",
                "result": result,
            })
        else:
            configs = dynamodb_stream_config.get(table_name, [])
            self.logger.info(f"Processing table {table_name} with {len(configs)} custom config(s)")
            
            for config in configs:
                try:
                    config_endpoint_id = config.get("endpoint_id", self._get_endpoint_id())
                    config_function_name = config.get("funct", "stream_handle")
                    config_parameters = {
                        **parameters,
                        "config": config,
                    }
                    
                    result = self._invoke(
                        endpoint_id=str(config_endpoint_id).strip(),
                        function_name=str(config_function_name).strip(),
                        parameters=config_parameters,
                    )
                    results.append({
                        "table_name": table_name,
                        "config_index": configs.index(config),
                        "status": "success",
                        "result": result,
                    })
                except Exception as e:
                    self.logger.error(f"Failed to process config for table {table_name}: {e}")
                    results.append({
                        "table_name": table_name,
                        "config_index": configs.index(config),
                        "status": "failed",
                        "error": str(e),
                    })
        
        self.logger.info(f"DynamoDB stream processing complete: {len(results)} result(s)")
        return {
            "processed": len(results),
            "results": results,
        }
