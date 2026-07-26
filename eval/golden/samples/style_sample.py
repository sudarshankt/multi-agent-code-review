"""Sample file with intentional style issues for eval/golden style dataset."""
import os
import sys
import json


def CalculateTotal(Items):
    unused_var = 42
    total = 0
    for i in Items:
        total = total + i
    return total


def check_value(x):
    if x == None:
        return False
    return True


def risky():
    try:
        return 1 / 0
    except:
        pass
