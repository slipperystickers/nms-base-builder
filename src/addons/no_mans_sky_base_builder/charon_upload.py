"""Launch Charon with a snapshot of the build currently loaded into Blender."""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile

import bpy

_upload = None


class UploadToCharon(bpy.types.Operator):
    bl_idname = 'bbe.upload_to_charon'
    bl_label = 'Upload to Charon'
    bl_description = 'Attach the current ship or base and finish its listing on Charon'

    @classmethod
    def poll(cls, context):
        if not bpy.app.online_access:
            cls.poll_message_set('Enable Allow Online Access in Blender Preferences')
            return False
        return os.name == 'nt' and context.scene is not None

    def execute(self, context):
        global _upload
        if _upload and _upload.poll() is None:
            self.report({'INFO'}, 'An Upload to Charon window is already open')
            return {'CANCELLED'}
        scene = context.scene
        ship = scene.nms_base_tool.string_base_type == 'PlayerShipBase'
        kind = 'ship' if ship else 'base'
        name = scene.nms_base_tool.string_base.strip() or Path(bpy.data.filepath).stem or kind.title()
        folder = tempfile.TemporaryDirectory(prefix='bbe-charon-')
        path = Path(folder.name) / ('build.nmsship' if ship else 'build.json')
        warnings = []
        try:
            if ship:
                selected = scene.nms_save_data.get_current_base_identifiers()
                use_save = bool(scene.get('bbe_build_source_suffix') != '.nmsship' and selected
                                and selected.base_type == 'PlayerShipBase' and type(selected.user_data) is int
                                and 0 <= selected.user_data < 12)
                count = scene.nms_main.export_ship_file(str(path), '', use_save, warnings)
            else:
                count, _ = scene.nms_main.export_base_file(str(path))
            if not count:
                raise ValueError('The current build contains no parts')
            if path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError('The build exceeds the 8 MB file limit')
            get_window = ctypes.windll.user32.GetActiveWindow
            get_window.restype = ctypes.c_void_p
            helper = Path(__file__).with_name('charon') / 'CharonUpload.exe'
            process = subprocess.Popen([str(helper), str(path), name, str(os.getpid()), str(get_window() or 0)])
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            folder.cleanup()
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        _upload = process

        def cleanup():
            if process.poll() is None:
                return 1.0
            folder.cleanup()
            return None

        bpy.app.timers.register(cleanup, first_interval=1.0, persistent=True)
        if warnings:
            self.report({'WARNING'}, ' '.join(warnings))
        return {'FINISHED'}

