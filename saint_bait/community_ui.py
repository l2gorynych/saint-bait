"""Nearby catch feed and optional connection settings."""
from datetime import datetime
from types import SimpleNamespace
import customtkinter as ctk
from .prices import estimate_price


class CommunityPanel(ctk.CTkFrame):
    def __init__(self,master,ui,colors,font):
        super().__init__(master,fg_color='transparent')
        self.ui=ui;self.colors=colors;self._last_text=None
        self._events={}
        self.grid_columnconfigure(0,weight=1)
        self.location=ctk.CTkLabel(self,text='Ожидание координат игры',anchor='w',font=(font,12,'bold'))
        self.location.grid(row=0,column=0,sticky='ew',padx=6)
        self.status=ctk.CTkLabel(self,text='Локальный журнал',anchor='w',font=(font,10),text_color=colors['muted'])
        self.status.grid(row=1,column=0,sticky='ew',padx=6)
        self.mode=ctk.CTkSegmentedButton(self,values=['Уловы точки','Мой садок'],height=24,
                                       selected_color=colors['accent_dark'],selected_hover_color=colors['border'],
                                       unselected_color=colors['raised'],unselected_hover_color=colors['border'],
                                       command=lambda _value:setattr(self,'_last_text',None))
        self.mode.set('Уловы точки')
        self.mode.grid(row=2,column=0,sticky='ew',padx=6,pady=(4,0))
        self.feed=ctk.CTkTextbox(self,height=180,corner_radius=0,fg_color=colors['input'],
                                text_color=colors['text'],font=(font,11),wrap='word',state='disabled')
        self.feed.grid(row=3,column=0,sticky='ew',padx=6,pady=5)
        self.feed.bind('<Button-1>',self.open_event,add='+')
        self.connection=ctk.CTkFrame(self,fg_color='transparent')
        self.connection.grid(row=4,column=0,sticky='ew',padx=6)
        self.connection.grid_columnconfigure(0,weight=1)
        self.update_status=ctk.CTkLabel(self.connection,text='',anchor='w',font=(font,10),wraplength=550)
        self.update_status.grid(row=0,column=0,sticky='ew')

    def refresh(self):
        scene=self.ui.rod_registry.scene()
        current=(scene.waterbody_id,*scene.coordinates) if scene and scene.waterbody_id and scene.coordinates else None
        location,rows,status=self.ui.community.snapshot()
        self.location.configure(text=(f'{current[0]} · {current[1]}:{current[2]} · рядом ±3' if current else 'Ожидание координат игры'))
        self.status.configure(text=status+(' · ошибка локального журнала' if self.ui.rod_monitor.journal_error else ''))
        lines=[]
        priced=0;total_cents=0
        own_corf=self.mode.get()=='Мой садок'
        events={}
        if own_corf:
            rows=[]
            for fish in self.ui.rod_registry.corf():
                recorded=self.ui.catch_journal.find_fish(fish.fish_id)
                rows.append(recorded or dict(fish_id=fish.fish_id,species=fish.species,weight_g=fish.weight_g,
                    grade=fish.grade,occurred_at=fish.caught_at,waterbody_id=fish.caught_waterbody,bait_id=fish.bait_id))
        if current and (location==current or own_corf):
            samples=self.ui.community.price_snapshot()
            for item in rows:
                species=self.ui._fish_names.get(item.get('species'),item.get('species','Рыба'))
                try:date=datetime.fromisoformat(item['occurred_at']).astimezone().strftime('%d.%m %H:%M:%S')
                except (KeyError,TypeError,ValueError):date='—'
                bait=item.get('bait_id')
                bait_name=self.ui._equipment_art.names.get(bait,{}).get('name',bait or 'наживка неизвестна')
                clip=str(item['clip_m'])+' м' if item.get('clip_m') is not None else '—'
                fish=SimpleNamespace(fish_id=item.get('fish_id'),species=item.get('species'),weight_g=item.get('weight_g',0),
                                     grade=item.get('grade'),caught_at=item.get('occurred_at'))
                estimate=estimate_price(fish,current[0],samples)
                if estimate:
                    priced+=1;total_cents+=estimate['cents']
                price=(' · '+('' if estimate['exact'] else '≈')+f"{estimate['cents']/100:.2f} сер.") if estimate else ' · цена —'
                events[len(lines)*3+1]={**item,'_estimate':estimate}
                events[len(lines)*3+2]=events[len(lines)*3+1]
                point=f" · {item['x']}:{item['y']}" if item.get('x') is not None and item.get('y') is not None else ''
                lines.append(f"{date} · {species} {item.get('weight_g',0)/1000:.3f} кг{point}{price}\n"
                             f"{bait_name} · клипса {clip} · нажми для состава снасти")
        text='\n\n'.join(lines) if lines else ('Садок пуст или данные ещё загружаются.' if own_corf else 'Уловов рядом пока нет. Подтверждённые уловы сохраняются автоматически.')
        if own_corf and current:
            summary=(f'Оценено {priced} из {len(rows)} рыб: ≈{total_cents/100:.2f} сер.' if priced else
                     f'В садке {len(rows)} рыб · для оценки цен пока мало данных')
            text=summary+'\n\n'+text
            events={line+2:item for line,item in events.items()}
        self._events=events
        if text!=self._last_text:
            self._last_text=text
            self.feed.configure(state='normal');self.feed.delete('1.0','end');self.feed.insert('1.0',text);self.feed.configure(state='disabled')
        self.update_status.configure(text=self.ui.updates.status)

    def open_event(self,event):
        try:line=int(self.feed.index(f'@{event.x},{event.y}').split('.')[0])
        except (ValueError,AttributeError):return
        item=self._events.get(line)
        if item:
            from .catch_details import open_catch_details
            open_catch_details(self.ui,item,self.colors)
