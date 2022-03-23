#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import traceback, boto3, os
from silvaengine_utility import Utility
from .lambdabase import LambdaBase


class Tasks(LambdaBase):

    sns = boto3.client("sns", region_name=os.environ["REGIONNAME"])

    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    @classmethod
    def dispatch(cls, endpoint_id, funct, params=None):
        (setting, function) = cls.get_function(endpoint_id, funct)

        payload = {
            "MODULENAME": function.config.module_name,
            "CLASSNAME": function.config.class_name,
            "funct": function.function,
            "setting": Utility.json_dumps(setting),
            "params": Utility.json_dumps(params),
        }

        cls.invoke(
            function.aws_lambda_arn,
            payload,
            invocation_type=function.config.funct_type,
        )

    def handle(self, event, context):
        # TODO implement

        try:
            if event.get("Records") and len(event.get("Records")) > 0:
                if event.get("Records")[0]["eventSource"] == "aws:sqs":
                    for record in event.get("Records"):
                        endpoint_id = record["messageAttributes"]["endpoint_id"].get(
                            "stringValue"
                        )
                        funct = record["messageAttributes"]["funct"].get("stringValue")
                        params = Utility.json_loads(record["body"])["params"]

                        self.logger.info(f"endpoint: {endpoint_id}, funct: {funct}")
                        Tasks.dispatch(
                            endpoint_id,
                            funct,
                            params=params,
                        ),
                else:
                    raise Exception(
                        f"The event source ({event.get('Records')[0]['eventSource']}) is not supported!!!"
                    )
            else:
                endpoint_id = event.get("endpoint_id")
                funct = event.get("funct")
                params = event.get("params")

                self.logger.info(f"endpoint: {endpoint_id}, funct: {funct}")
                Tasks.dispatch(
                    endpoint_id,
                    funct,
                    params=params,
                ),

        except Exception:
            self.logger.info(event)
            log = traceback.format_exc()
            self.logger.exception(log)
            if os.environ.get("SNSTOPICARN"):
                Tasks.sns.publish(
                    TopicArn=os.environ["SNSTOPICARN"],
                    Subject=context.invoked_function_arn,
                    MessageStructure="json",
                    Message=Utility.json_dumps({"default": log}),
                )
