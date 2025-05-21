"""
FBX Exporter for MotionBuilder

Refactored to separate constraint handling from axis conversion:
- prepare_constrained_root_for_export(): Handles constraint-based plotting (always executed)
- apply_axis_conversion_to_root(): Applies Y-up to Z-up rotation (only if enabled)
- cleanup_after_export(): Unified cleanup based on what was done during preparation

This separation allows the exporter to properly handle constrained roots regardless
of whether axis conversion is enabled.
"""

import os
import json
import sys
import tempfile
import traceback
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QCheckBox, QLineEdit, QGroupBox, 
                             QScrollArea, QProgressBar, QFileDialog, QFrame, QMessageBox,
                             QSizePolicy, QToolButton, QGridLayout, QDialog, QComboBox)

# Try to import FBX SDK for axis conversion
try:
    import fbx
    FBX_SDK_AVAILABLE = True
    # Since we integrated the converter code, we're available if FBX SDK is available
    FBX_CONVERTER_AVAILABLE = True
except ImportError:
    FBX_SDK_AVAILABLE = False
    FBX_CONVERTER_AVAILABLE = False
from PySide6.QtCore import Qt, QSize, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon, QColor, QDoubleValidator

from pyfbsdk import FBApplication, FBSystem, FBMessageBox, FBModelList, FBModel, FBGetSelectedModels, FBFindModelByLabelName, FBTime, FBAnimationNode
from pyfbsdk import FBModelNull, FBVector3d, FBConstraintManager, FBPlotOptions, FBRotationFilter, FBBeginChangeAllModels, FBEndChangeAllModels
from pyfbsdk import FBPlayerControl, FBFbxOptions, FBUndoManager, FBConstraint  # Added FBPlayerControl, FBFbxOptions, FBUndoManager, and FBConstraint to imports


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

# Path for storing group states between window instances
def get_temp_state_file():
    """Get a temporary file path for storing group states"""
    temp_dir = tempfile.gettempdir()
    app = FBApplication()
    # Create a unique identifier for the current session
    session_id = app.FBXFileName or "default_session"
    session_id = os.path.basename(session_id).replace(".", "_")
    return os.path.join(temp_dir, f"mb_exporter_states_{session_id}.json")

def save_group_states(states):
    """Save group states to temp file"""
    try:
        with open(get_temp_state_file(), 'w') as f:
            json.dump(states, f)
    except:
        pass  # Silently ignore errors

def load_group_states():
    """Load group states from temp file"""
    try:
        if os.path.exists(get_temp_state_file()):
            with open(get_temp_state_file(), 'r') as f:
                content = f.read().strip()
                if not content:  # Empty file
                    return {}
                return json.loads(content)
    except:
        # If there's an error, recreate the file with empty contents
        try:
            with open(get_temp_state_file(), 'w') as f:
                json.dump({}, f)
        except:
            pass  # If we can't create the file, just continue
    return {}

class CollapsibleGroupBox(QWidget):
    """Custom collapsible group box for take groups"""
    def __init__(self, title, parent=None, initial_collapsed=False, collapse_callback=None):
        super(CollapsibleGroupBox, self).__init__(parent)
        self.title = title
        self.collapsed = initial_collapsed
        self.collapse_callback = collapse_callback
        
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Header layout
        self.header_widget = QWidget()
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(5, 5, 5, 5)
        
        # Toggle button
        self.toggle_button = QToolButton()
        self.toggle_button.setText("▾" if not self.collapsed else "▸")
        self.toggle_button.setAutoRaise(True)
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        self.header_layout.addWidget(self.toggle_button)
        
        # Count label
        self.count_label = QLabel("0/0")
        self.count_label.setStyleSheet("font-size: 9pt;")
        self.header_layout.addWidget(self.count_label)
        
        # Title button
        self.title_button = QPushButton(title)
        self.title_button.setStyleSheet("text-align: left; color: white; border: none; font-weight: bold;")
        self.title_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.header_layout.addWidget(self.title_button)
        
        # Container for content
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 0, 0, 0)
        
        # Add widgets to main layout
        self.layout.addWidget(self.header_widget)
        self.layout.addWidget(self.content_widget)
        
        # Set initial collapsed state
        self.content_widget.setVisible(not self.collapsed)
        
    def toggle_collapsed(self):
        self.collapsed = not self.collapsed
        self.content_widget.setVisible(not self.collapsed)
        self.toggle_button.setText("▸" if self.collapsed else "▾")
        
        # Call the callback if provided
        if self.collapse_callback:
            self.collapse_callback(self.title, self.collapsed)
        
    def add_widget(self, widget):
        self.content_layout.addWidget(widget)
        
    def set_count(self, checked, total):
        self.count_label.setText(f"{checked}/{total}")


