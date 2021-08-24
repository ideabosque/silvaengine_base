#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import json, traceback, asyncio
from .lambdabase import LambdaBase
from silvaengine_auth import Auth
from event_triggers import Cognito
from silvaengine_utility import Utility, Authorizer
from importlib.util import find_spec
from importlib import import_module


class Resources(LambdaBase):
    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    def handle(self, event, context):
        try:
            # Trigger aws hooks
            if event and event.get("triggerSource") and event.get("userPoolId"):
                settings = LambdaBase.get_setting("event_triggers")

                return Cognito(self.logger, **settings).pre_token_generate(
                    event, context
                )

            area = event["pathParameters"]["area"]
            api_key = event["requestContext"]["identity"]["apiKey"]
            endpoint_id = event["pathParameters"]["endpoint_id"]
            funct = event["pathParameters"]["proxy"]
            params = dict(
                {"endpoint_id": endpoint_id, "area": area},
                **(
                    event["queryStringParameters"]
                    if event["queryStringParameters"] is not None
                    else {}
                ),
            )
            method = (
                event.get("requestContext").get("httpMethod")
                if event.get("requestContext").get("httpMethod")
                else event["httpMethod"]
            )

            (setting, function) = LambdaBase.get_function(
                endpoint_id, funct, api_key=api_key, method=method
            )

            assert (
                area == function.area
            ), f"Area ({area}) is not matched the configuration of the function ({funct}).  Please check the parameters."

            event.update(
                {"fnConfigurations": Utility.json_loads(Utility.json_dumps(function))}
            )

            print("ORIGIN REQUEST:", event)

            # If auth_required is True, validate authorization.
            # If graphql, append the graphql query path to the path.
            if str(event.get("type")).lower() == "request":
                return Auth(self.logger).authorize(event, context)
            elif event.get("body"):
                event.update(Auth(self.logger).verify_permission(event, context))

            # Execute triggers.
            self.trigger_hooks(
                logger=self.logger, settings=json.dumps(setting), event=event
            )

            # Transfer the request to the lower-level logic
            payload = {
                "MODULENAME": function.config.module_name,
                "CLASSNAME": function.config.class_name,
                "funct": function.function,
                "setting": json.dumps(setting),
                "params": json.dumps(params),
                "body": event["body"],
                "context": Utility.json_dumps(event["requestContext"]),
            }

            if function.config.funct_type == "Event":
                LambdaBase.invoke(
                    function.aws_lambda_arn,
                    payload,
                    invocation_type=function.config.funct_type,
                )

                return {
                    "statusCode": 200,
                    "headers": {
                        "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                        "Access-Control-Allow-Origin": "*",
                    },
                    "body": "",
                }

            res = Utility.json_loads(
                LambdaBase.invoke(
                    function.aws_lambda_arn,
                    payload,
                    invocation_type=function.config.funct_type,
                )
            )
            status_code = res.pop("status_code", 200)

            return {
                "statusCode": status_code,
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": Utility.json_dumps(res),
            }

        except Exception as e:
            log = traceback.format_exc()
            self.logger.exception(log)
            message = e.args[0]
            status_code = 500

            if len(e.args) > 1 and type(e.args[1]) is int:
                status_code = e.args[1]

            if message is None:
                message = log

            if str(event.get("type")).lower() == "request":
                principal = event.get("path")
                aws_account_id = event.get("requestContext").get("accountId")
                api_id = event.get("requestContext").get("apiId")
                region = event.get("methodArn").split(":")[3]
                stage = event.get("requestContext").get("stage")
                ctx = {"error_message": message}

                return Authorizer(
                    principal=principal,
                    aws_account_id=aws_account_id,
                    api_id=api_id,
                    region=region,
                    stage=stage,
                ).authorize(is_allow=False, context=ctx)

            return {
                "statusCode": int(status_code),
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": message}),
            }

    # Exec hooks
    def trigger_hooks(self, logger=None, settings=None, event=None, context=None):
        try:
            # print("Execute hooks")
            # # 1. Record the activity log.
            # arguments = {
            #     "module_name": "event_recorder",
            #     "function_name": "add_event_log",
            #     "class_name": "Recorder",
            #     "constructor_parameters": {"logger": logger, "setting": settings},
            # }
            # print(arguments)
            # log_recorder = Utility.import_dynamically(**arguments)

            # # 2. Call recorder by async
            # if log_recorder:
            #     print("Record event log")
            #     Utility.callByAsync(lambda: log_recorder(event))
            return None
        except Exception:
            logger.exception(traceback.format_exc())
