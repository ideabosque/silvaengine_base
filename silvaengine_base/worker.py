#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import json
from decimal import Decimal
from .lambdabase import LambdaBase


class Worker(LambdaBase):
    last_request_id = None

    @classmethod
    def set_last_request_id(cls, aws_request_id):
        if cls.last_request_id == aws_request_id:
            return  # abort
        else:
            cls.last_request_id = aws_request_id

    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    def handle(self, event, context):
        # TODO implement
        Worker.set_last_request_id(context.aws_request_id)

        _class = getattr(__import__(event.get("MODULENAME")), event.get("CLASSNAME"))
        funct = getattr(
            _class(self.logger, **json.loads(event.get("setting"))), event.get("funct")
        )
        params = event.get("params")
        body = event.get("body")
        context = event.get("context")

        if params is None and body is None:
            return funct()

        params = dict(
            (k, v)
            for k, v in dict(
                ({} if params is None else json.loads(params, parse_float=Decimal)),
                **({} if body is None else json.loads(body, parse_float=Decimal)),
                **(
                    {}
                    if context is None
                    else {"context": json.loads(context, parse_float=Decimal)}
                )
            ).items()
            if v is not None and v != ""
        )

        return funct(**params)
