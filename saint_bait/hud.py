"""Compact overlay formatting, independent of Tk and the game reader."""
from .rods import RodPhase


SHORT_PHASE={RodPhase.UNKNOWN:'нет данных',RodPhase.READY:'готова',RodPhase.DEPLOYED:'ожидание',
             RodPhase.REEL_IN:'сматываю',RodPhase.HOOKED:'рыба',RodPhase.CATCH:'улов',RodPhase.CASTING:'заброс'}


def compact_line(rod,names,index=1):
    label=rod.slot_key or str(index)
    parts=[label,SHORT_PHASE[rod.phase]]
    if rod.hooked or rod.phase==RodPhase.CATCH:
        fish=names.get(rod.species)
        if fish:parts.append(fish)
        if rod.weight_g:
            parts.append((f'{rod.weight_g} г' if rod.weight_g<1000 else f'{rod.weight_g/1000:.2f} кг').replace('.',','))
    if rod.load_fraction is not None and (rod.active or rod.hooked):
        parts.append(f'{rod.load_fraction*100:.0f}%')
    return ' · '.join(parts)
