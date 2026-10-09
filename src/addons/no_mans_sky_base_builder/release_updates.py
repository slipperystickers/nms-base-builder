"""Shared Blender UI; loaded as a private module by each add-on."""
import json
import os
import platform
from pathlib import Path
import bpy
from bpy.props import StringProperty
from .furby_updates import ProcessUpdateClient as UpdateClient

_classes=[]
_client=None
_reporter=None
_restore_errors=None

def start(action='check'):
    if not getattr(bpy.app,'online_access',True):
        _client.message='Allow online access in Blender Preferences to check or download updates.'
        return
    _client.start(action)

def register(product, installed, category):
    global _client, _reporter, _restore_errors
    from .furby_errors import ErrorReporter, guard_blender
    _reporter=ErrorReporter(product,installed,platform.system()+" / Blender "+bpy.app.version_string)
    _client=UpdateClient(product,installed)
    prefix='furby_'+product
    class Check(bpy.types.Operator):
        bl_idname=prefix+'.check_updates';bl_label='Check for updates'
        def execute(self, context):
            start();return {'FINISHED'}
    class Download(bpy.types.Operator):
        bl_idname=prefix+'.download_update';bl_label='Download verified ZIP'
        def execute(self, context):
            start('download');return {'FINISHED'}
    class Auto(bpy.types.Operator):
        bl_idname=prefix+'.auto_updates';bl_label='Check for updates on startup'
        def execute(self, context):
            _client.set_auto(not _client.settings.get('auto_check',True))
            if getattr(bpy.app,'online_access',True):_client.maybe_check()
            return {'FINISHED'}
    class Folder(bpy.types.Operator):
        bl_idname=prefix+'.download_folder';bl_label='Open downloads folder'
        def execute(self, context):
            folder=Path.home()/'Downloads/Furby App Updates';folder.mkdir(parents=True,exist_ok=True)
            bpy.ops.wm.path_open(filepath=str(folder));return {'FINISHED'}
    class Report(bpy.types.Operator):
        bl_idname=prefix+'.support_report';bl_label='Save a support report'
        description: StringProperty(name='What went wrong?',description='Describe the error and the steps to reproduce it',maxlen=12000)
        def invoke(self,context,event):
            return context.window_manager.invoke_props_dialog(self,width=500)
        def draw(self,context):
            self.layout.prop(self,'description')
            self.layout.label(text='Saves a local file for you to review. Nothing is sent.')
        def execute(self,context):
            import datetime
            folder=Path.home()/'Downloads/Furby Support Reports';folder.mkdir(parents=True,exist_ok=True)
            now=datetime.datetime.now(datetime.timezone.utc)
            path=folder/(product+'-'+now.strftime('%Y%m%d-%H%M%S-%f')+'.json')
            path.write_text(json.dumps(dict(app=product,version=installed,blender=bpy.app.version_string,
                platform=platform.system(),python=platform.python_version(),createdUtc=now.isoformat(),
                description=self.description),indent=2),encoding='utf-8')
            self.report({'INFO'},'Support report saved to Downloads/Furby Support Reports')
            return {'FINISHED'}
    class Email(bpy.types.Operator):
        bl_idname=prefix+'.email_support';bl_label='Private support conversation'
        def execute(self,context):
            from urllib.parse import urlencode
            query=urlencode(dict(kind='conversation',app=product,version=installed,environment=platform.system()+' / Blender '+bpy.app.version_string))
            bpy.ops.wm.url_open(url='https://furiousfurby.com/support/?'+query)
            return {'FINISHED'}
    class Online(bpy.types.Operator):
        bl_idname=prefix+'.online_support';bl_label='Report an issue online'
        def execute(self,context):
            from urllib.parse import urlencode
            query=urlencode(dict(app=product,version=installed,environment=platform.system()+' / Blender '+bpy.app.version_string))
            bpy.ops.wm.url_open(url='https://furiousfurby.com/support/?'+query)
            return {'FINISHED'}
    class ErrorPrompt(bpy.types.Operator):
        bl_idname=prefix+'.error_report_prompt';bl_label='Send an error report?'
        payload_json: StringProperty(options={'HIDDEN'})
        def invoke(self,context,event):
            self.payload_json=json.dumps(_reporter.latest or {})
            return context.window_manager.invoke_props_dialog(self,width=540)
        def draw(self,context):
            import textwrap
            for line in textwrap.wrap(json.loads(self.payload_json or '{}').get('title','An app error occurred'),60):self.layout.label(text=line)
            self.layout.label(text='Open a report to review and attach screenshots or videos.')
            self.layout.label(text='Choose Discord or anonymous reporting on the website.')
            self.layout.label(text='Nothing is uploaded until you select Send report there.')
        def execute(self,context):
            payload=json.loads(self.payload_json or '{}')
            if payload:
                _reporter.save(payload)
                bpy.ops.wm.url_open(url=_reporter.url(payload))
            return {'FINISHED'}
    class Panel(bpy.types.Panel):
        bl_idname=prefix.upper()+'_PT_updates';bl_label='Updates & Support'
        bl_space_type='VIEW_3D';bl_region_type='UI';bl_category=category;bl_options={'DEFAULT_CLOSED'}
        def draw_header(self,context):
            self.layout.label(text='', icon='COLLECTION_COLOR_05')
        def draw(self,context):
            layout=self.layout
            layout.label(text='Installed: '+installed)
            import textwrap
            for line in textwrap.wrap(_client.message,40):layout.label(text=line)
            row=layout.row();row.enabled=not _client.busy
            row.operator(Check.bl_idname,text='Check now',icon='FILE_REFRESH')
            row=layout.row();row.enabled=not _client.busy and bool((_client.result or {}).get('available'))
            row.operator(Download.bl_idname,icon='IMPORT')
            layout.operator(Auto.bl_idname,text='Check on startup',icon='CHECKBOX_HLT' if _client.settings.get('auto_check') else 'CHECKBOX_DEHLT')
            layout.operator(Folder.bl_idname,icon='FILE_FOLDER')
            layout.label(text='Install ZIP after saving and restarting Blender.')
            layout.separator();layout.operator(Report.bl_idname,icon='TEXT')
            layout.operator(Online.bl_idname,icon='URL')
            layout.operator(Email.bl_idname,icon='URL')
            layout.label(text='Support@furiousfurby.com')
    for kind,cls in [('OT_check',Check),('OT_download',Download),('OT_auto',Auto),('OT_folder',Folder),('OT_report',Report),('OT_online',Online),('OT_email',Email),('OT_error_prompt',ErrorPrompt),('PT_updates',Panel)]:
        cls.__name__=prefix.upper()+'_'+kind
        bpy.utils.register_class(cls);_classes.append(cls)
    _restore_errors=guard_blender(_reporter,__package__)
    if getattr(bpy.app,'online_access',True):_client.maybe_check()
    bpy.app.timers.register(poll,first_interval=.5)

def poll():
    if _client is None:return None
    if _reporter is not None and not bpy.app.background:
        import queue
        try:payload=_reporter.queue.get_nowait()
        except queue.Empty:payload=None
        if payload:
            _reporter.latest=payload
            try:getattr(bpy.ops,'furby_'+_client.product).error_report_prompt('INVOKE_DEFAULT')
            except (AttributeError,RuntimeError):
                # A busy/modal context must not discard the user's prompt.
                _reporter.queue.put(payload)
    before=_client.message
    _client.poll()
    if _client.busy or before!=_client.message:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type=='VIEW_3D':area.tag_redraw()
    return .5 if _client.busy else 2.0

def unregister():
    global _client, _reporter, _restore_errors
    if _restore_errors:_restore_errors();_restore_errors=None
    _reporter=None
    if _client is not None:_client.close();_client=None
    if bpy.app.timers.is_registered(poll):bpy.app.timers.unregister(poll)
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
