"""Shared units for live tackle cards and historical catch snapshots."""
KINDS={'rod':'Удилище','reel':'Катушка','line':'Леска / шнур','leader':'Поводок','hook':'Крючок',
       'sinker':'Грузило','bait':'Наживка','alarm':'Сигнализатор','component':'Компонент'}


def number(value):
    return f'{value:.2f}'.rstrip('0').rstrip('.').replace('.',',')


def measurements(item):
    get=item.get if isinstance(item,dict) else lambda key,default=None:getattr(item,key,default)
    parts=[]
    length=get('length_m')
    if isinstance(length,(int,float)) and 0<length<=10000:
        parts.append(number(length*100)+' см' if get('kind')=='leader' and length<1 else number(length)+' м')
    diameter=get('diameter_mm')
    if isinstance(diameter,(int,float)) and 0<diameter<=100:parts.append('Ø '+number(diameter)+' мм')
    mass=get('mass_g')
    if isinstance(mass,(int,float)) and 0<mass<=100000:parts.append(number(mass)+' г')
    return ' · '.join(parts)


def condition_text(item):
    get=item.get if isinstance(item,dict) else lambda key,default=None:getattr(item,key,default)
    parts=[]
    condition=get('condition');strength=get('strength_kg')
    if isinstance(condition,(int,float)) and 0<=condition<=1.001:parts.append(f'{condition*100:.1f}%')
    if isinstance(strength,(int,float)) and 0<strength<=100000:parts.append(number(strength)+' кг')
    return ' · '.join(parts)
