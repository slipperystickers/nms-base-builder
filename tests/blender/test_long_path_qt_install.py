"""Run in an isolated, enabled Windows Blender profile, after installing the release ZIP."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import bpy

name = 'bl_ext.user_default.no_mans_sky_base_builder'
addon = importlib.import_module(name)
runtime = importlib.import_module(name + '.qt_runtime')
chat = importlib.import_module(name + '.bbe_chat')
wheels = runtime.bundled_wheels()
assert wheels.parent.resolve().is_relative_to(Path(os.environ['BLENDER_USER_EXTENSIONS']).resolve())
assert len(os.environ['BLENDER_USER_EXTENSIONS']) >= 105
assert 'PySide6' not in sys.modules
child = """
import pathlib,runpy,sys
wheels=pathlib.Path(sys.argv[1])
sys.path.insert(0,str(wheels.parent))
import qt_runtime
site=qt_runtime.activate(wheels)
from PySide6 import QtWidgets,QtCore,QtNetwork,QtGui
import shiboken6
assert pathlib.Path(QtWidgets.__file__).resolve().parent.parent.samefile(site)
assert pathlib.Path(shiboken6.__file__).resolve().parent.parent.samefile(site)
app=QtWidgets.QApplication([])
window=QtWidgets.QMainWindow()
window.resize(250,170)
assert not window.grab().isNull()
data=runpy.run_path(str(wheels.parent/'bbe_chat_messenger.py'),run_name='bbe_qt_smoke')
assert issubclass(data['Messenger'], QtWidgets.QWidget)
assert (pathlib.Path(site)/'PySide6/qml/QtQuick/Controls/FluentWinUI3/light/images/pageindicatordelegate-indicator-delegate-current-hovered@2x.png').is_file()
"""
with tempfile.TemporaryDirectory(dir=runtime._filesystem_path(tempfile.gettempdir())) as root:
    # A redirected Local AppData path also puts the original offending artwork over 260.
    env = dict(os.environ, LOCALAPPDATA=str(Path(tempfile.gettempdir())/Path(root).name/('redirected-'*8)), QT_QPA_PLATFORM='offscreen')
    args = [chat._python_executable(), '-I', '-c', child, str(wheels)]
    workers = [subprocess.Popen(args, env=env) for _ in range(2)]
    assert [proc.wait(timeout=120) for proc in workers] == [0, 0]
    assert subprocess.run(args, env=env, timeout=30).returncode == 0
    roots = list((Path(env['LOCALAPPDATA'])/'BaseBuilderExtended/qt').iterdir())
    assert len(roots) == 1 and (roots[0]/'.complete').is_file()
print('PASS long extensions path, redirected cache, concurrent first use, cached restart, Qt widget and messenger')
