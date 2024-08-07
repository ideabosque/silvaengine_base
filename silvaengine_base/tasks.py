#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import os
import traceback
import urllib.parse

import boto3

from silvaengine_utility import Utility

from .lambdabase import LambdaBase


class Tasks(LambdaBase):
    sqs = boto3.client("sqs", region_name=os.getenv("REGIONNAME", "us-east-1"))
    sns = boto3.client("sns", region_name=os.getenv("REGIONNAME", "us-east-1"))

    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    @staticmethod
    def extract_table_name(arn):
        # Split the ARN by '/'
        parts = arn.split("/")

        # The table name is the part immediately after "table"
        for i, part in enumerate(parts):
            if part.find(":table") != -1:
                return parts[i + 1]

        return None

    @classmethod
    def dispatch(cls, endpoint_id, funct, params=None):
        print(
            "-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_ START -_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_"
        )
        print(endpoint_id, funct)
        (setting, function) = cls.get_function(endpoint_id, funct)
        payload = {
            "MODULENAME": function.config.module_name,
            "CLASSNAME": function.config.class_name,
            "funct": function.function,
            "setting": Utility.json_dumps(setting),
            "params": Utility.json_dumps(params),
        }

        print(function.aws_lambda_arn, function.config.funct_type, payload)
        print("-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_ END -_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_")

        result = cls.invoke(
            function.aws_lambda_arn,
            payload,
            invocation_type=function.config.funct_type,
        )

        print(">>>>>>>>>>> TASK EXECUTE RESULT::::", result)
        return result

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

                        self.logger.info(
                            f"endpoint_id: {endpoint_id}, funct: {funct}, params: {Utility.json_dumps(params)}"
                        )
                        Tasks.dispatch(
                            endpoint_id,
                            funct,
                            params=params,
                        )
                elif event.get("Records")[0]["eventSource"] == "aws:s3":
                    bucket = event["Records"][0]["s3"]["bucket"]["name"]
                    key = urllib.parse.unquote(
                        event["Records"][0]["s3"]["object"]["key"]
                    )

                    pieces = key.split("/")
                    params = dict(
                        {
                            "bucket": bucket,
                            "key": key,
                            "id": pieces[-1]
                            .replace(".csv", "")
                            .replace(".xlsx", "")
                            .replace(".pdf", ""),
                        },
                        **{
                            piece.split(":")[0]: piece.split(":")[1]
                            for piece in pieces
                            if piece.find(":") != -1
                        },
                    )

                    endpoint_id = pieces[0]
                    funct = pieces[1]

                    self.logger.info(
                        f"endpoint_id: {endpoint_id}, funct: {funct}, params: {Utility.json_dumps(params)}"
                    )
                    Tasks.dispatch(
                        endpoint_id,
                        funct,
                        params=params,
                    )
                elif event.get("Records")[0]["eventSource"] == "aws:dynamodb":
                    endpoint_id = os.getenv("DYNAMODBSTREAMENDPOINTID")
                    funct = "stream_handle"

                    ## Retrieve the table name to find the funct name and endpoint_id.
                    table_name = Tasks.extract_table_name(
                        event.get("Records")[0]["eventSourceARN"]
                    )
                    dynamodb_stream_config = LambdaBase.get_setting(
                        "dynamodb_stream_config"
                    )
                    if dynamodb_stream_config.get(table_name):
                        endpoint_id = dynamodb_stream_config[table_name]["endpoint_id"]
                        funct = dynamodb_stream_config[table_name]["funct"]

                    params = {"records": event.get("Records")}

                    Tasks.dispatch(
                        endpoint_id,
                        funct,
                        params=params,
                    )
                else:
                    raise Exception(
                        f"The event source ({event.get('Records')[0]['eventSource']}) is not supported!!!"
                    )
            elif event.get("bot") is not None:
                endpoint_id = event["bot"]["id"]
                funct = f"{event['bot']['name'].lower()}_lex_dispatch"
                params = event
                self.logger.info(
                    f"endpoint_id: {endpoint_id}, funct: {funct}, params: {Utility.json_dumps(params)}"
                )
                return Tasks.dispatch(
                    endpoint_id,
                    funct,
                    params=params,
                )
            else:
                self.logger.info(
                    f"endpoint_id: {event.get('endpoint_id')}, funct: {event.get('funct')}, params: {Utility.json_dumps(event.get('params'))}"
                )
                return Tasks.dispatch(
                    event.get("endpoint_id"),
                    event.get("funct"),
                    params=event.get("params"),
                )

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
