"""A catch opens its recorded tackle, not the player's current equipment."""
import customtkinter as ctk
from .equipment_text import measurements


def open_catch_details(ui,event,colors):
    window=ctk.CTkToplevel(ui)
    window.title('Saint Bait · улов')
    window.geometry('540x650')
    window.configure(fg_color=colors['window'])
    species=ui._fish_names.get(event.get('species'),event.get('species','Рыба'))
    head=f"{species} · {event.get('weight_g',0)/1000:.3f} кг"
    ctk.CTkLabel(window,text=head,font=('Myriad Pro',19,'bold')).pack(anchor='w',padx=16,pady=(14,5))
    clip=str(event['clip_m'])+' м' if event.get('clip_m') is not None else 'нет данных'
    bait=event.get('bait_id')
    bait=ui._equipment_art.names.get(bait,{}).get('name',bait or 'нет данных')
    info=f"{event.get('occurred_at','—')}\n{event.get('waterbody_id','—')} · {event.get('x','—')}:{event.get('y','—')}\nНаживка: {bait} · клипса: {clip}"
    estimate=event.get('_estimate')
    if estimate:
        info+=f"\n{'Оценка рынка' if estimate['exact'] else 'Примерная цена'}: {estimate['cents']/100:.2f} серебра · примеров: {estimate['samples']}"
        info+=f"\nЦены наблюдались: {estimate['observed_at']}"
    groundbait=event.get('groundbait_used')
    info+='\nПрикормка: '+('применялась' if groundbait is True else 'не применялась' if groundbait is False else 'нет подтверждённых данных')
    for item in event.get('groundbait') or []:
        if isinstance(item,dict):info+='\n  '+str(item.get('name') or item.get('system_id') or 'смесь')[:200]
    ctk.CTkLabel(window,text=info,justify='left',anchor='w',font=('Myriad Pro',11),wraplength=500).pack(fill='x',padx=16,pady=5)
    frame=ctk.CTkScrollableFrame(window,fg_color=colors['window'],corner_radius=0)
    frame.pack(fill='both',expand=True,padx=10,pady=(5,12))
    equipment=event.get('equipment') or []
    if not equipment:
        ctk.CTkLabel(frame,text='Состав снасти для этого улова не записан.',font=('Myriad Pro',12)).pack(pady=12)
    kinds={'rod':'Удилище','reel':'Катушка','line':'Леска / шнур','leader':'Поводок','hook':'Крючок',
           'sinker':'Грузило','bait':'Наживка','alarm':'Сигнализатор','component':'Компонент'}
    for item in equipment[:20]:
        if not isinstance(item,dict) or not isinstance(item.get('system_id'),str):continue
        row=ctk.CTkFrame(frame,fg_color=colors['surface'],corner_radius=0)
        row.pack(fill='x',pady=3)
        picture=ui._equipment_art.image(item.get('icon_id') or item['system_id'],(64,64))
        ctk.CTkLabel(row,text='' if picture else '—',image=picture,width=70,height=70).pack(side='left',padx=5)
        name=ui._equipment_art.names.get(item['system_id'],{}).get('name',item['system_id'])
        text=kinds.get(item.get('kind'),'Компонент')+' · '+name[:160]
        condition=item.get('condition');strength=item.get('strength_kg')
        if isinstance(condition,(float,int)) and 0<=condition<=1:text+=f'\nСостояние {condition*100:.1f}%'
        if isinstance(strength,(float,int)) and 0<strength<100000:text+=f' · прочность {strength:.2f} кг'
        if measurements(item):text+='\n'+measurements(item)
        ctk.CTkLabel(row,text=text,anchor='w',justify='left',wraplength=390,font=('Myriad Pro',11)).pack(side='left',fill='x',expand=True,padx=4,pady=8)
