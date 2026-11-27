"""Asset Atlas measurements shared by asset tiles and the viewport analysis."""
import gzip
import json
from functools import lru_cache
from pathlib import Path
from . import i18n

MIB = 1024 ** 2
TITLE = "NMS performance impact"
SUMMARY = "Estimates how much work the game does to load and display this part."
LEGEND_HELP = (
    SUMMARY,
    "The score includes models, textures, animations, lights and particle effects.",
    "White and green mean lower impact. Red and burgundy mean higher impact. Gray means unknown.",
)
# Fixed score bands apply across categories and the build overlay.
BANDS = (
    (0, "Very low", "#eff9e7"), (1, "Low", "#83d59c"),
    (16, "Moderate", "#c4d76b"), (64, "Elevated", "#f1ad55"),
    (128, "High", "#e96350"), (192, "Very high", "#962345"),
)
UNKNOWN = (None, "Unmeasured", "#858a97")


@lru_cache(maxsize=1)
def catalogue():
    with gzip.open(Path(__file__).parent / "resources" / "asset_weights.json.gz", "rt", encoding="utf8") as handle:
        return json.load(handle)["parts"]


def record(part):
    return catalogue().get(str(part).lstrip("^").upper())


def band(row):
    if not row or row["mapping"] == "Placement proxy only" or not row["maxRoot"]:
        return UNKNOWN
    score = row.get("weightScore", row["maxRoot"] / MIB)
    return next(entry for entry in reversed(BANDS) if score >= entry[0])


@lru_cache(maxsize=4096)
def rgba(part):
    return hex_rgba(band(record(part))[2])


@lru_cache(maxsize=16)
def hex_rgba(colour):
    return tuple(int(colour[i:i+2], 16) / 255 for i in (1, 3, 5)) + (1.0,)


def size(value):
    return f"{value / MIB:.2f} MiB"


def lines(part):
    return _part_lines(part, i18n.interface_locale())


def legend_lines():
    return tuple(i18n.interface(message) for message in (TITLE, *LEGEND_HELP))


@lru_cache(maxsize=4096)
def _part_lines(part, locale):
    row = record(part)
    _, name, _ = band(row)
    translate = lambda message: i18n.for_locale(locale, message)
    output = [f"{translate(TITLE)} · {translate(name)}", str(part), translate(SUMMARY)]
    if name == "Unmeasured":
        reason = "Only the placement proxy is mapped." if row else "No asset measurement in the atlas."
        return tuple(output + [reason])
    fx = row.get("runtimeEffects", {})
    if "weightScore" in row:
        output.append(translate("Impact score   {score} points").format(score=f"{row['weightScore']:.2f}"))
    for key, label in (("emitters", "Particle emitters"), ("particleBudget", "Estimated particles"),
                       ("animators", "Animation controllers"), ("holograms", "Holograms"),
                       ("animatedMaterials", "Animated materials"), ("glow", "Glow materials"),
                       ("blended", "Blended materials"), ("lights", "Scene lights"),
                       ("volumetricLights", "Lights with volumetrics"),
                       ("refractiveMaterials", "Refractive materials"),
                       ("reflectiveMaterials", "Screen-space reflection materials")):
        if fx.get(key):
            output.append(f"{label}   {fx[key]}")
    output += [f"Peak scene   {size(row['maxRoot'])}",
               f"All scenes   {size(row['total'])} · {row['fileCount']} files"]
    for label, key in (("Textures", "Texture"), ("Geometry", "Geometry"), ("Animations", "Animation")):
        output.append(f"{label}   {size(row[key])} · {row[key+'Count']} files")
    output += [f"Exclusive to this ID   {size(row['exclusive'])}",
               f"Materials   {row['materials']}     FX scenes   {row['effects']}"]
    if row.get("active") is not None:
        output.append(f"Game frame cost (active 0)   {row['active']:.4g}")
    if row["gaps"] or row["mapping"] == "Inferred scene":
        output.append("Partial coverage" if row["gaps"] else "Inferred scene mapping")
    output.append("Visible copies can repeat effects and share asset files.")
    return tuple(output)


@lru_cache(maxsize=4096)
def fill_fraction(part):
    entry = band(record(part))
    return (BANDS.index(entry) + 1) / len(BANDS) if entry != UNKNOWN else 1.0


def meter_bounds(x, y, width, scale):
    return (x+6*scale, y, max(1, width-12*scale), 11*scale)


def draw_meter(x, y, width, height, scale, part):
    from .curve_widgets import rounded
    baseline = y + 3*scale
    rounded(None, x, baseline, width, 3*scale, 0, (.55, .55, .55, .32))
    rounded(None, x, baseline, width*fill_fraction(part), 3*scale, 0, rgba(part))


def draw_key(x, y, width, scale, ink):
    """One-line key; the compact version fits a narrow sidebar."""
    import blf
    from .curve_widgets import rounded, text
    size = 10*scale
    blf.size(0, size)
    start = x
    right = x + width
    prefix, low, high, unknown = map(i18n.interface, (TITLE, "Low", "High", "Unknown"))
    def label_width(label):
        return blf.dimensions(0, label)[0]
    spectrum = len(BANDS)*7*scale
    if label_width(prefix)+label_width(low)+label_width(high)+spectrum+18*scale > width:
        prefix = i18n.interface("NMS impact")
    if label_width(prefix)+spectrum+5*scale > width:
        return None
    text(prefix, x, y, size, ink)
    x += label_width(prefix)+6*scale
    show_ends = x + label_width(low)+label_width(high)+spectrum+10*scale <= right
    if show_ends:
        text(low, x, y, size, ink)
        x += label_width(low)+4*scale
    for _, _, colour in BANDS:
        rounded(None, x, y+scale, 6*scale, 4*scale, 0, hex_rgba(colour))
        x += 7*scale
    if show_ends:
        text(high, x+2*scale, y, size, ink)
        x += label_width(high)+4*scale
    if x+17*scale+label_width(unknown) <= right:
        rounded(None, x+6*scale, y+scale, 8*scale, 4*scale, 0, hex_rgba(UNKNOWN[2]))
        text(unknown, x+17*scale, y, size, ink)
        x += 17*scale+label_width(unknown)
    return (start, y-3*scale, x-start, 16*scale)
