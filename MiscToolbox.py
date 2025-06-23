"""
MotionBuilder Misc Toolbox
This script creates a PySide6 UI that provides easy access to various utility tools.
Tools are loaded dynamically from separate Python files in the MiscToolbox subfolder.

HOW TO USE:
1. Execute this script in MotionBuilder to open the Misc Toolbox window
2. The window will automatically discover and list all available tools from the MiscToolbox folder
3. Click any button to run the corresponding tool (the toolbox will close automatically)

HOW TO ADD NEW TOOLS:
1. Create a new Python file (.py) in the MiscToolbox subfolder
2. Add these required elements to your tool file:
   - DISPLAY_NAME = "Your Tool Name"  # Custom display name with proper capitalization
   - DESCRIPTION = "Brief description"  # Description shown in the UI
   - def run():  # Main function that executes when the tool is launched

EXAMPLE TOOL FILE (MiscToolbox/MyCustomTool.py):
# DISPLAY_NAME = "My Custom Tool"
# DESCRIPTION = "Does something useful with the scene"
# 
# def run():
#     '''Your tool code here'''
#     from pyfbsdk import FBMessageBox
#     FBMessageBox("My Tool", "Hello from my custom tool!", "OK")

The toolbox will automatically discover new tool files and create buttons for them.
No manual UI updates needed - just add files to the MiscToolbox folder!
"""

import sys
import traceback
import inspect
import os
import importlib.util

# Import MotionBuilder Python modules first to check availability
try:
    from pyfbsdk import *
    from pyfbsdk_additions import *
    MOBU_AVAILABLE = True
except ImportError:
    MOBU_AVAILABLE = False

# Import PySide6 modules
try:
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QPushButton, QMessageBox, QLabel, QScrollArea, QWidget,
        QSizePolicy, QFrame, QButtonGroup, QCheckBox, QRadioButton
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont
except ImportError as e:
    raise ImportError("PySide6 is required. Please install it in MotionBuilder's Python environment.") from e


def get_motionbuilder_main_window():
    """
    Find the main MotionBuilder window/QWidget.
    This will be used as the parent for dialogs.
    
    Returns:
        QWidget if found or None if not
    """
    # Get all top level windows
    top_level_windows = QApplication.topLevelWidgets()
    
    # Find the main application window - look specifically for MotionBuilder
    for w in top_level_windows:
        if (hasattr(w, 'windowTitle') and 
            'MotionBuilder' in w.windowTitle() and
            w.parentWidget() is None):
            return w
    
    # If not found by title, try to find the largest top-level widget
    # (usually the main window)
    if top_level_windows:
        main_window = max(top_level_windows, 
                         key=lambda w: w.width() * w.height() if hasattr(w, 'width') else 0)
        return main_window
    
    return None


