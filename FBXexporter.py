import os
import json
import sys
import tempfile
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QCheckBox, QLineEdit, QGroupBox, 
                             QScrollArea, QProgressBar, QFileDialog, QFrame, QMessageBox,
                             QSizePolicy, QToolButton, QGridLayout, QDialog, QComboBox)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon, QColor

from pyfbsdk import FBApplication, FBSystem, FBMessageBox, FBModelList, FBModel, FBGetSelectedModels, FBFindModelByLabelName, FBTime, FBAnimationNode
from pyfbsdk import FBModelNull, FBVector3d, FBConstraintManager, FBPlotOptions, FBRotationFilter, FBBeginChangeAllModels, FBEndChangeAllModels
from pyfbsdk import FBPlayerControl, FBFbxOptions  # Added FBPlayerControl and FBFbxOptions to imports


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
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the main window UI"""
        self.setWindowTitle("MotionBuilder Animation Exporter")
        self.resize(710, 600)  # Increase width by 10px instead of 75px
        
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
            print(f"Error saving settings: {e}")
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
            print("No skeleton root to unparent")
            return False
        try:
            if hasattr(self.skeleton_root, 'Parent') and self.skeleton_root.Parent:
                print(f"Unparenting skeleton root: {self.skeleton_root.Name} from {self.skeleton_root.Parent.Name}")
                self.original_parent = self.skeleton_root.Parent
                self.skeleton_root.Parent = None
                print("Successfully unparented skeleton root")
                return True
            else:
                print("Skeleton root has no parent to unparent from")
                return False
        except Exception as e:
            print(f"Error unparenting skeleton root: {e}")
            return False
            
    def reparent_skeleton_root(self):
        """Reparent the skeleton root to its original parent"""
        if not self.skeleton_root or not self.original_parent:
            print("Missing skeleton root or original parent for reparenting")
            return False
        try:
            print(f"Reparenting skeleton root: {self.skeleton_root.Name} to {self.original_parent.Name}")
            self.skeleton_root.Parent = self.original_parent
            print("Successfully reparented skeleton root")
            return True
        except Exception as e:
            print(f"Error reparenting skeleton root: {e}")
            return False
    
            
            

    
    
    
    def plot_root_animation(self):
        """Plot the root's animation by evaluating each frame using plotAnimation"""
        if not self.skeleton_root:
            print("No skeleton root to plot")
            return False
            
        try:
            print("Starting animation frame-by-frame evaluation and plotting...")
            
            # Get current take 
            current_take = FBSystem().CurrentTake
            print(f"Current take: {current_take.Name}")
            
            # Get take timespan to ensure we plot the entire animation
            take_span = current_take.LocalTimeSpan
            start_frame = take_span.GetStart().GetFrame()
            end_frame = take_span.GetStop().GetFrame()
            print(f"Take timespan: {start_frame} to {end_frame} frames")
            
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
            
            print("Testing constraint status...")
            # Jump to first and last frames to check if constraint is working properly
            test_frames = [int(start_frame), int(end_frame)]
            for test_frame in test_frames:
                player_control.Goto(FBTime(0, 0, 0, test_frame))
                FBSystem().Scene.Evaluate()
                print(f"Frame {test_frame}: Position = {self.skeleton_root.Translation}, Rotation = {self.skeleton_root.Rotation}")
            
            # Make sure the root node is selected for plotting
            FBBeginChangeAllModels()
            
            # Clear all selections first
            for model in self.selected_nodes:
                model.Selected = False
                
            # Select only the root
            self.skeleton_root.Selected = True
            
            print(f"Selected root: {self.skeleton_root.LongName}")
            
            # First method: Use FBSystem().Scene.Evaluate() with PlotTakeOnSelected
            # Go to the start frame to begin plotting
            player_control.Goto(FBTime(0, 0, 0, start_frame))
            FBSystem().Scene.Evaluate()
            
            # Plot selected models (only the root should be selected at this point)
            print("Plotting root animation using PlotTakeOnSelected...")
            try:
                # Plot all selected objects 
                current_take.PlotTakeOnSelected(plot_options)
                print("Plotting completed successfully.")
            except Exception as e:
                print(f"Error during PlotTakeOnSelected: {e}")
                
                # Try alternative method: Plot using classic keyframe approach
                print("Trying alternative method...")
                self.manual_plot_by_frame(start_frame, end_frame)
            
            FBEndChangeAllModels()
            
            # Restore the original time
            player_control.Goto(original_time)
            FBSystem().Scene.Evaluate()
            
            return True
            
        except Exception as e:
            print(f"Error plotting root animation: {e}")
            # Try to restore original time in case of error
            if 'original_time' in locals() and 'player_control' in locals():
                player_control.Goto(original_time)
            return False
            
    def manual_plot_by_frame(self, start_frame, end_frame):
        """Manual fallback method to plot frame by frame if the main method fails"""
        print("Using manual frame-by-frame plotting...")
        
        player_control = FBPlayerControl()
        
        # Make sure properties are animated
        self.skeleton_root.Translation.SetAnimated(True)
        self.skeleton_root.Rotation.SetAnimated(True)
        
        # Get animation nodes
        translation_node = self.skeleton_root.Translation.GetAnimationNode()
        rotation_node = self.skeleton_root.Rotation.GetAnimationNode()
        
        if not translation_node or not rotation_node:
            print("Failed to get animation nodes for root")
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
                print(f"Processed frame {frame}/{end_frame}")
                
        print("Manual plotting completed")
    
    def remove_root_keys(self):
        """Remove all animation keys from the root node"""
        if not self.skeleton_root:
            print("No skeleton root to remove keys from")
            return False
            
        try:
            print(f"Removing animation keys from root: {self.skeleton_root.Name}")
            
            # Get the root's animation node
            anim_node = self.skeleton_root.AnimationNode
            if not anim_node:
                print("No animation node found for root")
                return False
                
            # Check if we have any keys
            if anim_node.KeyCount == 0:
                print("No keys to remove")
                return True
                
            # Process all animation nodes recursively
            self.remove_keys_recursive(anim_node)
            
            print("Successfully removed all keys from root")
            return True
            
        except Exception as e:
            print(f"Error removing root keys: {e}")
            return False
    
    def remove_keys_recursive(self, anim_node):
        """Recursively remove all keys from an animation node and its children"""
        try:
            # If this node has an FCurve with keys, clear it
            if hasattr(anim_node, 'FCurve') and anim_node.FCurve:
                if anim_node.FCurve.Keys:
                    print(f"Clearing keys from FCurve: {anim_node.Name}")
                    anim_node.FCurve.EditClear()
            
            # Process all child nodes
            if hasattr(anim_node, 'Nodes'):
                for node in anim_node.Nodes:
                    self.remove_keys_recursive(node)
        except Exception as e:
            print(f"Error in remove_keys_recursive: {e}")
    
    
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
        
        self.options_btn = QToolButton()
        self.options_btn.setText("⚙")
        self.options_btn.setAutoRaise(True)
        self.options_btn.setFixedSize(QSize(24, 24))
        self.options_btn.setCheckable(True)  # Make it checkable
        self.options_btn.clicked.connect(self.toggle_options)
        folder_layout.addWidget(self.options_btn)
        
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
    
    def create_options_panel(self, parent_layout):
        """Create simplified export options panel"""
        self.options_widget = QWidget()
        options_layout = QGridLayout(self.options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
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
        anim_layout = QHBoxLayout(anim_group)
        
        self.bake_anim_cb = QCheckBox("Bake Animation")
        self.bake_anim_cb.setChecked(self.load_settings().get("bake_animation", True))
        anim_layout.addWidget(self.bake_anim_cb)
        
        self.export_log_cb = QCheckBox("Show Export Log")
        self.export_log_cb.setChecked(self.load_settings().get("export_log", True))
        anim_layout.addWidget(self.export_log_cb)
        
        options_layout.addWidget(anim_group, 1, 0, 1, 3)
        
        # Skeleton info
        skeleton_group = QGroupBox("Skeleton Information")
        skeleton_layout = QVBoxLayout(skeleton_group)
        
        self.skeleton_info_label = QLabel("Skeleton Root: Not detected\nSelected Nodes: 0")
        skeleton_layout.addWidget(self.skeleton_info_label)
        
        options_layout.addWidget(skeleton_group, 2, 0, 1, 3)
        
        parent_layout.addWidget(self.options_widget)
        
        # Initially hide options
        self.options_widget.hide()
        
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
    
    def toggle_options(self):
        """Toggle visibility of options panel"""
        is_visible = not self.options_widget.isVisible()
        self.options_widget.setVisible(is_visible)
        
        # Update button appearance based on state
        if is_visible:
            self.options_btn.setStyleSheet("background-color: #404040; border-radius: 3px;")
        else:
            self.options_btn.setStyleSheet("")
            
        # Keep the checked state matching the visibility
        self.options_btn.setChecked(is_visible)
    
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
                print(f"Error looking for {name}: {e}")
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
            print(f"Error selecting children: {e}")
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
                            print(f"Error accessing child {i}: {e}")
                            i += 1
                            if i > 1000:
                                break
        except Exception as e:
            print(f"Error in select_children_simple for {node.Name if hasattr(node, 'Name') else 'unnamed'}: {e}")
    
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
            print(f"Error processing child: {e}")
            
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
        try:
            print("Starting export process")
            if not self.select_skeleton_hierarchy():
                print("Failed to select skeleton hierarchy")
                QMessageBox.warning(self, "Export Warning", "Failed to select skeleton hierarchy.")
                return
                
            try:
                if self.unparent_skeleton_root():
                    cleanup_required = True
                    print("Successfully unparented skeleton root")
                
            except Exception as e:
                print(f"Warning: Error unparenting skeleton root: {e}")
                QMessageBox.warning(self, "Export Warning", f"Error preparing skeleton: {e}")
            
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
                self.open_export_log(updated_settings)
        
        except Exception as e:
            print(f"Error during export process: {e}")
            QMessageBox.critical(self, "Export Error", f"Error during export process: {e}")
        finally:
            try:
                # Reparent the skeleton root
                if cleanup_required:
                    print("Reparenting skeleton root in finally block")
                    self.reparent_skeleton_root()
            except Exception as e:
                print(f"Error during cleanup: {e}")
    
    def export_selected_takes(self, global_folder, export_items, prefix, bake_animation=True):
        """Export the selected takes to FBX files"""
        scene = FBSystem().Scene
        if not scene:
            return
        
        original_take = FBSystem().CurrentTake
        takes_export_info = {}
        total = len(export_items)
        
        for idx, item in enumerate(export_items, start=1):
            take = item["take"]
            export_folder = item["export_folder"]
            exported = False
            export_path = ""
            
            if not os.path.isdir(export_folder):
                try:
                    os.makedirs(export_folder)
                    print(f"Created folder: {export_folder}")
                except Exception as e:
                    print(f"Error creating folder {export_folder}: {e}")
                    QMessageBox.warning(self, "Export Error", f"Failed to create folder: {export_folder}")
                    continue
            
            try:
                # Set current take
                print(f"Setting current take to: {take.Name}")
                FBSystem().CurrentTake = take
                
                # Standard export
                file_name = (prefix if prefix else "") + take.Name + ".fbx"
                export_path = os.path.join(export_folder, file_name)
                print(f"Exporting take: {take.Name} to {export_path}")
                FBApplication().FileExport(export_path)
                print(f"Exported take: {take.Name} to {export_path}")
                exported = True
                
            except Exception as e:
                print(f"Error exporting take: {take.Name} - {e}")
                exported = False
            
            takes_export_info[take.Name] = {"export_path": export_path, "exported": exported}
            self.progress_bar.setValue(idx)
            QApplication.processEvents()
        
        FBSystem().CurrentTake = original_take
        
        current_take_names = {take.Name for take in scene.Takes}
        takes_export_info = {k: v for k, v in takes_export_info.items() if k in current_take_names}
        
        for take in scene.Takes:
            if take.Name not in takes_export_info:
                takes_export_info[take.Name] = {"export_path": "", "exported": False}
        
        scene_settings = self.load_settings()
        scene_settings["global"] = global_folder
        scene_settings["takes"] = takes_export_info
        self.save_settings(scene_settings)
    
    def open_export_log(self, updated_settings):
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
            print(f"Error opening folder: {e}")
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
        print(f"Error in exporter: {e}")
        raise

main()