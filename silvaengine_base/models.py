#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from enum import Enum
from datetime import datetime, date
from typing import Any, Dict, Union, Type
from silvaengine_utility import Utility
from pynamodb.indexes import AllProjection, GlobalSecondaryIndex
from pynamodb.models import Model
from pynamodb.attributes import (
    Attribute,
    BooleanAttribute,
    ListAttribute,
    MapAttribute,
    UnicodeAttribute,
    JSONAttribute,
    UTCDateTimeAttribute
)
import os, decimal, pickle


class AnyAttribute(Attribute[Any]):
    """
    Universal Attribute that can store and retrieve any data type supported by DynamoDB
    """
    
    def serialize(self, value: Any) -> Dict[str, Any]:
        """
        Serialize Python values to DynamoDB format
        """
        # Handle None
        if value is None:
            return {"NULL": True}
        
        # Handle boolean values
        elif isinstance(value, bool):
            return {"BOOL": value}
        
        # Handle numbers
        elif isinstance(value, (int, float, decimal.Decimal)):
            # Preserve Decimal precision
            if isinstance(value, decimal.Decimal):
                num_str = str(value)
            else:
                num_str = str(value)
            return {"N": num_str}
        
        # Handle strings
        elif isinstance(value, str):
            return {"S": value}
        
        # Handle binary data
        elif isinstance(value, bytes):
            return {"B": value}
        
        # Handle byte arrays
        elif isinstance(value, bytearray):
            return {"B": bytes(value)}
        
        # Handle lists
        elif isinstance(value, (list, tuple)):
            return {"L": [self.serialize(item) for item in value]}
        
        # Handle dictionaries
        elif isinstance(value, dict):
            return {"M": {k: self.serialize(v) for k, v in value.items()}}
        
        # Handle sets
        elif isinstance(value, set):
            # Check the type of elements in the set
            if not value:  # Empty set
                return {"L": []}
            
            first_item = next(iter(value))
            
            # Number set
            if isinstance(first_item, (int, float, decimal.Decimal)):
                return {"NS": [str(item) for item in value]}
            
            # String set
            elif isinstance(first_item, str):
                return {"SS": list(value)}
            
            # Binary set
            elif isinstance(first_item, (bytes, bytearray)):
                binary_items = [bytes(item) if isinstance(item, bytearray) else item 
                              for item in value]
                return {"BS": binary_items}
            
            else:
                # Store other types of sets as lists
                return {"L": [self.serialize(item) for item in value]}
        
        # Handle datetime objects
        elif isinstance(value, (datetime, date)):
            return {"S": value.isoformat()}
        
        # Handle enumerations
        elif isinstance(value, Enum):
            return {"S": value.value if hasattr(value, 'value') else value.name}
        
        # Try JSON serialization
        else:
            try:
                return {"S": Utility.json_dumps(value, default=self._json_default)}
            except:
                # Finally try pickle serialization
                try:
                    pickled = pickle.dumps(value)
                    return {"B": pickled}
                except:
                    raise ValueError(f"Cannot serialize value of type {type(value)}: {value}")
    
    def _json_default(self, obj):
        """JSON default handler"""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, decimal.Decimal):
            return float(obj)
        elif isinstance(obj, Enum):
            return obj.value if hasattr(obj, 'value') else obj.name
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def deserialize(self, value: Dict[str, Any]) -> Any:
        """
        Deserialize DynamoDB format to Python values
        """
        # Deserialize based on DynamoDB data type keys
        if "NULL" in value:
            return None
        
        elif "BOOL" in value:
            return value["BOOL"]
        
        elif "N" in value:
            # Intelligently convert number types
            num_str = value["N"]
            return self._parse_number(num_str)
        
        elif "S" in value:
            str_value = value["S"]
            # Try parsing as datetime
            try:
                # Try ISO format datetime
                return datetime.fromisoformat(str_value.replace('Z', '+00:00'))
            except:
                # Try JSON parsing
                try:
                    return Utility.json_loads(str_value, parse_float=decimal.Decimal)
                except:
                    return str_value
        
        elif "B" in value:
            binary_data = value["B"]
            # Try unpickling
            try:
                return pickle.loads(binary_data)
            except:
                # Return raw binary data
                return binary_data
        
        elif "L" in value:
            return [self.deserialize(item) for item in value["L"]]
        
        elif "M" in value:
            return {k: self.deserialize(v) for k, v in value["M"].items()}
        
        elif "NS" in value:
            return set([self._parse_number(n) for n in value["NS"]])
        
        elif "SS" in value:
            return set(value["SS"])
        
        elif "BS" in value:
            return set(value["BS"])
        
        else:
            return value
    
    def _parse_number(self, num_str: str) -> Union[int, float, decimal.Decimal]:
        """
        Intelligently parse number strings
        """
        # Try integer
        try:
            if '.' not in num_str and 'e' not in num_str.lower():
                return int(num_str)
        except:
            pass
        
        # Try float
        try:
            return float(num_str)
        except:
            pass
        
        # Finally try Decimal
        return decimal.Decimal(num_str)


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
    value = AnyAttribute()


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
