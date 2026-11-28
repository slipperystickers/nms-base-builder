"""Resolve a saved galactic address against the station descriptors extracted from NMS."""
import json
import re
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / 'resources' / 'station'
SYSTEM_MASK = (1 << 52) - 1
WORD = (1 << 32) - 1
DOUBLE_WORD = (1 << 64) - 1


def read_address(value):
    """Save fields use decimal or explicit hexadecimal. Empty exports have no location."""
    if type(value) is int:
        number = value
    elif isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r'(?:0[xX][0-9a-fA-F]{1,14}|[0-9]{1,17})', text):
            return None
        number = int(text, 16 if text.lower().startswith('0x') else 10)
    else:
        return None
    return number & SYSTEM_MASK if 0 < number < 1 << 56 and number & SYSTEM_MASK else None


class Draws:
    """NMS multiply-with-carry stream. A nested scene starts a fresh stream."""
    def __init__(self, seed):
        low = seed & WORD
        self.value = low or 1
        self.carry = ((low >> 16 | low << 16) & WORD) ^ low ^ (seed >> 32)

    def draw(self):
        self.carry, self.value = divmod(self.value * 1517746329 + self.carry, 1 << 32)
        return self.value

    def branch(self):
        value = self.draw() | (self.draw() << 32)
        for factor in (0x64DD81482CBD31D7, 0xE36AA5C613612997):
            value = ((value ^ (value >> 33)) * factor) & DOUBLE_WORD
        return value ^ (value >> 33)

    def skip(self, words):
        for _ in range(words):
            self.draw()


@lru_cache(maxsize=1)
def tables():
    return json.loads((ASSETS / 'address_tables.json').read_bytes())


def descriptors(seed):
    scenes = tables()['scenes']
    selected = set()

    def traverse(groups, stream):
        for options in groups:
            if any(name in selected for name, _, _ in options):
                continue
            weights = [0 if 'XNEVER' in name else 1 if 'XRARE' in name else 20 for name, _, _ in options]
            total = sum(weights)
            if not total:
                continue
            position = stream.draw() * total >> 32
            for (name, children, scenes_used), weight in zip(options, weights):
                position -= weight
                if position >= 0:
                    continue
                selected.add(re.sub(r'LOD[0-9]$', '', name))
                for child in children:
                    traverse(child, Draws(stream.branch()))
                for scene in scenes_used:
                    branch = stream.branch()
                    if scene is not None:
                        traverse(scenes[scene], Draws(branch))
                break

    traverse(scenes['models/space/spacestation/spacestationtypeb'], Draws(Draws(seed).branch()))
    return selected


def hull_colours(seed):
    """Primary swatches of SpaceStationBase and SpaceStationAlt, in linear RGB."""
    root = Draws(seed)
    root.skip(4)
    planet = Draws(root.branch())
    palette = Draws(planet.branch())
    palette.skip(52 * 10 + 2)
    extra = Draws(palette.branch())
    extra.skip(10)
    tail = Draws(extra.branch())
    # Eight slots precede SpaceStationBase here. Slot 56 uses its own stream.
    tail.skip(7 * 10)
    colours = []
    for name in ('SpaceStationBase', 'SpaceStationAlt'):
        row, column = tail.draw() >> 29, tail.draw() >> 29
        index = row * 8 + column if name == 'SpaceStationBase' else (row // 2 * 8 + column // 2) * 2
        rgb = tables()['palettes'][name][index]
        colours.append(tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb) + (1.0,))
        tail.skip(8)
    return colours

