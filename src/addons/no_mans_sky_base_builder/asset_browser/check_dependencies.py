"""The floating browser uses Qt supplied in the bundled extension wheels."""

def check_dependencies():
    from .. import qt_runtime
    try:
        qt_runtime.activate()
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        print('Install the complete Station Import ZIP through Blender Install from Disk '
              'and restart Blender to load its bundled asset-browser libraries.')
        return False
    return True
