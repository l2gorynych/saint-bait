"""Keepnet state read from the game's own HUD model."""
import re


def parse_keepnet(text):
    if not isinstance(text,str):return None,None
    match=re.fullmatch(r'\s*(\d{1,5})\s*/\s*(\d{1,5})\s*',text)
    if not match:return None,None
    count,capacity=map(int,match.groups())
    if not 0<capacity<=10000 or not 0<=count<=capacity:return None,None
    return count,capacity


def keepnet_full(scene):
    return (scene.keepnet_count is not None and scene.keepnet_capacity is not None
            and scene.keepnet_capacity>0 and scene.keepnet_count>=scene.keepnet_capacity)
