#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from pynamodb.indexes import AllProjection, GlobalSecondaryIndex
from pynamodb.models import Model
from pynamodb.attributes import (
    BooleanAttribute,
    ListAttribute,
    MapAttribute,
    UnicodeAttribute,
    JSONAttribute,
    UTCDateTimeAttribute
)
import os


class BaseModel(Model):
    class Meta:
        region = os.getenv("REGIONNAME", "us-east-1")
        billing_mode = "PAY_PER_REQUEST"


class EndpointModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-endpoints"

    endpoint_id = UnicodeAttribute(hash_key=True)
    special_connection = BooleanAttribute(default=False)


class FunctionMap(MapAttribute):
    aws_lambda_arn = UnicodeAttribute()
    function = UnicodeAttribute()
    setting = UnicodeAttribute()


class ConnectionModel(BaseModel):
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


class FunctionModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-functions"

    aws_lambda_arn = UnicodeAttribute(hash_key=True)
    function = UnicodeAttribute(range_key=True)
    area = UnicodeAttribute()
    config = ConfigMap()


class HookModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-hooks"

    api_id = UnicodeAttribute(hash_key=True)
    module_name = UnicodeAttribute(range_key=True)
    function_name = UnicodeAttribute()
    is_async = BooleanAttribute(default=False)
    is_interruptible = BooleanAttribute(default=False)
    status = BooleanAttribute(default=True)
    description = UnicodeAttribute()


class ConfigModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-configdata"

    setting_id = UnicodeAttribute(hash_key=True)
    variable = UnicodeAttribute()
    value = JSONAttribute()


class ConnectionIdIndex(GlobalSecondaryIndex):
    """
    This class represents a local secondary index
    """

    class Meta:
        billing_mode = "PAY_PER_REQUEST"
        projection = AllProjection()
        index_name = "connection_id-index"

    connection_id = UnicodeAttribute(hash_key=True)


class WSSConnectionModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "se-wss-connections"

    endpoint_id = UnicodeAttribute(hash_key=True)
    connection_id = UnicodeAttribute(range_key=True)
    api_key = UnicodeAttribute()
    area = UnicodeAttribute()
    data = MapAttribute(default=dict)
    status = UnicodeAttribute(default="active")
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()
    connect_id_index = ConnectionIdIndex()