class MotionBuilderExporter(QMainWindow):
    """Main exporter class that handles settings, UI, and export functionality"""
    
    def __init__(self, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(MotionBuilderExporter, self).__init__(parent)
        self.settings = {}
        self.export_items = []
        self.full_export_folder = ""
        self.group_info_list = []
        self.skeleton_root = None
        self.original_parent = None
        self.selected_nodes_count = 0
        self.selected_nodes = []
        
        # Store references to collapsible groups for later updating
        self.group_boxes = {}
        
        # Debug flag - set to False to disable print statements
        self.debug = False
        
        # List to track exported files for post-processing
        self.exported_files = []
        
        self.init_ui()
    
    def debug_print(self, message):
        """Print message only if debug is enabled"""
        if self.debug:
            print(f"[FBXExporter] {message}")
        
    def init_ui(self):
        """Initialize the main window UI"""
        self.setWindowTitle("MotionBuilder Animation Exporter")
        self.resize(750, 650)  # Slightly larger default size
        self.setMinimumWidth(750)  # Increased minimum width
        self.setMinimumHeight(550)  # Increased minimum height to ensure options are visible
        
        # Set window to stay on top of parent only (not all windows)
        if self.parent():
            # For MotionBuilder, use Window flag without StaysOnTop
            self.setWindowFlags(Qt.Window)
        else:
            # Fallback if no parent found
            self.setWindowFlags(Qt.Window)
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Create progress bar
        self.create_progress_bar(main_layout)
        
        # Create folder selection
        self.create_folder_selection(main_layout)
        
        # Create options panel
        self.create_options_panel(main_layout)
        
        # Create export button
        button_frame = QWidget()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.export_button = QPushButton("Export")
        self.export_button.setMinimumHeight(30)
        self.export_button.setFixedWidth(120)  # Fixed width for the button
        self.export_button.clicked.connect(self.on_export)
        button_layout.addStretch(1)  # Add stretch before button
        button_layout.addWidget(self.export_button)
        button_layout.addStretch(1)  # Add stretch after button
        
        main_layout.addWidget(button_frame)
        
        # Create takes selection
        self.create_takes_selection(main_layout)
        
        # Auto-check for scene changes
        self.current_fbx = FBApplication().FBXFileName
        self.timer_id = self.startTimer(500)  # Check every 500ms
        
        # Initial skeleton detection
        self.select_skeleton_hierarchy()
    
    def timerEvent(self, event):
        """Handle timer events to check for scene changes"""
        if FBApplication().FBXFileName != self.current_fbx:
            self.close()
            
    def update_rotation_inputs_state(self):
        """Update the state of rotation input fields based on current axis selection"""
        if not hasattr(self, 'x_rotation_input'):
            return
            
        is_manual = self.up_axis_combo.currentText() == "Manual Rotations"
        
        # Enable/disable rotation inputs
        self.x_rotation_input.setEnabled(is_manual)
        self.y_rotation_input.setEnabled(is_manual)
        self.z_rotation_input.setEnabled(is_manual)
        
        # Set default values based on selected preset
        if not is_manual:
            if self.up_axis_combo.currentText() == "Y-up (None)":
                self.x_rotation_input.setText("0.0")
                self.y_rotation_input.setText("0.0")
                self.z_rotation_input.setText("0.0")
            elif self.up_axis_combo.currentText() == "Z-up":
                self.x_rotation_input.setText("-90.0")
                self.y_rotation_input.setText("0.0")
                self.z_rotation_input.setText("0.0")
    
    def get_settings_file(self):
        """Determine the appropriate settings file path based on current scene"""
        base_dir = os.path.join(os.path.expanduser("~"), "Documents", "MB", "ExporterSaveDataFiles")
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        app = FBApplication()
        fbx_file_name = app.FBXFileName
        if fbx_file_name and fbx_file_name.lower() != "scene":
            base = os.path.basename(fbx_file_name)
            base_no_ext = os.path.splitext(base)[0]
            settings_file = os.path.join(base_dir, "_" + base_no_ext + "_Exporter_Settings.json")
        else:
            settings_file = os.path.join(base_dir, "Default_Exporter_Settings.json")
        return settings_file

    def load_settings(self):
        """Load saved settings from JSON file"""
        settings_file = self.get_settings_file()
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r") as f:
                    content = f.read().strip()
                    if not content:  # Empty file
                        return {}
                    self.settings = json.loads(content)
                    return self.settings
            except Exception as e:
                # Create a new valid JSON file to avoid future errors
                try:
                    with open(settings_file, "w") as f:
                        json.dump({}, f, indent=4)
                except:
                    pass  # If we can't write the file, just continue
                return {}
        return {}

    def save_settings(self, settings):
        """Save settings to JSON file"""
        settings_file = self.get_settings_file()
        try:
            with open(settings_file, "w") as f:
                json.dump(settings, f, indent=4)
            self.settings = settings
        except Exception as e:
            # print(f"Error saving settings: {e}")
            FBMessageBox("Export Error", f"Failed to save settings: {e}", "OK")

    def get_default_export_folder(self):
        """Get the default export folder from settings or scene location"""
        scene = FBSystem().Scene
        saved_settings = self.load_settings()
        if "global" in saved_settings and os.path.exists(saved_settings["global"]):
            return saved_settings["global"]
        elif scene and (hasattr(scene, 'FullName') and scene.FullName):
            return os.path.dirname(scene.FullName)
        else:
            return os.path.expanduser("~")

    @staticmethod
    def truncate_path(full_path, num_parts=3):
        """Truncate a path to show only the last N parts for display"""
        parts = os.path.normpath(full_path).split(os.sep)
        return os.sep.join(parts[-num_parts:]) if len(parts) > num_parts else full_path
    
    def unparent_skeleton_root(self):
        """Unparent the skeleton root node and store its original parent"""
        if not self.skeleton_root:
            # print("No skeleton root to unparent")
            return False
        try:
            if hasattr(self.skeleton_root, 'Parent') and self.skeleton_root.Parent:
                # print(f"Unparenting skeleton root: {self.skeleton_root.Name} from {self.skeleton_root.Parent.Name}")
                self.original_parent = self.skeleton_root.Parent
                
                # Go to first frame to avoid pivot offsets
                player_control = FBPlayerControl()
                current_take = FBSystem().CurrentTake
                first_frame = current_take.LocalTimeSpan.GetStart()
                player_control.Goto(first_frame)
                FBSystem().Scene.Evaluate()
                
                self.skeleton_root.Parent = None
                # print("Successfully unparented skeleton root")
                return True
            else:
                # print("Skeleton root has no parent to unparent from")
                return False
        except Exception as e:
            # print(f"Error unparenting skeleton root: {e}")
            return False
            
    def reparent_skeleton_root(self):
        """Reparent the skeleton root to its original parent"""
        if not self.skeleton_root or not self.original_parent:
            # print("Missing skeleton root or original parent for reparenting")
            return False
        try:
            # print(f"Reparenting skeleton root: {self.skeleton_root.Name} to {self.original_parent.Name}")
            
            # Go to first frame to avoid pivot offsets
            player_control = FBPlayerControl()
            current_take = FBSystem().CurrentTake
            first_frame = current_take.LocalTimeSpan.GetStart()
            player_control.Goto(first_frame)
            FBSystem().Scene.Evaluate()
            
            self.skeleton_root.Parent = self.original_parent
            # print("Successfully reparented skeleton root")
            return True
        except Exception as e:
            # print(f"Error reparenting skeleton root: {e}")
            return False
    
            
            

    
    
    
    def plot_root_animation(self):
        """Plot the root's animation by evaluating each frame using plotAnimation"""
        if not self.skeleton_root:
            # print("No skeleton root to plot")
            return False
            
        try:
            # print("Starting animation frame-by-frame evaluation and plotting...")
            
            # Get current take 
            current_take = FBSystem().CurrentTake
            # print(f"Current take: {current_take.Name}")
            
            # Get take timespan to ensure we plot the entire animation
            take_span = current_take.LocalTimeSpan
            start_frame = take_span.GetStart().GetFrame()
            end_frame = take_span.GetStop().GetFrame()
            # print(f"Take timespan: {start_frame} to {end_frame} frames")
            
            # Store current player time to restore it later
            player_control = FBPlayerControl()
            original_time = FBSystem().LocalTime
            
            # Set up plot options
            plot_options = FBPlotOptions()
            plot_options.ConstantKeyReducerKeepOneKey = True
            plot_options.PlotAllTakes = False
            plot_options.PlotOnFrame = True
            plot_options.PlotPeriod = FBTime(0, 0, 0, 1)  # 1 frame
            plot_options.PlotTranslationOnRootOnly = False
            plot_options.PreciseTimeDiscontinuities = True
            plot_options.RotationFilterToApply = FBRotationFilter.kFBRotationFilterUnroll
            plot_options.UseConstantKeyReducer = False
            
            # print("Testing constraint status...")
            # Jump to first and last frames to check if constraint is working properly
            test_frames = [int(start_frame), int(end_frame)]
            for test_frame in test_frames:
                player_control.Goto(FBTime(0, 0, 0, test_frame))
                FBSystem().Scene.Evaluate()
                # print(f"Frame {test_frame}: Position = {self.skeleton_root.Translation}, Rotation = {self.skeleton_root.Rotation}")
            
            # Make sure the root node is selected for plotting
            FBBeginChangeAllModels()
            
            # Clear all selections first
            for model in self.selected_nodes:
                model.Selected = False
                
            # Select only the root
            self.skeleton_root.Selected = True
            
            # print(f"Selected root: {self.skeleton_root.LongName}")
            
            # First method: Use FBSystem().Scene.Evaluate() with PlotTakeOnSelected
            # Go to the start frame to begin plotting
            player_control.Goto(FBTime(0, 0, 0, start_frame))
            FBSystem().Scene.Evaluate()
            
            # Plot selected models (only the root should be selected at this point)
            # print("Plotting root animation using PlotTakeOnSelected...")
            try:
                # Plot all selected objects 
                current_take.PlotTakeOnSelected(plot_options)
                # print("Plotting completed successfully.")
            except Exception as e:
                # print(f"Error during PlotTakeOnSelected: {e}")
                
                # Try alternative method: Plot using classic keyframe approach
                # print("Trying alternative method...")
                self.manual_plot_by_frame(start_frame, end_frame)
            
            FBEndChangeAllModels()
            
            # Restore the original time
            player_control.Goto(original_time)
            FBSystem().Scene.Evaluate()
            
            return True
            
        except Exception as e:
            # print(f"Error plotting root animation: {e}")
            # Try to restore original time in case of error
            if 'original_time' in locals() and 'player_control' in locals():
                player_control.Goto(original_time)
            return False
            
    def manual_plot_by_frame(self, start_frame, end_frame):
        """Manual fallback method to plot frame by frame if the main method fails"""
        # print("Using manual frame-by-frame plotting...")
        
        player_control = FBPlayerControl()
        
        # Make sure properties are animated
        self.skeleton_root.Translation.SetAnimated(True)
        self.skeleton_root.Rotation.SetAnimated(True)
        
        # Get animation nodes
        translation_node = self.skeleton_root.Translation.GetAnimationNode()
        rotation_node = self.skeleton_root.Rotation.GetAnimationNode()
        
        if not translation_node or not rotation_node:
            # print("Failed to get animation nodes for root")
            return False
            
        # Clear any existing keys in the FCurves
        if translation_node.FCurve:
            translation_node.FCurve.EditClear()
        if rotation_node.FCurve:
            rotation_node.FCurve.EditClear()
        
        # Go through every frame and create keys
        for frame in range(int(start_frame), int(end_frame) + 1):
            frame_time = FBTime(0, 0, 0, frame)
            
            # Go to frame and evaluate
            player_control.Goto(frame_time)
            FBSystem().Scene.Evaluate()
            
            # Evaluate a second time to ensure constraint is fully solved
            FBSystem().Scene.Evaluate()
            
            # Get values
            trans_value = self.skeleton_root.Translation
            rot_value = self.skeleton_root.Rotation
            
            # Add keys
            translation_node.KeyAdd(frame_time, [trans_value[0], trans_value[1], trans_value[2]])
            rotation_node.KeyAdd(frame_time, [rot_value[0], rot_value[1], rot_value[2]])
            
            if frame % 10 == 0:
                pass  # Progress update disabled for performance
                
        # print("Manual plotting completed")
    
    def remove_root_keys(self):
        """Remove all animation keys from the root node"""
        if not self.skeleton_root:
            # print("No skeleton root to remove keys from")
            return False
            
        try:
            # print(f"Removing animation keys from root: {self.skeleton_root.Name}")
            
            # Get the root's animation node
            anim_node = self.skeleton_root.AnimationNode
            if not anim_node:
                # print("No animation node found for root")
                return False
                
            # Check if we have any keys
            if anim_node.KeyCount == 0:
                # print("No keys to remove")
                return True
                
            # Process all animation nodes recursively
            self.remove_keys_recursive(anim_node)
            
            # print("Successfully removed all keys from root")
            return True
            
        except Exception as e:
            # print(f"Error removing root keys: {e}")
            return False
    
    def remove_keys_recursive(self, anim_node):
        """Recursively remove all keys from an animation node and its children"""
        try:
            # If this node has an FCurve with keys, clear it
            if hasattr(anim_node, 'FCurve') and anim_node.FCurve:
                fcurve = anim_node.FCurve
                if fcurve and hasattr(fcurve, 'Keys') and len(fcurve.Keys) > 0:
                    # print(f"Clearing keys from FCurve: {anim_node.Name}")
                    fcurve.EditClear()
            
            # Process all child nodes - Nodes is a list, not an object with GetCount()
            if hasattr(anim_node, 'Nodes'):
                for child in anim_node.Nodes:
                    self.remove_keys_recursive(child)
        except Exception as e:
            pass  # Error handling disabled for performance
    
    def remove_all_keys_from_root(self):
        """Remove all animation keys from the root joint"""
        if not self.skeleton_root:
            return
            
        try:
            # print("\n=== REMOVING KEYS FROM ROOT ===")
            cleared_count = 0
            
            # Clear animation from all properties
            for prop in self.skeleton_root.PropertyList:
                try:
                    # Check if property is animated
                    if prop.IsAnimatable() and prop.IsAnimated():
                        anim_node = prop.GetAnimationNode()
                        
                        # Clear FCurve if it exists
                        if anim_node and anim_node.FCurve:
                            anim_node.FCurve.EditClear()
                            cleared_count += 1
                            # print(f"  Cleared keys from {prop.Name}")
                        
                        # Handle properties with sub-nodes (like Translation, Rotation, Scaling)
                        if anim_node:
                            for sub_node in anim_node.Nodes:
                                if sub_node and sub_node.FCurve:
                                    sub_node.FCurve.EditClear()
                                    cleared_count += 1
                                    # print(f"  Cleared keys from {prop.Name}.{sub_node.Name}")
                except Exception as e:
                    pass  # Error handling disabled for performance
            
            # print(f"Total keys cleared: {cleared_count}")
            # print("=== KEY REMOVAL COMPLETE ===")
            
        except Exception as e:
            pass  # Error handling disabled for performance
    
    # Removed store_root_state - now using capture_original_animation
    
    # Removed store_animation_recursive - now using capture_original_animation
    
    # Removed restore_root_state - now using restore_from_original_null
    
    # Removed restore_animation_recursive - now using restore_from_original_null
    
    def prepare_constrained_root_for_export(self):
        """Detects if root has constraints, captures animation to temporary null and plots it back"""
        if not self.skeleton_root:
            return None
            
        try:
            # Check if root has active constraints
            active_constraints = []
            src_count = self.skeleton_root.GetSrcCount()
            for i in range(src_count):
                const = self.skeleton_root.GetSrc(i)
                if isinstance(const, FBConstraint) and const.Active:
                    active_constraints.append(const)
            
            has_constraints = len(active_constraints) > 0
            
            # Create capture null
            capture_null = FBModelNull("TEMP_ROOT_CAPTURE")
            capture_null.Show = False
            
            # Create constraint to capture the root's animation
            constraint_manager = FBConstraintManager()
            capture_constraint = constraint_manager.TypeCreateConstraint("Parent/Child")
            capture_constraint.Name = "TEMP_CAPTURE_CONSTRAINT"
            
            # Set references (child = capture null, parent = root)
            capture_constraint.ReferenceAdd(0, capture_null)  # Child
            capture_constraint.ReferenceAdd(1, self.skeleton_root)  # Parent
            
            # Do not use Snap to ensure null exactly matches root with no offset
            capture_constraint.Snap = False
            capture_constraint.Active = True
            
            # Plot the capture null (with constraints still active on root)
            FBBeginChangeAllModels()
            for model in self.selected_nodes:
                model.Selected = False
            capture_null.Selected = True
            FBEndChangeAllModels()
            
            plot_options = FBPlotOptions()
            plot_options.ConstantKeyReducerKeepOneKey = False
            plot_options.PlotAllTakes = False
            plot_options.PlotOnFrame = True
            plot_options.PlotPeriod = FBTime(0, 0, 0, 1)
            plot_options.UseConstantKeyReducer = False
            
            FBSystem().CurrentTake.PlotTakeOnSelected(plot_options)
            
            # Remove the capture constraint
            capture_constraint.Active = False
            capture_constraint.FBDelete()
            
            # If root has constraints, disable them now
            disabled_constraints = []
            if has_constraints:
                disabled_constraints = self.disable_root_constraints()
                
                # Plot the root animation from the capture null
                restore_constraint = constraint_manager.TypeCreateConstraint("Parent/Child")
                restore_constraint.Name = "TEMP_RESTORE_CONSTRAINT"
                
                # Set references (child = root, parent = capture null)
                restore_constraint.ReferenceAdd(0, self.skeleton_root)  # Child
                restore_constraint.ReferenceAdd(1, capture_null)  # Parent
                
                # Do NOT use Snap - we want to transfer the exact animation without offset
                restore_constraint.Snap = False
                restore_constraint.Active = True
                
                # Plot the root
                FBBeginChangeAllModels()
                for model in self.selected_nodes:
                    model.Selected = False
                self.skeleton_root.Selected = True
                FBEndChangeAllModels()
                
                FBSystem().CurrentTake.PlotTakeOnSelected(plot_options)
                
                # Clean up restore constraint
                restore_constraint.Active = False
                restore_constraint.FBDelete()
            
            # Restore skeleton selection
            self.select_skeleton_hierarchy()
            
            return {
                'capture_null': capture_null,
                'has_constraints': has_constraints,
                'disabled_constraints': disabled_constraints
            }
            
        except Exception as e:
            # print(f"Error preparing constrained root: {e}")
            return None
    
    def apply_axis_conversion_to_root(self, capture_null, target_axis):
        """Apply axis rotation to an already prepared root"""
        if not self.skeleton_root or not capture_null:
            return False
            
        try:
            # Create axis conversion null
            axis_null = FBModelNull("TEMP_AXIS_PARENT")
            axis_null.Show = False
            
            # Set rotation based on target axis
            if target_axis == "Y-up":
                # For Y-up, apply 0 rotation (identity transform)
                axis_null.Rotation = FBVector3d(0.0, 0.0, 0.0)
            elif target_axis == "Z-up":
                # Apply only X rotation for Z-up (no Y rotation)
                axis_null.Rotation = FBVector3d(-90.0, 0.0, 0.0)
            elif target_axis == "Manual Rotations":
                # Get values from rotation input fields
                try:
                    x_rot = float(self.x_rotation_input.text())
                    y_rot = float(self.y_rotation_input.text())
                    z_rot = float(self.z_rotation_input.text())
                    axis_null.Rotation = FBVector3d(x_rot, y_rot, z_rot)
                except ValueError:
                    # Default to Z-up rotation if there's an error parsing values
                    self.debug_print("Error parsing rotation values, using default Z-up rotation")
                    axis_null.Rotation = FBVector3d(-90.0, 0.0, 0.0)
            else:
                # Default to no rotation for any undefined axis
                axis_null.Rotation = FBVector3d(0.0, 0.0, 0.0)
            
            # Parent the capture null to the axis null
            player_control = FBPlayerControl()
            current_take = FBSystem().CurrentTake
            first_frame = current_take.LocalTimeSpan.GetStart()
            player_control.Goto(first_frame)
            FBSystem().Scene.Evaluate()
            
            capture_null.Parent = axis_null
            
            # Create constraint from capture null (now rotated) to root
            constraint_manager = FBConstraintManager()
            final_constraint = constraint_manager.TypeCreateConstraint("Parent/Child")
            final_constraint.Name = "TEMP_AXIS_CONSTRAINT"
            
            # Set references (child = root, parent = capture null)
            final_constraint.ReferenceAdd(0, self.skeleton_root)  # Child
            final_constraint.ReferenceAdd(1, capture_null)  # Parent
            
            # Do NOT use Snap - we want to transfer the exact rotation without offset
            final_constraint.Snap = False
            final_constraint.Active = True
            FBSystem().Scene.Evaluate()
            
            # Plot the root with axis conversion applied
            FBBeginChangeAllModels()
            for model in self.selected_nodes:
                model.Selected = False
            self.skeleton_root.Selected = True
            FBEndChangeAllModels()
            
            plot_options = FBPlotOptions()
            plot_options.ConstantKeyReducerKeepOneKey = False
            plot_options.PlotAllTakes = False
            plot_options.PlotOnFrame = True
            plot_options.PlotPeriod = FBTime(0, 0, 0, 1)
            plot_options.UseConstantKeyReducer = False
            
            FBSystem().CurrentTake.PlotTakeOnSelected(plot_options)
            
            # Clean up
            final_constraint.Active = False
            final_constraint.FBDelete()
            axis_null.FBDelete()
            
            # Restore skeleton selection
            self.select_skeleton_hierarchy()
            
            return True
            
        except Exception as e:
            # print(f"Error applying axis conversion: {e}")
            return False
    
    def cleanup_after_export(self, export_data):
        """Clean up after export based on what was done during preparation"""
        if not export_data:
            return
            
        try:
            capture_null = export_data.get('capture_null')
            has_constraints = export_data.get('has_constraints', False)
            disabled_constraints = export_data.get('disabled_constraints', [])
            unparented = export_data.get('unparented', False)
            backup_null = export_data.get('backup_null')
            
            # Clean up capture null
            if capture_null:
                capture_null.Selected = False
                capture_null.FBDelete()
            
            # If root had constraints, clean up and re-enable them
            if has_constraints and disabled_constraints:
                # Remove all keys from root (for cleaner result)
                self.remove_all_keys_from_root()
                
                # Re-enable the constraints
                self.restore_constraints(disabled_constraints)
            
            # Reparent the skeleton root if it was unparented
            if unparented:
                try:
                    self.reparent_skeleton_root()
                    self.debug_print("Successfully reparented skeleton root during cleanup")
                except Exception as e:
                    self.debug_print(f"Warning: Error reparenting skeleton root: {e}")
            
            # Restore the original animation from the backup null
            if backup_null:
                try:
                    self.restore_original_root_animation(backup_null)
                    self.debug_print("Successfully restored original root animation during cleanup")
                except Exception as e:
                    self.debug_print(f"Warning: Error restoring original root animation: {e}")
            
        except Exception as e:
            # print(f"Error during cleanup: {e}")
            pass
    
    
    def disable_root_constraints(self):
        """Find and disable any constraints affecting the root"""
        if not self.skeleton_root:
            # print("No skeleton root found")
            return []
            
        disabled_constraints = []
        
        try:
            # print(f"\n=== DISABLE ROOT CONSTRAINTS ===")
            # print(f"Root: {self.skeleton_root.Name}")
            # print(f"Root position before disable: T={self.skeleton_root.Translation}, R={self.skeleton_root.Rotation}")
            
            # Get all destinations (things that this object affects)
            try:
                dst_count = self.skeleton_root.GetDstCount()
                # print(f"GetDstCount: {dst_count}")
                for i in range(dst_count):
                    const = self.skeleton_root.GetDst(i)
                    if isinstance(const, FBConstraint):
                        # print(f"  Found constraint (as source): {const.Name}")
                        # print(f"    Type: {const.ClassName()}")
                        # print(f"    Active: {const.Active}")
                        if const.Active:
                            const.Active = False
                            disabled_constraints.append(const)
                            # print(f"    ** Disabled constraint: {const.Name}")
            except Exception as e:
                pass  # Error handling disabled for performance
            
            # Get all sources (things that affect this object)
            try:
                src_count = self.skeleton_root.GetSrcCount()
                # print(f"GetSrcCount: {src_count}")
                for i in range(src_count):
                    const = self.skeleton_root.GetSrc(i)
                    if isinstance(const, FBConstraint):
                        # print(f"  Found constraint (as destination): {const.Name}")
                        # print(f"    Type: {const.ClassName()}")
                        # print(f"    Active: {const.Active}")
                        if const.Active:
                            const.Active = False
                            disabled_constraints.append(const)
                            # print(f"    ** Disabled constraint: {const.Name}")
            except Exception as e:
                pass  # Error handling disabled for performance
            
            # print(f"\nTotal constraints disabled: {len(disabled_constraints)}")
            for constraint in disabled_constraints:
                pass  # Constraint listing disabled for performance
            
            # print(f"Root position after disable: T={self.skeleton_root.Translation}, R={self.skeleton_root.Rotation}")
            # print("=== DISABLE COMPLETE ===")
            return disabled_constraints
            
        except Exception as e:
            # print(f"Error disabling root constraints: {e}")
            import traceback
            traceback.print_exc()
            return disabled_constraints
    
    def restore_constraints(self, constraints):
        """Re-enable previously disabled constraints"""
        if not constraints:
            return
            
        # print(f"\n=== RESTORE CONSTRAINTS ===")
        # print(f"Restoring {len(constraints)} constraints...")
        for constraint in constraints:
            try:
                constraint.Active = True
                # print(f"  Re-enabled constraint: {constraint.Name}")
            except Exception as e:
                pass  # Error handling disabled for performance
        
        # Force scene evaluation to update the root with constraint effects
        # print("Evaluating scene to update constraint effects...")
        FBSystem().Scene.Evaluate()
        
        # Go to first frame and evaluate again
        player_control = FBPlayerControl()
        current_take = FBSystem().CurrentTake
        first_frame = current_take.LocalTimeSpan.GetStart()
        player_control.Goto(first_frame)
        FBSystem().Scene.Evaluate()
        
        # print("=== RESTORE CONSTRAINTS COMPLETE ===")
    
    def store_original_root_animation(self):
        """Store the original root animation to a null for later restoration"""
        if not self.skeleton_root:
            return None
            
        try:
            # Create a backup null to store the original animation
            backup_null = FBModelNull("TEMP_ORIGINAL_BACKUP")
            backup_null.Show = False
            
            # Create constraint to capture the root's original animation
            constraint_manager = FBConstraintManager()
            backup_constraint = constraint_manager.TypeCreateConstraint("Parent/Child")
            backup_constraint.Name = "TEMP_BACKUP_CONSTRAINT"
            
            # Set references (child = backup null, parent = root)
            backup_constraint.ReferenceAdd(0, backup_null)  # Child
            backup_constraint.ReferenceAdd(1, self.skeleton_root)  # Parent
            
            # Do not use Snap to ensure exact copy
            backup_constraint.Snap = False
            backup_constraint.Active = True
            
            # Plot the backup null to capture the animation
            FBBeginChangeAllModels()
            for model in self.selected_nodes:
                model.Selected = False
            backup_null.Selected = True
            FBEndChangeAllModels()
            
            plot_options = FBPlotOptions()
            plot_options.ConstantKeyReducerKeepOneKey = False
            plot_options.PlotAllTakes = False
            plot_options.PlotOnFrame = True
            plot_options.PlotPeriod = FBTime(0, 0, 0, 1)
            plot_options.UseConstantKeyReducer = False
            
            FBSystem().CurrentTake.PlotTakeOnSelected(plot_options)
            
            # Remove the backup constraint
            backup_constraint.Active = False
            backup_constraint.FBDelete()
            
            self.debug_print("Successfully stored original root animation to backup null")
            return backup_null
            
        except Exception as e:
            self.debug_print(f"Error storing original root animation: {e}")
            return None
    
    def restore_original_root_animation(self, backup_null):
        """Restore the original root animation from the backup null"""
        if not self.skeleton_root or not backup_null:
            return False
            
        try:
            self.debug_print("Restoring original root animation from backup null")
            
            # Create constraint from backup null to root
            constraint_manager = FBConstraintManager()
            restore_constraint = constraint_manager.TypeCreateConstraint("Parent/Child")
            restore_constraint.Name = "TEMP_RESTORE_ORIGINAL_CONSTRAINT"
            
            # Set references (child = root, parent = backup null)
            restore_constraint.ReferenceAdd(0, self.skeleton_root)  # Child
            restore_constraint.ReferenceAdd(1, backup_null)  # Parent
            
            # Do not use Snap to ensure exact transfer
            restore_constraint.Snap = False
            restore_constraint.Active = True
            
            # Plot the root to restore original animation
            FBBeginChangeAllModels()
            for model in self.selected_nodes:
                model.Selected = False
            self.skeleton_root.Selected = True
            FBEndChangeAllModels()
            
            plot_options = FBPlotOptions()
            plot_options.ConstantKeyReducerKeepOneKey = False
            plot_options.PlotAllTakes = False
            plot_options.PlotOnFrame = True
            plot_options.PlotPeriod = FBTime(0, 0, 0, 1)
            plot_options.UseConstantKeyReducer = False
            
            FBSystem().CurrentTake.PlotTakeOnSelected(plot_options)
            
            # Clean up restore constraint
            restore_constraint.Active = False
            restore_constraint.FBDelete()
            
            # Clean up backup null
            backup_null.Selected = False
            backup_null.FBDelete()
            
            self.debug_print("Successfully restored original root animation")
            return True
            
        except Exception as e:
            self.debug_print(f"Error restoring original root animation: {e}")
            return False
    
    def prepare_root_for_export(self, target_axis=None):
        """Prepare the root for export with optional axis conversion"""
        if not self.skeleton_root:
            return None
            
        try:
            # First, store the original root animation for later restoration
            backup_null = self.store_original_root_animation()
            
            # Next, handle constraint-based plotting (always done)
            export_data = self.prepare_constrained_root_for_export()
            if not export_data:
                return None
                
            # Store the backup null for restoration after export
            export_data['backup_null'] = backup_null
                
            # Now unparent the root AFTER animation is captured
            unparented = False
            try:
                if self.unparent_skeleton_root():
                    unparented = True
                    self.debug_print("Successfully unparented skeleton root after animation capture")
            except Exception as e:
                self.debug_print(f"Warning: Error unparenting skeleton root: {e}")
            
            # Store the unparenting status in export_data
            export_data['unparented'] = unparented
            
            # Always apply axis conversion, using 0 rotation for Y-up
            capture_null = export_data.get('capture_null')
            if capture_null:
                success = self.apply_axis_conversion_to_root(capture_null, target_axis)
                if not success:
                    # Clean up on failure
                    self.cleanup_after_export(export_data)
                    return None
            
            return export_data
            
        except Exception as e:
            # print(f"Error preparing root for export: {e}")
            return None
    
    
    def create_progress_bar(self, parent_layout):
        """Create the progress bar for export tracking"""
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        parent_layout.addWidget(self.progress_bar)
    
    def create_folder_selection(self, parent_layout):
        """Create the global export folder selection UI"""
        folder_frame = QWidget()
        folder_layout = QHBoxLayout(folder_frame)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        
        folder_label = QLabel("Global Export Folder:")
        folder_layout.addWidget(folder_label)
        
        self.folder_entry = QLineEdit()
        default_folder = self.get_default_export_folder()
        self.full_export_folder = default_folder
        self.folder_entry.setText(self.truncate_path(default_folder))
        folder_layout.addWidget(self.folder_entry, 1)  # Stretch factor 1
        
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.on_global_browse)
        folder_layout.addWidget(browse_button)
        
        # Add information button
        info_button = QPushButton("ℹ")
        info_button.setFixedSize(24, 24)
        info_button.setToolTip("Show help information")
        info_button.clicked.connect(self.show_help_dialog)
        folder_layout.addWidget(info_button)
        
        parent_layout.addWidget(folder_frame)
    
    def on_global_browse(self):
        """Handle browse button click for global export folder"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select Global Export Folder", 
            self.full_export_folder
        )
        if folder:
            self.full_export_folder = folder
            self.folder_entry.setText(self.truncate_path(folder))
    
    def get_collapsible_group_style(self):
        """Get the style for collapsible group boxes"""
        return """
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 3px;
                margin-top: 6px;
                padding-top: 6px;
                padding-bottom: 6px;
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
    
    def get_inner_group_style(self):
        """Get the style for inner group boxes"""
        return """
            QGroupBox {
                font-weight: normal;
                border: 1px solid #888888;
                border-radius: 3px;
                margin-top: 6px;
                padding-top: 6px;
                padding-bottom: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """
        
    def create_options_panel(self, parent_layout):
        """Create collapsible export options panel"""
        # Get saved options expanded state, default to True (expanded) for first use
        settings = self.load_settings()
        expanded = settings.get("options_expanded", True)
        
        # Create collapsible group for options
        self.options_group = QGroupBox("▼ Export Options" if expanded else "► Export Options")
        self.options_group.setStyleSheet(self.get_collapsible_group_style())
        self.options_group.mousePressEvent = lambda event: self.toggle_options_group()
        self.options_group_expanded = expanded
        
        # Create options container widget
        self.options_widget = QWidget()
        options_layout = QGridLayout(self.options_widget)
        options_layout.setContentsMargins(5, 5, 5, 5)
        
        # File prefix
        prefix_label = QLabel("Filename Prefix:")
        options_layout.addWidget(prefix_label, 0, 0)
        
        self.prefix_entry = QLineEdit()
        default_prefix = self.load_settings().get("prefix", "")
        self.prefix_entry.setText(default_prefix)
        self.prefix_entry.textChanged.connect(self.save_prefix)  # Save prefix on change
        options_layout.addWidget(self.prefix_entry, 0, 1)
        
        # JSON settings file button
        json_btn = QPushButton("Open Settings File")
        json_btn.clicked.connect(self.open_settings_file)
        options_layout.addWidget(json_btn, 0, 2)
        
        # Animation options
        anim_group = QGroupBox("Animation Options")
        anim_group.setStyleSheet(self.get_inner_group_style())
        anim_layout = QHBoxLayout(anim_group)
        anim_layout.setContentsMargins(10, 5, 10, 5)  # Reduced vertical margins
        anim_layout.setSpacing(10)  # Reduced spacing
        
        self.bake_anim_cb = QCheckBox("Bake Animation")
        self.bake_anim_cb.setChecked(self.load_settings().get("bake_animation", True))
        anim_layout.addWidget(self.bake_anim_cb)
        
        self.export_log_cb = QCheckBox("Show Export Log")
        self.export_log_cb.setChecked(self.load_settings().get("export_log", True))
        anim_layout.addWidget(self.export_log_cb)
        
        # Add a stretch to push checkboxes to the left
        anim_layout.addStretch(1)
        
        # Set a fixed size height to reduce empty space
        anim_group.setFixedHeight(60)
        
        options_layout.addWidget(anim_group, 1, 0, 1, 3)
        
        # Axis conversion options
        axis_group = QGroupBox("Axis Conversion")
        axis_group.setStyleSheet(self.get_inner_group_style())
        axis_layout = QGridLayout(axis_group)
        axis_layout.setContentsMargins(10, 5, 10, 5)  # Reduced vertical margins
        axis_layout.setSpacing(5)  # Reduced spacing
        
        # FBX SDK Axis Conversion option - NOW FIRST
        sdk_axis_label = QLabel("FBX SDK Axis Conversion:")
        enabled = FBX_SDK_AVAILABLE
        sdk_axis_label.setEnabled(enabled)
        if not enabled:
            sdk_axis_label.setStyleSheet("color: gray;")
            sdk_axis_label.setToolTip("FBX SDK not installed - SDK axis conversion unavailable")
        axis_layout.addWidget(sdk_axis_label, 0, 0)
        
        self.sdk_up_axis_combo = QComboBox()
        self.sdk_up_axis_combo.addItems(["Y-up (None)", "Z-up"])
        # Get saved value, default to Y-up (None)
        saved_sdk_axis = self.load_settings().get("fbx_sdk_axis_conversion", {}).get("target_axis", "Y-up")
        # Force to Y-up unless explicitly enabled with a different value
        if not self.load_settings().get("fbx_sdk_axis_conversion", {}).get("enabled", False):
            saved_sdk_axis = "Y-up"  # Force to Y-up if not enabled
            
        # Handle Z-down in previous settings (now removed), default to Z-up
        if saved_sdk_axis == "Z-down":
            saved_sdk_axis = "Z-up"
            
        self.sdk_up_axis_combo.setCurrentText("Y-up (None)" if saved_sdk_axis == "Y-up" else saved_sdk_axis)
        self.sdk_up_axis_combo.setEnabled(enabled)
        if not enabled:
            # Gray out dropdown with clear message when FBX SDK is not available
            self.sdk_up_axis_combo.setStyleSheet("color: gray; background-color: #eeeeee;")
            self.sdk_up_axis_combo.setToolTip("FBX SDK not installed - Please install FBX SDK to use this feature")
        axis_layout.addWidget(self.sdk_up_axis_combo, 0, 1)
        
        # Plotted Axis Conversion - NOW SECOND
        axis_label = QLabel("Plotted Axis Conversion:")
        axis_layout.addWidget(axis_label, 1, 0)
        
        self.up_axis_combo = QComboBox()
        self.up_axis_combo.addItems(["Y-up (None)", "Z-up", "Manual Rotations"])
        # Get saved value, default to Y-up (None)
        saved_axis = self.load_settings().get("axis_conversion", {}).get("target_axis", "Y-up")
        # Force to Y-up unless explicitly enabled with a different value
        if not self.load_settings().get("axis_conversion", {}).get("enabled", False):
            saved_axis = "Y-up"  # Force to Y-up if not enabled
            
        # Handle Z-down in previous settings, convert to Manual Rotations
        if saved_axis == "Z-down":
            saved_axis = "Manual Rotations"
            
        self.up_axis_combo.setCurrentText("Y-up (None)" if saved_axis == "Y-up" else saved_axis)
        axis_layout.addWidget(self.up_axis_combo, 1, 1)
        
        # Add rotation input fields
        rotation_frame = QWidget()
        rotation_layout = QHBoxLayout(rotation_frame)
        rotation_layout.setContentsMargins(0, 5, 0, 0)
        
        rotation_label = QLabel("Manual Rotation (X, Y, Z):")
        rotation_layout.addWidget(rotation_label)
        
        # Get manual rotation values from settings
        saved_manual_rotation = self.load_settings().get("axis_conversion", {}).get("manual_rotation", {})
        default_x = saved_manual_rotation.get("x", -90.0) if saved_axis == "Manual Rotations" else 0.0
        default_y = saved_manual_rotation.get("y", 0.0)
        default_z = saved_manual_rotation.get("z", 0.0)
        
        # X rotation
        self.x_rotation_input = QLineEdit()
        self.x_rotation_input.setFixedWidth(50)
        self.x_rotation_input.setValidator(QDoubleValidator())
        self.x_rotation_input.setText(str(default_x))
        rotation_layout.addWidget(self.x_rotation_input)
        
        # Y rotation
        self.y_rotation_input = QLineEdit()
        self.y_rotation_input.setFixedWidth(50)
        self.y_rotation_input.setValidator(QDoubleValidator())
        self.y_rotation_input.setText(str(default_y))
        rotation_layout.addWidget(self.y_rotation_input)
        
        # Z rotation
        self.z_rotation_input = QLineEdit()
        self.z_rotation_input.setFixedWidth(50)
        self.z_rotation_input.setValidator(QDoubleValidator())
        self.z_rotation_input.setText(str(default_z))
        rotation_layout.addWidget(self.z_rotation_input)
        
        axis_layout.addWidget(rotation_frame, 2, 0, 1, 2)
        
        # Set initial state of rotation inputs
        self.update_rotation_inputs_state()
        
        # Connect signal to update state when selection changes
        self.up_axis_combo.currentTextChanged.connect(self.update_rotation_inputs_state)
        
        # Set fixed height for the axis group
        axis_group.setFixedHeight(130)
        
        options_layout.addWidget(axis_group, 2, 0, 1, 3)
        
        # Skeleton info
        skeleton_group = QGroupBox("Skeleton Information")
        skeleton_group.setStyleSheet(self.get_inner_group_style())
        skeleton_layout = QVBoxLayout(skeleton_group)
        skeleton_layout.setContentsMargins(10, 5, 10, 5)  # Reduced vertical margins
        
        self.skeleton_info_label = QLabel("Skeleton Root: Not detected\nSelected Nodes: 0")
        skeleton_layout.addWidget(self.skeleton_info_label)
        
        # Set fixed height for the skeleton group
        skeleton_group.setFixedHeight(60)
        
        options_layout.addWidget(skeleton_group, 3, 0, 1, 3)
        
        # Add options widget to group
        group_layout = QVBoxLayout(self.options_group)
        group_layout.setContentsMargins(10, 20, 10, 10)  # Add top margin for title
        group_layout.setSpacing(0)
        group_layout.addWidget(self.options_widget)
        
        # Set initial visibility based on saved state
        self.options_widget.setVisible(self.options_group_expanded)
        
        # Adjust height if collapsed
        if not self.options_group_expanded:
            self.options_group.setFixedHeight(30)
        else:
            self.options_group.setMaximumHeight(16777215)
        
        # Add group to parent layout
        parent_layout.addWidget(self.options_group)
        
    # Removed on_axis_combo_changed and on_sdk_axis_combo_changed as we no longer use checkboxes
        
    def open_settings_file(self):
        """Open the settings JSON file in the default text editor"""
        settings_file = self.get_settings_file()
        
        if not os.path.exists(settings_file):
            # Create the file if it doesn't exist
            try:
                with open(settings_file, "w") as f:
                    json.dump({}, f, indent=4)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create settings file: {e}")
                return
                
        try:
            if sys.platform.startswith('win'):
                os.startfile(settings_file)
            elif sys.platform.startswith('darwin'):  # macOS
                os.system(f'open "{settings_file}"')
            else:  # Linux
                os.system(f'xdg-open "{settings_file}"')
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open settings file: {e}")
    
    def toggle_options_group(self):
        """Toggle visibility of options panel"""
        self.options_group_expanded = not self.options_group_expanded
        
        # Update arrow indicator
        title = self.options_group.title()
        if self.options_group_expanded:
            # Expand the options
            self.options_group.setTitle(title.replace("►", "▼"))
            self.options_group.setMaximumHeight(16777215)  # Default maximum height
            
            # Set explicit height for visibility
            self.options_widget.setMinimumHeight(350)
            
            # Show content AFTER setting sizes
            self.options_widget.setVisible(True)
            
            # Force layout update
            QApplication.processEvents()
            
            # Now adjust the window size to accommodate content
            # First get the minimum required height
            required_height = self.options_group.sizeHint().height() + 350  # Add buffer for other content
            
            # Check the current window height
            current_height = self.height()
            if current_height < required_height:
                # Resize window to fit content
                self.resize(self.width(), required_height)
        else:
            # Collapse the options
            self.options_group.setTitle(title.replace("▼", "►"))
            self.options_widget.setVisible(False)
            self.options_group.setFixedHeight(30)
            
        # Save state to settings
        settings = self.load_settings()
        settings["options_expanded"] = self.options_group_expanded
        self.save_settings(settings)
    
    def show_help_dialog(self):
        """Show help information dialog"""
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("FBX Exporter Help")
        help_dialog.setFixedSize(600, 400)
        
        layout = QVBoxLayout(help_dialog)
        
        # Create a scroll area to ensure content fits
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        # Create content widget for the scroll area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # Help content using HTML formatting
        help_text = """<html>
        <h3>FBX Exporter - Quick Guide</h3>
        
        <p><b>Global Export Folder:</b> Base directory where exports will be saved. Uses groups for organization.</p>
        
        <p><b>File Prefix:</b> Optional prefix added to all exported filenames.</p>
        
        <h4>Animation Options</h4>
        <p><b>Bake Animation:</b> When enabled, plots animation for all skeleton joints before export using Unroll filter, making it independent of constraints and resulting in smoother rotations. After export, animation keys are removed to reduce scene size.</p>
        <p><b>Show Export Log:</b> Displays a summary of exports after completion.</p>
        
        <h4>Axis Conversion</h4>
        <p><b>FBX SDK Axis Conversion:</b> Uses FBX SDK to convert axis system <i>after</i> export. Recommended for compatibility with software expecting Z-up axis systems. Doesn't modify the scene.</p>
        
        <p><b>Plotted Axis Conversion:</b> Uses constraints to temporarily rotate the skeleton during export. This method plots the animation in the new orientation before export.</p>
        
        <p><b>Rotation Presets:</b></p>
        <ul>
            <li><b>Y-up (None):</b> No rotation applied (X=0, Y=0, Z=0)</li>
            <li><b>Z-up:</b> Rotates around X-axis to convert Y-up to Z-up (X=-90, Y=0, Z=0)</li>
            <li><b>Manual Rotations:</b> Use custom rotation values from the X, Y, Z input fields</li>
        </ul>
        
        <h4>Takes</h4>
        <p>Select takes to export by checking them in the list. Use groups (==Group Name==) to organize takes and define separate export locations.</p>
        <p>Toggle groups by clicking their header. Toggle all takes with the "Toggle All" button.</p>
        
        <p><i>Click Export to process all selected takes according to these settings.</i></p>
        </html>"""
        
        help_label = QLabel(help_text)
        help_label.setWordWrap(True)
        help_label.setTextFormat(Qt.RichText)
        content_layout.addWidget(help_label)
        
        # Add some spacing at the bottom
        content_layout.addStretch(1)
        
        # Set the content widget in the scroll area
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        # Add a close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(help_dialog.accept)
        close_button.setMaximumWidth(100)
        close_button_layout = QHBoxLayout()
        close_button_layout.addStretch(1)
        close_button_layout.addWidget(close_button)
        close_button_layout.addStretch(1)
        layout.addLayout(close_button_layout)
        
        # Show the dialog as modal
        help_dialog.exec_()
        
    def select_skeleton_hierarchy(self):
        """Select the Skeleton Root node and all its Skeleton Node children using a simpler approach"""
        selection = FBModelList()
        FBGetSelectedModels(selection)
        for model in selection:
            model.Selected = False
            
        skeleton_root = None
        potential_root_names = ["root", "Root", "Skeleton_Root", "SKELETON_ROOT", "SkeletonRoot"]
        for name in potential_root_names:
            try:
                root = FBFindModelByLabelName(name)
                if root:
                    skeleton_root = root
                    break
            except Exception as e:
                # print(f"Error looking for {name}: {e}")
                continue
                
        if not skeleton_root:
            self.skeleton_info_label.setText("Skeleton Root: Not detected\nSelected Nodes: 0")
            return False
        
        self.skeleton_root = skeleton_root
        if hasattr(skeleton_root, 'Parent') and skeleton_root.Parent:
            skeleton_root.Parent.Selected = False
        skeleton_root.Selected = True
        try:
            self.select_children_simple(skeleton_root)
        except Exception as e:
            pass  # Error handling disabled for performance
        self.deselect_null_objects()
        selection = FBModelList()
        FBGetSelectedModels(selection)
        self.selected_nodes_count = len(selection)
        self.selected_nodes = [selection[i] for i in range(selection.GetCount())]
        if self.skeleton_info_label:
            self.skeleton_info_label.setText(
                f"Skeleton Root: {self.skeleton_root.Name if hasattr(self.skeleton_root, 'Name') else 'unknown'}\n"
                f"Selected Nodes: {self.selected_nodes_count}"
            )
        return self.selected_nodes_count > 0
        
    def select_children_simple(self, node):
        """Select all children of this node using a simpler approach"""
        try:
            try:
                for child in node.Children:
                    self.process_child(child)
            except TypeError:
                try:
                    count = node.Children.GetCount()
                    for i in range(count):
                        child = node.Children.GetAt(i)
                        self.process_child(child)
                except:
                    i = 0
                    while True:
                        try:
                            child = node.Children[i]
                            self.process_child(child)
                            i += 1
                        except IndexError:
                            break
                        except Exception as e:
                            # print(f"Error accessing child {i}: {e}")
                            i += 1
                            if i > 1000:
                                break
        except Exception as e:
            pass  # Error handling disabled for performance
    
    def process_child(self, child):
        """Process a single child node - select it if not a null object and recurse to its children"""
        try:
            is_null = False
            if hasattr(child, 'Name'):
                name = child.Name.lower()
                if 'null' in name or 'dummy' in name or 'grp' in name:
                    is_null = True
            if hasattr(child, 'ClassName'):
                class_name = child.ClassName()
                if 'Null' in class_name or 'Group' in class_name:
                    is_null = True
            if not is_null:
                child.Selected = True
            self.select_children_simple(child)
        except Exception as e:
            pass  # Error handling disabled for performance
            
    def deselect_null_objects(self):
        """Deselect any null objects that might be selected"""
        selection = FBModelList()
        FBGetSelectedModels(selection)
        for model in selection:
            is_null = False
            if hasattr(model, 'Name'):
                name = model.Name.lower()
                if 'null' in name or 'dummy' in name or 'grp' in name:
                    is_null = True
            if hasattr(model, 'ClassName'):
                class_name = model.ClassName()
                if 'Null' in class_name or 'Group' in class_name:
                    is_null = True
            if is_null:
                model.Selected = False
                
    def create_takes_selection(self, parent_layout):
        """Create the UI for selecting takes to export"""
        takes_group = QGroupBox("Takes")
        takes_layout = QVBoxLayout(takes_group)
        
        # Global toggle button
        global_toggle_frame = QWidget()
        global_toggle_layout = QHBoxLayout(global_toggle_frame)
        global_toggle_layout.setContentsMargins(0, 0, 0, 0)
        
        global_toggle_btn = QPushButton("Toggle All")
        global_toggle_btn.setFixedWidth(100)
        global_toggle_layout.addWidget(global_toggle_btn)
        global_toggle_layout.addStretch(1)
        
        takes_layout.addWidget(global_toggle_frame)
        
        # Scroll area for takes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        takes_container = QWidget()
        takes_container_layout = QVBoxLayout(takes_container)
        takes_container_layout.setContentsMargins(0, 0, 0, 0)
        takes_container_layout.setSpacing(0)
        
        scroll_area.setWidget(takes_container)
        takes_layout.addWidget(scroll_area)
        
        # Get scene and takes
        scene = FBSystem().Scene
        if not scene or not scene.Takes:
            self.close()
            return
        
        saved_scene = self.load_settings()
        groups = self.organize_takes_into_groups(scene.Takes)
        
        # Create UI for each take group
        all_checkboxes = []
        self.group_info_list = []
        
        for group in groups:
            group_key = group["header"].Name if group["header"] else "ungrouped"
            saved_group_selections = saved_scene.get("selections", {}).get(group_key, {})
            
            if group["header"]:
                # Create collapsible group
                # Get the stored collapse state from file
                states = load_group_states()
                initial_collapsed = states.get(group["header"].Name, False)
                
                group_box = CollapsibleGroupBox(
                    group["header"].Name, 
                    initial_collapsed=initial_collapsed,
                    collapse_callback=self.on_group_collapse_change
                )
                
                # Store reference to group box
                self.group_boxes[group["header"].Name] = group_box
                group_info = {
                    "header_text": group["header"].Name,
                    "checkbox_vars": {},
                    "check_labels": {},
                    "group_box": group_box
                }
                
                # Add group folder override
                override_frame = QWidget()
                override_layout = QHBoxLayout(override_frame)
                override_layout.setContentsMargins(0, 0, 0, 0)
                override_layout.setSpacing(2)  # Reduce spacing
                
                # Get the override path from settings (empty string if not set)
                override_default = saved_scene.get("groups", {}).get(group["header"].Name, "")
                group_info["override_full"] = override_default
                
                override_entry = QLineEdit()
                # Only show the path if there's a user-set override
                if override_default:
                    override_entry.setText(self.truncate_path(override_default))
                
                override_entry.setMaximumWidth(200)  # Limit width of override path field
                override_entry.textChanged.connect(lambda text, info=group_info: self.save_group_override(text, info))
                override_layout.addWidget(override_entry, 1)
                
                override_browse = QPushButton("Browse")
                override_browse.setMaximumWidth(70)  # Make browse button smaller
                override_browse.clicked.connect(lambda checked=False, info=group_info: self.on_group_browse(info))
                override_layout.addWidget(override_browse)
                
                group_info["override_entry"] = override_entry
                
                # Add to header layout with right alignment
                spacer = QWidget()
                spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                group_box.header_layout.addWidget(spacer)
                group_box.header_layout.addWidget(override_frame)
                group_box.header_layout.setContentsMargins(5, 5, 0, 5)  # Remove right margin
                
                # Add take checkboxes
                group_checkbox_list = []
                for take in group["takes"]:
                    default_sel = saved_group_selections.get(take.Name, True)
                    take_row = QWidget()
                    take_layout = QHBoxLayout(take_row)
                    take_layout.setContentsMargins(0, 0, 0, 0)
                    
                    checkbox = QCheckBox(take.Name)
                    checkbox.setChecked(default_sel)
                    take_layout.addWidget(checkbox)
                    
                    export_info = saved_scene.get("takes", {}).get(take.Name, None)
                    mark_text = "✔" if export_info is not None and export_info.get("exported", False) else ""
                    mark_label = QLabel(mark_text)
                    mark_label.setStyleSheet("color: green;")
                    take_layout.addWidget(mark_label)
                    take_layout.addStretch(1)
                    
                    group_box.add_widget(take_row)
                    group_info["checkbox_vars"][take] = checkbox
                    group_info["check_labels"][take] = mark_label
                    group_checkbox_list.append(checkbox)
                    all_checkboxes.append(checkbox)
                    
                    # Connect change event
                    checkbox.stateChanged.connect(
                        lambda _, box=group_box, checkboxes=group_checkbox_list: 
                        box.set_count(sum(1 for cb in checkboxes if cb.isChecked()), len(checkboxes))
                    )
                
                # Set initial count
                group_box.set_count(sum(1 for cb in group_checkbox_list if cb.isChecked()), len(group_checkbox_list))
                
                # Connect title button to toggle all checkboxes in group
                # Fix: Use a properly constructed lambda without expecting the clicked parameter
                group_box.title_button.clicked.connect(
                    lambda checked=False, checkboxes=group_checkbox_list: 
                    self.toggle_checkboxes(checkboxes)
                )
                
                takes_container_layout.addWidget(group_box)
                self.group_info_list.append(group_info)
            else:
                # For ungrouped takes
                ungrouped_info = {
                    "checkbox_vars": {},
                    "check_labels": {}
                }
                
                ungrouped_group = QGroupBox("Ungrouped Takes")
                ungrouped_layout = QVBoxLayout(ungrouped_group)
                
                for take in group["takes"]:
                    default_sel = saved_group_selections.get(take.Name, True)
                    take_row = QWidget()
                    take_layout = QHBoxLayout(take_row)
                    take_layout.setContentsMargins(0, 0, 0, 0)
                    
                    checkbox = QCheckBox(take.Name)
                    checkbox.setChecked(default_sel)
                    take_layout.addWidget(checkbox)
                    
                    export_info = saved_scene.get("takes", {}).get(take.Name, None)
                    mark_text = "✔" if export_info is not None and export_info.get("exported", False) else ""
                    mark_label = QLabel(mark_text)
                    mark_label.setStyleSheet("color: green;")
                    take_layout.addWidget(mark_label)
                    take_layout.addStretch(1)
                    
                    ungrouped_layout.addWidget(take_row)
                    ungrouped_info["checkbox_vars"][take] = checkbox
                    ungrouped_info["check_labels"][take] = mark_label
                    all_checkboxes.append(checkbox)
                
                takes_container_layout.addWidget(ungrouped_group)
                self.group_info_list.append(ungrouped_info)
        
        # Connect global toggle button
        global_toggle_btn.clicked.connect(lambda: self.toggle_checkboxes(all_checkboxes))
        
        takes_container_layout.addStretch(1)
        parent_layout.addWidget(takes_group, 1)  # 1 = stretch factor
        
    def toggle_checkboxes(self, checkboxes):
        """Toggle all checkboxes in a list"""
        if all(cb.isChecked() for cb in checkboxes):
            # All are checked, so uncheck all
            for cb in checkboxes:
                cb.setChecked(False)
        else:
            # Some or none are checked, so check all
            for cb in checkboxes:
                cb.setChecked(True)
    
    def save_prefix(self, text):
        """Save the prefix value to settings when it changes"""
        settings = self.load_settings()
        settings["prefix"] = text
        self.save_settings(settings)
        
    def save_group_override(self, text, group_info):
        """Save the group override path when it changes"""
        settings = self.load_settings()
        header_text = group_info.get("header_text")
        
        if not header_text:
            return
            
        # Update settings based on text content
        settings.setdefault("groups", {})
        
        if text.strip():
            # Non-empty text - interpret as a path and update internal full path
            # If it looks different from truncated version, try to resolve full path
            truncated = self.truncate_path(group_info["override_full"]) if group_info["override_full"] else ""
            
            if truncated != text and os.path.isabs(text):
                # Absolute path entered directly
                group_info["override_full"] = text
            elif truncated != text:
                # Relative path - try to resolve against existing full path or global path
                try:
                    # If we had a previous path, use that as base
                    if group_info["override_full"]:
                        parts = group_info["override_full"].split(os.sep)
                        trunc_parts = text.split(os.sep)
                        if len(parts) > len(trunc_parts):
                            new_path = os.sep.join(parts[:-len(trunc_parts)]) + os.sep + text
                            group_info["override_full"] = new_path
                        else:
                            group_info["override_full"] = text
                    else:
                        # No previous path, use global as base for relative paths
                        # Only if text looks like it could be a relative path
                        if os.sep in text or '/' in text or '\\' in text:
                            parts = self.full_export_folder.split(os.sep)
                            trunc_parts = text.split(os.sep)
                            if len(parts) > len(trunc_parts):
                                new_path = os.sep.join(parts[:-len(trunc_parts)]) + os.sep + text
                                group_info["override_full"] = new_path
                            else:
                                group_info["override_full"] = text
                        else:
                            # Just a name, probably a folder at global path
                            group_info["override_full"] = os.path.join(self.full_export_folder, text)
                except:
                    # Fall back to using the text directly
                    group_info["override_full"] = text
                
            # Save the override to settings
            settings["groups"][header_text] = group_info["override_full"]
        else:
            # Empty text - remove any override
            group_info["override_full"] = ""
            
            # Remove from settings if present
            if header_text in settings["groups"]:
                del settings["groups"][header_text]
                
        self.save_settings(settings)
    
    def on_group_collapse_change(self, group_name, collapsed):
        """Track group collapse state and save to temporary file"""
        # Load current states, update, and save back
        states = load_group_states()
        states[group_name] = collapsed
        save_group_states(states)
        
    def showEvent(self, event):
        """Override showEvent to apply collapse states after window is shown"""
        super().showEvent(event)
        
        # Use a timer to ensure UI is fully rendered before applying states
        QTimer.singleShot(100, self.apply_group_states)
        
    def apply_group_states(self):
        """Apply the saved group collapse states"""
        states = load_group_states()
        
        for group_name, is_collapsed in states.items():
            if group_name in self.group_boxes:
                group_box = self.group_boxes[group_name]
                
                # Force update the state to match the saved state
                group_box.collapsed = is_collapsed
                group_box.content_widget.setVisible(not is_collapsed)
                group_box.toggle_button.setText("▸" if is_collapsed else "▾")
        
    def on_group_browse(self, group_info):
        """Handle browse button click for group export folder"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select Group Export Folder", 
            group_info["override_full"] if group_info["override_full"] else self.full_export_folder
        )
        if folder:
            group_info["override_full"] = folder
            group_info["override_entry"].setText(self.truncate_path(folder))
            
            # Update settings
            settings = self.load_settings()
            header_text = group_info.get("header_text")
            if header_text:
                settings.setdefault("groups", {})
                settings["groups"][header_text] = folder
                self.save_settings(settings)
    
    def organize_takes_into_groups(self, takes):
        """Organize takes into groups based on names starting with == or --"""
        groups = []
        current_group = {"header": None, "takes": []}
        for take in takes:
            if take.Name.startswith("==") or take.Name.startswith("--"):
                if current_group["takes"]:
                    groups.append(current_group)
                current_group = {"header": take, "takes": []}
            else:
                current_group["takes"].append(take)
        if current_group["header"] or current_group["takes"]:
            groups.append(current_group)
        return groups
    
    def on_export(self):
        """Handle the export button click with reliable cleanup routines"""
        cleanup_required = False
        # Initialize this variable here to ensure it's defined in all code paths
        sdk_axis_conversion_summary = None
        try:
            self.debug_print("Starting export process")
            if not self.select_skeleton_hierarchy():
                self.debug_print("Failed to select skeleton hierarchy")
                QMessageBox.warning(self, "Export Warning", "Failed to select skeleton hierarchy.")
                return
            
            export_items = []
            selections_to_save = {}
            groups_to_save = {}
            
            for info in self.group_info_list:
                if "header_text" in info:
                    header = info["header_text"]
                    group_folder = info.get("override_full", "").strip()
                    
                    # Only save non-empty group overrides to settings
                    if group_folder:
                        groups_to_save[header] = group_folder
                    
                    # For export operations, use global folder if override is empty
                    if not group_folder:
                        group_folder = self.full_export_folder
                        
                    selections_to_save.setdefault(header, {})
                    
                    for take, checkbox in info["checkbox_vars"].items():
                        selections_to_save[header][take.Name] = checkbox.isChecked()
                        if checkbox.isChecked():
                            export_items.append({"take": take, "export_folder": group_folder})
                else:
                    group_folder = self.full_export_folder
                    selections_to_save.setdefault("ungrouped", {})
                    
                    for take, checkbox in info["checkbox_vars"].items():
                        selections_to_save["ungrouped"][take.Name] = checkbox.isChecked()
                        if checkbox.isChecked():
                            export_items.append({"take": take, "export_folder": group_folder})
            
            new_scene_settings = {
                "global": self.full_export_folder,
                "groups": groups_to_save,
                "selections": selections_to_save,
                "prefix": self.prefix_entry.text(),
                "bake_animation": self.bake_anim_cb.isChecked(),
                "export_log": self.export_log_cb.isChecked(),
                "axis_conversion": {
                    "enabled": self.up_axis_combo.currentText() != "Y-up (None)",
                    "target_axis": self.up_axis_combo.currentText().replace(" (None)", ""),
                    "manual_rotation": {
                        "x": float(self.x_rotation_input.text() or 0),
                        "y": float(self.y_rotation_input.text() or 0),
                        "z": float(self.z_rotation_input.text() or 0)
                    }
                },
                "fbx_sdk_axis_conversion": {
                    "enabled": self.sdk_up_axis_combo.currentText() != "Y-up (None)",
                    "target_axis": self.sdk_up_axis_combo.currentText().replace(" (None)", "")
                },
                "takes": {}
            }
            
            current_takes = {take.Name: take for take in FBSystem().Scene.Takes}
            for name, take in current_takes.items():
                new_scene_settings["takes"][name] = {"export_path": "", "exported": False}
            
            self.save_settings(new_scene_settings)
            
            total_items = len(export_items)
            if total_items == 0:
                QMessageBox.information(self, "Export Takes", "No takes selected for export.")
                return
            
            self.progress_bar.setRange(0, total_items)
            self.progress_bar.setValue(0)
            
            prefix = self.prefix_entry.text().strip()
            if prefix and not prefix.endswith("_"):
                prefix = prefix + "_"
            
            self.export_selected_takes(
                self.full_export_folder, 
                export_items, 
                prefix, 
                bake_animation=self.bake_anim_cb.isChecked()
            )
            
            updated_settings = self.load_settings()
            for info in self.group_info_list:
                for take, label in info["check_labels"].items():
                    exp_info = updated_settings.get("takes", {}).get(take.Name, {"exported": False})
                    new_mark = "✔" if exp_info.get("exported", False) else ""
                    label.setText(new_mark)
            
            if self.export_log_cb.isChecked():
                self.open_export_log(updated_settings, sdk_axis_conversion_summary)
        
        except Exception as e:
            # print(f"Error during export process: {e}")
            QMessageBox.critical(self, "Export Error", f"Error during export process: {e}")
        finally:
            # No need to reparent here anymore as it's now handled in cleanup_after_export
            pass
    
    def convert_fbx_axes(self, file_path, target_axis="Z-up", output_path=None, fbx_version=None):
        """Convert the axis system of an FBX file using the FBX Python SDK (integrated version)"""
        # Check if FBX SDK is available
        if not FBX_SDK_AVAILABLE:
            self.debug_print(f"Error: FBX SDK not available")
            return False

        if not os.path.exists(file_path):
            self.debug_print(f"Error: File does not exist: {file_path}")
            return False
            
        if output_path is None:
            output_path = file_path
        
        try:
            # Initialize the FBX SDK
            sdk_manager = fbx.FbxManager.Create()
            if not sdk_manager:
                self.debug_print("Error: Unable to create FBX Manager")
                return False
            
            self.debug_print("FBX SDK Manager created successfully.")
            
            # Create an IO settings object
            ios = fbx.FbxIOSettings.Create(sdk_manager, fbx.IOSROOT)
            sdk_manager.SetIOSettings(ios)
            
            # Create an importer
            importer = fbx.FbxImporter.Create(sdk_manager, "")
            
            # Initialize the importer
            if not importer.Initialize(file_path, -1, sdk_manager.GetIOSettings()):
                error_msg = f"Error: Unable to initialize importer for {file_path}"
                if hasattr(importer, 'GetStatus') and hasattr(importer.GetStatus(), 'GetErrorString'):
                    error_msg += f"\n{importer.GetStatus().GetErrorString()}"
                self.debug_print(error_msg)
                importer.Destroy()
                sdk_manager.Destroy()
                return False
            
            self.debug_print("FBX importer initialized successfully")
            
            # Create a new scene
            scene = fbx.FbxScene.Create(sdk_manager, "Scene")
            
            # Import the contents of the file into the scene
            importer.Import(scene)
            importer.Destroy()
            
            self.debug_print("FBX file imported successfully")
            
            # Get the current axis system
            global_settings = scene.GetGlobalSettings()
            current_axis = global_settings.GetAxisSystem()
            
            # Create the target axis system
            target_axis_system = None
            
            if target_axis == "Y-up":
                # MotionBuilder default: Y-up, Z-front, X-right
                target_axis_system = fbx.FbxAxisSystem(
                    fbx.FbxAxisSystem.EUpVector.eYAxis,
                    fbx.FbxAxisSystem.EFrontVector.eParityOdd,
                    fbx.FbxAxisSystem.ECoordSystem.eRightHanded
                )
                self.debug_print("Created Y-up axis system")
            elif target_axis == "Z-up":
                # Z-up, Y-front, X-right
                target_axis_system = fbx.FbxAxisSystem(
                    fbx.FbxAxisSystem.EUpVector.eZAxis,
                    fbx.FbxAxisSystem.EFrontVector.eParityOdd,
                    fbx.FbxAxisSystem.ECoordSystem.eRightHanded
                )
                self.debug_print("Created Z-up axis system")
            else:
                error_msg = f"Error: Unknown target axis: {target_axis}"
                self.debug_print(error_msg)
                sdk_manager.Destroy()
                return False
            
            # Convert the scene to the new axis system
            target_axis_system.ConvertScene(scene)
            
            # Create an exporter
            exporter = fbx.FbxExporter.Create(sdk_manager, "")
            
            # Set up export options including FBX version
            io_settings = sdk_manager.GetIOSettings()
            
            # Set FBX file format version if specified
            if fbx_version:
                # Try to set version using the string directly
                try:
                    self.debug_print(f"Setting FBX version to {fbx_version} using string value")
                    io_settings.SetEnumProp(fbx.EExportFormat.eExportFormatFBX, "FBXExportFileVersion", fbx_version)
                except Exception as e:
                    self.debug_print(f"Warning: Failed to set FBX version {fbx_version}: {e}")
                    self.debug_print("Continuing with default version")
            
            # Initialize the exporter
            if not exporter.Initialize(output_path, -1, io_settings):
                error_msg = f"Error: Unable to initialize exporter for {output_path}"
                try:
                    if hasattr(exporter, 'GetStatus') and hasattr(exporter.GetStatus(), 'GetErrorString'):
                        error_msg += f"\n{exporter.GetStatus().GetErrorString()}"
                except:
                    pass  # Skip if not available
                self.debug_print(error_msg)
                exporter.Destroy()
                sdk_manager.Destroy()
                return False
            
            # Export the scene
            exporter.Export(scene)
            exporter.Destroy()
            
            self.debug_print(f"Exported converted file to {output_path}")
            
            # Destroy the SDK manager and all objects it created
            sdk_manager.Destroy()
            
            return True
        
        except Exception as e:
            error_msg = f"Error converting axis system: {str(e)}"
            self.debug_print(error_msg)
            self.debug_print(traceback.format_exc())
            return False

    def post_process_exported_files(self):
        """Post-process exported files with FBX SDK Axis Conversion"""
        if self.sdk_up_axis_combo.currentText() == "Y-up (None)" or not self.exported_files:
            self.debug_print("FBX SDK Axis Conversion skipped - Not enabled or no files exported")
            return [], None
            
        if not FBX_SDK_AVAILABLE:
            self.debug_print("FBX SDK not available, skipping post-processing")
            QMessageBox.warning(self, "Warning", "FBX SDK not available, skipping axis conversion.")
            return [], None
            
        target_axis = self.sdk_up_axis_combo.currentText().replace(" (None)", "")
        self.debug_print(f"Starting FBX SDK Axis Conversion for {len(self.exported_files)} files to {target_axis}")
        
        processed_files = []
        conversion_errors = []
        total_files = len(self.exported_files)
        
        # Update progress bar for conversion phase
        self.progress_bar.setRange(0, total_files)
        self.progress_bar.setValue(0)
        
        for idx, file_path in enumerate(self.exported_files, start=1):
            self.debug_print(f"Processing file {idx}/{total_files}: {file_path}")
            
            try:
                # Convert the file in-place (overwrite) using our integrated method
                success = self.convert_fbx_axes(file_path, target_axis, output_path=None, fbx_version=None)
                
                if success:
                    processed_files.append(file_path)
                    self.debug_print(f"Successfully converted: {file_path}")
                else:
                    conversion_errors.append(file_path)
                    self.debug_print(f"Failed to convert: {file_path}")
            except Exception as e:
                conversion_errors.append(file_path)
                self.debug_print(f"Error converting {file_path}: {str(e)}")
                
            # Update progress bar
            self.progress_bar.setValue(idx)
            QApplication.processEvents()
        
        # Prepare a simple message about the conversion
        if processed_files:
            # Simplified message - just stating what axis was converted to
            message = f"Converted to {target_axis}"
            self.debug_print(f"Successfully converted {len(processed_files)} FBX files to {target_axis}")
        else:
            message = None
            self.debug_print(f"No files were successfully converted to {target_axis}")
            
        # Return the file list and summary message for the export log without showing any popup
        return processed_files, message
        
    def plot_all_skeleton_joints(self):
        """Plot all skeleton joints for the current take"""
        if not self.selected_nodes:
            self.debug_print("No skeleton nodes to plot")
            return False
            
        try:
            self.debug_print("Starting bake animation for all skeleton joints...")
            
            # Get current take
            current_take = FBSystem().CurrentTake
            self.debug_print(f"Current take: {current_take.Name}")
            
            # Store the current selection
            original_selection = FBModelList()
            FBGetSelectedModels(original_selection)
            
            # Store current time to restore later
            player_control = FBPlayerControl()
            original_time = FBSystem().LocalTime
            
            # Select all skeleton nodes for plotting
            FBBeginChangeAllModels()
            
            # Clear all selections first
            for model in original_selection:
                model.Selected = False
                
            # Select all skeleton nodes we want to plot
            for model in self.selected_nodes:
                model.Selected = True
                
            self.debug_print(f"Selected {len(self.selected_nodes)} skeleton nodes for plotting")
            
            # Set up plot options
            plot_options = FBPlotOptions()
            plot_options.ConstantKeyReducerKeepOneKey = True  # Keep at least one key per property
            plot_options.PlotAllTakes = False                 # Only plot current take
            plot_options.PlotOnFrame = True                   # Plot on each frame
            plot_options.PlotPeriod = FBTime(0, 0, 0, 1)      # 1 frame interval
            plot_options.PlotTranslationOnRootOnly = False    # Plot translation on all joints
            plot_options.PreciseTimeDiscontinuities = True    # Ensure accurate plotting at discontinuities
            plot_options.RotationFilterToApply = FBRotationFilter.kFBRotationFilterUnroll  # Use unroll filter
            plot_options.UseConstantKeyReducer = True         # Use key reducer
            
            # Go to the start frame to begin plotting
            take_span = current_take.LocalTimeSpan
            start_frame = take_span.GetStart().GetFrame()
            player_control.Goto(FBTime(0, 0, 0, start_frame))
            FBSystem().Scene.Evaluate()
            
            # Plot the animation for all selected models
            self.debug_print("Plotting all skeleton joints...")
            try:
                current_take.PlotTakeOnSelected(plot_options)
                self.debug_print("Joint plotting completed successfully")
            except Exception as e:
                self.debug_print(f"Error during joint plotting: {e}")
                
            # Restore original selection
            for model in self.selected_nodes:
                model.Selected = False
                
            for model in original_selection:
                model.Selected = True
                
            FBEndChangeAllModels()
            
            # Restore the original time
            player_control.Goto(original_time)
            FBSystem().Scene.Evaluate()
            
            return True
            
        except Exception as e:
            self.debug_print(f"Error plotting all skeleton joints: {e}")
            return False
    
    def clear_animation_on_all_joints(self):
        """Clean up animation by removing all keys from skeleton joints"""
        try:
            # Count statistics
            cleared_nodes = 0
            cleared_curves = 0
            
            # Process each joint in the selected nodes
            for joint in self.selected_nodes:
                # Skip non-skeleton nodes
                if not hasattr(joint, 'ClassName') or joint.ClassName() != "FBModelSkeleton":
                    continue
                
                # Process all properties in the joint
                for prop in joint.PropertyList:
                    if prop.IsAnimatable() and prop.IsAnimated():
                        try:
                            # Get animation node for this property
                            anim_node = prop.GetAnimationNode()
                            if not anim_node:
                                continue
                                
                            # Check for direct FCurve on node
                            if hasattr(anim_node, 'FCurve') and anim_node.FCurve:
                                try:
                                    # Correctly check for keys using len(fcurve.Keys)
                                    keys_count = len(anim_node.FCurve.Keys) if hasattr(anim_node.FCurve, 'Keys') else 0
                                    if keys_count > 0:
                                        anim_node.FCurve.EditClear()
                                        cleared_curves += 1
                                        cleared_nodes += 1
                                except Exception:
                                    pass
                            
                            # Check for child nodes (for vector properties like Translation, Rotation)
                            if hasattr(anim_node, 'Nodes') and anim_node.Nodes:
                                for sub_node in anim_node.Nodes:
                                    if hasattr(sub_node, 'FCurve') and sub_node.FCurve:
                                        try:
                                            # Correctly check for keys using len(fcurve.Keys)
                                            keys_count = len(sub_node.FCurve.Keys) if hasattr(sub_node.FCurve, 'Keys') else 0
                                            if keys_count > 0:
                                                sub_node.FCurve.EditClear()
                                                cleared_curves += 1
                                        except Exception:
                                            pass
                        except Exception:
                            pass
            
            # Set a key on the current frame for all joints to preserve positions
            self.set_keys_on_joints()
            
            return True
        except Exception:
            return False
            
    def set_keys_on_joints(self):
        """Set keys on all joints to preserve their positions"""
        # Get current time
        current_time = FBSystem().LocalTime
        
        try:
            # Process each joint in the selected nodes
            for joint in self.selected_nodes:
                # Skip non-skeleton nodes
                if not hasattr(joint, 'ClassName') or joint.ClassName() != "FBModelSkeleton":
                    continue
                
                # Handle standard transform properties
                for prop_name in ['Translation', 'Rotation']:
                    if hasattr(joint, prop_name):
                        try:
                            prop = getattr(joint, prop_name)
                            
                            # Make sure it's animatable
                            if prop.IsAnimatable():
                                # Set property as animated
                                prop.SetAnimated(True)
                                
                                # Get animation node
                                anim_node = prop.GetAnimationNode()
                                if anim_node and hasattr(anim_node, 'Nodes'):
                                    # Get current values
                                    values = []
                                    for i in range(3):  # X, Y, Z
                                        values.append(prop[i])
                                        
                                    # Add keys for each component
                                    for i, component in enumerate(['X', 'Y', 'Z']):
                                        try:
                                            if i < len(anim_node.Nodes):
                                                component_node = anim_node.Nodes[i]
                                                if hasattr(component_node, 'FCurve') and component_node.FCurve:
                                                    # Add a key at current time with current value
                                                    component_node.FCurve.KeyAdd(current_time, values[i])
                                        except Exception:
                                            pass
                        except Exception:
                            pass
        except Exception:
            pass
            
    def export_selected_takes(self, global_folder, export_items, prefix, bake_animation=True):
        """Export the selected takes to FBX files"""
        scene = FBSystem().Scene
        if not scene:
            return
        
        # Clear the list of exported files for this session
        self.exported_files = []
        
        original_take = FBSystem().CurrentTake
        takes_export_info = {}
        total = len(export_items)
        
        # Check if axis conversion is enabled based on dropdown selection
        axis_conversion_enabled = self.up_axis_combo.currentText() != "Y-up (None)"
        target_axis = self.up_axis_combo.currentText().replace(" (None)", "")
        
        # Store original root state if axis conversion is enabled
        original_root_state = None
        if axis_conversion_enabled and self.skeleton_root:
            pass  # Axis conversion enabled
        
        for idx, item in enumerate(export_items, start=1):
            take = item["take"]
            export_folder = item["export_folder"]
            exported = False
            export_path = ""
            
            if not os.path.isdir(export_folder):
                try:
                    os.makedirs(export_folder)
                    self.debug_print(f"Created folder: {export_folder}")
                except Exception as e:
                    self.debug_print(f"Error creating folder {export_folder}: {e}")
                    QMessageBox.warning(self, "Export Error", f"Failed to create folder: {export_folder}")
                    continue
            
            try:
                # Set current take
                self.debug_print(f"Setting current take to: {take.Name}")
                FBSystem().CurrentTake = take
                
                # Step 1: Bake animation FIRST if option is enabled
                baked_animation = False
                if self.bake_anim_cb.isChecked() and self.selected_nodes:
                    self.debug_print("Baking Animation (plotting all skeleton joints)...")
                    baked_animation = self.plot_all_skeleton_joints()
                    if baked_animation:
                        self.debug_print("Animation baking completed successfully")
                    else:
                        self.debug_print("WARNING: Animation baking failed or was incomplete")
                        
                # Step 2: Prepare root for export (handles constraints and/or axis conversion)
                export_prep_data = None
                if self.skeleton_root:
                    self.debug_print(f"Preparing take '{take.Name}' for export...")
                    # Apply axis conversion only if enabled
                    if axis_conversion_enabled:
                        export_prep_data = self.prepare_root_for_export(target_axis)
                    else:
                        export_prep_data = self.prepare_root_for_export(None)
                    
                    if not export_prep_data:
                        export_prep_data = None
                        self.debug_print("WARNING: Failed to prepare root for export")
                
                # Step 3: Export the file
                file_name = (prefix if prefix else "") + take.Name + ".fbx"
                export_path = os.path.join(export_folder, file_name)
                self.debug_print(f"Exporting take: {take.Name} to {export_path}")
                FBApplication().FileExport(export_path)
                self.debug_print(f"Exported take: {take.Name} to {export_path}")
                exported = True
                
                # Add successfully exported file to the list for post-processing
                if exported and os.path.exists(export_path):
                    self.exported_files.append(export_path)
                
                # Step 4: Cleanup after export
                # 4.1 First cleanup any special root handling
                if export_prep_data:
                    self.cleanup_after_export(export_prep_data)
                
                # 4.2 Clean up baked animation to reduce scene size
                if baked_animation:
                    self.clear_animation_on_all_joints()
                
            except Exception as e:
                self.debug_print(f"Error exporting take: {take.Name} - {e}")
                exported = False
                
                # Make sure to restore state even on error
                if export_prep_data:
                    try:
                        self.cleanup_after_export(export_prep_data)
                    except:
                        pass
            
            takes_export_info[take.Name] = {"export_path": export_path, "exported": exported}
            self.progress_bar.setValue(idx)
            QApplication.processEvents()
        
        # Restore original take
        FBSystem().CurrentTake = original_take
        
        # Update takes export info
        current_take_names = {take.Name for take in scene.Takes}
        takes_export_info = {k: v for k, v in takes_export_info.items() if k in current_take_names}
        
        for take in scene.Takes:
            if take.Name not in takes_export_info:
                takes_export_info[take.Name] = {"export_path": "", "exported": False}
        
        # Save settings with updated export info
        scene_settings = self.load_settings()
        scene_settings["global"] = global_folder
        scene_settings["takes"] = takes_export_info
        self.save_settings(scene_settings)
        
        # Run post-processing on all exported files if SDK axis conversion is enabled
        if self.sdk_up_axis_combo.currentText() != "Y-up (None)" and self.exported_files:
            self.debug_print(f"Running post-processing on {len(self.exported_files)} exported files")
            processed_files, sdk_axis_conversion_summary = self.post_process_exported_files()
    
    def open_export_log(self, updated_settings, conversion_summary=None):
        """Open a window showing the export log"""
        log_dialog = QDialog(self)
        log_dialog.setWindowTitle("Export Log")
        log_dialog.setWindowFlags(log_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        log_dialog.resize(500, 400)
        
        log_layout = QVBoxLayout(log_dialog)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # Add FBX SDK Axis Conversion summary if available - simplified version
        if conversion_summary:
            conversion_frame = QFrame()
            conversion_frame.setFrameShape(QFrame.StyledPanel)
            conversion_layout = QVBoxLayout(conversion_frame)
            
            # Simplified message with clear formatting
            conversion_label = QLabel("FBX SDK Axis Conversion: " + conversion_summary)
            conversion_label.setStyleSheet("font-weight: bold;")
            conversion_layout.addWidget(conversion_label)
            
            content_layout.addWidget(conversion_frame)
        
        selections = updated_settings.get("selections", {})
        takes = updated_settings.get("takes", {})
        
        folder_groups = {}
        for group, items in selections.items():
            for take_name, selected in items.items():
                if selected and takes.get(take_name, {}).get("exported", False):
                    folder = updated_settings.get("groups", {}).get(group, "") if group != "ungrouped" else updated_settings.get("global", "")
                    folder_groups.setdefault(folder, []).append(take_name)
        
        row = 0
        for folder, take_list in folder_groups.items():
            if not take_list:
                continue
            
            group_frame = QFrame()
            group_frame.setFrameShape(QFrame.StyledPanel)
            group_layout = QVBoxLayout(group_frame)
            
            header_frame = QWidget()
            header_layout = QHBoxLayout(header_frame)
            header_layout.setContentsMargins(0, 0, 0, 0)
            
            truncated_folder = self.truncate_path(folder, 2)
            header_label = QLabel(f"Exported Takes to {truncated_folder}")
            header_label.setStyleSheet("font-weight: bold; text-decoration: underline;")
            header_layout.addWidget(header_label, 1)
            
            open_btn = QPushButton("Open")
            open_btn.setStyleSheet("color: white; background-color: #555555; border: none; padding: 2px 8px; border-radius: 2px;")
            open_btn.setMaximumWidth(40)  # Make button smaller
            open_btn.setMaximumHeight(20)  # Make button smaller
            open_btn.clicked.connect(lambda checked=False, f=folder: self.open_folder(f))
            header_layout.addWidget(open_btn)
            
            group_layout.addWidget(header_frame)
            
            for take_name in sorted(take_list):
                take_label = QLabel(take_name)
                group_layout.addWidget(take_label)
            
            content_layout.addWidget(group_frame)
            row += 1
        
        if row == 0:
            no_takes_label = QLabel("No takes were exported.")
            no_takes_label.setAlignment(Qt.AlignCenter)
            content_layout.addWidget(no_takes_label)
        
        content_layout.addStretch(1)
        scroll_area.setWidget(content_widget)
        log_layout.addWidget(scroll_area)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(log_dialog.accept)
        log_layout.addWidget(close_btn)
        
        # Execute the dialog
        log_dialog.exec()
        
        # Reset progress bar after closing the dialog
        self.progress_bar.setValue(0)
    
    def open_folder(self, folder):
        """Open a folder in the file explorer"""
        try:
            os.startfile(folder)
        except Exception as e:
            # print(f"Error opening folder: {e}")
            QMessageBox.warning(self, "Error", f"Unable to open folder: {e}")


def main():
    try:
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        
        # Get the MotionBuilder main window as parent
        mb_parent = get_motionbuilder_main_window()
        exporter = MotionBuilderExporter(parent=mb_parent)
        exporter.show()
        app.exec()
    except Exception as e:
        FBMessageBox("Error", f"An error occurred in the exporter: {str(e)}", "OK")
        # print(f"Error in exporter: {e}")
        raise

main()