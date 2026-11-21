"""Workspace readouts for the active 3D viewport."""
import re

import blf
import bpy
from bpy.app.handlers import persistent

from . import part_counts, undo_guard
from .utils import dictionary

draw_handler = None


def object_details(obj):
    if obj is None or not obj.select_get():
        return {}
    if obj.get('bbe_shape_controller'):
        part_id = obj.bbe_shape.part_id
        rows = {'Shape': obj.name, 'Part ID': part_id}
    elif 'ObjectID' in obj:
        part_id = obj['ObjectID']
        rows = {'Part ID': part_id}
    else:
        return {}
    name = dictionary.get_nice_names_diictionary().get(part_id)
    if name:
        rows['Part Name'] = ''.join(s if s.startswith('(') else s.title()
                                    for s in re.split(r'(\([^)]*\))', name))
    for label in ('Colour', 'Material'):
        value = obj.get('readonly:' + label)
        if value:
            rows[label] = value
    return rows


def sections(context, prefs):
    if prefs.nms_check_show_part_count:
        base = context.scene.nms_base_tool
        rows = {}
        if base.string_base and base.string_address:
            rows['Name'] = base.string_base
        rows['Part Count'] = part_counts.displayed(context.scene)
        yield prefs.nms_part_count_position, ('' if 'Name' in rows else 'No Base/Corvette imported'), rows
    if prefs.nms_check_show_active_object_properties:
        rows = object_details(context.active_object)
        if rows:
            yield prefs.nms_active_object_properties_position, 'Active Object Properties', rows


def studio_obstacles(context):
    from . import asset_strip, curve_tools, shape_studio
    obstacles = []
    strip = asset_strip._states.get(asset_strip.key(context))
    if strip and strip.get('enabled') and strip.get('bounds') and asset_strip.visible(context):
        obstacles.append(strip['bounds'])
    space = context.space_data
    if space.show_gizmo and space.show_gizmo_context:
        root = shape_studio.valid_root(context)
        if root:
            obstacles.append(shape_studio.rect(context, root)[:4])
        elif context.active_object and curve_tools.BBE_GGT_curve_controls.poll(context):
            obstacles.append(curve_tools.card_rect(context))
    return obstacles


def place_block(left, right, low, high, w, h, top, obstacles, pad):
    # Prefer the requested corner. Try alongside or below a card before using
    # an obstructed position, including when a sidebar narrows the viewport.
    xmax, ymax = max(left, right-w), max(low, high-h)
    xs = [left] + [max(left, min(xmax, x+ow+pad)) for x,y,ow,oh in obstacles]
    ys = [ymax if top else low]
    for x,y,ow,oh in obstacles:
        ys.extend((max(low, min(ymax, y-h-pad)), max(low, min(ymax, y+oh+pad))))
    def cost(pos):
        x,y = pos
        covered = sum(max(0,min(x+w,ox+ow+pad)-max(x,ox-pad)) *
                      max(0,min(y+h,oy+oh+pad)-max(y,oy-pad)) for ox,oy,ow,oh in obstacles)
        return covered, abs(y-ys[0]), x-left
    return min(((x,y) for x in xs for y in ys), key=cost)


def draw_callback_px():
    ctx = bpy.context
    addon = ctx.preferences.addons.get(__package__)
    if not addon or not undo_guard.history_ready():
        return
    blocks = list(sections(ctx, addon.preferences))
    if not blocks:
        return
    region, scale = ctx.region, ctx.preferences.system.ui_scale
    pad, line = 8*scale, 15*scale
    left, right = pad, region.width-pad
    low, high = 20*scale, region.height-88*scale
    for side in ctx.area.regions:
        if side.width<=1 or side.height<=1:
            continue
        if side.type=='TOOLS' and ctx.space_data.show_region_toolbar:
            left=max(left, side.x+side.width-region.x+pad)
        elif side.type=='UI' and ctx.space_data.show_region_ui:
            right=min(right, side.x-region.x-pad)
        elif side.type in {'ASSET_SHELF','ASSET_SHELF_HEADER','HEADER','TOOL_HEADER'}:
            y=side.y-region.y
            if y<region.height/2:low=max(low,y+side.height+pad)
            else:high=min(high,y-68*scale)
    obstacles = studio_obstacles(ctx)
    font=0
    blf.size(font,11*scale)
    blf.color(font,1,1,1,1)
    blf.enable(font,blf.SHADOW)
    try:
        blf.shadow(font,3,0,0,0,1)
        blf.shadow_offset(font,0,-1)
        for position in ('Top','Bottom'):
            tables=[(title,rows) for anchor,title,rows in blocks if anchor==position]
            if not tables:continue
            key_w=max(blf.dimensions(font,k+' |')[0] for _,rows in tables for k in rows)
            val_w=max(blf.dimensions(font,str(v))[0] for _,rows in tables for v in rows.values())
            w=max(key_w+pad+val_w,max(blf.dimensions(font,title)[0] for title,_ in tables))
            h=line*sum(len(rows)+bool(title) for title,rows in tables)+pad*(len(tables)-1)
            x,y=place_block(left,right,low,high,w,h,position=='Top',obstacles,pad)
            obstacles.append((x,y,w,h))
            baseline=y+3*scale
            for title,rows in (reversed(tables) if position=='Top' else tables):
                for k,v in reversed(rows.items()):
                    label=k+' |'
                    blf.position(font,x+key_w-blf.dimensions(font,label)[0],baseline,0)
                    blf.draw(font,label)
                    blf.position(font,x+key_w+pad,baseline,0)
                    blf.draw(font,str(v))
                    baseline+=line
                if title:
                    blf.position(font,x,baseline,0)
                    blf.draw(font,title)
                    baseline+=line
                baseline+=pad
    finally:
        blf.disable(font,blf.SHADOW)


@persistent
def bind_draw(*_):
    global draw_handler
    if draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler,'WINDOW')
    draw_handler=bpy.types.SpaceView3D.draw_handler_add(draw_callback_px,(),'WINDOW','POST_PIXEL')


def register_draw():
    bind_draw()
    if bind_draw not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(bind_draw)


def unregister_draw():
    global draw_handler
    if bind_draw in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(bind_draw)
    if draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler,'WINDOW')
        draw_handler=None
