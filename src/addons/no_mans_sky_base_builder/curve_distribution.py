"""First-party spacing math for tapered repeat patterns (no editor dependency)."""
import math

KEY = 'bbe_size_spacing'


def scale_at(index, count, taper):
    return 1.0 - min(.99, max(0.0, taper / 100.0)) * index / max(1, count - 1)


def prepare(guide, length, count, props):
    # Old projects retain their exact layout until the taper is edited/rebuilt.
    if KEY in guide or props.taper <= 0 or count < 2:
        return
    intervals = count if guide.data.splines[0].use_cyclic_u else count - 1
    guide[KEY] = {'pitch': min(float(guide.get('bbe_curve_spacing', length / intervals)), length / intervals),
                  'size': max(.001, float(guide.get('radius_multiplier', 1))),
                  'curve_scale': max(1e-8, abs(guide.matrix_world.to_scale().x))}


def pitch(guide):
    state = guide[KEY]
    return (state['pitch'] * max(.001, float(guide.get('radius_multiplier', 1))) / state['size']
            * max(1e-8, abs(guide.matrix_world.to_scale().x)) / state['curve_scale'])


def set_pitch(guide, value):
    state = guide[KEY]
    state['pitch'] = max(.001, value) * state['size'] / max(.001, float(guide.get('radius_multiplier', 1)))
    state['pitch'] *= state['curve_scale'] / max(1e-8, abs(guide.matrix_world.to_scale().x))


def capacity(guide, length, props):
    if KEY not in guide:
        return 1000
    average = 1 - min(.99, max(0, props.taper / 100)) / 2
    intervals = math.floor((max(0, length) + 1e-6) / max(1e-8, pitch(guide) * average))
    return max(1, min(1000, intervals + (not guide.data.splines[0].use_cyclic_u)))


def distances(guide, count, props):
    step = pitch(guide)
    result = [0.0]
    for i in range(1, count):
        # The touching faces sit half a scaled copy away from each center.
        result.append(result[-1] + step * (scale_at(i-1, count, props.taper) + scale_at(i, count, props.taper)) / 2)
    return result


def max_pitch(guide, length, count, props):
    intervals = count if guide.data.splines[0].use_cyclic_u else max(1, count - 1)
    return length / (intervals * (1 - props.taper / 200))


def fill(guide, length, count, props):
    if KEY not in guide or count < 2:
        return
    intervals = count if guide.data.splines[0].use_cyclic_u else count - 1
    set_pitch(guide, length / (intervals * (1 - props.taper / 200)))


def twist_at(guide, index, count, props):
    denominator = count if guide.data.splines[0].use_cyclic_u else max(1, count - 1)
    return props.twist * index / denominator
