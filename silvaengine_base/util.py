#!/usr/bin/python
# -*- coding: utf-8 -*-
import functools, inspect, time

def monitor_decorator(original_function):
    @functools.wraps(original_function)
    def wrapper_function(*args, **kwargs):
        print(
            f">>> Start function: {original_function.__name__} at {time.strftime('%X')}!!"
        )
        result = original_function(*args, **kwargs)
        print(
            f">>> End function: {original_function.__name__} at {time.strftime('%X')}!!"
        )
        return result

    return wrapper_function