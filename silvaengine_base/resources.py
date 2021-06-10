#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import json, traceback
from .lambdabase import LambdaBase
from silvaengine_auth import Auth
from silvaengine_utility import Utility


class Resources(LambdaBase):
    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    def handle(self, event, context):
        # TODO implement
        try:
            area = event["pathParameters"]["area"]
            method = event["httpMethod"]
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
            body = event["body"]
            api_key = event["requestContext"]["identity"]["apiKey"]

            (setting, function) = LambdaBase.get_function(
                endpoint_id, funct, api_key=api_key, method=method
            )

            assert (
                area == function.area
            ), f"Area ({area}) is not matched the configuration of the function ({funct}).  Please check the parameters."

            # If auth_required is True, validate authorization.
            # If graphql, append the graphql query path to the path.
            if function.config.auth_required:
                # user = event["requestContext"]["identity"].get("user")
                # params = {
                #     "uid": event["requestContext"]["identity"].get("user"),
                #     "path": f"/{area}/{endpoint_id}/{funct}",
                #     "permission": 2,
                # }
                collection = event
                collection["fnConfigurations"] = function

                is_authorized = Auth.is_authorized(collection, self.logger)
                self.logger.info("Authorized: ")
                self.logger.info(is_authorized)

                if not is_authorized:
                    return {
                        "statusCode": 403,
                        "headers": {
                            "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                            "Access-Control-Allow-Origin": "*",
                        },
                        "body": (
                            json.dumps(
                                {
                                    "error": f"Don't have the permission to access at /{area}/{endpoint_id}/{funct}."
                                },
                                indent=4,
                            )
                        ),
                    }

                # assert (
                #     True if function.config.auth_required else True
                # ), f"Don't have the permission to access at /{area}/{endpoint_id}/{funct}."

            payload = {
                "MODULENAME": function.config.module_name,
                "CLASSNAME": function.config.class_name,
                "funct": function.function,
                "setting": json.dumps(setting),
                "params": json.dumps(params),
                "body": body,
                "context": Utility.json_dumps(event["requestContext"]),
            }

            self.logger.info("Request payload: ")
            self.logger.info(payload)

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

        except Exception:
            log = traceback.format_exc()
            self.logger.exception(log)
            return {
                "statusCode": 500,
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": (json.dumps({"error": log}, indent=4)),
            }
