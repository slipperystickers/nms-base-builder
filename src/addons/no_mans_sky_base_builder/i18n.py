"""Offline interface and part-name translations for this extension."""
from functools import lru_cache
import json
from pathlib import Path
import textwrap
import unicodedata

_FOLDER = Path(__file__).with_name("locales")
CONTEXT = "BBEExtendedInterface"
LANGUAGES = (
    ("AUTO", "Follow Blender", ""),
    ("en_US", "English", ""),
    ("it_IT", "Italiano", ""),
    ("zh_HANS", "简体中文", ""),
    ("zh_HANT", "繁體中文", ""),
    ("fil_PH", "Filipino (Tagalog)", ""),
)
_registered_choice = None


@lru_cache(maxsize=1)
def catalogues():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(_FOLDER.glob("*.json"))}


def locale_key(locale):
    tag = (locale or "").replace("-", "_").lower().split(".")[0]
    primary, *subtags = tag.split("_")
    if primary == "zh":
        return "zh_HANT" if any(s in {"hant", "tw", "hk", "mo"} for s in subtags) else "zh_HANS"
    return {"it": "it_IT", "tl": "fil_PH", "fil": "fil_PH"}.get(primary, "")


def for_locale(locale, message):
    return catalogues().get(locale_key(locale), {}).get(message, message)


def choice():
    import bpy
    prefs = getattr(bpy.context, "preferences", None)
    addon = prefs.addons.get(__package__) if prefs else None
    return getattr(getattr(addon, "preferences", None), "bbe_language", "AUTO")


def interface_locale():
    import bpy
    selected = choice()
    if selected != "AUTO":
        return selected
    return bpy.app.translations.locale if bpy.context.preferences.view.use_translate_interface else ""


def interface(message):
    return for_locale(interface_locale(), message)


def tooltip(message):
    import bpy
    if not bpy.context.preferences.view.use_translate_tooltips:
        return message
    selected = choice()
    return for_locale(bpy.app.translations.locale if selected == "AUTO" else selected, message)


def wrapped(message, width):
    translated = interface(message)
    if locale_key(interface_locale()) not in {"zh_HANS", "zh_HANT"}:
        return textwrap.wrap(translated, width=width)
    # Chinese usually has no spaces between words. Budget two columns for full-width glyphs.
    lines, line, used = [], "", 0
    for char in translated:
        size = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        if char == "\n" or used + size > width:
            lines.append(line.rstrip())
            line, used = "", 0
        if char != "\n":
            line += char
            used += size
    if line:
        lines.append(line.rstrip())
    return lines


@lru_cache(maxsize=8)
def _part_names(tag):
    path = _FOLDER / "parts" / (tag + ".json")
    if not tag or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {part: name.capitalize() if name.isupper() else name for part, name in data.items()}


def part_names():
    return _part_names(locale_key(interface_locale()))


def language_changed(self, context):
    _refresh()
    wm = getattr(context, "window_manager", None)
    for window in wm.windows if wm else ():
        for area in window.screen.areas:
            area.tag_redraw()


def language_property():
    import bpy
    return bpy.props.EnumProperty(name="Language", items=LANGUAGES, default="AUTO",
                                  translation_context=CONTEXT, update=language_changed)


class _Layout:
    """Translate extension controls when the user chooses an explicit interface language."""
    def __init__(self, layout, catalogue):
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_catalogue", catalogue)

    def __setattr__(self, key, value):
        setattr(self._layout, key, value)

    def __getattr__(self, name):
        original = getattr(self._layout, name)
        if name in {"row", "column", "column_flow", "grid_flow", "split", "box", "menu_pie"}:
            return lambda *a, **kw: _Layout(original(*a, **kw), self._catalogue)
        if name not in {"label", "operator", "operator_menu_enum", "operator_enum", "menu", "popover",
                        "prop", "prop_enum", "prop_search", "prop_menu_enum", "prop_tabs_enum"}:
            return original

        def draw(*args, **kwargs):
            if kwargs.get("translate") is False:
                return original(*args, **kwargs)
            text = kwargs.get("text")
            if text is None and args and name in {"operator", "operator_menu_enum"}:
                import bpy
                module, _, key = args[0].partition(".")
                if key:
                    try:
                        text = getattr(getattr(bpy.ops, module), key).get_rna_type().name
                    except (AttributeError, RuntimeError, KeyError):
                        pass
            if text is None and len(args) >= 2 and name in {"prop", "prop_search", "prop_menu_enum"}:
                prop = getattr(getattr(args[0], "bl_rna", None), "properties", {}).get(args[1])
                if prop:
                    text = prop.name
            if text is not None and name != "operator_enum":
                kwargs["text"] = self._catalogue.get(text, text)
                kwargs["translate"] = False
            return original(*args, **kwargs)
        return draw


def localized_layout(layout):
    selected = choice()
    if isinstance(layout, _Layout):
        return layout
    if selected == "AUTO":
        # Native UILayout follows Blender. GPU menu trees draw their own captions.
        if not getattr(type(layout), "bbe_translates_text", False):
            return layout
        selected = locale_key(interface_locale())
        if not selected:
            return layout
    return _Layout(layout, catalogues().get(selected, {}))


def _refresh():
    import bpy
    global _registered_choice
    selected = choice()
    if selected == _registered_choice:
        return
    t = bpy.app.translations
    if _registered_choice is not None:
        t.unregister(__package__)
    tags = set(t.locales) | set(catalogues())
    by_language = {}
    # Regional aliases use identical dictionaries, including unsupported locales.
    for language in {locale_key(tag) for tag in tags}:
        automatic = catalogues().get(language, {})
        # Only the extension's private context follows its override.
        entries = {(ctx, key): val for ctx in (t.contexts.default, t.contexts.operator_default, __package__)
                   for key, val in automatic.items()}
        scoped = automatic if selected == "AUTO" else catalogues().get(selected, {})
        if selected == "en_US":
            scoped = {source: source for source in automatic}
        entries.update({(CONTEXT, key): val for key, val in scoped.items()})
        by_language[language] = entries
    t.register(__package__, {tag: by_language[locale_key(tag)] for tag in tags})
    _registered_choice = selected


def register():
    import bpy
    _refresh()
    if not bpy.app.timers.is_registered(_refresh):
        bpy.app.timers.register(_refresh, first_interval=0.1)


def unregister():
    import bpy
    global _registered_choice
    if bpy.app.timers.is_registered(_refresh):
        bpy.app.timers.unregister(_refresh)
    if _registered_choice is not None:
        bpy.app.translations.unregister(__package__)
    _registered_choice = None
    catalogues.cache_clear()
    _part_names.cache_clear()
