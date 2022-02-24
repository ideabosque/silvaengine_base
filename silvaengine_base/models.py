#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from pynamodb.models import Model
from pynamodb.attributes import (
    MapAttribute,
    ListAttribute,
    UnicodeAttribute,
    BooleanAttribute,
    NumberAttribute,
)
import os


__author__ = "bibow"


class BaseModel(Model):
    class Meta:
        region = os.environ["REGIONNAME"]
        billing_mode = "PAY_PER_REQUEST"


class ConfigDataModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-configdata"

    setting_id = UnicodeAttribute(hash_key=True)
    variable = UnicodeAttribute(range_key=True)
    value = UnicodeAttribute()


class EndpointsModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-endpoints"

    endpoint_id = UnicodeAttribute(hash_key=True)
    code = NumberAttribute()
    special_connection = BooleanAttribute(default=False)


class FunctionMap(MapAttribute):
    aws_lambda_arn = UnicodeAttribute()
    function = UnicodeAttribute()
    setting = UnicodeAttribute()


class ConnectionsModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-connections"

    endpoint_id = UnicodeAttribute(hash_key=True)
    api_key = UnicodeAttribute(range_key=True, default="#####")
    functions = ListAttribute(of=FunctionMap)
    whitelist = ListAttribute()


class OperationMap(MapAttribute):
    # create = ListAttribute()
    query = ListAttribute()
    mutation = ListAttribute()
    # update = ListAttribute()
    # delete = ListAttribute()


class ConfigMap(MapAttribute):
    class_name = UnicodeAttribute()
    funct_type = UnicodeAttribute()
    methods = ListAttribute()
    module_name = UnicodeAttribute()
    setting = UnicodeAttribute()
    auth_required = BooleanAttribute(default=False)
    graphql = BooleanAttribute(default=False)
    operations = OperationMap()


class FunctionsModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-functions"

    aws_lambda_arn = UnicodeAttribute(hash_key=True)
    function = UnicodeAttribute(range_key=True)
    area = UnicodeAttribute()
    config = ConfigMap()


class HooksModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-hooks"

    api_id = UnicodeAttribute(hash_key=True)
    module_name = UnicodeAttribute(range_key=True)
    function_name = UnicodeAttribute()
    is_async = BooleanAttribute(default=False)
    is_interruptible = BooleanAttribute(default=False)
    status = BooleanAttribute(default=True)
    description = UnicodeAttribute()
