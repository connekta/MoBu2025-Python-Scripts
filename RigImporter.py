import json
import os
import subprocess
import base64
from pyfbsdk import *
from pyfbsdk_additions import *

# Try to import PySide6 for MotionBuilder 2025
try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    # Try PySide2 next
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
    except ImportError:
        # Fall back to PySide for older versions
        from PySide import QtGui, QtCore
        QtWidgets = QtGui

def get_motionbuilder_main_window():
    """Find the main MotionBuilder window/QWidget."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        try:
            from PySide2.QtWidgets import QApplication
        except ImportError:
            from PySide.QtGui import QApplication
    
    top_level_windows = QApplication.topLevelWidgets()
    
    # Look for the MotionBuilder main window
    for w in top_level_windows:
        if (hasattr(w, 'windowTitle') and 
            'MotionBuilder' in w.windowTitle() and
            w.parentWidget() is None):
            return w
    
    # Fallback: find the largest top-level window
    if top_level_windows:
        main_window = max(top_level_windows, 
                         key=lambda w: w.width() * w.height() if hasattr(w, 'width') else 0)
        return main_window
    
    return None

# Dynamic configuration for any user
DEFAULT_JSON_PATH = os.path.join(os.path.expanduser("~"), "Documents", "MB", "CustomPythonSaveData", "RigReferences.json")

class FBXMergerUI(QtWidgets.QDialog):
    def __init__(self, json_path=None, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(FBXMergerUI, self).__init__(parent)
        
        # Use provided path or default
        self.json_path = json_path if json_path else DEFAULT_JSON_PATH
        
        # Define thumbnails directory
        self.thumbnails_dir = os.path.join(os.path.dirname(self.json_path), "RigFileImages")
        
        # Current group filter
        self.current_group = "All"
        
        # Ensure thumbnails directory exists
        if not os.path.exists(self.thumbnails_dir):
            try:
                os.makedirs(self.thumbnails_dir)
            except Exception as e:
                print(f"Failed to create thumbnails directory: {str(e)}")
        
        self.setWindowTitle("FBX Merger Tool")
        self.setMinimumWidth(450)  # Reduced from 500
        self.setMinimumHeight(400)
        
        # Create main layout
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)
        
        # Add header with folder button and add button
        header_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("Select an FBX file to merge into the current scene:")
        header_layout.addWidget(label)
        
        # Create a button layout for the folder and + buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        # Add folder button
        folder_button = QtWidgets.QPushButton()
        folder_button.setToolTip("Open JSON folder location")
        folder_button.setFixedSize(24, 24)
        folder_button.setText("📁")  # Folder icon as text
        folder_button.clicked.connect(self.open_json_folder)
        button_layout.addWidget(folder_button)
        
        # Add the + button
        self.add_button = QtWidgets.QPushButton()
        self.add_button.setToolTip("Add current file to rig references")
        self.add_button.setFixedSize(24, 24)
        self.add_button.setText("+")  # Plus symbol
        self.add_button.clicked.connect(self.add_current_file)
        button_layout.addWidget(self.add_button)
        
        # Add button layout to header
        header_layout.addLayout(button_layout)
        main_layout.addLayout(header_layout)
        
        # Create the group combo box
        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.setStyleSheet("QComboBox { color: #FFFFFF; }")
        self.group_combo.currentTextChanged.connect(self.on_group_changed)
        
        # Create namespace input field
        namespace_layout = QtWidgets.QHBoxLayout()
        namespace_label = QtWidgets.QLabel("Namespace:")
        namespace_layout.addWidget(namespace_label)
        
        self.namespace_input = QtWidgets.QLineEdit()
        self.namespace_input.setPlaceholderText("Enter namespace (optional)")
        # Make the text brighter
        self.namespace_input.setStyleSheet("QLineEdit { color: #FFFFFF; }")
        namespace_layout.addWidget(self.namespace_input)
        
        main_layout.addLayout(namespace_layout)
        
        # Add group selector under namespace field, centered
        group_layout = QtWidgets.QHBoxLayout()
        group_layout.setContentsMargins(0, 0, 0, 8)  # Add some bottom margin
        
        # Create a spacer to center the combo box
        group_layout.addStretch(1)
        
        group_label = QtWidgets.QLabel("Group:")
        group_layout.addWidget(group_label)
        
        # Add the combo box
        group_layout.addWidget(self.group_combo)
        
        group_layout.addStretch(1)  # Add another spacer for centering
        
        # Add the group selector to the main layout
        main_layout.addLayout(group_layout)
        
        # Add a separator line
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        separator.setMaximumHeight(1)
        main_layout.addWidget(separator)
        
        # Create scrollable area for buttons
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        
        # Create container for buttons
        self.button_container = QtWidgets.QWidget()
        self.button_layout = QtWidgets.QVBoxLayout(self.button_container)
        scroll_area.setWidget(self.button_container)
        
        # Add close button
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.close)
        main_layout.addWidget(close_button)
        
        # Load the JSON file
        if os.path.exists(self.json_path):
            self.load_json_and_create_buttons()
        else:
            # If default JSON doesn't exist, show a message
            self.show_no_json_message()
            
        # Check if the current file is already in the JSON
        self.update_add_button_state()
    
    def open_json_folder(self):
        """Open the folder containing the JSON file"""
        if self.json_path and os.path.exists(os.path.dirname(self.json_path)):
            folder_path = os.path.dirname(self.json_path)
            # Open folder in file explorer (works on Windows)
            try:
                os.startfile(folder_path)
            except AttributeError:
                # For non-Windows platforms
                try:
                    subprocess.Popen(['xdg-open', folder_path])  # Linux
                except:
                    try:
                        subprocess.Popen(['open', folder_path])  # macOS
                    except:
                        QtWidgets.QMessageBox.warning(self, "Warning", "Could not open folder")
        else:
            QtWidgets.QMessageBox.warning(self, "Warning", "JSON file location not found")
    
    def get_current_file_path(self):
        """Get the path of the currently open file in MotionBuilder"""
        app = FBApplication()
        current_file = app.FBXFileName
        
        # If the file is not saved or not an FBX, return None
        if not current_file or not current_file.lower().endswith('.fbx'):
            return None
            
        return current_file
    
    def update_add_button_state(self):
        """Update the state of the add button based on whether the current file is in the JSON"""
        current_file = self.get_current_file_path()
        
        # If no current FBX file, disable the button
        if not current_file:
            self.add_button.setEnabled(False)
            self.add_button.setToolTip("No FBX file currently open")
            return
            
        # Check if the file already exists in the JSON
        try:
            # Ensure JSON directory exists
            json_dir = os.path.dirname(self.json_path)
            if not os.path.exists(json_dir):
                os.makedirs(json_dir)
                
            # Load existing JSON or create empty structure
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                    
                # Check if data is a modernized format or legacy
                if isinstance(data, dict) and 'files' in data:
                    # Modern format with file objects
                    filepaths = [file_obj['path'] for file_obj in data['files']]
                elif isinstance(data, list):
                    # Legacy format (simple list of paths)
                    filepaths = data
                elif isinstance(data, dict) and 'filepaths' in data:
                    # Legacy format (dict with filepaths list)
                    filepaths = data['filepaths']
                else:
                    filepaths = []
            else:
                filepaths = []
                
            # Check if current file is already in the list
            if current_file in filepaths:
                self.add_button.setEnabled(False)
                self.add_button.setToolTip("Current file already in references")
            else:
                self.add_button.setEnabled(True)
                self.add_button.setToolTip("Add current file to rig references")
                
        except Exception as e:
            self.add_button.setEnabled(False)
            self.add_button.setToolTip(f"Error checking JSON: {str(e)}")
    
    def capture_thumbnail(self, filepath):
        """Create a simple thumbnail with the filename"""
        try:
            # Create a unique filename for the thumbnail
            filename = os.path.basename(filepath)
            base_name = os.path.splitext(filename)[0]
            thumbnail_path = os.path.join(self.thumbnails_dir, f"{base_name}.png")
            
            # Create a simple square thumbnail with text
            size = 60  # Square size
            
            # Create a QImage with the filename
            image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
            image.fill(QtGui.QColor(60, 60, 60))
            
            # Draw the filename as text
            painter = QtGui.QPainter(image)
            font = QtGui.QFont()
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QtGui.QColor(255, 255, 255))
            
            # Get character name from filepath for a nicer display
            char_name = base_name.replace("_", " ").title()
            painter.drawText(image.rect(), QtCore.Qt.AlignCenter, char_name)
            
            # End painting
            painter.end()
            
            # Save the image
            image.save(thumbnail_path)
            
            return thumbnail_path
        except Exception as e:
            print(f"Error creating thumbnail: {str(e)}")
            return None
    
    def add_current_file(self):
        """Add the current file to the JSON references with a thumbnail"""
        current_file = self.get_current_file_path()
        
        if not current_file:
            QtWidgets.QMessageBox.warning(self, "Warning", "No FBX file currently open")
            return
            
        try:
            # Ensure JSON directory exists
            os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
                
            # Load existing JSON or create empty structure
            data = {'files': []}
            if os.path.exists(self.json_path):
                try:
                    with open(self.json_path, 'r') as file:
                        data = json.load(file)
                except json.JSONDecodeError:
                    pass  # Use the default empty structure
                
            # Convert legacy formats to new format
            if isinstance(data, list):
                data = {'files': [{'path': path, 'favorite': False, 'thumbnail': None, 'groups': []} for path in data]}
            elif isinstance(data, dict) and 'filepaths' in data:
                data = {'files': [{'path': path, 'favorite': False, 'thumbnail': None, 'groups': []} for path in data['filepaths']]}
            elif not isinstance(data, dict) or 'files' not in data:
                data = {'files': []}
                
            # Check if file already exists
            if current_file not in [file_obj['path'] for file_obj in data['files']]:
                # Capture thumbnail and get filename
                thumbnail_path = self.capture_thumbnail(current_file)
                thumbnail_filename = os.path.basename(thumbnail_path) if thumbnail_path else None
                
                # Add new file object
                data['files'].append({
                    'path': current_file,
                    'favorite': False,
                    'thumbnail': thumbnail_filename,
                    'groups': []
                })
                
                # Save back to the JSON file
                with open(self.json_path, 'w') as file:
                    json.dump(data, file, indent=4)
                
                # Just reload UI without any popups
                self.update_group_combo()
                self.load_json_and_create_buttons()
                
                # Update add button state
                self.update_add_button_state()
            else:
                QtWidgets.QMessageBox.information(self, "Information", 
                    "Current file already exists in references")
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", 
                f"Failed to add file to JSON: {str(e)}")
    
    def show_no_json_message(self):
        """Show a message when no JSON file is found"""
        msg = QtWidgets.QLabel(f"JSON file not found at:\n{self.json_path}\n\nClick the folder icon to access the directory.")
        msg.setAlignment(QtCore.Qt.AlignCenter)
        self.button_layout.addWidget(msg)
    
    def create_fbx_button_widget(self, file_obj):
        """Create a button widget with thumbnail and favorite star for an FBX file"""
        # Create a widget to hold the button, thumbnail, and favorite icon
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 1, 0, 1)  # Reduced vertical margins
        layout.setSpacing(4)  # Reduced spacing between elements
        
        # Create the thumbnail label with hover capability
        class HoverLabel(QtWidgets.QLabel):
            def __init__(self, parent=None):
                super(HoverLabel, self).__init__(parent)
                self.setMouseTracking(True)
                self.popup = None
                self.original_pixmap = None
                
            def enterEvent(self, event):
                if self.original_pixmap:
                    self.showPopup()
                super(HoverLabel, self).enterEvent(event)
                
            def leaveEvent(self, event):
                self.closePopup()
                super(HoverLabel, self).leaveEvent(event)
                
            def showPopup(self):
                if self.popup:
                    return
                    
                self.popup = QtWidgets.QLabel(self.window())
                self.popup.setWindowFlags(QtCore.Qt.ToolTip)
                self.popup.setFrameStyle(QtWidgets.QFrame.StyledPanel)
                
                # Set larger size for popup
                large_size = 150
                self.popup.setFixedSize(large_size, large_size)
                
                # Scale pixmap
                self.popup.setPixmap(self.original_pixmap.scaled(
                    large_size, large_size, 
                    QtCore.Qt.KeepAspectRatio, 
                    QtCore.Qt.SmoothTransformation
                ))
                
                # Position popup near the thumbnail but not under mouse
                pos = self.mapToGlobal(QtCore.QPoint(self.width(), 0))
                self.popup.move(pos)
                
                self.popup.show()
                
            def closePopup(self):
                if self.popup:
                    self.popup.close()
                    self.popup.deleteLater()
                    self.popup = None
        
        # Create hover label with smaller size
        thumbnail_label = HoverLabel()
        thumbnail_label.setFixedSize(48, 48)  # Reduced from 60x60 to 48x48
        thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        thumbnail_label.setStyleSheet("background-color: #333333; border: 1px solid #555555;")
        
        # Load thumbnail if available
        if file_obj.get('thumbnail'):
            thumbnail_path = os.path.join(self.thumbnails_dir, file_obj['thumbnail'])
            if os.path.exists(thumbnail_path):
                pixmap = QtGui.QPixmap(thumbnail_path)
                thumbnail_label.original_pixmap = pixmap
                thumbnail_label.setPixmap(pixmap.scaled(
                    thumbnail_label.width(), 
                    thumbnail_label.height(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                ))
            else:
                thumbnail_label.setText(os.path.basename(file_obj['path'])[:8])  # Show fewer characters
        else:
            thumbnail_label.setText(os.path.basename(file_obj['path'])[:8])  # Show fewer characters
            
        layout.addWidget(thumbnail_label)
        
        # Create the main button with formatted filename
        basename = os.path.basename(file_obj['path'])
        filename_without_ext = os.path.splitext(basename)[0]
        
        # Replace underscores with spaces and capitalize first letter of each word
        formatted_name = ' '.join(word.capitalize() for word in filename_without_ext.split('_'))
        
        # Limit name length if too long
        if len(formatted_name) > 25:
            formatted_name = formatted_name[:22] + "..."
        
        button = QtWidgets.QPushButton(formatted_name)
        button.setToolTip(file_obj['path'])
        button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(
            lambda pos, b=button, p=file_obj['path']: self.show_context_menu(b, p, pos))
        button.clicked.connect(lambda checked=False, path=file_obj['path']: self.merge_fbx(path))
        
        # Set a fixed height for the button to make it more compact
        button.setFixedHeight(32)
        layout.addWidget(button, 1)  # 1 = stretch factor
        
        # Create favorite button
        fav_button = QtWidgets.QPushButton("★" if file_obj.get('favorite', False) else "☆")
        fav_button.setFixedSize(20, 20)  # Reduced from 24x24 to 20x20
        fav_button.setToolTip("Toggle favorite")
        fav_button.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {'gold' if file_obj.get('favorite', False) else 'white'}; }}")
        fav_button.clicked.connect(
            lambda checked=False, path=file_obj['path']: self.toggle_favorite(path))
        
        layout.addWidget(fav_button)
        return widget
    
    def toggle_favorite(self, filepath):
        """Toggle the favorite status of a file in the JSON"""
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                # Ensure we have the modern format
                if not isinstance(data, dict) or 'files' not in data:
                    QtWidgets.QMessageBox.warning(
                        self, 
                        "Warning", 
                        "Cannot toggle favorite: JSON format is not compatible."
                    )
                    return
                
                # Find the file and toggle favorite status
                for file_obj in data['files']:
                    if file_obj['path'] == filepath:
                        file_obj['favorite'] = not file_obj.get('favorite', False)
                        break
                
                # Save the updated data
                with open(self.json_path, 'w') as file:
                    json.dump(data, file, indent=4)
                
                # Reload the buttons to reflect changes
                self.load_json_and_create_buttons()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to toggle favorite status: {str(e)}"
            )
    
    def show_context_menu(self, button, filepath, position):
        """Show the context menu for a rig file button"""
        context_menu = QtWidgets.QMenu()
        
        # Add menu actions
        merge_action = context_menu.addAction("Merge")
        remove_action = context_menu.addAction("Remove from List")
        copy_path_action = context_menu.addAction("Copy Path")
        
        # Add group submenu
        group_menu = context_menu.addMenu("Assign to Group")
        
        # Get all available groups
        groups = self.get_all_groups()
        
        # Add group actions
        group_actions = []
        # First add "None" option to remove from groups
        none_action = group_menu.addAction("None")
        group_actions.append(none_action)
        
        # Add separator
        group_menu.addSeparator()
        
        # Add existing groups
        for group in groups:
            if group != "All":  # Skip "All" as it's a special filter
                action = group_menu.addAction(group)
                group_actions.append(action)
        
        # Add separator and "New Group" option
        group_menu.addSeparator()
        new_group_action = group_menu.addAction("New Group...")
        group_actions.append(new_group_action)
        
        # Create divider
        context_menu.addSeparator()
        
        # Add explore/finder action
        explore_action = context_menu.addAction("Show in Explorer/Finder")
        
        # Show the menu at the cursor position
        action = context_menu.exec_(button.mapToGlobal(position))
        
        # Handle menu actions
        if action == merge_action:
            self.merge_fbx(filepath)
        elif action == remove_action:
            self.remove_file_from_json(filepath)
        elif action == copy_path_action:
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(filepath)
        elif action == explore_action:
            self.show_in_explorer(filepath)
        elif action == new_group_action:
            self.add_to_new_group(filepath)
        elif action == none_action:
            self.remove_from_groups(filepath)
        elif action in group_actions:
            self.add_to_group(filepath, action.text())
    
    def regenerate_thumbnail(self, filepath):
        """Regenerate the thumbnail for a file"""
        try:
            # Only regenerate if the file exists
            if not os.path.exists(filepath):
                QtWidgets.QMessageBox.warning(
                    self, 
                    "Warning", 
                    f"File not found: {filepath}"
                )
                return
            
            # Generate thumbnail
            thumbnail_path = self.capture_thumbnail(filepath)
            
            # Update thumbnail in JSON
            if thumbnail_path and os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                if isinstance(data, dict) and 'files' in data:
                    thumbnail_filename = os.path.basename(thumbnail_path)
                    for file_obj in data['files']:
                        if file_obj['path'] == filepath:
                            file_obj['thumbnail'] = thumbnail_filename
                            break
                    
                    with open(self.json_path, 'w') as file:
                        json.dump(data, file, indent=4)
            
            # Reload buttons
            self.load_json_and_create_buttons()
            
            QtWidgets.QMessageBox.information(
                self, 
                "Success", 
                "Thumbnail regenerated successfully"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to regenerate thumbnail: {str(e)}"
            )
    
    def show_in_explorer(self, filepath):
        """Show the file in Explorer/Finder"""
        if os.path.exists(filepath):
            folder_path = os.path.dirname(filepath)
            try:
                os.startfile(folder_path)
            except AttributeError:
                # For non-Windows platforms
                try:
                    subprocess.Popen(['xdg-open', folder_path])  # Linux
                except:
                    try:
                        subprocess.Popen(['open', folder_path])  # macOS
                    except:
                        QtWidgets.QMessageBox.warning(
                            self, 
                            "Warning", 
                            "Could not open folder"
                        )
        else:
            QtWidgets.QMessageBox.warning(
                self, 
                "Warning", 
                f"File not found: {filepath}"
            )
    
    def remove_file_from_json(self, filepath):
        """Remove a file from the JSON references"""
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                # Handle different JSON formats
                if isinstance(data, dict) and 'files' in data:
                    # Modern format
                    data['files'] = [f for f in data['files'] if f['path'] != filepath]
                elif isinstance(data, list):
                    # Legacy list format
                    data = [f for f in data if f != filepath]
                elif isinstance(data, dict) and 'filepaths' in data:
                    # Legacy dict format
                    data['filepaths'] = [f for f in data['filepaths'] if f != filepath]
                
                # Save updated data
                with open(self.json_path, 'w') as file:
                    json.dump(data, file, indent=4)
                
                # Reload buttons
                self.load_json_and_create_buttons()
                
                # Update add button state
                self.update_add_button_state()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to remove file: {str(e)}"
            )
    
    def load_json_and_create_buttons(self):
        """Load JSON file and create buttons for each filepath, filtered by current group"""
        if not os.path.exists(self.json_path):
            self.show_no_json_message()
            return
            
        try:
            # Clear existing buttons
            for i in reversed(range(self.button_layout.count())):
                widget = self.button_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()
            
            with open(self.json_path, 'r') as file:
                data = json.load(file)
            
            # Convert any format to file objects list
            file_objects = []
            
            if isinstance(data, dict) and 'files' in data:
                file_objects = data['files']
            elif isinstance(data, list):
                file_objects = [{'path': path, 'favorite': False, 'thumbnail': None, 'groups': []} for path in data]
            elif isinstance(data, dict) and 'filepaths' in data:
                file_objects = [{'path': path, 'favorite': False, 'thumbnail': None, 'groups': []} for path in data['filepaths']]
            
            # Update the groups dropdown
            self.update_group_combo()
            
            # Filter files by current group if not "All"
            if self.current_group != "All":
                file_objects = [
                    file_obj for file_obj in file_objects 
                    if 'groups' in file_obj and self.current_group in file_obj['groups']
                ]
            
            # Sort: favorites first, then alphabetically
            sorted_files = sorted(file_objects, 
                key=lambda x: (not x.get('favorite', False), os.path.basename(x['path']).lower()))
            
            # Create a button widget for each file
            buttons_added = False
            for file_obj in sorted_files:
                if 'path' in file_obj and file_obj['path'].lower().endswith('.fbx'):
                    file_exists = os.path.exists(file_obj['path'])
                    button_widget = self.create_fbx_button_widget(file_obj)
                    
                    # Gray out missing files
                    if not file_exists:
                        for i in range(button_widget.layout().count()):
                            item = button_widget.layout().itemAt(i).widget()
                            if isinstance(item, QtWidgets.QPushButton) or isinstance(item, QtWidgets.QLabel):
                                item.setEnabled(False)
                                if isinstance(item, QtWidgets.QPushButton) and not item.text() in ["★", "☆"]:
                                    item.setText(f"{item.text()} (missing)")
                    
                    self.button_layout.addWidget(button_widget)
                    buttons_added = True
            
            # If no buttons were added, show a message
            if not buttons_added:
                if self.current_group != "All":
                    no_fbx_msg = QtWidgets.QLabel(f"No .fbx files found in group '{self.current_group}'")
                else:
                    no_fbx_msg = QtWidgets.QLabel("No .fbx files found in the JSON file")
                no_fbx_msg.setAlignment(QtCore.Qt.AlignCenter)
                self.button_layout.addWidget(no_fbx_msg)
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load JSON file: {str(e)}")
    
    def on_group_changed(self, group_name):
        """Handle when user changes the group selection"""
        self.current_group = group_name
        self.load_json_and_create_buttons()

    def get_all_groups(self):
        """Get all group names from the JSON file"""
        groups = set(["All"])  # Always include "All"
        
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                if isinstance(data, dict) and 'files' in data:
                    for file_obj in data['files']:
                        if 'groups' in file_obj and file_obj['groups']:
                            for group in file_obj['groups']:
                                groups.add(group)
        except Exception as e:
            print(f"Error getting groups: {str(e)}")
            
        return sorted(list(groups))
    
    def update_group_combo(self):
        """Update the group combo box with all available groups"""
        current_text = self.group_combo.currentText()
        
        # Block signals to avoid triggering on_group_changed during update
        self.group_combo.blockSignals(True)
        
        # Clear and repopulate
        self.group_combo.clear()
        for group in self.get_all_groups():
            self.group_combo.addItem(group)
            
        # Try to restore previous selection
        index = self.group_combo.findText(current_text)
        if index >= 0:
            self.group_combo.setCurrentIndex(index)
        else:
            self.group_combo.setCurrentText("All")
            
        self.group_combo.blockSignals(False)
    
    def add_to_new_group(self, filepath):
        """Prompt for a new group name and add the file to it"""
        group_name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add to New Group",
            "Enter group name:"
        )
        
        if ok and group_name:
            self.add_to_group(filepath, group_name)
    
    def add_to_group(self, filepath, group_name):
        """Add a file to a specified group"""
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                if isinstance(data, dict) and 'files' in data:
                    for file_obj in data['files']:
                        if file_obj['path'] == filepath:
                            # Initialize groups array if it doesn't exist
                            if 'groups' not in file_obj:
                                file_obj['groups'] = []
                                
                            # Add to group if not already in it
                            if group_name not in file_obj['groups']:
                                file_obj['groups'].append(group_name)
                            
                            # Save changes
                            with open(self.json_path, 'w') as outfile:
                                json.dump(data, outfile, indent=4)
                            
                            # Update UI
                            self.update_group_combo()
                            self.load_json_and_create_buttons()
                            return
                            
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    f"File not found in references: {filepath}"
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to add to group: {str(e)}"
            )
    
    def remove_from_groups(self, filepath):
        """Remove a file from all groups"""
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                if isinstance(data, dict) and 'files' in data:
                    for file_obj in data['files']:
                        if file_obj['path'] == filepath:
                            # Clear groups
                            file_obj['groups'] = []
                            
                            # Save changes
                            with open(self.json_path, 'w') as outfile:
                                json.dump(data, outfile, indent=4)
                            
                            # Update UI
                            self.update_group_combo()
                            self.load_json_and_create_buttons()
                            return
                
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    f"File not found in references: {filepath}"
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to remove from groups: {str(e)}"
            )
    
    def merge_fbx(self, filepath):
        """Merge the selected FBX file into the current scene with namespace"""
        try:
            if not os.path.exists(filepath):
                QtWidgets.QMessageBox.warning(self, "Warning", f"File not found: {filepath}")
                return
            
            # Get namespace from input
            namespace = self.namespace_input.text().strip()
            
            app = FBApplication()
            
            # Setup options for merge
            merge_options = FBFbxOptions(True)  # True to load from config file
            
            # Set namespace if provided
            if namespace:
                merge_options.NamespaceList = namespace
            
            # Set ALL scene elements to merge
            merge_options.SetAll(FBElementAction.kFBElementActionMerge, True)
            
            # Explicitly set each element to merge
            merge_options.Actors = FBElementAction.kFBElementActionMerge
            merge_options.ActorFaces = FBElementAction.kFBElementActionMerge
            merge_options.Audio = FBElementAction.kFBElementActionMerge
            merge_options.Bones = FBElementAction.kFBElementActionMerge
            merge_options.Cameras = FBElementAction.kFBElementActionMerge
            merge_options.Characters = FBElementAction.kFBElementActionMerge
            merge_options.CharacterFaces = FBElementAction.kFBElementActionMerge
            merge_options.CharacterExtensions = FBElementAction.kFBElementActionMerge
            merge_options.Constraints = FBElementAction.kFBElementActionMerge
            merge_options.Devices = FBElementAction.kFBElementActionMerge
            merge_options.FileReferences = FBElementAction.kFBElementActionMerge
            merge_options.Groups = FBElementAction.kFBElementActionMerge
            merge_options.HUDs = FBElementAction.kFBElementActionMerge
            merge_options.KeyingGroups = FBElementAction.kFBElementActionMerge
            merge_options.Lights = FBElementAction.kFBElementActionMerge
            merge_options.Materials = FBElementAction.kFBElementActionMerge
            merge_options.Models = FBElementAction.kFBElementActionMerge
            merge_options.Notes = FBElementAction.kFBElementActionMerge
            merge_options.OpticalData = FBElementAction.kFBElementActionMerge
            merge_options.Poses = FBElementAction.kFBElementActionMerge
            merge_options.PhysicalProperties = FBElementAction.kFBElementActionMerge
            merge_options.Scripts = FBElementAction.kFBElementActionMerge
            merge_options.Sets = FBElementAction.kFBElementActionMerge
            merge_options.Shaders = FBElementAction.kFBElementActionMerge
            merge_options.Solvers = FBElementAction.kFBElementActionMerge
            merge_options.Story = FBElementAction.kFBElementActionMerge
            merge_options.Textures = FBElementAction.kFBElementActionMerge
            merge_options.Video = FBElementAction.kFBElementActionMerge
            
            # Additional elements
            merge_options.ModelsTakes = FBElementAction.kFBElementActionMerge
            merge_options.Animation = FBElementAction.kFBElementActionMerge
            
            # Keep the camera settings as they are
            merge_options.BaseCameras = FBElementAction.kFBElementActionDiscard
            merge_options.CameraSwitcherSettings = FBElementAction.kFBElementActionDiscard
            merge_options.GlobalLightingSettings = FBElementAction.kFBElementActionDiscard
            merge_options.CurrentCameraSettings = FBElementAction.kFBElementActionDiscard
            
            # Perform the merge without showing UI
            status = app.FileMerge(filepath, False, merge_options)
            
            if status:
                success_msg = f"Successfully merged: {os.path.basename(filepath)}"
                if namespace:
                    success_msg += f" with namespace '{namespace}'"
                QtWidgets.QMessageBox.information(self, "Success", success_msg)
                
                # Refresh the scene
                FBSystem().Scene.Evaluate()
            else:
                QtWidgets.QMessageBox.warning(self, "Warning", f"Failed to merge: {os.path.basename(filepath)}")
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Error merging file: {str(e)}")

def show_fbx_merger_ui(json_path=None):
    """Show the FBX Merger UI"""
    # Close existing UI if it exists
    global fbx_merger_ui
    try:
        fbx_merger_ui.close()
        fbx_merger_ui.deleteLater()
    except:
        pass
    
    # Get the MotionBuilder main window as parent
    mb_parent = get_motionbuilder_main_window()
    
    # Create and show new UI
    fbx_merger_ui = FBXMergerUI(json_path, parent=mb_parent)
    fbx_merger_ui.show()

# Store the UI object reference to prevent garbage collection
fbx_merger_ui = None

# Show the UI when this script is executed
show_fbx_merger_ui()