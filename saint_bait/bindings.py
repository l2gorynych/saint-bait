"""Supported Unity keys and verified gameplay action identifiers."""
ACTION_IDS={'reel':101,'pull':102,'stand':21,'net':26,'spool':107,
            'flashlight':18,'boost':5,'drag_down':55,'drag_up':54,'speed_modifier':19,
            'food':28,
            **{'slot'+str(n):30+n for n in range(1,8)}}
KEYS={8:'backspace',9:'tab',13:'enter',19:'pause',27:'esc',32:'space',127:'delete',
      256:'num0',257:'num1',258:'num2',259:'num3',260:'num4',261:'num5',262:'num6',
      263:'num7',264:'num8',265:'num9',266:'decimal',267:'divide',268:'multiply',
      269:'subtract',270:'add',271:'num_enter',273:'up',274:'down',275:'right',276:'left',
      277:'insert',278:'home',279:'end',280:'pageup',281:'pagedown',300:'numlock',
      301:'capslock',302:'scrolllock',303:'right shift',304:'left shift',
      305:'right ctrl',306:'left ctrl',307:'right alt',308:'left alt',
      323:'mouse:left',324:'mouse:right',325:'mouse:middle'}
KEYS.update({value:chr(value) for value in range(33,127)})
KEYS.update({281+n:'f'+str(n) for n in range(1,16)})


def unity_key(code):
    return KEYS.get(code)


def direct_key(key):
    return {'left alt':'altleft','right alt':'altright','left ctrl':'ctrlleft',
            'right ctrl':'ctrlright','left shift':'shiftleft','right shift':'shiftright'}.get(key,key)


def resolve_bindings(defaults,overrides,modifiers=None):
    merged={**defaults,**overrides}
    result={}
    for name,action in ACTION_IDS.items():
        # InputPair contains alternative inputs, not a modifier chord.
        for code in merged.get(action,()):
            value=unity_key(code)
            if value:
                result[name]=value
                # InputPair.kpfhbdgmmif (0x1362420) maps these values to
                # Shift/Ctrl/Alt. The pair's two InputUnits remain alternatives.
                modifier=(modifiers or {}).get(action)
                if modifier in (2,3,4):
                    result[name+'_modifier']={2:'left shift',3:'left ctrl',4:'left alt'}[modifier]
                break
    return tuple(sorted(result.items()))
