"""Keep uncertain catches and awards; release only positively identified small fish."""
import random


def release_small(grade,trophy,card,roll=random.random):
    return grade==1 and trophy is False and card is False and roll()<.25
