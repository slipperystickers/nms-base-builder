"""Local, bounded error reports. A browser review is always required to send."""
import datetime
import functools
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import queue
import re
import sys
import traceback
from urllib.parse import quote

def redact(value):
    text=str(value)
    text=re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:access[_-]?token|refresh[_-]?token|password|client[_-]?secret|gateway[_-]?key)\s*["\']?\s*[:=]\s*["\']?)[^\s,"\'\n]+',r'\1[redacted]',text)
    text=re.sub(r'(?i)(https?://[^\s?#]+)[?#][^\s]+',r'\1[private parameters removed]',text)
    text=re.sub(r'(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n"\']+', '[local path]', text)
    text=re.sub(r'(?<![\w:])/(?:home|Users|tmp|var)/[^\r\n"\']+', '[local path]',text)
    text=re.sub(r'\b[^\s<>@]+@[^\s<>@]+\.[a-zA-Z]{2,}\b','[email]',text)
    return text[:10000]

class ErrorReporter:
    def __init__(self,product,version,environment='',directory=None):
        self.product,self.version,self.environment=product,version,environment
        self.directory=Path(directory or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Furby'/'Support Reports'/product)
        self.queue=queue.Queue();self.seen=set();self.latest=None;self.logger=None
    def claim_prompt(self,payload):
        fingerprint=hashlib.sha256((payload['title']+payload['description']).encode()).hexdigest()
        if fingerprint in self.seen or len(self.seen)>=20:return False
        self.seen.add(fingerprint);return True
    def record(self,title,detail,enqueue=True):
        # Reporting must never turn an application error into another exception.
        try:
            payload=dict(app=self.product,version=self.version,title=redact(title)[:160],description=redact(detail),environment=self.environment or platform.system(),createdUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            if self.logger is None:
                self.directory.mkdir(parents=True,exist_ok=True)
                self.logger=logging.Logger('furby-errors-'+self.product)
                self.logger.addHandler(RotatingFileHandler(self.directory/'errors.jsonl',maxBytes=1024*1024,backupCount=2,encoding='utf-8'))
            self.logger.error(json.dumps(payload,ensure_ascii=True))
            self.latest=payload
            if enqueue and self.claim_prompt(payload):self.queue.put(payload)
            return payload
        except Exception:
            return None
    def save(self,payload):
        self.directory.mkdir(parents=True,exist_ok=True)
        target=self.directory/'latest-report.json';target.write_text(json.dumps(payload,indent=2),encoding='utf-8');return target
    @staticmethod
    def url(payload):
        review={**payload,'description':payload.get('description','')[:3500]}
        return 'https://furiousfurby.com/support/#report='+quote(json.dumps(review,ensure_ascii=False,separators=(',',':')))
    def close(self):
        if self.logger:
            for handler in self.logger.handlers:handler.close()

def install_tk(root,dialogs,product,version,detail_hook=None):
    reporter=ErrorReporter(product,version);original=dialogs.showerror
    def prompt(payload):
        if not payload:return
        from tkinter import messagebox
        if messagebox.askyesno('Send an error report?',payload['title']+'\n\nOpen the report for review? You can attach screenshots or videos and choose Discord or anonymous reporting. Nothing is uploaded until you select Send report on the website.',parent=root):
            import webbrowser
            reporter.save(payload);webbrowser.open(reporter.url(payload))
    def showerror(title,detail,*args,**kwargs):
        extra=''
        if detail_hook:
            try:extra=detail_hook(title)
            except Exception:pass
        payload=reporter.record(title,str(detail)+extra,enqueue=False)
        result=original(title,detail,*args,**kwargs)
        if payload and reporter.claim_prompt(payload):prompt(payload)
        return result
    dialogs.showerror=showerror
    def exception(kind,value,tb):
        payload=reporter.record(kind.__name__,''.join(traceback.format_exception(kind,value,tb)),enqueue=False)
        original('Unexpected application error',redact(str(value))+'\nAn error report was saved locally.')
        if payload and reporter.claim_prompt(payload):prompt(payload)
    root.report_callback_exception=exception
    def poll():
        try:payload=reporter.queue.get_nowait()
        except queue.Empty:payload=None
        if payload:prompt(payload)
        root.after(700,poll)
    root.after(700,poll)
    return reporter

def startup_failure(error,product,version,gui=True):
    reporter=ErrorReporter(product,version)
    payload=reporter.record('Application startup failed',''.join(traceback.format_exception(type(error),error,error.__traceback__)))
    try:
        if payload:reporter.save(payload)
        if gui and payload:
            import tkinter as tk
            from tkinter import messagebox
            window=tk.Tk();window.withdraw()
            try:
                if messagebox.askyesno('Send an error report?','The app could not start. A report was saved locally. Open it for review, with screenshot/video attachments and Discord or anonymous reporting? Nothing is sent until you choose Send report on the website.',parent=window):
                    import webbrowser
                    webbrowser.open(reporter.url(payload))
            finally:window.destroy()
    except Exception:pass
    finally:reporter.close()

_active_reporter=None

def report_error(operator,kinds,message):
    if "ERROR" in kinds and _active_reporter is not None:_active_reporter.record(getattr(operator,"bl_label","Add-on error"),message)
    return operator.report(kinds,message)

def guard_blender(reporter,package):
    """Capture only this add-on's operators, including handled ERROR reports."""
    import bpy
    global _active_reporter
    _active_reporter=reporter
    originals=[];seen=set()
    for name,module in list(sys.modules.items()):
        if name!=package and not name.startswith(package+'.'):continue
        for cls in list(vars(module).values()):
            if not isinstance(cls,type) or cls in seen or not cls.__module__.startswith(package):continue
            seen.add(cls)
            try:
                if not issubclass(cls,bpy.types.Operator):continue
            except TypeError:continue
            if cls.__module__.endswith(('release_updates','furby_errors')):continue
            for attribute in ('execute','invoke'):
                if attribute not in cls.__dict__:continue
                original=getattr(cls,attribute)
                def wrap_method(fn,attribute):
                    def call(self,context,*extra):
                        try:return fn(self,context,*extra)
                        except Exception as error:
                            reporter.record(type(error).__name__,traceback.format_exc())
                            self.report({'ERROR'},redact(str(error)))
                            return {'CANCELLED'}
                    if attribute=='invoke':
                        @functools.wraps(fn)
                        def invoke(self,context,event):return call(self,context,event)
                        return invoke
                    @functools.wraps(fn)
                    def execute(self,context):return call(self,context)
                    return execute
                originals.append((cls,attribute,original,True));setattr(cls,attribute,wrap_method(original,attribute))
    def restore():
        global _active_reporter
        _active_reporter=None
        for cls,attribute,value,own in reversed(originals):
            if own:setattr(cls,attribute,value)
            else:delattr(cls,attribute)
        reporter.close()
    return restore
