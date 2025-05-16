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

class ViewportOverlay(QtWidgets.QWidget):
    """Overlay widget to show capture area in viewport"""
    
    def __init__(self, parent=None):
        super(ViewportOverlay, self).__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Draw semi-transparent dark overlay
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 100))
        
        # Calculate square in center horizontally but moved up
        width = self.width()
        height = self.height()
        
        
        # Make capture area 40% of the smaller dimension for more zoom
        square_size = int(min(width, height) * 0.4)
        x = (width - square_size) // 2
        y = max(0, (height - square_size) // 2 - 150)  # Move up 150px
        
        
        # Clear the capture area (make it transparent)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
        painter.fillRect(x, y, square_size, square_size, QtGui.QColor(0, 0, 0, 0))
        
        # Draw border around capture area
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        border_width = 3
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 0), border_width))  # Yellow border
        # Draw inside the actual capture area to show exactly what will be captured
        painter.drawRect(x, y, square_size, square_size)
        
        # Draw corner marks for better visibility
        corner_length = 20
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 0), 4))
        
        # Top-left corner
        painter.drawLine(x, y, x + corner_length, y)
        painter.drawLine(x, y, x, y + corner_length)
        
        # Top-right corner
        painter.drawLine(x + square_size, y, x + square_size - corner_length, y)
        painter.drawLine(x + square_size, y, x + square_size, y + corner_length)
        
        # Bottom-left corner
        painter.drawLine(x, y + square_size, x + corner_length, y + square_size)
        painter.drawLine(x, y + square_size, x, y + square_size - corner_length)
        
        # Bottom-right corner
        painter.drawLine(x + square_size, y + square_size, x + square_size - corner_length, y + square_size)
        painter.drawLine(x + square_size, y + square_size, x + square_size, y + square_size - corner_length)

