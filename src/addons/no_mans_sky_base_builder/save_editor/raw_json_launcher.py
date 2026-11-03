"""Open the advanced raw JSON viewer after a save slot is selected."""
from pathlib import Path
import os
import subprocess

import bpy

from . import backup_policy, raw_json_core
from ..furby_errors import report_error


class BBE_OT_raw_save_json(bpy.types.Operator):
    bl_idname = 'bbe.raw_save_json'
    bl_label = 'Advanced Raw Save JSON'
    bl_description = 'Browse and edit the selected Steam save as raw JSON; advanced users only'

    @classmethod
    def poll(cls, context):
        manager = getattr(context.scene, 'nms_save_data', None)
        return bool(manager and manager.get_current_slot_data())

    def execute(self, context):
        try:
            raw_json_core.require_game_closed()
            slot = context.scene.nms_save_data.get_current_slot_data()
            paths = [Path(path).resolve() for path in slot['saves']
                     if path and Path(path).is_file()]
            if not paths:
                raise ValueError('The selected save slot has no readable save point')
            selected = max(paths, key=lambda path: (path.stat().st_mtime_ns, str(path)))
            from .. import bbe_chat
            command = [bbe_chat._python_executable(),
                       str(Path(__file__).with_name('raw_json_window.py')),
                       '--qt-site', bbe_chat._qt_site_packages(),
                       '--save', str(selected),
                       '--parent-pid', str(os.getpid()),
                       '--backup-root', str(backup_policy.root_directory())]
            subprocess.Popen(command, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            self.report({'INFO'}, f'Opening advanced JSON editor for {selected.name}')
            return {'FINISHED'}
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(BBE_OT_raw_save_json)


def unregister():
    bpy.utils.unregister_class(BBE_OT_raw_save_json)
