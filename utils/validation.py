import argparse
import math


def require_assertions():
    if not __debug__:
        raise RuntimeError("Проверки требуют запуска без -O и PYTHONOPTIMIZE")


def positive_number(value):
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Нужно конечное число больше нуля") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Нужно конечное число больше нуля")
    return number