class ThumbnailPreviewDialog(QtWidgets.QDialog):
    """Minimal dialog with Save/Cancel buttons positioned below the yellow outline"""
    
    def __init__(self, parent=None):
        super(ThumbnailPreviewDialog, self).__init__(parent)
        
        # Store reference to parent window
        self.parent_window = parent
        
        # Set window flags for small toolbar window that stays on top
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)  # Don't steal focus
        self.setWindowModality(QtCore.Qt.NonModal)
        
        # Store the captured image data
        self.captured_pixmap = None
        
        # Minimize parent window if available
        if self.parent_window:
            self.parent_window.showMinimized()
        
        # Create main layout
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)
        main_layout.setContentsMargins(3, 3, 3, 3)
        main_layout.setSpacing(2)
        
        # Create button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(3)
        main_layout.addLayout(button_layout)
        
        # Add save button
        self.save_button = QtWidgets.QPushButton("Save")
        self.save_button.setMaximumHeight(20)
        self.save_button.clicked.connect(self.save_and_close)
        button_layout.addWidget(self.save_button)
        
        # Add cancel button
        cancel_button = QtWidgets.QPushButton("Cancel")
        cancel_button.setMaximumHeight(20)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        # Create spacing slider
        spacing_layout = QtWidgets.QHBoxLayout()
        spacing_layout.setSpacing(2)
        main_layout.addLayout(spacing_layout)
        
        spacing_label = QtWidgets.QLabel("Space:")
        spacing_label.setMinimumWidth(40)
        spacing_layout.addWidget(spacing_label)
        
        self.spacing_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.spacing_slider.setMaximumHeight(18)
        self.spacing_slider.setRange(0, 100)
        self.spacing_slider.setValue(30)  # 30% = 100 units
        self.spacing_slider.valueChanged.connect(self.update_light_positions)
        spacing_layout.addWidget(self.spacing_slider)
        
        self.spacing_value_label = QtWidgets.QLabel("30%")
        self.spacing_value_label.setMinimumWidth(30)
        spacing_layout.addWidget(self.spacing_value_label)
        
        # Create height slider
        height_layout = QtWidgets.QHBoxLayout()
        height_layout.setSpacing(2)
        main_layout.addLayout(height_layout)
        
        height_label = QtWidgets.QLabel("Height:")
        height_label.setMinimumWidth(40)
        height_layout.addWidget(height_label)
        
        self.height_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.height_slider.setMaximumHeight(18)
        self.height_slider.setRange(0, 100)  # 0-100% representing -100 to 300 units
        self.height_slider.setValue(25)  # 25% = 0 units (25% of the 400 unit range)
        self.height_slider.valueChanged.connect(self.update_light_positions)
        height_layout.addWidget(self.height_slider)
        
        self.height_value_label = QtWidgets.QLabel("0")
        self.height_value_label.setMinimumWidth(30)
        height_layout.addWidget(self.height_value_label)
        
        # Set dialog to be compact
        self.setFixedSize(160, 80)
        
        # Create viewport overlay
        self.viewport_overlay = None
        self.create_viewport_overlay()
        
        # Create light rig
        self.lights = []
        self.create_light_rig()
        
        # Ensure window is on top
        self.raise_()
        self.activateWindow()
    
    def position_below_outline(self):
        """Position the dialog directly below the yellow outline"""
        if self.viewport_overlay:
            overlay_rect = self.viewport_overlay.geometry()
            
            # Calculate the yellow outline position and size
            overlay_width = overlay_rect.width()
            overlay_height = overlay_rect.height()
            
            # Same calculations as the overlay's yellow box
            square_size = int(min(overlay_width, overlay_height) * 0.4)
            x = overlay_rect.x() + (overlay_width - square_size) // 2
            y = overlay_rect.y() + max(0, (overlay_height - square_size) // 2 - 150)
            
            # Position dialog centered below the yellow outline with a small gap
            dialog_x = x + (square_size - self.width()) // 2
            dialog_y = y + square_size + 20  # 20px gap below the outline
            
            self.move(dialog_x, dialog_y)
    
    def save_and_close(self):
        """Capture the viewport and save immediately"""
        self.capture_viewport()
        if self.captured_pixmap:
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to capture viewport")
    
    def create_light_rig(self):
        """Create 4 point lights positioned around the scene origin"""
        
        # Create 4 lights: front, back, left, right
        light_positions = [
            ("Front", [0, 0, 100]),    # Front
            ("Back", [0, 0, -100]),    # Back  
            ("Left", [-100, 0, 0]),    # Left
            ("Right", [100, 0, 0])     # Right
        ]
        
        for name, pos in light_positions:
            light = FBLight(f"Thumbnail_{name}_Light")
            light.LightType = FBLightType.kFBLightTypePoint
            light.Intensity = 100.0
            light.Show = True
            
            # Set initial position (30% = 100 units)
            light.Translation = FBVector3d(pos[0], pos[1], pos[2])
            
            self.lights.append(light)
        
        # Update with initial slider values
        self.update_light_positions()
    
    def update_light_positions(self):
        """Update light positions based on slider values"""
        spacing_percent = self.spacing_slider.value()
        height_percent = self.height_slider.value()
        
        # Update labels
        self.spacing_value_label.setText(f"{spacing_percent}%")
        
        # Convert height percentage to actual units (-100 to 300)
        # 0% = -100, 25% = 0, 100% = 300
        height_units = -100 + (height_percent * 4)
        self.height_value_label.setText(f"{int(height_units)}")
        
        # Convert spacing percentage to actual distance
        # 0% = 0 units, 30% = 100 units, 100% = 333.33 units
        spacing_units = spacing_percent * (1000.0 / 30.0) / 10.0  # Scale so 30% = 100 units
        
        # Update light positions
        if len(self.lights) >= 4:
            self.lights[0].Translation = FBVector3d(0, height_units, spacing_units)    # Front
            self.lights[1].Translation = FBVector3d(0, height_units, -spacing_units)   # Back
            self.lights[2].Translation = FBVector3d(-spacing_units, height_units, 0)   # Left
            self.lights[3].Translation = FBVector3d(spacing_units, height_units, 0)    # Right
        
    def create_viewport_overlay(self):
        """Create an overlay on the viewport to show capture area"""
        try:
            mb_window = get_motionbuilder_main_window()
            if mb_window:
                self.viewport_overlay = ViewportOverlay()
                # Position the overlay to cover the main window
                self.viewport_overlay.setGeometry(mb_window.geometry())
                self.viewport_overlay.show()
                
                # Position the dialog below the yellow outline
                self.position_below_outline()
                
                # Ensure the dialog stays on top
                self.raise_()
                self.activateWindow()
                
        except Exception as e:
            pass
    
    def closeEvent(self, event):
        """Clean up overlay and lights when dialog closes"""
        # Restore grid if it was enabled
        if hasattr(self, '_grid_managed') and self._producer_camera and self._grid_was_enabled:
            self._producer_camera.ViewShowGrid = True
        
        # Delete lights
        self.cleanup_lights()
        
        if self.viewport_overlay:
            self.viewport_overlay.close()
            self.viewport_overlay.deleteLater()
        
        # Restore parent window
        if self.parent_window:
            self.parent_window.showNormal()
            self.parent_window.raise_()
            self.parent_window.activateWindow()
        
        super(ThumbnailPreviewDialog, self).closeEvent(event)
    
    def reject(self):
        """Clean up overlay and lights when dialog is cancelled"""
        # Restore grid if it was enabled
        if hasattr(self, '_grid_managed') and self._producer_camera and self._grid_was_enabled:
            self._producer_camera.ViewShowGrid = True
        
        # Delete lights
        self.cleanup_lights()
        
        if self.viewport_overlay:
            self.viewport_overlay.close()
            self.viewport_overlay.deleteLater()
        
        # Restore parent window
        if self.parent_window:
            self.parent_window.showNormal()
            self.parent_window.raise_()
            self.parent_window.activateWindow()
        
        super(ThumbnailPreviewDialog, self).reject()
    
    def cleanup_lights(self):
        """Delete all created lights from the scene"""
        for light in self.lights:
            try:
                light.FBDelete()
            except:
                pass
        self.lights = []
    
    def capture_viewport(self):
        """Capture the current viewport and display preview"""
        try:
                # Use Qt to capture the MotionBuilder viewport
            mb_window = get_motionbuilder_main_window()
            
            if mb_window:
                # Hide overlay temporarily for clean capture
                if self.viewport_overlay:
                    self.viewport_overlay.hide()
                
                # Find Producer Perspective camera and disable grid
                scene = FBSystem().Scene
                grid_was_enabled = False
                producer_camera = None
                
                for camera in scene.Cameras:
                    if "Producer Perspective" in camera.LongName:
                        producer_camera = camera
                        grid_was_enabled = camera.ViewShowGrid
                        if grid_was_enabled:
                            camera.ViewShowGrid = False
                        break
                
                QtCore.QCoreApplication.processEvents()
                QtCore.QThread.msleep(50)  # Small delay for clean capture
                
                # Always capture the entire MotionBuilder window to match overlay
                screen = QtWidgets.QApplication.primaryScreen()
                
                # Get device pixel ratio to handle high DPI displays
                device_pixel_ratio = screen.devicePixelRatio()
                
                # Capture the same area as the overlay covers
                window_rect = mb_window.frameGeometry()
                
                screenshot = screen.grabWindow(
                    0,  # Use desktop window id
                    window_rect.x(),
                    window_rect.y(),
                    window_rect.width(),
                    window_rect.height()
                )
                
                # Show overlay again
                if self.viewport_overlay:
                    self.viewport_overlay.show()
                
                # Restore grid if it was enabled
                if producer_camera and grid_was_enabled:
                    producer_camera.ViewShowGrid = True
                
                # Get device pixel ratio
                device_pixel_ratio = screen.devicePixelRatio()
                
                # Calculate the capture area using screenshot dimensions
                screenshot_width = screenshot.width()
                screenshot_height = screenshot.height()
                
                # These should match the overlay dimensions when scaled
                logical_width = screenshot_width / device_pixel_ratio
                logical_height = screenshot_height / device_pixel_ratio
                
                
                # Use the same calculations as the overlay
                square_size = int(min(screenshot_width, screenshot_height) * 0.4)
                x = (screenshot_width - square_size) // 2
                
                # Scale the 150px offset by device pixel ratio
                y_offset = int(150 * device_pixel_ratio)
                y = max(0, (screenshot_height - square_size) // 2 - y_offset)
                
                
                # Account for the border - scale it too
                border_width = int(3 * device_pixel_ratio)
                x += border_width
                y += border_width
                square_size -= (border_width * 2)
                
                
                # Crop to square
                cropped = screenshot.copy(x, y, square_size, square_size)
                
                # Scale to 512x512
                self.captured_pixmap = cropped.scaled(
                    512, 512,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )
                
                # Debug: verify the pixmap is valid
                if not self.captured_pixmap or self.captured_pixmap.isNull():
                    self.captured_pixmap = None
                    QtWidgets.QMessageBox.warning(self, "Error", "Failed to create valid pixmap")
                
            else:
                self.captured_pixmap = None
                QtWidgets.QMessageBox.warning(self, "Error", "Could not find MotionBuilder window")
                
        except Exception as e:
            self.captured_pixmap = None
            QtWidgets.QMessageBox.critical(self, "Error", f"Error capturing viewport: {str(e)}")
    
    def get_captured_pixmap(self):
        """Return the captured QPixmap object"""
        return self.captured_pixmap

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
        
        # View mode (True = show thumbnails, False = text only)
        self.show_thumbnails = True
        
        # Ensure thumbnails directory exists
        if not os.path.exists(self.thumbnails_dir):
            try:
                os.makedirs(self.thumbnails_dir)
            except Exception as e:
                print(f"Failed to create thumbnails directory: {str(e)}")
        
        self.setWindowTitle("FBX Merger Tool")
        self.setMinimumWidth(450)  # Reduced from 500
        self.setMinimumHeight(400)
        
        # Set initial size to be reasonably tall
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        initial_height = min(screen.height() * 0.8, 800)  # 80% of screen or 800px, whichever is smaller
        self.resize(450, int(initial_height))
        
        # Create main layout
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)
        
        # Add header with folder button and add button
        header_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("Select an FBX file to merge into the current scene:")
        header_layout.addWidget(label)
        
        # Create a button layout for the view mode, folder and + buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        # Add view mode toggle button
        self.view_mode_button = QtWidgets.QPushButton()
        self.view_mode_button.setToolTip("Toggle between thumbnail and text view")
        self.view_mode_button.setFixedSize(24, 24)
        self.view_mode_button.setText("▤")  # Grid icon for thumbnail view
        self.view_mode_button.clicked.connect(self.toggle_view_mode)
        button_layout.addWidget(self.view_mode_button)
        
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
        self.group_combo.currentIndexChanged.connect(self.on_group_changed)
        
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
        
        # Create scrollable area for grid
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        # Make the scroll area non-selectable
        scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        main_layout.addWidget(scroll_area)
        
        # Create container for grid
        self.grid_container = QtWidgets.QWidget()
        self.grid_container.setStyleSheet("QWidget { selection-background-color: transparent; }")
        self.grid_container.setFocusPolicy(QtCore.Qt.NoFocus)
        self.grid_container.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.grid_container.customContextMenuRequested.connect(self.show_empty_area_context_menu)
        self.grid_layout = QtWidgets.QVBoxLayout(self.grid_container)  # Will contain group sections
        self.grid_layout.setSpacing(5)  # Minimal space between groups
        self.grid_layout.setContentsMargins(3, 3, 3, 3)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop)  # Align to top
        scroll_area.setWidget(self.grid_container)
        
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
        """Capture a viewport screenshot as thumbnail"""
        try:
            # Hide grid immediately when starting capture
            scene = FBSystem().Scene
            producer_camera = None
            grid_was_enabled = False
            
            for camera in scene.Cameras:
                if "Producer Perspective" in camera.LongName:
                    producer_camera = camera
                    grid_was_enabled = camera.ViewShowGrid
                    if grid_was_enabled:
                        camera.ViewShowGrid = False
                    break
                    
            # Create a unique filename for the thumbnail
            filename = os.path.basename(filepath)
            base_name = os.path.splitext(filename)[0]
            # Clean up the filename to avoid path issues
            base_name = base_name.replace('\\', '_').replace('/', '_')
            
            # If this is a retake, add a timestamp to avoid conflicts
            if hasattr(self, '_retake_filepath') and self._retake_filepath:
                import time
                timestamp = int(time.time())
                thumbnail_path = os.path.join(self.thumbnails_dir, f"{base_name}_{timestamp}.png")
            else:
                thumbnail_path = os.path.join(self.thumbnails_dir, f"{base_name}.png")
            
            
            # Create and show preview dialog (non-modal)
            self.preview_dialog = ThumbnailPreviewDialog(self)
            self.preview_dialog.thumbnail_path = thumbnail_path  # Store path for later use
            # Store grid state for later restoration
            self.preview_dialog._producer_camera = producer_camera
            self.preview_dialog._grid_was_enabled = grid_was_enabled
            
            # Connect dialog signals
            self.preview_dialog.accepted.connect(
                lambda: self._save_thumbnail(self.preview_dialog)
            )
            self.preview_dialog.rejected.connect(
                lambda: self._cleanup_preview_dialog()
            )
            self.preview_dialog.destroyed.connect(
                lambda: self._cleanup_preview_dialog()
            )
            
            self.preview_dialog.show()  # Use show() instead of exec_()
            
            return None  # Return None for now, actual save happens in _save_thumbnail
            
        except Exception as e:
            # Re-enable grid if error occurs
            if 'producer_camera' in locals() and producer_camera and 'grid_was_enabled' in locals() and grid_was_enabled:
                producer_camera.ViewShowGrid = True
            return None
    
    def _save_thumbnail(self, dialog):
        """Save the thumbnail from the preview dialog"""
        captured_pixmap = dialog.get_captured_pixmap()
        
        if captured_pixmap and hasattr(dialog, 'thumbnail_path'):
            # Save the QPixmap directly
            success = captured_pixmap.save(dialog.thumbnail_path, "PNG")
            if success:
                # Verify the file was actually saved
                if not os.path.exists(dialog.thumbnail_path):
                    QtWidgets.QMessageBox.warning(
                        self, 
                        "Warning", 
                        f"Thumbnail file not saved to: {dialog.thumbnail_path}"
                    )
                    return
                    
                # Check if this is a retake operation
                if hasattr(self, '_retake_filepath') and self._retake_filepath:
                    # Update thumbnail for existing file
                    self._update_existing_thumbnail(self._retake_filepath, dialog.thumbnail_path)
                    self._retake_filepath = None  # Clear the retake flag
                else:
                    # Update the JSON for adding new file
                    self._update_json_thumbnail(dialog.thumbnail_path)
                
                # Reload the UI to show the new thumbnail
                self.load_json_and_create_buttons()
            else:
                QtWidgets.QMessageBox.warning(
                    self, 
                    "Warning", 
                    f"Failed to save thumbnail to: {dialog.thumbnail_path}"
                )
        
        # Clean up the dialog and restore everything
        self._cleanup_preview_dialog()
        
        # Restore the FBX Merger window
        self.showNormal()
        self.raise_()
        self.activateWindow()
    
    def _update_existing_thumbnail(self, filepath, thumbnail_path):
        """Update thumbnail for an existing file"""
        try:
            
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                # Update the files list
                thumbnail_filename = os.path.basename(thumbnail_path)
                
                if isinstance(data, dict) and 'files' in data:
                    for file_obj in data['files']:
                        if file_obj['path'] == filepath:
                            # Delete old thumbnail file if exists
                            if file_obj.get('thumbnail'):
                                old_thumbnail_path = os.path.join(self.thumbnails_dir, file_obj['thumbnail'])
                                if os.path.exists(old_thumbnail_path):
                                    try:
                                        os.remove(old_thumbnail_path)
                                    except:
                                        pass
                            
                            # Update with new thumbnail
                            file_obj['thumbnail'] = thumbnail_filename
                            break
                
                # Save updated data back to JSON
                with open(self.json_path, 'w') as file:
                    json.dump(data, file, indent=4)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to update image: {str(e)}"
            )
    
    def _update_json_thumbnail(self, thumbnail_path):
        """Update JSON with the new thumbnail path"""
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                # Update the files list to add thumbnail to the relevant file
                current_file = self.get_current_file_path()
                thumbnail_filename = os.path.basename(thumbnail_path)
                
                if isinstance(data, dict) and 'files' in data:
                    for file_obj in data['files']:
                        if file_obj['path'] == current_file:
                            file_obj['thumbnail'] = thumbnail_filename
                            break
                
                # Save updated data back to JSON
                with open(self.json_path, 'w') as file:
                    json.dump(data, file, indent=4)
        except Exception as e:
            pass
    
    def _cleanup_preview_dialog(self):
        """Clean up the preview dialog and its overlay"""
        if hasattr(self, 'preview_dialog') and self.preview_dialog:
            try:
                # Restore grid if it was enabled
                if hasattr(self.preview_dialog, '_producer_camera') and self.preview_dialog._producer_camera:
                    if hasattr(self.preview_dialog, '_grid_was_enabled') and self.preview_dialog._grid_was_enabled:
                        self.preview_dialog._producer_camera.ViewShowGrid = True
                
                # Delete all lights created by the dialog
                if hasattr(self.preview_dialog, 'lights'):
                    for light in self.preview_dialog.lights:
                        try:
                            light.FBDelete()
                        except:
                            pass
                
                # Clean up overlay
                if hasattr(self.preview_dialog, 'viewport_overlay') and self.preview_dialog.viewport_overlay:
                    self.preview_dialog.viewport_overlay.close()
                    self.preview_dialog.viewport_overlay.deleteLater()
                    
                # Close dialog
                self.preview_dialog.close()
                self.preview_dialog.deleteLater()
                self.preview_dialog = None
            except Exception as e:
                pass
        
        # Restore the FBX Merger window
        self.showNormal()
        self.raise_()
        self.activateWindow()
    
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
                
                # Reload UI
                self.update_group_combo()
                self.load_json_and_create_buttons()
                
                # Update add button state
                self.update_add_button_state()
                
                # Reload UI without showing success message
            else:
                QtWidgets.QMessageBox.information(self, "Information", 
                    "Current file already exists in references")
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", 
                f"Failed to add file to JSON: {str(e)}")
    
    def clear_widgets(self):
        """Clear all widgets from the grid layout"""
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
    
    def show_no_json_message(self):
        """Display a message when no json files are found"""
        self.clear_widgets()
        label = QtWidgets.QLabel("No FBX reference files found.\n\nPlease use the FileBrowser to create JSON references.")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setStyleSheet("QLabel { color: #888; font-size: 16px; }")
        self.grid_layout.addWidget(label)
    
    def hover_handler(self, obj, event, widget):
        """Handle hover events for thumbnail preview"""
        if event.type() == QtCore.QEvent.Enter and hasattr(obj, 'thumbnail_path') and obj.thumbnail_path:
            # Create preview widget if it doesn't exist
            if not hasattr(self, 'hover_preview') or not self.hover_preview:
                self.hover_preview = QtWidgets.QWidget()
                self.hover_preview.setWindowFlags(QtCore.Qt.ToolTip)
                self.hover_preview.setObjectName("HoverPreview")
                
                # Create layout
                preview_layout = QtWidgets.QVBoxLayout(self.hover_preview)
                preview_layout.setContentsMargins(6, 6, 6, 6)
                preview_layout.setSpacing(4)
                
                # Create image label
                self.hover_image_label = QtWidgets.QLabel()
                self.hover_image_label.setAlignment(QtCore.Qt.AlignCenter)
                self.hover_image_label.setStyleSheet("QLabel { background: black; border: none; }")
                preview_layout.addWidget(self.hover_image_label)
                
                # Create name label
                self.hover_name_label = QtWidgets.QLabel()
                self.hover_name_label.setAlignment(QtCore.Qt.AlignCenter)
                self.hover_name_label.setStyleSheet("QLabel { color: white; font-size: 12px; font-weight: bold; border: none; }")
                preview_layout.addWidget(self.hover_name_label)
                
                # Style the preview widget - only the container has border
                self.hover_preview.setStyleSheet("""
                    #HoverPreview { 
                        border: 2px solid #000000; 
                        background: black; 
                        border-radius: 6px;
                    }
                """)
            
            # Load full size image (or max 512px to match original capture size)
            pixmap = QtGui.QPixmap(obj.thumbnail_path)
            preview_size = min(pixmap.width(), pixmap.height(), 512)
            scaled_pixmap = pixmap.scaled(
                preview_size, preview_size,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            self.hover_image_label.setPixmap(scaled_pixmap)
            
            # Set name from widget's file path
            filepath = widget.file_path
            basename = os.path.basename(filepath)
            filename_without_ext = os.path.splitext(basename)[0]
            formatted_name = filename_without_ext.replace('_', ' ').title()
            self.hover_name_label.setText(formatted_name)
            
            # Adjust widget size to content
            self.hover_preview.adjustSize()
            
            # Position near cursor but ensure it stays on screen
            pos = QtGui.QCursor.pos()
            screen = QtWidgets.QApplication.primaryScreen().geometry()
            widget_size = self.hover_preview.size()
            x = pos.x() + 10
            y = pos.y() + 10
            
            # Adjust position if preview would go off screen
            if x + widget_size.width() + 20 > screen.width():
                x = pos.x() - widget_size.width() - 10
            if y + widget_size.height() + 20 > screen.height():
                y = pos.y() - widget_size.height() - 10
                
            self.hover_preview.move(x, y)
            self.hover_preview.show()
            self.hover_preview.raise_()
            
        elif event.type() == QtCore.QEvent.Leave:
            # Hide hover preview
            if hasattr(self, 'hover_preview') and self.hover_preview:
                self.hover_preview.hide()
        
        return False
    
    def widget_click_handler(self, event, filepath):
        """Handle clicks on the widget"""
        if event.button() == QtCore.Qt.LeftButton:
            self.merge_fbx(filepath)
        # Right click is handled by context menu
    
    def toggle_view_mode(self):
        """Toggle between thumbnail and text-only view"""
        self.show_thumbnails = not self.show_thumbnails
        
        # Update button text
        if self.show_thumbnails:
            self.view_mode_button.setText("▤")  # Grid icon
            self.view_mode_button.setToolTip("Toggle between thumbnail and text view")
        else:
            self.view_mode_button.setText("☰")  # List icon
            self.view_mode_button.setToolTip("Toggle between thumbnail and text view")
        
        # Reload the UI with new view mode
        self.load_json_and_create_buttons()
    
    def create_fbx_text_widget(self, file_obj):
        """Create a text-only widget for list display"""
        widget = QtWidgets.QWidget()
        widget.setCursor(QtCore.Qt.PointingHandCursor)
        widget.file_path = file_obj['path']
        widget.setFixedHeight(24)  # Compact height for text-only
        
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)
        
        # Create favorite indicator
        if file_obj.get('favorite', False):
            favorite_label = QtWidgets.QLabel("★")
            favorite_label.setStyleSheet("QLabel { color: #FFD700; font-size: 12px; }")
            favorite_label.setFixedWidth(15)
            layout.addWidget(favorite_label)
        else:
            # Add empty space for alignment
            spacer = QtWidgets.QLabel("")
            spacer.setFixedWidth(15)
            layout.addWidget(spacer)
        
        # Create name label
        basename = os.path.basename(file_obj['path'])
        filename_without_ext = os.path.splitext(basename)[0]
        formatted_name = filename_without_ext.replace('_', ' ').title()
        
        name_label = QtWidgets.QLabel(formatted_name)
        name_label.setToolTip(file_obj['path'])
        name_label.setStyleSheet("QLabel { color: #FFFFFF; }")
        layout.addWidget(name_label)
        
        # Check if this rig exists in the current scene
        if self.is_rig_in_scene(file_obj['path']):
            status_label = QtWidgets.QLabel("●")
            status_label.setStyleSheet("QLabel { color: #00FF00; font-size: 10px; }")
            status_label.setFixedWidth(15)
            layout.addWidget(status_label)
        
        layout.addStretch()
        
        # Add click and context menu handling
        widget.mousePressEvent = lambda event: self.widget_click_handler(event, file_obj['path'])
        widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(widget, file_obj['path'], pos)
        )
        
        return widget
    
    def create_fbx_thumbnail_widget(self, file_obj):
        """Create a thumbnail widget for grid display"""
        widget = QtWidgets.QWidget()
        widget.setCursor(QtCore.Qt.PointingHandCursor)
        widget.file_path = file_obj['path']  # Store path for context menu
        widget.setFixedSize(70, 80)  # Reduced height for less wasted space
        
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)  # No spacing between elements
        layout.setAlignment(QtCore.Qt.AlignTop)  # Align content to top
        
        # Create a container for the thumbnail with overlay capability
        thumbnail_container = QtWidgets.QWidget()
        thumbnail_container.setFixedSize(60, 60)
        container_layout = QtWidgets.QGridLayout(thumbnail_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Create thumbnail label
        thumbnail_label = QtWidgets.QLabel()
        thumbnail_label.setFixedSize(60, 60)
        thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        thumbnail_label.setScaledContents(True)
        
        # Style the thumbnail with black outline for non-favorites
        if file_obj.get('favorite', False):
            # Yellow border for favorites
            thumbnail_label.setStyleSheet("QLabel { background-color: #333333; border: 2px solid #FFD700; }")
        else:
            # Black outline for regular items
            thumbnail_label.setStyleSheet("QLabel { background-color: #333333; border: 2px solid #000000; }")
        
        # Store thumbnail path for hover
        thumbnail_label.thumbnail_path = None
        
        # Load thumbnail if available
        if file_obj.get('thumbnail'):
            thumbnail_path = os.path.join(self.thumbnails_dir, file_obj['thumbnail'])
            if os.path.exists(thumbnail_path):
                pixmap = QtGui.QPixmap(thumbnail_path)
                thumbnail_label.setPixmap(pixmap.scaled(
                    thumbnail_label.width(), 
                    thumbnail_label.height(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                ))
                thumbnail_label.thumbnail_path = thumbnail_path
            else:
                thumbnail_label.setText("No\nImage")
        else:
            thumbnail_label.setText("No\nImage")
        
        # Install hover event filter
        thumbnail_label.installEventFilter(widget)
        widget.eventFilter = lambda obj, event: self.hover_handler(obj, event, widget)
        
        # Add thumbnail to container
        container_layout.addWidget(thumbnail_label, 0, 0)
        
        # Check if this rig exists in the current scene
        if self.is_rig_in_scene(file_obj['path']):
            # Create green circle indicator
            indicator = QtWidgets.QLabel()
            indicator.setFixedSize(16, 16)
            indicator.setStyleSheet("""
                QLabel {
                    background-color: #00FF00;
                    border: 2px solid #000000;
                    border-radius: 8px;
                }
            """)
            # Position in bottom right
            container_layout.addWidget(indicator, 0, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight)
        
        # Center the thumbnail container in the widget
        widget_container = QtWidgets.QWidget()
        widget_container.setFixedSize(70, 60)
        widget_layout = QtWidgets.QHBoxLayout(widget_container)
        widget_layout.setContentsMargins(5, 0, 5, 0)
        widget_layout.setAlignment(QtCore.Qt.AlignCenter)
        widget_layout.addWidget(thumbnail_container)
        
        layout.addWidget(widget_container)
        
        # Create name label
        basename = os.path.basename(file_obj['path'])
        filename_without_ext = os.path.splitext(basename)[0]
        formatted_name = filename_without_ext.replace('_', ' ').title()
        
        if len(formatted_name) > 12:
            formatted_name = formatted_name[:10] + "..."
        
        name_label = QtWidgets.QLabel(formatted_name)
        name_label.setAlignment(QtCore.Qt.AlignCenter)
        name_label.setToolTip(file_obj['path'])
        name_label.setFixedHeight(18)  # Reduced height
        name_label.setStyleSheet("QLabel { font-size: 9px; margin: 0px; padding: 0px; }")
        name_label.setWordWrap(True)
        
        layout.addWidget(name_label)
        
        # Add click and context menu handling to whole widget
        widget.mousePressEvent = lambda event: self.widget_click_handler(event, file_obj['path'])
        widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(widget, file_obj['path'], pos)
        )
        
        return widget
    
    def is_rig_in_scene(self, filepath):
        """Check if a rig from the file exists in the current scene"""
        try:
            # Get the filename without extension
            filename = os.path.basename(filepath)
            base_name = os.path.splitext(filename)[0]
            
            # Search for models with this name in the scene
            scene = FBSystem().Scene
            for model in scene.Components:
                if model and hasattr(model, 'Name'):
                    # Check if the model name contains the base filename
                    if base_name.lower() in model.Name.lower():
                        return True
            
            # Also check for namespaced versions
            for model in scene.Components:
                if model and hasattr(model, 'LongName'):
                    if base_name.lower() in model.LongName.lower():
                        return True
                        
            return False
        except Exception as e:
            return False
    
    def is_file_favorite(self, filepath):
        """Check if a file is marked as favorite"""
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r') as file:
                    data = json.load(file)
                
                if isinstance(data, dict) and 'files' in data:
                    for file_obj in data['files']:
                        if file_obj['path'] == filepath:
                            return file_obj.get('favorite', False)
            return False
        except Exception as e:
            return False
    
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
    
    def show_empty_area_context_menu(self, position):
        """Show context menu when right-clicking on empty area"""
        context_menu = QtWidgets.QMenu()
        
        # Add action to add rigs from path
        add_rigs_action = context_menu.addAction("Add Rigs from Path...")
        
        # Show the menu at the cursor position
        action = context_menu.exec_(self.grid_container.mapToGlobal(position))
        
        # Handle menu actions
        if action == add_rigs_action:
            self.add_rigs_from_path()
    
    def add_rigs_from_path(self):
        """Open file browser to add multiple FBX files to the rig references"""
        file_dialog = QtWidgets.QFileDialog()
        file_dialog.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("FBX Files (*.fbx)")
        
        if file_dialog.exec_():
            selected_files = file_dialog.selectedFiles()
            
            if selected_files:
                added_count = 0
                
                # Load existing JSON or create empty structure
                data = {'files': []}
                if os.path.exists(self.json_path):
                    try:
                        with open(self.json_path, 'r') as file:
                            existing_data = json.load(file)
                            
                        # Convert legacy formats to new format
                        if isinstance(existing_data, list):
                            data = {'files': [{'path': path, 'favorite': False, 'thumbnail': None, 'groups': []} for path in existing_data]}
                        elif isinstance(existing_data, dict) and 'filepaths' in existing_data:
                            data = {'files': [{'path': path, 'favorite': False, 'thumbnail': None, 'groups': []} for path in existing_data['filepaths']]}
                        elif isinstance(existing_data, dict) and 'files' in existing_data:
                            data = existing_data
                    except json.JSONDecodeError:
                        pass  # Use the default empty structure
                
                # Get existing file paths
                existing_paths = [file_obj['path'] for file_obj in data['files']]
                
                # Add new files
                for filepath in selected_files:
                    if filepath not in existing_paths:
                        # Add new file object with default "No Image" thumbnail
                        data['files'].append({
                            'path': filepath,
                            'favorite': False,
                            'thumbnail': None,  # No thumbnail
                            'groups': []
                        })
                        added_count += 1
                
                # Save back to the JSON file
                os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
                with open(self.json_path, 'w') as file:
                    json.dump(data, file, indent=4)
                
                # Reload UI
                self.update_group_combo()
                self.load_json_and_create_buttons()
                
                # Update add button state
                self.update_add_button_state()
                
                # Show result message
                if added_count > 0:
                    QtWidgets.QMessageBox.information(
                        self, 
                        "Success", 
                        f"Added {added_count} rig(s) to the reference list."
                    )
                else:
                    QtWidgets.QMessageBox.information(
                        self, 
                        "Information", 
                        "All selected files were already in the reference list."
                    )
    
    def show_context_menu(self, button, filepath, position):
        """Show the context menu for a rig file button"""
        context_menu = QtWidgets.QMenu()
        
        # Add menu actions
        merge_action = context_menu.addAction("Merge")
        open_action = context_menu.addAction("Open File")
        
        # Add favorite toggle
        is_favorite = self.is_file_favorite(filepath)
        favorite_text = "Remove from Favorites" if is_favorite else "Add to Favorites"
        favorite_action = context_menu.addAction(favorite_text)
        
        context_menu.addSeparator()
        
        remove_action = context_menu.addAction("Remove from List")
        
        # Add retake image action
        retake_image_action = context_menu.addAction("Retake Image")
        
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
        elif action == open_action:
            self.open_fbx(filepath)
        elif action == favorite_action:
            self.toggle_favorite(filepath)
        elif action == remove_action:
            self.confirm_and_remove_file(filepath)
        elif action == retake_image_action:
            self.retake_thumbnail(filepath)
        elif action == explore_action:
            self.show_in_explorer(filepath)
        elif action == new_group_action:
            self.add_to_new_group(filepath)
        elif action == none_action:
            self.remove_from_groups(filepath)
        elif action in group_actions:
            self.add_to_group(filepath, action.text())
    
    def retake_thumbnail(self, filepath):
        """Retake the screenshot for a file"""
        try:
            # Only retake if the file exists
            if not os.path.exists(filepath):
                QtWidgets.QMessageBox.warning(
                    self, 
                    "Warning", 
                    f"File not found: {filepath}"
                )
                return
            
            # Store the filepath for later use when thumbnail is captured
            self._retake_filepath = filepath
            
            # Capture new thumbnail using the preview dialog
            self.capture_thumbnail(filepath)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to retake image: {str(e)}"
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
    
    def confirm_and_remove_file(self, filepath):
        """Show confirmation dialog before removing file"""
        filename = os.path.basename(filepath)
        reply = QtWidgets.QMessageBox.question(
            self, 
            'Confirm Removal',
            f'Are you sure you want to remove "{filename}" from the list?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.remove_file_from_json(filepath)
    
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
        """Load JSON file and create thumbnail grid for each group"""
        if not os.path.exists(self.json_path):
            self.show_no_json_message()
            return
            
        try:
            # Clear existing widgets
            for i in reversed(range(self.grid_layout.count())):
                widget = self.grid_layout.itemAt(i).widget()
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
            
            # Get hierarchical groups first to have detected_parents available
            hierarchy, detected_parents = self.get_group_hierarchy()
            
            # Group files by their groups
            grouped_files = {}
            ungrouped_files = []
            
            for file_obj in file_objects:
                if file_obj.get('path', '').lower().endswith('.fbx') and os.path.exists(file_obj['path']):
                    groups = file_obj.get('groups', [])
                    if groups:
                        for group in groups:
                            if group not in grouped_files:
                                grouped_files[group] = []
                            grouped_files[group].append(file_obj)
                    else:
                        ungrouped_files.append(file_obj)
            
            # Filter by current group if not "All"
            if self.current_group != "All":
                filtered_groups = {}
                
                # Check if current group is a parent
                if self.current_group in detected_parents:
                    # Show all subgroups of this parent
                    for group_name, files in grouped_files.items():
                        if group_name.startswith(self.current_group + " - "):
                            filtered_groups[group_name] = files
                    # Also add the parent itself if it has direct files
                    if self.current_group in grouped_files:
                        filtered_groups[self.current_group] = grouped_files[self.current_group]
                else:
                    # Just show the selected group
                    if self.current_group in grouped_files:
                        filtered_groups[self.current_group] = grouped_files[self.current_group]
                
                # If no groups found, it might be due to extra spaces or formatting
                if not filtered_groups:
                    # Try to find the group with normalized matching
                    for group_name, files in grouped_files.items():
                        if group_name.strip() == self.current_group.strip():
                            filtered_groups[group_name] = files
                            break
                
                grouped_files = filtered_groups
                ungrouped_files = []  # Don't show ungrouped when filtering
            
            # Process groups differently for text vs thumbnail view
            if not self.show_thumbnails:
                # Text list view - create a simple hierarchical list
                for i, group_name in enumerate(hierarchy):
                    # Skip virtual parents and filtered groups
                    is_virtual_parent = group_name in detected_parents and group_name not in grouped_files
                    if is_virtual_parent and self.current_group != "All" and self.current_group != group_name:
                        continue
                    if self.current_group != "All" and group_name not in grouped_files:
                        continue
                    
                    group_files = grouped_files.get(group_name, [])
                    if not group_files and not is_virtual_parent:
                        continue
                    
                    # Create group widget
                    group_widget = QtWidgets.QWidget()
                    group_widget.setStyleSheet("QWidget { background-color: #2B2B2B; border-radius: 6px; }")
                    group_widget.setFocusPolicy(QtCore.Qt.NoFocus)
                    group_layout = QtWidgets.QVBoxLayout(group_widget)
                    group_layout.setContentsMargins(6, 4, 6, 6)
                    group_layout.setSpacing(2)
                    
                    # Determine if this is a parent or child group
                    is_parent = group_name in detected_parents
                    is_child = " - " in group_name
                    
                    # Create appropriate label with indentation for children
                    if is_child:
                        display_name = "  └ " + group_name.split(" - ", 1)[1]
                        group_label = QtWidgets.QLabel(display_name)
                        group_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10px; color: #CCCCCC; padding: 2px 4px; }")
                    else:
                        group_label = QtWidgets.QLabel(group_name)
                        group_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; color: #FFFFFF; padding: 2px 4px; }")
                    
                    group_label.setFixedHeight(20)
                    group_layout.addWidget(group_label)
                    
                    # Create grid for files
                    if group_files:
                        grid_widget = QtWidgets.QWidget()
                        grid_widget.setStyleSheet("QWidget { background-color: transparent; }")
                        grid = QtWidgets.QGridLayout(grid_widget)
                        grid.setSpacing(2)
                        grid.setContentsMargins(10 if is_child else 0, 0, 0, 0)  # Indent child files
                        group_layout.addWidget(grid_widget)
                        
                        # Sort and add files
                        sorted_group_files = sorted(group_files, 
                            key=lambda x: (not x.get('favorite', False), os.path.basename(x['path']).lower()))
                        
                        for idx, file_obj in enumerate(sorted_group_files):
                            text_widget = self.create_fbx_text_widget(file_obj)
                            grid.addWidget(text_widget, idx, 0)
                    
                    self.grid_layout.addWidget(group_widget)
            
            else:
                # Thumbnail view - keep existing nested layout
                current_parent = None
                parent_widget = None
                parent_layout = None
                
                for i, group_name in enumerate(hierarchy):
                    # Check if this is a virtual parent group (detected but has no direct files)
                    is_virtual_parent = group_name in detected_parents and group_name not in grouped_files
                    
                    # For virtual parents, check if we're filtering by this parent
                    if is_virtual_parent and self.current_group != "All" and self.current_group != group_name:
                        continue
                    
                    # Skip groups not in our filtered list when filtering
                    if self.current_group != "All" and group_name not in grouped_files:
                        continue
                        
                    group_files = grouped_files.get(group_name, [])
                    
                    # Skip empty non-virtual groups when not filtering by parent
                    if not group_files and not is_virtual_parent:
                        continue
                    
                    # Check if this is a parent or child group
                    is_parent = group_name in detected_parents
                    is_child = " - " in group_name
                    
                    # Determine parent name for children
                    parent_name = None
                    if is_child:
                        parent_name = group_name.split(" - ")[0]
                    
                    # When filtering by a specific group (not parent), display it directly
                    if self.current_group not in ["All"] and self.current_group not in detected_parents:
                        # Just display this group directly without parent container
                        group_widget = QtWidgets.QWidget()
                        group_widget.setStyleSheet("QWidget { background-color: #2B2B2B; border-radius: 6px; }")
                        group_widget.setFocusPolicy(QtCore.Qt.NoFocus)
                        group_layout = QtWidgets.QVBoxLayout(group_widget)
                        group_layout.setContentsMargins(6, 4, 6, 6)
                        group_layout.setSpacing(2)
                        group_layout.setAlignment(QtCore.Qt.AlignTop)
                        
                        # Group label
                        group_label = QtWidgets.QLabel(group_name)
                        group_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; color: #FFFFFF; padding: 2px 4px; }")
                        group_label.setFixedHeight(20)
                        group_layout.addWidget(group_label)
                        
                        # Create grid for the group
                        grid_widget = QtWidgets.QWidget()
                        grid_widget.setStyleSheet("QWidget { background-color: transparent; }")
                        grid = QtWidgets.QGridLayout(grid_widget)
                        grid.setSpacing(2)
                        grid.setContentsMargins(0, 0, 0, 0)
                        grid.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
                        group_layout.addWidget(grid_widget)
                        
                        # Sort files in group: favorites first, then alphabetically
                        sorted_group_files = sorted(group_files, 
                            key=lambda x: (not x.get('favorite', False), os.path.basename(x['path']).lower()))
                        
                        # Add files to grid or list
                        if self.show_thumbnails:
                            # Thumbnail grid view
                            row = 0
                            col = 0
                            cols_per_row = 7  # More columns with smaller thumbnails
                            
                            for file_obj in sorted_group_files:
                                thumbnail_widget = self.create_fbx_thumbnail_widget(file_obj)
                                grid.addWidget(thumbnail_widget, row, col)
                                
                                col += 1
                                if col >= cols_per_row:
                                    col = 0
                                    row += 1
                        else:
                            # Text list view
                            for i, file_obj in enumerate(sorted_group_files):
                                text_widget = self.create_fbx_text_widget(file_obj)
                                grid.addWidget(text_widget, i, 0)
                        
                        # Add widget to main layout
                        self.grid_layout.addWidget(group_widget)
                        
                        # Skip all further processing for this group
                        continue
                        
                    # For normal hierarchy display (All or parent group selected)
                    elif is_child and (not parent_widget or parent_name != current_parent):
                        current_parent = parent_name
                        parent_widget = QtWidgets.QWidget()
                        parent_widget.setStyleSheet("QWidget { background-color: #2B2B2B; border-radius: 6px; }")
                        parent_widget.setFocusPolicy(QtCore.Qt.NoFocus)
                        parent_layout = QtWidgets.QVBoxLayout(parent_widget)
                        parent_layout.setContentsMargins(6, 4, 6, 6)
                        parent_layout.setSpacing(4)
                        parent_layout.setAlignment(QtCore.Qt.AlignTop)
                        
                        # Parent label
                        parent_label = QtWidgets.QLabel(current_parent)
                        parent_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; color: #FFFFFF; padding: 2px 4px; }")
                        parent_label.setFixedHeight(20)
                        parent_layout.addWidget(parent_label)
                    
                    # Create parent container if this is a parent
                    elif is_parent:
                        current_parent = group_name
                        parent_widget = QtWidgets.QWidget()
                        parent_widget.setStyleSheet("QWidget { background-color: #2B2B2B; border-radius: 6px; }")
                        parent_widget.setFocusPolicy(QtCore.Qt.NoFocus)
                        parent_layout = QtWidgets.QVBoxLayout(parent_widget)
                        parent_layout.setContentsMargins(6, 4, 6, 6)
                        parent_layout.setSpacing(4)
                        parent_layout.setAlignment(QtCore.Qt.AlignTop)
                        
                        # Parent label
                        parent_label = QtWidgets.QLabel(current_parent)
                        parent_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; color: #FFFFFF; padding: 2px 4px; }")
                        parent_label.setFixedHeight(20)
                        parent_layout.addWidget(parent_label)
                    
                    # Skip creating content for virtual parent groups
                    if is_virtual_parent:
                        continue
                    
                    # Create child group container (no left margin)
                    if is_child:
                        child_widget = QtWidgets.QWidget()
                        child_widget.setStyleSheet("QWidget { background-color: #222222; border-radius: 4px; }")
                        child_layout = QtWidgets.QVBoxLayout(child_widget)
                        child_layout.setContentsMargins(6, 4, 6, 6)
                        child_layout.setSpacing(2)
                        
                        # Display only the suffix for child groups
                        display_name = group_name.split(" - ", 1)[1]
                        group_label = QtWidgets.QLabel(display_name)
                        group_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10px; color: #CCCCCC; padding: 2px 4px; }")
                        group_label.setFixedHeight(18)
                        child_layout.addWidget(group_label)
                    
                    # Create grid for this group
                    grid_widget = QtWidgets.QWidget()
                    grid_widget.setStyleSheet("QWidget { background-color: transparent; }")
                    grid = QtWidgets.QGridLayout(grid_widget)
                    grid.setSpacing(2)  # Reduced spacing between items
                    grid.setContentsMargins(0, 0, 0, 0)
                    grid.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)  # Align to top-left
                    
                    # Add grid to appropriate layout
                    if is_child:
                        child_layout.addWidget(grid_widget)
                        # Add child widget to parent layout
                        if parent_layout:
                            parent_layout.addWidget(child_widget)
                    else:
                        # This is a standalone group (not parent or child)
                        group_widget = QtWidgets.QWidget()
                        group_widget.setStyleSheet("QWidget { background-color: #2B2B2B; border-radius: 6px; }")
                        group_widget.setFocusPolicy(QtCore.Qt.NoFocus)
                        group_layout = QtWidgets.QVBoxLayout(group_widget)
                        group_layout.setContentsMargins(6, 4, 6, 6)
                        group_layout.setSpacing(2)
                        group_layout.setAlignment(QtCore.Qt.AlignTop)
                        
                        # Group label
                        group_label = QtWidgets.QLabel(group_name)
                        group_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; color: #FFFFFF; padding: 2px 4px; }")
                        group_label.setFixedHeight(20)
                        group_layout.addWidget(group_label)
                        group_layout.addWidget(grid_widget)
                    
                    # Sort files in group: favorites first, then alphabetically
                    sorted_group_files = sorted(group_files, 
                        key=lambda x: (not x.get('favorite', False), os.path.basename(x['path']).lower()))
                    
                    # Add files to grid (thumbnail view only)
                    # Thumbnail grid view
                    row = 0
                    col = 0
                    cols_per_row = 7  # More columns with smaller thumbnails
                    
                    for file_obj in sorted_group_files:
                        thumbnail_widget = self.create_fbx_thumbnail_widget(file_obj)
                        grid.addWidget(thumbnail_widget, row, col)
                        
                        col += 1
                        if col >= cols_per_row:
                            col = 0
                            row += 1
                    
                    # Add widgets to main layout at appropriate times
                    if self.current_group not in ["All"] and self.current_group not in detected_parents:
                        # Direct group display - add immediately
                        self.grid_layout.addWidget(group_widget)
                    elif is_parent:
                        # Parent widgets are added when switching to new parent or at end
                        pass
                    elif is_child:
                        # Check if this is the last child of current parent or last item overall
                        is_last_child = (i == len(hierarchy) - 1)
                        
                        if not is_last_child:
                            # Check if next item is a different parent or standalone group
                            next_group = hierarchy[i+1]
                            next_parent = next_group.split(" - ")[0] if " - " in next_group else None
                            is_last_child = (next_parent != current_parent)
                        
                        if is_last_child:
                            # Add parent widget with all children
                            if parent_widget:
                                self.grid_layout.addWidget(parent_widget)
                                parent_widget = None  # Reset after adding
                    else:
                        # Standalone group - add immediately
                        self.grid_layout.addWidget(group_widget)
            
            # Add ungrouped files if any
            if ungrouped_files and self.current_group == "All":
                ungrouped_widget = QtWidgets.QWidget()
                ungrouped_widget.setStyleSheet("QWidget { background-color: #242424; border-radius: 6px; }")
                ungrouped_widget.setFocusPolicy(QtCore.Qt.NoFocus)
                ungrouped_layout = QtWidgets.QVBoxLayout(ungrouped_widget)
                ungrouped_layout.setContentsMargins(6, 4, 6, 6)  # Minimal top margin
                ungrouped_layout.setSpacing(2)  # Minimal spacing between title and grid
                ungrouped_layout.setAlignment(QtCore.Qt.AlignTop)  # Align to top
                
                # Label for ungrouped
                ungrouped_label = QtWidgets.QLabel("Ungrouped")
                ungrouped_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; color: #999999; padding: 2px 4px; }")
                ungrouped_label.setFixedHeight(20)  # Fixed height for consistency
                ungrouped_layout.addWidget(ungrouped_label)
                
                # Create grid for ungrouped
                grid_widget = QtWidgets.QWidget()
                grid_widget.setStyleSheet("QWidget { background-color: transparent; }")
                grid = QtWidgets.QGridLayout(grid_widget)
                grid.setSpacing(3)
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)  # Align to top-left
                ungrouped_layout.addWidget(grid_widget)
                
                # Sort ungrouped files
                sorted_ungrouped = sorted(ungrouped_files, 
                    key=lambda x: (not x.get('favorite', False), os.path.basename(x['path']).lower()))
                
                # Add files to grid or list
                if self.show_thumbnails:
                    # Thumbnail grid view
                    row = 0
                    col = 0
                    cols_per_row = 7  # Same as grouped files
                    
                    for file_obj in sorted_ungrouped:
                        thumbnail_widget = self.create_fbx_thumbnail_widget(file_obj)
                        grid.addWidget(thumbnail_widget, row, col)
                        
                        col += 1
                        if col >= cols_per_row:
                            col = 0
                            row += 1
                else:
                    # Text list view
                    for i, file_obj in enumerate(sorted_ungrouped):
                        text_widget = self.create_fbx_text_widget(file_obj)
                        grid.addWidget(text_widget, i, 0)
                
                self.grid_layout.addWidget(ungrouped_widget)
            
            # Show message if no files
            if not grouped_files and not ungrouped_files:
                no_files_msg = QtWidgets.QLabel("No .fbx files found")
                no_files_msg.setAlignment(QtCore.Qt.AlignCenter)
                self.grid_layout.addWidget(no_files_msg)
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load JSON file: {str(e)}")
    
    def on_group_changed(self, index):
        """Handle when user changes the group selection"""
        # Get the group name directly from the combo box
        if index >= 0:
            self.current_group = self.group_combo.itemText(index)
        else:
            self.current_group = "All"
        
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
    
    def get_group_hierarchy(self):
        """Get groups organized in parent-child hierarchy"""
        all_groups = self.get_all_groups()
        if "All" in all_groups:
            all_groups.remove("All")
        
        # Detect parent groups from naming pattern (word before " - ")
        hierarchy = {}
        detected_parents = set()
        orphans = []
        
        # First pass: detect parent groups from patterns
        for group in all_groups:
            if " - " in group:
                parent_name = group.split(" - ")[0]
                detected_parents.add(parent_name)
                
                if parent_name not in hierarchy:
                    hierarchy[parent_name] = []
                hierarchy[parent_name].append(group)
            else:
                orphans.append(group)
        
        # Second pass: check if orphans are actually parents
        final_orphans = []
        for orphan in orphans:
            if orphan in detected_parents:
                # This is a detected parent, not an orphan
                if orphan not in hierarchy:
                    hierarchy[orphan] = []
            else:
                final_orphans.append(orphan)
        
        # Build final result
        result = []
        
        # Add all parent groups (both real and detected) with their children
        all_parents = sorted(list(detected_parents) + final_orphans)
        for parent in all_parents:
            if parent in detected_parents:
                # This is a parent group (real or virtual)
                result.append(parent)
                if parent in hierarchy:
                    # Add children sorted
                    result.extend(sorted(hierarchy[parent]))
            else:
                # This is a standalone group
                result.append(parent)
        
        return result, detected_parents  # Return both hierarchy and detected parents
    
    def update_group_combo(self):
        """Update the group combo box with all available groups"""
        current_text = self.group_combo.currentText()
        
        # Block signals to avoid triggering on_group_changed during update
        self.group_combo.blockSignals(True)
        
        # Clear and repopulate
        self.group_combo.clear()
        self.group_combo.addItem("All")
        
        # Add groups in hierarchical order
        hierarchy, detected_parents = self.get_group_hierarchy()
        for group in hierarchy:
            # Add all groups without indentation
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
        """Add a file to a specified group (replaces any existing group)"""
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
                                
                            # Replace existing groups with just this one
                            file_obj['groups'] = [group_name]
                            
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
                
                # Reload the UI to update green circles
                self.load_json_and_create_buttons()
            else:
                QtWidgets.QMessageBox.warning(self, "Warning", f"Failed to merge: {os.path.basename(filepath)}")
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Error merging file: {str(e)}")
    
    def open_fbx(self, filepath):
        """Open the selected FBX file directly (instead of merging)"""
        try:
            if not os.path.exists(filepath):
                QtWidgets.QMessageBox.warning(self, "Warning", f"File not found: {filepath}")
                return
            
            # Get application reference
            app = FBApplication()
            
            # Simple confirmation dialog before opening new file
            reply = QtWidgets.QMessageBox.question(
                self, 
                'Open File',
                f'Are you sure you want to open "{os.path.basename(filepath)}"?\n\nThis will replace the current scene.',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.No:
                return
            
            # Open the file (False = don't show dialog)
            status = app.FileOpen(filepath, False)
            
            if status:
                QtWidgets.QMessageBox.information(
                    self, 
                    "Success", 
                    f"Successfully opened: {os.path.basename(filepath)}"
                )
                
                # Close this dialog since we're opening a new scene
                self.close()
            else:
                QtWidgets.QMessageBox.warning(
                    self, 
                    "Warning", 
                    f"Failed to open: {os.path.basename(filepath)}"
                )
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, 
                "Error", 
                f"Error opening file: {str(e)}"
            )

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