"""Fishing coordinates from the game's compass label; stable waterbody ID."""
import re


def parse_coordinates(text):
    if not isinstance(text,str):return None
    match=re.fullmatch(r'\s*(-?\d{1,5})\s*:\s*(-?\d{1,5})\s*',text)
    return tuple(map(int,match.groups())) if match else None


def read_location(observer,controller,widgets):
    waterbody=None;coordinates=None
    try:
        loader=observer.ref(controller,'m_levelLoader')
        level=observer.ref(loader,'okjdbiempch') if loader else 0
        settings=observer.ref(level,'dhfmgieampn') if level else 0
        if settings and observer.cls(settings)['full_name']=='RF4.Client.FishingScene.FishingSceneSettings':
            value=observer.string(settings,'sceneLevelName')
            if value and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',value):waterbody=value
        compasses=[w for w in widgets if w and observer.cls(w)['full_name']=='RF4.Client.UI.HUD.RHUDCompassWidget']
        if len(compasses)==1:
            label=observer.ref(compasses[0],'coordinates')
            if label:coordinates=parse_coordinates(observer.string(label,'mText'))
    except (OSError,ValueError,StopIteration,KeyError):pass
    return waterbody,coordinates
