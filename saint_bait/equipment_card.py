"""Compact RF4-style equipment cards backed by exact native item IDs."""
import json
from functools import lru_cache
from pathlib import Path
import customtkinter as ctk
from PIL import Image
from .paths import resource_path
from .equipment_text import KINDS,measurements,condition_text


class EquipmentArt:
    def __init__(self):
        try:
            self.names=json.loads(Path(resource_path('assets/item_names.json')).read_text(encoding='utf-8'))
        except (OSError,ValueError):self.names={}

    def name(self,item,fallback):
        return self.names.get(item.system_id,{}).get('name',item.system_id) if item else fallback

    @lru_cache(maxsize=64)
    def image(self,system_id,size):
        # IDs are validated by the memory reader; restrict paths independently.
        if Path(system_id).name!=system_id or '/' in system_id or '\\' in system_id:return None
        try:
            with Image.open(resource_path('assets/equipment/'+system_id+'.png')) as source:
                picture=source.convert('RGBA')
            return ctk.CTkImage(light_image=picture,dark_image=picture,size=size)
        except (OSError,ValueError):return None


class EquipmentCard(ctk.CTkFrame):
    def __init__(self,master,art,colors,font,index):
        super().__init__(master,fg_color=colors['surface'],corner_radius=0)
        self.art=art;self.colors=colors
        self.grid_columnconfigure(0,weight=1)
        self.title=ctk.CTkLabel(self,text=f'Снасть {index+1}',anchor='w',height=22,
                              font=(font,11,'bold'),text_color=colors['muted'])
        self.title.grid(row=0,column=0,sticky='ew',padx=9)
        pictures=ctk.CTkFrame(self,fg_color=colors['raised'],height=68,corner_radius=0)
        pictures.grid(row=1,column=0,sticky='ew',padx=7)
        pictures.grid_columnconfigure((0,1),weight=1,uniform='art')
        self.pictures={}
        for col,(kind,size) in enumerate((('rod',64),('reel',54))):
            label=ctk.CTkLabel(pictures,text='—',width=48,height=68,text_color=colors['muted'])
            label.grid(row=0,column=col,sticky='nsew')
            self.pictures[kind]=(label,(size,size))
        self.names={}
        for row,(kind,text) in enumerate((('rod','Удилище —'),('reel','Катушка —')),2):
            label=ctk.CTkLabel(self,text=text,anchor='w',height=30,wraplength=250,justify='left',
                              font=(font,11,'bold') if kind=='rod' else (font,10),
                              text_color=colors['text'] if kind=='rod' else colors['muted'])
            label.grid(row=row,column=0,sticky='ew',padx=9)
            self.names[kind]=label
        self.components=ctk.CTkFrame(self,fg_color='transparent',corner_radius=0,height=1)
        self.components.grid(row=4,column=0,sticky='ew',padx=6,pady=(3,0))
        self.components.grid_columnconfigure(0,weight=1)
        self._component_layout=None
        self._component_rows=[]
        self.phase=ctk.CTkLabel(self,text='Ожидание игры',anchor='w',height=22,wraplength=250,
                              justify='left',font=(font,11),text_color=colors['text'])
        self.phase.grid(row=5,column=0,sticky='ew',padx=9,pady=(3,0))
        self.detail=ctk.CTkLabel(self,text='',anchor='w',height=34,wraplength=250,justify='left',
                               font=(font,10),text_color=colors['muted'])
        self.detail.grid(row=6,column=0,sticky='ew',padx=9,pady=(0,5))
        self.load=ctk.CTkProgressBar(self,height=3,corner_radius=0,fg_color=colors['raised'],
                                   progress_color=colors['accent'])
        self.load.grid(row=7,column=0,sticky='ew')
        self.load.set(0)
        self._equipment=None
        self._rod=None
        self._details=None
        self.details_button=ctk.CTkButton(self,text='Состав и состояние',height=22,corner_radius=0,
                                         fg_color=colors['raised'],hover_color=colors['border'],
                                         text_color=colors['text'],font=(font,10),command=self.show_details)
        self.details_button.grid(row=8,column=0,sticky='ew')

    def update_equipment(self,rod):
        self._rod=rod
        equipment=rod.equipment if rod else ()
        if equipment!=self._equipment:
            self._equipment=equipment
            parts={item.kind:item for item in equipment}
            for kind,(label,size) in self.pictures.items():
                item=parts.get(kind)
                picture=self.art.image(item.icon_id or item.system_id,size) if item else None
                label.configure(image=picture,text='' if picture else '—')
                name=self.art.name(item,{'rod':'Удилище —','reel':'Катушка —'}[kind])
                if item:name+='\n'+' · '.join(filter(None,(measurements(item),condition_text(item))))
                self.names[kind].configure(text=name)
            self._update_components(tuple(item for item in equipment if item.kind not in ('rod','reel')))
        fraction=rod.load_fraction if rod else None
        self.load.set(max(0,min(1,fraction or 0)))
        self.load.configure(progress_color=self.colors['danger'] if fraction and fraction>=.85 else self.colors['accent'])
        if self._details and self._details.winfo_exists():self._render_details()

    def _update_components(self,items):
        layout=tuple((item.kind,item.system_id,item.icon_id) for item in items)
        if layout!=self._component_layout:
            self._component_layout=layout
            for frame,_label in self._component_rows:frame.destroy()
            self._component_rows=[]
            for index,item in enumerate(items):
                frame=ctk.CTkFrame(self.components,fg_color=self.colors['input'],corner_radius=0)
                frame.grid(row=index,column=0,sticky='ew',pady=(0,2))
                frame.grid_columnconfigure(1,weight=1)
                picture=self.art.image(item.icon_id or item.system_id,(28,28))
                ctk.CTkLabel(frame,text='' if picture else '·',image=picture,width=30,height=32).grid(row=0,column=0,padx=2)
                label=ctk.CTkLabel(frame,text='',anchor='w',justify='left',font=('Myriad Pro',10),wraplength=225,
                                   text_color=self.colors['text'])
                label.grid(row=0,column=1,sticky='ew',padx=(2,4),pady=2)
                self._component_rows.append((frame,label))
        for item,(_frame,label) in zip(items,self._component_rows):
            name=KINDS.get(item.kind,'Компонент')+' · '+self.art.name(item,'—')
            if len(name)>43:name=name[:42]+'…'
            stats=' · '.join(filter(None,(measurements(item),condition_text(item))))
            if item.kind=='bait' and item.quantity is not None:stats+=f' · {item.quantity} шт.'
            label.configure(text=name+'\n'+stats)

    def show_details(self):
        if self._details and self._details.winfo_exists():
            self._details.lift();return
        window=ctk.CTkToplevel(self)
        self._details=window
        window.title('Saint Bait · состав снасти')
        window.geometry('510x580')
        window.configure(fg_color=self.colors['window'])
        self._details_header=ctk.CTkLabel(window,text='',font=('Myriad Pro',15,'bold'),anchor='w')
        self._details_header.pack(fill='x',padx=16,pady=(12,6))
        self._details_frame=ctk.CTkScrollableFrame(window,fg_color=self.colors['window'],corner_radius=0)
        self._details_frame.pack(fill='both',expand=True,padx=10,pady=(0,10))
        self._details_rows=[]
        self._details_signature=None
        self._render_details()

    def _render_details(self):
        rod=self._rod
        signature=(tuple((i.kind,i.system_id,round(i.condition,3) if i.condition is not None else None,
                          round(i.strength_kg,2) if i.strength_kg is not None else None,i.quantity,
                          i.length_m,i.diameter_mm,i.mass_g,i.icon_id)
                         for i in rod.equipment),round(rod.tackle_limit or 0,1)) if rod else None
        if signature==self._details_signature:return
        self._details_signature=signature
        for row in self._details_rows:row.destroy()
        self._details_rows=[]
        self._details_header.configure(text=('Предел снасти: '+f'{rod.tackle_limit/9.80665:.2f} кгс'
            if rod and rod.tackle_limit else 'Предел снасти: —'))
        kinds={'rod':'Удилище','reel':'Катушка','line':'Леска / шнур','leader':'Поводок','hook':'Крючок',
               'sinker':'Грузило','bait':'Наживка','alarm':'Сигнализатор','component':'Компонент'}
        for item in rod.equipment if rod else ():
            row=ctk.CTkFrame(self._details_frame,fg_color=self.colors['surface'],corner_radius=0)
            row.pack(fill='x',pady=3)
            self._details_rows.append(row)
            picture=self.art.image(item.icon_id or item.system_id,(64,64))
            image=ctk.CTkLabel(row,text='' if picture else '—',image=picture,width=70,height=70)
            image.pack(side='left',padx=5)
            text=kinds.get(item.kind,item.kind)+' · '+self.art.name(item,'—')
            condition=f'{item.condition*100:.1f}%' if item.condition is not None else '—'
            strength=f'{item.strength_kg:.2f} кг' if item.strength_kg is not None else '—'
            text+=f'\nСостояние {condition} · текущая прочность {strength}'
            if item.nominal_kg is not None:text+=f' · исходная {item.nominal_kg:.2f} кг'
            if measurements(item):text+='\n'+measurements(item)
            if item.quantity is not None:text+=f'\nНа оснастке: {item.quantity} шт.'
            label=ctk.CTkLabel(row,text=text,anchor='w',justify='left',wraplength=360,
                               font=('Myriad Pro',11),text_color=self.colors['text'])
            label.pack(side='left',fill='x',expand=True,padx=4,pady=8)