class MiscToolboxDialog(QDialog):
    """Main dialog for the Misc Toolbox"""
    
    def __init__(self, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(MiscToolboxDialog, self).__init__(parent)
        
        # Set window properties
        self.setWindowTitle("Misc Toolbox - Utility Scripts")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        
        # Window flags - same as Controlify
        if parent:
            # For MotionBuilder, use Dialog flag without Tool or StaysOnTop
            self.setWindowFlags(Qt.Dialog)
        else:
            # Fallback if no parent found
            self.setWindowFlags(Qt.Window)
        
        # Create the main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # Add scrollable tools area
        self.create_tools_area(main_layout)
    
    def create_tools_area(self, main_layout):
        """Create the scrollable tools area"""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameStyle(QFrame.NoFrame)
        
        # Create content widget
        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_widget.setLayout(content_layout)
        
        # Get all available tool functions and sort them alphabetically
        tool_functions = self.get_tool_functions()
        
        if tool_functions:
            for func_name, func_obj in tool_functions:
                self.create_tool_button(content_layout, func_name, func_obj)
        else:
            # Show message when no tools are available
            no_tools_label = QLabel("No tools available yet.\nTools will appear here when added to this script.")
            no_tools_label.setAlignment(Qt.AlignCenter)
            no_tools_label.setStyleSheet("color: #aaaaaa; font-style: italic; padding: 20px;")
            content_layout.addWidget(no_tools_label)
        
        # Add stretch to push everything to the top
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
    
    def create_tool_button(self, layout, func_name, func_obj):
        """Create a button for a tool function"""
        # Extract description from module's DESCRIPTION attribute or docstring
        description = ""
        if hasattr(func_obj, 'DESCRIPTION'):
            description = func_obj.DESCRIPTION
        elif hasattr(func_obj, '__doc__') and func_obj.__doc__:
            # Get first line of docstring as description
            description = func_obj.__doc__.strip().split('\n')[0]
        
        # Create button group
        button_group = QGroupBox()
        button_group.setStyleSheet(self.get_tool_button_group_style())
        
        button_layout = QVBoxLayout()
        button_group.setLayout(button_layout)
        
        # Create the main button
        button = QPushButton(self.format_function_name(func_name))
        button.setStyleSheet(self.get_tool_button_style())
        button.setMinimumHeight(35)
        button.clicked.connect(lambda: self.run_tool(func_name, func_obj))
        button_layout.addWidget(button)
        
        # Add description if available
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #cccccc; font-size: 10px; margin: 2px 4px;")
            button_layout.addWidget(desc_label)
        
        layout.addWidget(button_group)
    
    def get_tool_functions(self):
        """Get all tool functions from MiscToolbox folder, sorted alphabetically"""
        tool_functions = []
        
        # Get the MiscToolbox folder path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        toolbox_dir = os.path.join(script_dir, "MiscToolbox")
        
        if not os.path.exists(toolbox_dir):
            return tool_functions
        
        # Scan for Python files in the MiscToolbox folder
        for filename in os.listdir(toolbox_dir):
            if filename.endswith('.py') and not filename.startswith('_'):
                module_name = filename[:-3]  # Remove .py extension
                module_path = os.path.join(toolbox_dir, filename)
                
                try:
                    # Load the module dynamically
                    spec = importlib.util.spec_from_file_location(module_name, module_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Check if the module has a 'run' function
                    if hasattr(module, 'run') and callable(module.run):
                        # Create a wrapper function name for compatibility
                        func_name = f"tool_{module_name.lower()}"
                        tool_functions.append((func_name, module))
                except Exception as e:
                    # Skip modules that fail to load
                    continue
        
        # Sort alphabetically by function name
        tool_functions.sort(key=lambda x: x[0])
        
        return tool_functions
    
    def format_function_name(self, func_name):
        """Convert function name to readable button text"""
        # For tool modules, check if module has a DISPLAY_NAME attribute
        if func_name.startswith('tool_'):
            module_name = func_name[5:]  # Remove 'tool_' prefix
            
            # Try to get the module from our loaded tools
            for name, module in self.get_tool_functions():
                if name == func_name:
                    if hasattr(module, 'DISPLAY_NAME'):
                        return module.DISPLAY_NAME
                    break
        
        # Default formatting: Remove 'tool_' prefix and convert underscores to spaces
        name = func_name[5:]  # Remove 'tool_' prefix
        name = name.replace('_', ' ')
        # Capitalize each word
        return ' '.join(word.capitalize() for word in name.split())
    
    def run_tool(self, func_name, func_obj):
        """Run a tool function with error handling"""
        try:
            # For tool modules, call the run() function
            if hasattr(func_obj, 'run'):
                func_obj.run()
            else:
                func_obj()
            # Close the toolbox window after running a tool
            self.close()
        except Exception as e:
            QMessageBox.warning(
                self, 
                "Tool Error", 
                f"Error running {self.format_function_name(func_name)}:\n\n{str(e)}"
            )
    
    def get_group_style(self):
        """Get the style for group boxes - same as Controlify"""
        return """
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 3px;
                margin-top: 6px;
                padding-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QGroupBox:hover::title {
                color: #cccccc;
            }
        """
    
    def get_tool_button_group_style(self):
        """Get the style for tool button groups - MotionBuilder themed"""
        return """
            QGroupBox {
                border: 1px solid #555555;
                border-radius: 4px;
                margin: 2px;
                padding: 6px;
                background-color: #404040;
            }
        """
    
    def get_tool_button_style(self):
        """Get the style for tool buttons - MotionBuilder themed"""
        return """
            QPushButton {
                background-color: #606060;
                color: #ffffff;
                border: 1px solid #707070;
                padding: 8px 16px;
                border-radius: 3px;
                font-weight: normal;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #707070;
                border-color: #808080;
            }
            QPushButton:pressed {
                background-color: #505050;
                border-color: #606060;
            }
        """


# =============================================================================
# TOOLS - Tools are now loaded dynamically from the MiscToolbox folder
# =============================================================================

# Tools are loaded from individual Python files in the MiscToolbox subfolder.
# Each tool file should have:
# - DISPLAY_NAME: Custom display name for the tool (preserves capitalization)
# - DESCRIPTION: Brief description of what the tool does  
# - run(): Main function that executes the tool
#
# The toolbox automatically scans the MiscToolbox folder and creates buttons
# for each valid tool file. Tools run independently and can be added/removed
# without modifying this main file.

# =============================================================================
# DIALOG MANAGEMENT
# =============================================================================

def show_dialog():
    """Show the dialog"""
    try:
        dialog = MiscToolboxDialog()
        dialog.show()
        # Store a reference to prevent garbage collection
        global misc_toolbox_dialog
        misc_toolbox_dialog = dialog
    except Exception as e:
        if MOBU_AVAILABLE:
            FBMessageBox("Error", f"Failed to show Misc Toolbox:\n{str(e)}", "OK")
        else:
            pass


# Entry point for MotionBuilder
try:
    show_dialog()
except Exception as e:
    if MOBU_AVAILABLE:
        FBMessageBox("Error", f"Failed to initialize Misc Toolbox:\n{str(e)}", "OK")
    else:
        pass