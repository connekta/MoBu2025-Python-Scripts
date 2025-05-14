import os
import sys
from PySide6 import QtWidgets
from pyfbsdk import FBSystem, FBApplication

# Ensure the script directory is in the path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

# Import the file browser module using the full path to each module
from FileBrowser.file_browser import MotionBuilderFileBrowser

def show_file_browser():
    """Create and show the file browser dialog"""
    # Get main window as parent
    app = QtWidgets.QApplication.instance()
    parent = next((w for w in app.topLevelWidgets() if w.objectName() == "MainWindow"), None)
    
    dialog = MotionBuilderFileBrowser(parent)
    dialog.exec_()

# Show the dialog when script is executed
show_file_browser()