#!/usr/bin/python
# -*- coding: utf-8 -*-
import functools, inspect, time

def monitor_decorator(original_function):
    @functools.wraps(original_function)
    def wrapper_function(*args, **kwargs):
        print(
            f"### Start function: {str(original_function)} at {time.strftime('%X')}!!"
        )
        result = original_function(*args, **kwargs)
        print(
            f"### End function: {str(original_function)} at {time.strftime('%X')}!!"
        )
        return result

    return wrapper_function