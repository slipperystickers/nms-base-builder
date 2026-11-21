"""Readable native Corvette bonuses shared by the thumbnail and button tooltips."""
from functools import lru_cache
import json
from pathlib import Path

LABELS={
 'Ship_Boost':'Boost speed', 'Ship_BoostManeuverability':'Boost maneuverability',
 'Ship_Maneuverability':'Maneuverability', 'Ship_PulseDrive_MiniJumpFuelSpending':'Pulse fuel use',
 'Ship_Launcher_TakeOffCost':'Launch fuel cost', 'Ship_Launcher_AutoCharge':'Launch auto recharge',
 'Ship_Hyperdrive_JumpDistance':'Hyperdrive range', 'Ship_Hyperdrive_JumpsPerCell':'Hyperdrive fuel efficiency',
 'Ship_Armour_Shield_Strength':'Shield strength', 'Ship_Cargo_Slots':'Cargo slots',
 'Ship_TractorBeam':'Tractor beam', 'Ship_Weapons_Guns_Damage':'Weapon damage',
 'Ship_Weapons_Guns_Rate':'Weapon fire rate','Ship_Weapons_Guns_HeatTime':'Weapon heat capacity',
 'Ship_Weapons_Guns_CoolTime':'Weapon cooldown','Ship_Weapons_Guns_Range':'Weapon range',
 'Ship_Weapons_Lasers_Damage':'Laser damage','Ship_Weapons_Lasers_HeatTime':'Laser heat capacity'}
PERCENT_MULTIPLIERS={'Ship_Boost','Ship_BoostManeuverability','Ship_Maneuverability',
 'Ship_PulseDrive_MiniJumpFuelSpending','Ship_Launcher_TakeOffCost'}

@lru_cache(maxsize=1)
def catalogue():
    return json.loads((Path(__file__).parent/'resources/part_stats.json').read_text(encoding='utf8'))['parts']

def lines(part):
    from . import i18n
    return _lines(part, i18n.interface_locale())


@lru_cache(maxsize=512)
def _lines(part, locale):
    from . import i18n
    def translated(label):
        return i18n.for_locale(locale, label)
    record=catalogue().get(str(part).lstrip('^'))
    if not record:return ()
    output=[translated('Corvette bonuses (native ranges)')]
    for stat in record['stats']:
        name=stat['stat'];a=stat['minimum'];b=stat['maximum']
        if name in PERCENT_MULTIPLIERS:
            a=round((a-1)*100,4);b=round((b-1)*100,4);unit='%';fmt=lambda v:f'{v:+g}'
        elif name=='Ship_Armour_Shield_Strength':
            a*=100;b*=100;unit='%';fmt=lambda v:f'{v:+g}'
        else:
            unit=' ly' if name=='Ship_Hyperdrive_JumpDistance' else ''
            fmt=lambda v:f'{v:g}'
        number=fmt(a) if a==b else fmt(a)+'–'+fmt(b)
        output.append(translated(LABELS.get(name,name.removeprefix('Ship_').replace('_',' ')))+': '+number+unit)
    if record['count_min']<len(record['stats']):
        output.append(translated('Rolls {minimum}–{maximum} of these bonuses.').format(
            minimum=record['count_min'], maximum=record['count_max']))
    output.append(translated('Final values depend on the build.'))
    return tuple(output)
