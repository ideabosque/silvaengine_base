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
                ),
            ).items()
            if v is not None and v != ""
        )

        return funct(**params)


#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import json
from decimal import Decimal
from typing import Any, Dict, Optional

from .lambdabase import LambdaBase


class Worker(LambdaBase):
    last_request_id: Optional[str] = None

    @classmethod
    def set_last_request_id(cls, aws_request_id: str) -> None:
        """Set the last AWS request ID to avoid redundant requests."""
        if cls.last_request_id == aws_request_id:
            return  # Abort if request ID is the same
        cls.last_request_id = aws_request_id

    def __init__(self, logger: Any) -> None:
        """Initialize the Worker with a logger."""
        self.logger = logger

    def handle(self, event: Dict[str, Any], context: Any) -> Any:
        """
        Handle incoming Lambda events and dynamically execute functions.
        :param event: The event data passed to the Lambda function.
        :param context: The Lambda context object.
        """
        try:
            # Set request ID to prevent processing the same request twice
            Worker.set_last_request_id(context.aws_request_id)

            # Dynamically import the module and class
            module_name = event.get("MODULENAME")
            class_name = event.get("CLASSNAME")
            funct_name = event.get("funct")
            settings = (
                json.loads(event.get("setting"))
                if event.get("setting") is not None
                else {}
            )

            _class = getattr(__import__(module_name), class_name)
            instance = _class(self.logger, **settings)
            funct = getattr(instance, funct_name)

            if event.get("params") is None and event.get("body") is None:
                return funct()

            # Prepare parameters
            params = self._prepare_params(event)

            # Log the execution details
            self.logger.info(
                f"Executing {funct_name} from {module_name}.{class_name} with params: {params}"
            )

            # Call the function with prepared parameters
            return funct(**params)

        except Exception as e:
            self.logger.error(f"Error in handling event: {str(e)}")
            raise

    def _prepare_params(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare the parameters for function execution by merging params, body, and context.
        :param event: The Lambda event data.
        :return: Merged parameters dictionary.
        """
        try:
            params = event.get("params")
            body = event.get("body")
            context = event.get("context")

            params = dict(
                (k, v)
                for k, v in dict(
                    ({} if params is None else json.loads(params, parse_float=Decimal)),
                    **({} if body is None else json.loads(body, parse_float=Decimal)),
                    **(
                        {}
                        if context is None
                        else {"context": json.loads(context, parse_float=Decimal)}
                    ),
                ).items()
                if v is not None and v != ""
            )

            return params
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding JSON in event data: {str(e)}")
            raise
