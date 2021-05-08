#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import json, traceback, os
from .lambdabase import LambdaBase
from .models import BaseModel
from silvaengine_auth import Auth
from silvaengine_utility import Utility


class Resources(LambdaBase):
    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger
        BaseModel.Meta.region = os.environ["REGIONNAME"]

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

                print(type(event))
                collection = event
                collection["fnConfigurations"] = function

                isAuthorized = Auth.isAuthorized(collection, self.logger)
                self.logger.info("Authorized: ")
                self.logger.info(isAuthorized)

                if not isAuthorized:
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
            }

            self.logger.info("Request payload: ")
            self.logger.info(payload)

            res = LambdaBase.invoke(
                function.aws_lambda_arn,
                payload,
                invocation_type=function.config.funct_type,
            )
            return {
                "statusCode": 500
                if funct.find("graphql") != -1
                and "errors" in Utility.json_loads(res).keys()
                else 200,
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": res,
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
