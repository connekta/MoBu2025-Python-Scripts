"""
MotionBuilder Control Rig Creator
This script creates a PySide6 UI for generating control rig markers and constraints.
It allows users to select objects, choose constraint types, and automatically create
null + marker control setups with proper naming and constraints.
"""

import sys
import traceback

# Import MotionBuilder Python modules first to check availability
try:
    from pyfbsdk import *
    from pyfbsdk_additions import *
    MOBU_AVAILABLE = True
    print("MotionBuilder SDK loaded successfully")
except ImportError:
    MOBU_AVAILABLE = False
    print("Warning: pyfbsdk not found. Running in development mode.")

# Import PySide6 modules
try:
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QRadioButton, QPushButton, QMessageBox, QLabel, QSpinBox,
        QComboBox, QColorDialog, QDoubleSpinBox, QGridLayout, QCheckBox,
        QSizePolicy, QTextEdit
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor
    print("PySide6 modules imported successfully")
except ImportError as e:
    print(f"Error importing PySide6: {str(e)}")
    # Try to give helpful error message about PySide6 installation
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


class ControlifyDialog(QDialog):
    """Main dialog for the Controlify tool"""
    
    # Dictionary of marker look names and their corresponding values
    MARKER_LOOK_TYPES = {
        "Cube": 0,
        "Hard Cross": 1,
        "Light Cross": 2,
        "Sphere": 3, 
        "Capsule": 4,
        "Box": 5,
        "Bone": 6,
        "Circle": 7,
        "Square": 8,
        "Stick": 9,
        "None": 10,
        "Rigid Goal": 11,
        "Rotation Goal": 12,
        "Aim/Roll Goal": 13
    }
    
    def __init__(self, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(ControlifyDialog, self).__init__(parent)
        
        # Set window properties
        self.setWindowTitle("Controlify - Control Rig Creator")
        self.setMinimumWidth(450)
        
        # Try the approach that works in Maya - simply use default dialog behavior
        # with proper parent. QDialog should automatically stay on top of its parent.
        if parent:
            # For MotionBuilder, use Dialog flag without Tool or StaysOnTop
            self.setWindowFlags(Qt.Dialog)
        else:
            # Fallback if no parent found
            self.setWindowFlags(Qt.Window)
        
        # Initialize preview objects
        self.preview_markers = []
        self.preview_enabled = True  # Default to enabled
        self.preview_timer = None
        
        # Create the main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # Add preview checkbox at the top
        self.create_preview_checkbox(main_layout)
        
        # Add constraint type selection
        self.create_constraint_group(main_layout)
        
        # Add marker appearance controls
        self.create_marker_appearance_group(main_layout)
        
        # Add offset controls
        self.create_offset_group(main_layout)
        
        # Add buttons
        self.create_buttons(main_layout)
        
        # Delete button (hidden by default)
        delete_layout = QHBoxLayout()
        delete_layout.addStretch()
        
        self.delete_button = QPushButton("Delete Control")
        self.delete_button.clicked.connect(self.delete_controls)
        self.delete_button.setVisible(False)
        self.delete_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.delete_button.setMaximumHeight(30)  # Fixed height
        delete_layout.addWidget(self.delete_button)
        
        delete_layout.addStretch()
        main_layout.addLayout(delete_layout)
        
        # Status label
        self.status_label = QLabel("Select objects and press Controlify")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Create custom constraints folder on initialization
        self.ensure_custom_constraints_folder_exists()
        
        # Set up preview timer
        self.setup_preview_timer()
        
        # Connect closeEvent to clean up previews
        self.destroyed.connect(self.cleanup_previews)
        
        # Start preview immediately since it's on by default
        if self.preview_enabled:
            self.toggle_preview(True)
    
    def ensure_custom_constraints_folder_exists(self):
        """Make sure the custom constraints folder exists"""
        try:
            folder_name = "Custom_Constraints"
            found_folder = None
            
            # Check if the folder already exists in the scene
            scene = FBSystem().Scene
            for component in scene.Components:
                if component.Name == folder_name and component.ClassName() == "FBFolder":
                    found_folder = component
                    print(f"Found existing folder: {folder_name}")
                    break
            
            # If folder doesn't exist, create it
            if not found_folder:
                # Find the Constraints component to use as the category reference
                constraints_component = None
                for component in scene.Components:
                    if component.Name == "Constraints":
                        constraints_component = component
                        break
                
                if constraints_component:
                    # Create the folder with a reference to the Constraints component to make it appear in that category
                    found_folder = FBFolder(folder_name, constraints_component)
                    print(f"Created new folder: {folder_name}")
                else:
                    print("Could not find Constraints component in scene")
            
            # Store reference to the folder
            self.custom_folder = found_folder
            
        except Exception as e:
            print(f"Error creating custom folder: {str(e)}")
            traceback.print_exc()
            self.custom_folder = None
    
    def create_constraint_group(self, parent_layout):
        """Create the constraint type selection group"""
        group_box = QGroupBox("Constraint Type")
        group_layout = QGridLayout()
        
        # Create radio buttons
        self.rb_parent = QRadioButton("Parent")
        self.rb_rotation = QRadioButton("Rotation")
        self.rb_position = QRadioButton("Position")
        self.rb_aim = QRadioButton("Aim")
        
        # Set default selection
        self.rb_parent.setChecked(True)
        
        # Add to grid layout - 2 columns
        group_layout.addWidget(self.rb_parent, 0, 0)     # Row 0, Col 0
        group_layout.addWidget(self.rb_aim, 1, 0)        # Row 1, Col 0
        group_layout.addWidget(self.rb_rotation, 0, 1)   # Row 0, Col 1
        group_layout.addWidget(self.rb_position, 1, 1)   # Row 1, Col 1
        
        # Set group layout
        group_box.setLayout(group_layout)
        
        # Add to parent layout
        parent_layout.addWidget(group_box)
        
        # Connect the radio buttons to the preview update function
        self.rb_parent.toggled.connect(self.on_settings_changed)
        self.rb_rotation.toggled.connect(self.on_settings_changed)
        self.rb_position.toggled.connect(self.on_settings_changed)
        self.rb_aim.toggled.connect(self.on_settings_changed)
    
    def create_offset_group(self, parent_layout):
        """Create the controller offset settings group"""
        group_box = QGroupBox("Controller Offset")
        group_layout = QGridLayout()
        
        # Translation Offset
        group_layout.addWidget(QLabel("Translation (X,Y,Z):"), 0, 0)
        trans_layout = QHBoxLayout()
        
        self.offset_trans_x = QDoubleSpinBox()
        self.offset_trans_x.setRange(-1000, 1000)
        self.offset_trans_x.setValue(0.0)
        self.offset_trans_x.setSingleStep(1.0)
        trans_layout.addWidget(self.offset_trans_x)
        
        self.offset_trans_y = QDoubleSpinBox()
        self.offset_trans_y.setRange(-1000, 1000)
        self.offset_trans_y.setValue(0.0)
        self.offset_trans_y.setSingleStep(1.0)
        trans_layout.addWidget(self.offset_trans_y)
        
        self.offset_trans_z = QDoubleSpinBox()
        self.offset_trans_z.setRange(-1000, 1000)
        self.offset_trans_z.setValue(0.0)
        self.offset_trans_z.setSingleStep(1.0)
        trans_layout.addWidget(self.offset_trans_z)
        
        # Reset button for translation
        self.reset_trans_button = QPushButton("↻")  # Unicode refresh symbol
        self.reset_trans_button.setFixedWidth(30)
        self.reset_trans_button.setToolTip("Reset translation to 0,0,0")
        self.reset_trans_button.clicked.connect(self.reset_translation)
        trans_layout.addWidget(self.reset_trans_button)
        
        group_layout.addLayout(trans_layout, 0, 1)
        
        # Rotation Offset
        group_layout.addWidget(QLabel("Rotation (X,Y,Z):"), 1, 0)
        rot_layout = QHBoxLayout()
        
        self.offset_rot_x = QDoubleSpinBox()
        self.offset_rot_x.setRange(-360, 360)
        self.offset_rot_x.setValue(0.0)
        self.offset_rot_x.setSingleStep(5.0)
        rot_layout.addWidget(self.offset_rot_x)
        
        self.offset_rot_y = QDoubleSpinBox()
        self.offset_rot_y.setRange(-360, 360)
        self.offset_rot_y.setValue(0.0)
        self.offset_rot_y.setSingleStep(5.0)
        rot_layout.addWidget(self.offset_rot_y)
        
        self.offset_rot_z = QDoubleSpinBox()
        self.offset_rot_z.setRange(-360, 360)
        self.offset_rot_z.setValue(0.0)
        self.offset_rot_z.setSingleStep(5.0)
        rot_layout.addWidget(self.offset_rot_z)
        
        # Reset button for rotation
        self.reset_rot_button = QPushButton("↻")  # Unicode refresh symbol
        self.reset_rot_button.setFixedWidth(30)
        self.reset_rot_button.setToolTip("Reset rotation to 0,0,0")
        self.reset_rot_button.clicked.connect(self.reset_rotation)
        rot_layout.addWidget(self.reset_rot_button)
        
        group_layout.addLayout(rot_layout, 1, 1)
        
        # Connect offset changes to preview update
        for spinbox in [self.offset_trans_x, self.offset_trans_y, self.offset_trans_z,
                        self.offset_rot_x, self.offset_rot_y, self.offset_rot_z]:
            spinbox.valueChanged.connect(self.on_settings_changed)
        
        # Manual Offset button (only visible when single marker selected)
        manual_offset_layout = QHBoxLayout()
        manual_offset_layout.addStretch()
        
        self.manual_offset_button = QPushButton("Manual Offset")
        self.manual_offset_button.clicked.connect(self.toggle_manual_offset)
        self.manual_offset_button.setVisible(False)
        self.manual_offset_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.manual_offset_button.setMaximumHeight(30)  # Fixed height
        manual_offset_layout.addWidget(self.manual_offset_button)
        
        manual_offset_layout.addStretch()
        group_layout.addLayout(manual_offset_layout, 2, 0, 1, 2)
        
        group_box.setLayout(group_layout)
        parent_layout.addWidget(group_box)
        
        # Initialize manual offset state
        self.manual_offset_active = False
        self.manual_offset_marker = None
        self.manual_offset_constraint = None
        
        # Set up selection change monitoring
        self.selection_timer = QTimer(self)
        self.selection_timer.timeout.connect(self.check_selection)
        self.selection_timer.start(200)  # Check every 200ms
    
    def create_marker_appearance_group(self, parent_layout):
        """Create the marker appearance settings group"""
        group_box = QGroupBox("Marker Appearance")
        group_layout = QGridLayout()
        
        # Label for marker look dropdown
        look_label = QLabel("Look:")
        group_layout.addWidget(look_label, 0, 0)
        
        # Create marker look dropdown
        self.marker_look_combo = QComboBox()
        for look_name in self.MARKER_LOOK_TYPES.keys():
            self.marker_look_combo.addItem(look_name)
        # Set default to "Hard Cross"
        self.marker_look_combo.setCurrentText("Hard Cross")
        group_layout.addWidget(self.marker_look_combo, 0, 1)
        self.marker_look_combo.currentIndexChanged.connect(self.on_settings_changed)
        
        # Marker size control
        size_label = QLabel("Size:")
        group_layout.addWidget(size_label, 1, 0)
        
        self.marker_size_spin = QSpinBox()
        self.marker_size_spin.setRange(1, 10000)
        self.marker_size_spin.setValue(100)  # Default size
        group_layout.addWidget(self.marker_size_spin, 1, 1)
        self.marker_size_spin.valueChanged.connect(self.on_settings_changed)
        
        
        # Marker color controls
        color_label = QLabel("Color (RGB):")
        group_layout.addWidget(color_label, 2, 0)
        
        color_layout = QHBoxLayout()
        
        self.color_r_spin = QDoubleSpinBox()
        self.color_r_spin.setRange(0.0, 1.0)
        self.color_r_spin.setValue(1.0)  # Default red value
        self.color_r_spin.setSingleStep(0.1)
        self.color_r_spin.valueChanged.connect(self.update_color_button)
        self.color_r_spin.valueChanged.connect(self.on_settings_changed)
        color_layout.addWidget(self.color_r_spin)
        
        self.color_g_spin = QDoubleSpinBox()
        self.color_g_spin.setRange(0.0, 1.0)
        self.color_g_spin.setValue(0.0)  # Default green value
        self.color_g_spin.setSingleStep(0.1)
        self.color_g_spin.valueChanged.connect(self.update_color_button)
        self.color_g_spin.valueChanged.connect(self.on_settings_changed)
        color_layout.addWidget(self.color_g_spin)
        
        self.color_b_spin = QDoubleSpinBox()
        self.color_b_spin.setRange(0.0, 1.0)
        self.color_b_spin.setValue(0.0)  # Default blue value
        self.color_b_spin.setSingleStep(0.1)
        self.color_b_spin.valueChanged.connect(self.update_color_button)
        self.color_b_spin.valueChanged.connect(self.on_settings_changed)
        color_layout.addWidget(self.color_b_spin)
        
        # Color picker button
        self.color_pick_button = QPushButton("Pick")
        self.color_pick_button.clicked.connect(self.pick_color)
        color_layout.addWidget(self.color_pick_button)
        
        # Set initial color for the button
        self.update_color_button()
        
        group_layout.addLayout(color_layout, 2, 1)
        
        # Right/Left checkbox and color pickers on same line
        self.lr_color_checkbox = QCheckBox("Right/Left colors")
        self.lr_color_checkbox.setChecked(False)
        self.lr_color_checkbox.toggled.connect(self.on_lr_color_toggled)
        self.lr_color_checkbox.toggled.connect(self.on_settings_changed)
        
        # Add checkbox to grid at position (3, 0)
        group_layout.addWidget(self.lr_color_checkbox, 3, 0)
        
        # Right/Left color pickers layout
        lr_buttons_layout = QHBoxLayout()
        
        # Left color picker
        self.left_color_button = QPushButton("Left")
        self.left_color_button.clicked.connect(self.pick_left_color)
        self.left_color_button.setMaximumWidth(60)
        self.left_color_r = 1.0  # Default red
        self.left_color_g = 0.0
        self.left_color_b = 0.0
        self.update_left_color_button()
        self.left_color_button.setVisible(False)  # Hidden by default
        lr_buttons_layout.addWidget(self.left_color_button)
        
        # Right color picker
        self.right_color_button = QPushButton("Right")
        self.right_color_button.clicked.connect(self.pick_right_color)
        self.right_color_button.setMaximumWidth(60)
        self.right_color_r = 0.0  # Default blue
        self.right_color_g = 0.0
        self.right_color_b = 1.0
        self.update_right_color_button()
        self.right_color_button.setVisible(False)  # Hidden by default
        lr_buttons_layout.addWidget(self.right_color_button)
        
        # Add buttons layout to grid at position (3, 1) - same row as checkbox
        group_layout.addLayout(lr_buttons_layout, 3, 1)
        
        # Set the group layout
        group_box.setLayout(group_layout)
        
        # Add to parent layout
        parent_layout.addWidget(group_box)
    
    def on_lr_color_toggled(self, checked):
        """Toggle the color spinboxes based on Right/Left checkbox"""
        self.color_r_spin.setEnabled(not checked)
        self.color_g_spin.setEnabled(not checked)
        self.color_b_spin.setEnabled(not checked)
        self.color_pick_button.setEnabled(not checked)
        self.left_color_button.setVisible(checked)
        self.right_color_button.setVisible(checked)
    
    def create_preview_checkbox(self, parent_layout):
        """Create a checkbox for enabling/disabling preview with info button"""
        # Create a horizontal layout for the preview line
        preview_layout = QHBoxLayout()
        
        self.preview_checkbox = QCheckBox("Preview marker appearance")
        self.preview_checkbox.setChecked(True)  # Default to on
        self.preview_checkbox.toggled.connect(self.toggle_preview)
        preview_layout.addWidget(self.preview_checkbox)
        
        preview_layout.addStretch()  # Push info button to the right
        
        # Add information button - make it square
        self.info_button = QPushButton("?")
        self.info_button.setFixedSize(20, 20)  # Square button
        self.info_button.clicked.connect(self.show_info_dialog)
        self.info_button.setToolTip("Show information about this script")
        preview_layout.addWidget(self.info_button)
        
        parent_layout.addLayout(preview_layout)
    
    def setup_preview_timer(self):
        """Set up a timer for updating preview markers"""
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_preview_markers)
        self.preview_timer.setInterval(200)  # Update every 200ms
    
    
    def toggle_preview(self, checked):
        """Toggle preview mode on/off"""
        self.preview_enabled = checked
        
        if checked:
            # Create preview markers for selected objects
            self.create_preview_markers()
            # Start timer to update preview markers
            self.preview_timer.start()
        else:
            # Clean up preview markers
            self.cleanup_previews()
            # Stop timer
            self.preview_timer.stop()
    
    def reset_translation(self):
        """Reset translation offset values to 0"""
        self.offset_trans_x.setValue(0.0)
        self.offset_trans_y.setValue(0.0)
        self.offset_trans_z.setValue(0.0)
    
    def reset_rotation(self):
        """Reset rotation offset values to 0"""
        self.offset_rot_x.setValue(0.0)
        self.offset_rot_y.setValue(0.0)
        self.offset_rot_z.setValue(0.0)
    
    def on_settings_changed(self):
        """Update preview markers when settings change"""
        if self.preview_enabled:
            # Check if selection is a single marker (should remove preview)
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            if len(selected_models) == 1 and selected_models[0].ClassName() == "FBModelMarker":
                self.cleanup_previews()
            else:
                # Update existing preview markers
                self.update_preview_markers()
    
    def create_preview_markers(self):
        """Create preview markers for selected objects"""
        # Clean up any existing preview markers first
        self.cleanup_previews()
        
        # Get selected objects
        selected_models = FBModelList()
        FBGetSelectedModels(selected_models)
        
        if len(selected_models) == 0:
            return
            
        # If selection is a single marker, don't create preview
        if len(selected_models) == 1 and selected_models[0].ClassName() == "FBModelMarker":
            return
        
        # Get the scene reference for evaluation
        scene = FBSystem().Scene
        
        # Check if we have any valid objects for preview
        valid_objects_count = 0
        
        # Create a preview marker for each selected object
        for model in selected_models:
            # Skip if this is already a marker
            if model.ClassName() == "FBModelMarker":
                continue
                
            # Skip if this is one of our created nulls
            if model.ClassName() == "FBModelNull":
                name = model.Name
                if name.endswith("_OFFSET_PARENT") or name.endswith("_OFFSET") or name.endswith("_NULL"):
                    continue
                    
            # Check existing constraints for this model
            current_constraint_type = self.get_selected_constraint_type()
            
            # Count constraints by type for THIS specific model
            has_parent = False
            has_position = False
            has_rotation = False
            
            # Check all constraints to see which types exist for this model
            constraints_found = []
            for constraint in FBSystem().Scene.Constraints:
                # Check if this model is the constrained (target) object
                ref_group_count = constraint.ReferenceGroupGetCount()
                is_constrained = False
                
                # Check if this model is the constrained object (group 0)
                if ref_group_count > 0:
                    ref_count = constraint.ReferenceGetCount(0)
                    for j in range(ref_count):
                        ref_obj = constraint.ReferenceGet(0, j)
                        if ref_obj and ref_obj == model:
                            is_constrained = True
                            break
                
                if is_constrained:
                    # Get constraint type from the class name
                    constraint_class = constraint.ClassName()
                    constraint_name = constraint.Name
                    constraints_found.append(f"{constraint_name} ({constraint_class})")
                    
                    # Check constraint type based on the name since class might be generic
                    if "_Rotation_Constraint" in constraint_name:
                        has_rotation = True
                    elif "_Position_Constraint" in constraint_name:
                        has_position = True
                    elif "_Parent_Child_Constraint" in constraint_name:
                        has_parent = True
                    elif "_Aim_Constraint" in constraint_name:
                        has_rotation = True  # Aim constraint affects rotation, so treat it like rotation
                    # Also check for the offset parent position constraint
                    elif "_OffsetParent_Position_Constraint" in constraint_name:
                        # This is a position constraint on the offset parent for rotation controls
                        pass  # Don't count this as a position constraint on the model itself
            
            # Debug print to check what we found
            print(f"\nChecking constraints for model {model.Name}:")
            print(f"  Current radio selection: {current_constraint_type}")
            print(f"  Constraints found: {constraints_found}")
            print(f"  Has Parent: {has_parent}, Has Position: {has_position}, Has Rotation: {has_rotation}")
            
            # RULE 1: If has parent constraint, disable ALL preview
            if has_parent:
                continue
                
            # RULE 2: If has both position and rotation, disable ALL preview
            if has_position and has_rotation:
                continue
                
            # RULE 3: If has only rotation, allow only position preview
            if has_rotation and not has_position:
                if current_constraint_type != "Position":
                    continue
                    
            # RULE 4: If has only position, allow only rotation preview
            if has_position and not has_rotation:
                if current_constraint_type != "Rotation":
                    continue
                    
            # RULE 5: If trying to create same type that already exists, skip
            if (current_constraint_type == "Parent/Child" and has_parent) or \
               (current_constraint_type == "Position" and has_position) or \
               (current_constraint_type == "Rotation" and has_rotation):
                continue
            # Create ALL preview objects first at default 0,0,0 position
            # Create offset parent null
            offset_parent_name = f"PREVIEW_{model.Name}_OFFSET_PARENT"
            offset_parent = FBModelNull(offset_parent_name)
            offset_parent.Show = True
            offset_parent.Size = 20
            
            # Create offset null
            offset_name = f"PREVIEW_{model.Name}_OFFSET"
            offset_null = FBModelNull(offset_name)
            offset_null.Show = True
            offset_null.Size = 15
            
            # Create marker
            marker_name = f"PREVIEW_{model.Name}_CTRL"
            marker = FBModelMarker(marker_name)
            marker.Show = True
            self.apply_appearance_to_marker(marker, model.Name)
            
            # Set up the hierarchy (all objects still at 0,0,0)
            marker.Parent = offset_null
            offset_null.Parent = offset_parent
            
            # Evaluate scene to update hierarchy
            scene.Evaluate()
            
            # Now position only the top-level object (offset_parent) to match the model
            # All children will follow automatically
            offset_parent_matrix = FBMatrix()
            model.GetMatrix(offset_parent_matrix)
            offset_parent.SetMatrix(offset_parent_matrix)
            
            # Evaluate scene to update positions
            scene.Evaluate()
            
            # Now apply the offset from UI to the offset null
            offset_trans = FBVector3d(
                self.offset_trans_x.value(),
                self.offset_trans_y.value(),
                self.offset_trans_z.value()
            )
            offset_rot = FBVector3d(
                self.offset_rot_x.value(),
                self.offset_rot_y.value(),
                self.offset_rot_z.value()
            )
            
            # Use SetVector for local transforms (more reliable than LclTranslation/LclRotation)
            offset_null.SetVector(offset_trans, FBModelTransformationType.kModelTranslation, False)  # False = local space
            offset_null.SetVector(offset_rot, FBModelTransformationType.kModelRotation, False)  # False = local space
            
            
            # Final evaluation
            scene.Evaluate()
            
            
            # Add to our list of preview markers
            self.preview_markers.append(marker)
            self.preview_markers.append(offset_null)
            self.preview_markers.append(offset_parent)  # Track offset parent too
            valid_objects_count += 1
        
        # If no valid objects found, clean up
        if valid_objects_count == 0:
            self.cleanup_previews()
    
    def update_preview_markers(self):
        """Update existing preview markers with current settings"""
        if not self.preview_enabled:
            return
            
        # First check if the selection has changed
        selected_models = FBModelList()
        FBGetSelectedModels(selected_models)
        
        # If selection is a single marker, don't show preview
        if len(selected_models) == 1 and selected_models[0].ClassName() == "FBModelMarker":
            self.cleanup_previews()
            return
            
        # Check if selected models are valid for preview
        valid_model_count = 0
        for model in selected_models:
            if model.ClassName() == "FBModelMarker":
                continue
            if model.ClassName() == "FBModelNull":
                name = model.Name
                if name.endswith("_OFFSET_PARENT") or name.endswith("_OFFSET") or name.endswith("_NULL"):
                    continue
            valid_model_count += 1
        
        # If selection count has changed or no valid objects, recreate or clean up
        # Note: We now have 3 previews per model (marker + offset null + offset parent)
        if valid_model_count * 3 != len(self.preview_markers):
            self.create_preview_markers()
            return
            
        # Update offset values
        offset_trans = FBVector3d(
            self.offset_trans_x.value(),
            self.offset_trans_y.value(),
            self.offset_trans_z.value()
        )
        offset_rot = FBVector3d(
            self.offset_rot_x.value(),
            self.offset_rot_y.value(),
            self.offset_rot_z.value()
        )
        
        # If we still have preview markers, update their appearance and offsets
        for i in range(0, len(self.preview_markers), 3):
            marker = self.preview_markers[i]
            offset_null = self.preview_markers[i + 1] if i + 1 < len(self.preview_markers) else None
            offset_parent = self.preview_markers[i + 2] if i + 2 < len(self.preview_markers) else None
            
            if marker and marker.ClassName() == "FBModelMarker":
                self.apply_appearance_to_marker(marker)
            
            if offset_null and offset_null.ClassName() == "FBModelNull":
                # Use SetVector for local transforms (more reliable than LclTranslation/LclRotation)
                offset_null.SetVector(offset_trans, FBModelTransformationType.kModelTranslation, False)  # False = local space
                offset_null.SetVector(offset_rot, FBModelTransformationType.kModelRotation, False)  # False = local space
        
        # Evaluate scene to update the preview
        FBSystem().Scene.Evaluate()
    
    def apply_appearance_to_marker(self, marker, model_name=None):
        """Apply current appearance settings to a marker"""
        # Get marker appearance settings from UI
        marker_size = self.marker_size_spin.value()
        marker_look_name = self.marker_look_combo.currentText()
        marker_look_value = self.MARKER_LOOK_TYPES[marker_look_name]
        
        # Determine color based on Right/Left setting
        if self.lr_color_checkbox.isChecked():
            # Use the original model name if provided, otherwise use marker name
            check_name = model_name.lower() if model_name else marker.Name.lower()
            
            # Right side patterns - use custom right color
            if any(pattern in check_name for pattern in ["_r_", "_right_", "_rgt_", "_r.", "_right.", "_rgt.", 
                                                        "_r", "_right", "_rgt"]):
                marker_color = FBColor(self.right_color_r, self.right_color_g, self.right_color_b)
            # Left side patterns - use custom left color
            elif any(pattern in check_name for pattern in ["_l_", "_left_", "_lft_", "_l.", "_left.", "_lft.",
                                                          "_l", "_left", "_lft"]):
                marker_color = FBColor(self.left_color_r, self.left_color_g, self.left_color_b)
            else:
                # Default to UI color if no pattern found
                marker_color = FBColor(
                    self.color_r_spin.value(),
                    self.color_g_spin.value(),
                    self.color_b_spin.value()
                )
        else:
            # Use manual color settings
            marker_color = FBColor(
                self.color_r_spin.value(),
                self.color_g_spin.value(),
                self.color_b_spin.value()
            )
        
        # Apply marker settings
        marker.Size = marker_size
        marker.PropertyList.Find('LookUI').Data = marker_look_value
        marker.Color = marker_color
    
    def cleanup_previews(self):
        """Remove all preview markers from the scene"""
        # First try to delete any objects we have references to
        for obj in list(self.preview_markers):  # Use list to make a copy before modifying
            if obj:
                try:
                    obj.FBDelete()
                except:
                    print(f"Failed to delete object directly: {obj.Name if hasattr(obj, 'Name') else 'Unknown'}")
        
        # Clear our internal list
        self.preview_markers.clear()
        
        # Second pass: search the entire scene for any preview objects we missed
        for component in FBSystem().Scene.Components:
            if component.Name.startswith("PREVIEW_"):
                if component.ClassName() in ["FBModelMarker", "FBModelNull"]:
                    try:
                        component.FBDelete()
                    except:
                        pass
                    
        # Force scene evaluation to update the viewport
        FBSystem().Scene.Evaluate()
    
    def pick_color(self):
        """Open a color picker dialog to choose the marker color"""
        current_color = QColor(
            int(self.color_r_spin.value() * 255),
            int(self.color_g_spin.value() * 255),
            int(self.color_b_spin.value() * 255)
        )
        
        color_dialog = QColorDialog(current_color, self)
        if color_dialog.exec_():
            color = color_dialog.selectedColor()
            # Convert 0-255 range to 0.0-1.0 range for MotionBuilder
            self.color_r_spin.setValue(color.red() / 255.0)
            self.color_g_spin.setValue(color.green() / 255.0)
            self.color_b_spin.setValue(color.blue() / 255.0)
            
            # Update the button color to show current selection
            self.update_color_button()
    
    def pick_left_color(self):
        """Open a color picker dialog to choose the left side color"""
        current_color = QColor(
            int(self.left_color_r * 255),
            int(self.left_color_g * 255),
            int(self.left_color_b * 255)
        )
        
        color_dialog = QColorDialog(current_color, self)
        if color_dialog.exec_():
            color = color_dialog.selectedColor()
            # Convert 0-255 range to 0.0-1.0 range for MotionBuilder
            self.left_color_r = color.red() / 255.0
            self.left_color_g = color.green() / 255.0
            self.left_color_b = color.blue() / 255.0
            
            # Update the button color to show current selection
            self.update_left_color_button()
            self.on_settings_changed()
    
    def pick_right_color(self):
        """Open a color picker dialog to choose the right side color"""
        current_color = QColor(
            int(self.right_color_r * 255),
            int(self.right_color_g * 255),
            int(self.right_color_b * 255)
        )
        
        color_dialog = QColorDialog(current_color, self)
        if color_dialog.exec_():
            color = color_dialog.selectedColor()
            # Convert 0-255 range to 0.0-1.0 range for MotionBuilder
            self.right_color_r = color.red() / 255.0
            self.right_color_g = color.green() / 255.0
            self.right_color_b = color.blue() / 255.0
            
            # Update the button color to show current selection
            self.update_right_color_button()
            self.on_settings_changed()
    
    def update_color_button(self):
        """Update the color button to show the current color"""
        color = QColor(
            int(self.color_r_spin.value() * 255),
            int(self.color_g_spin.value() * 255),
            int(self.color_b_spin.value() * 255)
        )
        
        # Create a style sheet for the button
        style = f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); color: {'white' if color.lightness() < 128 else 'black'};"
        self.color_pick_button.setStyleSheet(style)
    
    def update_left_color_button(self):
        """Update the left color button to show the current color"""
        color = QColor(
            int(self.left_color_r * 255),
            int(self.left_color_g * 255),
            int(self.left_color_b * 255)
        )
        
        # Create a style sheet for the button
        style = f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); color: {'white' if color.lightness() < 128 else 'black'};"
        self.left_color_button.setStyleSheet(style)
    
    def update_right_color_button(self):
        """Update the right color button to show the current color"""
        color = QColor(
            int(self.right_color_r * 255),
            int(self.right_color_g * 255),
            int(self.right_color_b * 255)
        )
        
        # Create a style sheet for the button
        style = f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); color: {'white' if color.lightness() < 128 else 'black'};"
        self.right_color_button.setStyleSheet(style)
    
    def create_buttons(self, parent_layout):
        """Create the action buttons"""
        button_layout = QHBoxLayout()
        
        # Add stretch to center the button
        button_layout.addStretch()
        
        # Create Controlify button
        self.controlify_button = QPushButton("Controlify")
        self.controlify_button.clicked.connect(self.on_controlify)
        self.controlify_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.controlify_button.setMaximumHeight(30)  # Fixed height
        button_layout.addWidget(self.controlify_button)
        
        # Add stretch after the button
        button_layout.addStretch()
        
        # Add button layout to parent
        parent_layout.addLayout(button_layout)
    
    def get_selected_constraint_type(self):
        """Return the selected constraint type name"""
        if self.rb_parent.isChecked():
            return "Parent/Child"
        elif self.rb_rotation.isChecked():
            return "Rotation"
        elif self.rb_position.isChecked():
            return "Position"
        elif self.rb_aim.isChecked():
            return "Aim"
        return "Parent/Child"  # Default
    
    def on_controlify(self):
        """Handle Controlify button click"""
        try:
            # Clean up any preview markers first
            self.cleanup_previews()
            
            # Get selected objects
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            
            # Validate selection
            if len(selected_models) == 0:
                QMessageBox.warning(self, "Selection Error", "No objects selected. Please select at least one object.")
                return
            
            # Get constraint type
            constraint_type = self.get_selected_constraint_type()
            
            # List to store created markers for selection
            created_markers = []
            
            # Process each selected object
            created_count = 0
            for model in selected_models:
                result = self.create_control_for_model(model, constraint_type)
                if result:
                    # The marker is the 4th element in the returned tuple
                    marker = result[3]
                    created_markers.append(marker)
                created_count += 1
            
            # Clear existing selection
            for component in FBSystem().Scene.Components:
                component.Selected = False
                
            # Select all newly created markers
            for marker in created_markers:
                marker.Selected = True
            
            # Update status
            self.status_label.setText(f"Created {created_count} control rig(s)")
            
            # Reset offset values for next creation
            self.reset_translation()
            self.reset_rotation()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            traceback.print_exc()
    
    def get_or_create_parent_control(self, model):
        """
        Find or create a parent control for the model
        
        If model has a parent, this will create a control at the parent's position
        that will control our entire setup. If a parent control already exists,
        it will be reused.
        
        Returns the parent control null or None if no parent exists
        """
        if not model.Parent:
            return None
        
        parent_model = model.Parent
        parent_model_name = parent_model.Name
        parent_control_name = f"{parent_model_name}_CTRL_parent"
        
        # Check if parent control already exists
        existing_parent_control = None
        for component in FBSystem().Scene.Components:
            if component.Name == parent_control_name and component.ClassName() == "FBModelNull":
                print(f"Found existing parent control: {parent_control_name}")
                existing_parent_control = component
                break
        
        if existing_parent_control:
            return existing_parent_control
        
        # Create new parent control
        print(f"Creating new parent control: {parent_control_name}")
        parent_control = FBModelNull(parent_control_name)
        parent_control.Show = True
        
        # Set parent control properties
        parent_control.Size = 10  # Small size for the parent control
        null_prop = parent_control.PropertyList.Find('Look')
        if null_prop:
            null_prop.Data = 10  # 10 = None
        
        # Copy the transform of the parent object to the parent control
        parent_matrix = FBMatrix()
        parent_model.GetMatrix(parent_matrix)
        parent_control.SetMatrix(parent_matrix)
        
        # Create parent constraint between parent model and parent control
        # INVERTED: Now parent_control is constrained by parent_model
        # Don't snap this constraint - just activate it
        constraint = self.create_constraint("Parent/Child", parent_control, parent_model, f"{parent_model_name}_CTRL", use_snap=False)
        
        # Add to custom folder
        if constraint and self.custom_folder:
            self.add_constraint_to_folder(constraint)
        
        return parent_control
    
    def create_control_for_model(self, model, constraint_type):
        """Create a control rig for the specified model"""
        model_name = model.Name
        
        # First, get or create the parent control if applicable
        parent_control = self.get_or_create_parent_control(model)
        
        # Get the scene reference for evaluation
        scene = FBSystem().Scene
        
        # Determine suffix based on constraint type
        if constraint_type == "Rotation":
            suffix = "_R"
        elif constraint_type == "Position":
            suffix = "_P"
        elif constraint_type == "Aim":
            suffix = "_A"
        else:
            suffix = ""
        
        # Create ALL objects first at default 0,0,0 position
        # Create offset parent null
        offset_parent_name = f"{model_name}{suffix}_OFFSET_PARENT"
        offset_parent = FBModelNull(offset_parent_name)
        offset_parent.Show = True
        offset_parent.Size = 20
        
        # Create offset null
        offset_null_name = f"{model_name}{suffix}_OFFSET"
        offset_null = FBModelNull(offset_null_name)
        offset_null.Show = True
        offset_null.Size = 15
        
        # Create main null
        null_name = f"{model_name}{suffix}_NULL"
        null = FBModelNull(null_name)
        null.Show = True
        null.Size = 10
        
        # Create marker
        marker_name = f"{model_name}{suffix}_CTRL"
        marker = FBModelMarker(marker_name)
        marker.Show = True
        self.apply_appearance_to_marker(marker, model.Name)
        
        # Now set up the hierarchy (all objects are still at 0,0,0)
        marker.Parent = null
        null.Parent = offset_null
        offset_null.Parent = offset_parent
        
        # If we have a parent control, parent the offset parent to it
        if parent_control:
            offset_parent.Parent = parent_control
        
        # Evaluate scene to update hierarchy
        scene.Evaluate()
        
        # Now position only the top-level object (offset_parent) to match the model
        # All children will follow automatically
        offset_parent_matrix = FBMatrix()
        model.GetMatrix(offset_parent_matrix)
        offset_parent.SetMatrix(offset_parent_matrix)
        
        # Evaluate scene to update positions
        scene.Evaluate()
        
        # Now apply the offset from UI to the offset null
        offset_trans = FBVector3d(
            self.offset_trans_x.value(),
            self.offset_trans_y.value(),
            self.offset_trans_z.value()
        )
        offset_rot = FBVector3d(
            self.offset_rot_x.value(),
            self.offset_rot_y.value(),
            self.offset_rot_z.value()
        )
        
        # Use SetVector for local transforms (more reliable than LclTranslation/LclRotation)
        offset_null.SetVector(offset_trans, FBModelTransformationType.kModelTranslation, False)  # False = local space
        offset_null.SetVector(offset_rot, FBModelTransformationType.kModelRotation, False)  # False = local space
        
        
        # Final evaluation
        scene.Evaluate()
        
        # Set nulls to invisible and lock their transforms
        for null_obj in [offset_parent, offset_null, null]:
            null_obj.Visibility = False
            null_obj.PropertyList.Find('Translation').SetLocked(True)
            null_obj.PropertyList.Find('Rotation').SetLocked(True)
            null_obj.PropertyList.Find('Scaling').SetLocked(True)
        
        # Set marker visibility inheritance to false so it stays visible
        marker.PropertyList.Find('Visibility Inheritance').Data = False
        
        # Create constraint between marker and original object
        constraint = self.create_constraint(constraint_type, model, marker, f"{model_name}{suffix}")
        
        # Move constraint to the custom folder
        if constraint and self.custom_folder:
            self.add_constraint_to_folder(constraint)
            
        # If creating a parent constraint, also create a scale constraint
        if constraint_type == "Parent/Child":
            scale_constraint = self.create_constraint("Scale", model, marker, f"{model_name}{suffix}_Scale")
            if scale_constraint and self.custom_folder:
                self.add_constraint_to_folder(scale_constraint)
            
        # If creating a rotation constraint, also create a position constraint on the offset parent
        if constraint_type == "Rotation":
            position_constraint = self.create_constraint("Position", offset_parent, model, f"{model_name}{suffix}_OffsetParent")
            if position_constraint and self.custom_folder:
                self.add_constraint_to_folder(position_constraint)
        
        return offset_parent, offset_null, null, marker, constraint
    
    def add_constraint_to_folder(self, constraint):
        """Add the constraint to the custom folder"""
        try:
            if self.custom_folder:
                self.custom_folder.ConnectSrc(constraint)
                print(f"Added constraint {constraint.Name} to custom folder")
            else:
                print("No custom folder available")
        except Exception as e:
            print(f"Error adding constraint to folder: {str(e)}")
            traceback.print_exc()
    
    def create_constraint(self, constraint_type, source, target, model_name, use_snap=True):
        """Create a constraint between two objects"""
        try:
            # Create the constraint by name (most reliable method)
            constraint = FBConstraintManager().TypeCreateConstraint(constraint_type)
            
            if constraint:
                # Set a meaningful name for the constraint
                constraint.Name = f"{model_name}_{constraint_type.replace('/', '_')}_Constraint"
                
                # Add constrained object (the one that will be controlled)
                constraint.ReferenceAdd(0, source)  # 0 is the index for constrained objects
                
                # Add source object (the controller)
                constraint.ReferenceAdd(1, target)  # 1 is the index for source objects
                
                # Special setup for Aim constraint
                if constraint_type == "Aim":
                    # Set aim vector to +Z (default forward)
                    aim_vector_prop = constraint.PropertyList.Find('AimVector')
                    if aim_vector_prop:
                        aim_vector_prop.Data = FBVector3d(0.0, 0.0, 1.0)
                    
                    # Set up vector to +Y (default up)
                    up_vector_prop = constraint.PropertyList.Find('UpVector')
                    if up_vector_prop:
                        up_vector_prop.Data = FBVector3d(0.0, 1.0, 0.0)
                
                # Use snap if requested (default true for regular constraints)
                if use_snap:
                    constraint.Snap()  # This maintains the current offset
                    
                constraint.Active = True
                
                print(f"Created constraint: {constraint.Name} (snap={use_snap})")
                return constraint
                
        except Exception as e:
            print(f"Error creating constraint: {str(e)}")
            traceback.print_exc()
            return None
    
    def check_selection(self):
        """Check if a single marker is selected"""
        if self.manual_offset_active:
            # During manual offset mode, force selection to stay on offset null
            self.manual_offset_button.setVisible(True)
            self.update_ui_from_offset_null()
            
            # Find the offset null based on the marker name
            offset_name = None
            if "_CTRL" in self.manual_offset_marker.Name:
                offset_name = self.manual_offset_marker.Name.replace("_CTRL", "_OFFSET")
            else:
                offset_name = self.manual_offset_marker.Name + "_OFFSET"
                
            offset_null = None
            for component in FBSystem().Scene.Components:
                if component.Name == offset_name and component.ClassName() == "FBModelNull":
                    offset_null = component
                    break
            
            # If offset null is not selected, reselect it
            if offset_null and not offset_null.Selected:
                # Clear all selections
                for component in FBSystem().Scene.Components:
                    component.Selected = False
                # Reselect the offset null
                offset_null.Selected = True
            
            return
            
        selected_models = FBModelList()
        FBGetSelectedModels(selected_models)
        
        # Count selected markers
        marker_count = 0
        for model in selected_models:
            if model.ClassName() == "FBModelMarker" and "_CTRL" in model.Name:
                marker_count += 1
        
        # Update delete button visibility and text
        if marker_count > 0:
            self.delete_button.setVisible(True)
            self.delete_button.setText(f"Delete Control{'s' if marker_count > 1 else ''}")
        else:
            self.delete_button.setVisible(False)
        
        # Show manual offset button only if single marker selected
        if len(selected_models) == 1 and selected_models[0].ClassName() == "FBModelMarker":
            marker = selected_models[0]
            # Check if this is one of our created markers (has _CTRL suffix)
            if "_CTRL" in marker.Name:
                self.manual_offset_button.setVisible(True)
                # Don't update radio buttons for manual offset markers
                return
        else:
            self.manual_offset_button.setVisible(False)
            
        # Update radio button states based on selected objects' constraints
        self.update_constraint_radio_states(selected_models)
    
    def update_constraint_radio_states(self, selected_models):
        """Update the enabled state of constraint radio buttons based on selection"""
        # If no selection, enable all
        if len(selected_models) == 0:
            self.rb_parent.setEnabled(True)
            self.rb_rotation.setEnabled(True)
            self.rb_position.setEnabled(True)
            return
            
        # Check constraints on all selected objects
        can_create_parent = True
        can_create_rotation = True
        can_create_position = True
        
        for model in selected_models:
            # Skip markers and nulls
            if model.ClassName() == "FBModelMarker":
                continue
            if model.ClassName() == "FBModelNull":
                name = model.Name
                if name.endswith("_OFFSET_PARENT") or name.endswith("_OFFSET") or name.endswith("_NULL"):
                    continue
                    
            # Check existing constraints for this model
            has_parent = False
            has_position = False
            has_rotation = False
            
            for constraint in FBSystem().Scene.Constraints:
                # Check if this model is the constrained object
                ref_group_count = constraint.ReferenceGroupGetCount()
                is_constrained = False
                
                if ref_group_count > 0:
                    ref_count = constraint.ReferenceGetCount(0)
                    for j in range(ref_count):
                        ref_obj = constraint.ReferenceGet(0, j)
                        if ref_obj and ref_obj == model:
                            is_constrained = True
                            break
                
                if is_constrained:
                    constraint_name = constraint.Name
                    
                    # Check constraint type based on the name
                    if "_Rotation_Constraint" in constraint_name:
                        has_rotation = True
                    elif "_Position_Constraint" in constraint_name:
                        has_position = True
                    elif "_Parent_Child_Constraint" in constraint_name:
                        has_parent = True
            
            # Update what we can create based on this object's constraints
            if has_parent:
                # If has parent, can't create any
                can_create_parent = False
                can_create_rotation = False
                can_create_position = False
            else:
                # If has rotation, can't create rotation or parent
                if has_rotation:
                    can_create_rotation = False
                    can_create_parent = False
                # If has position, can't create position or parent
                if has_position:
                    can_create_position = False
                    can_create_parent = False
                # If has both, can't create anything
                if has_rotation and has_position:
                    can_create_parent = False
                    can_create_rotation = False
                    can_create_position = False
        
        # Update radio button states
        self.rb_parent.setEnabled(can_create_parent)
        self.rb_rotation.setEnabled(can_create_rotation)
        self.rb_position.setEnabled(can_create_position)
        self.rb_aim.setEnabled(can_create_rotation)  # Aim constraint follows rotation rules
    
    def toggle_manual_offset(self):
        """Toggle manual offset mode"""
        if not self.manual_offset_active:
            self.start_manual_offset()
        else:
            self.end_manual_offset()
    
    def start_manual_offset(self):
        """Start manual offset mode"""
        selected_models = FBModelList()
        FBGetSelectedModels(selected_models)
        
        if len(selected_models) != 1 or selected_models[0].ClassName() != "FBModelMarker":
            return
            
        marker = selected_models[0]
        
        # Find the offset null (handle different suffixes)
        offset_name = None
        if "_CTRL" in marker.Name:
            offset_name = marker.Name.replace("_CTRL", "_OFFSET")
        else:
            offset_name = marker.Name + "_OFFSET"
            
        offset_null = None
        for component in FBSystem().Scene.Components:
            if component.Name == offset_name and component.ClassName() == "FBModelNull":
                offset_null = component
                break
        
        if not offset_null:
            return
            
        # Find and disable all constraints related to this marker
        constraints_to_disable = []
        for c in FBSystem().Scene.Constraints:
            try:
                ref_group_count = c.ReferenceGroupGetCount()
                for i in range(ref_group_count):
                    ref_count = c.ReferenceGetCount(i)
                    for j in range(ref_count):
                        if c.ReferenceGet(i, j) == marker:
                            constraints_to_disable.append(c)
                            break
                    if c in constraints_to_disable:
                        break
            except:
                continue
        
        # Disable all found constraints
        for constraint in constraints_to_disable:
            constraint.Active = False
            
        # Unlock offset null transforms including scaling
        offset_null.PropertyList.Find('Translation').SetLocked(False)
        offset_null.PropertyList.Find('Rotation').SetLocked(False)
        offset_null.PropertyList.Find('Scaling').SetLocked(False)
        
        # Clear selection by setting all components to unselected
        for component in FBSystem().Scene.Components:
            component.Selected = False
        # Select the offset null
        offset_null.Selected = True
        
        # Update state
        self.manual_offset_active = True
        self.manual_offset_marker = marker
        self.manual_offset_constraints = constraints_to_disable  # Store all constraints
        self.manual_offset_button.setText("⚠ Set Manual Offset ⚠")
        # Set green background color for the button
        self.manual_offset_button.setStyleSheet("""
            QPushButton {
                background-color: #90EE90;  /* Light green */
                font-weight: bold;
                color: #000000;
                border: 2px solid #228B22;
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #77DD77;  /* Slightly darker green on hover */
            }
            QPushButton:pressed {
                background-color: #66CC66;  /* Even darker green when pressed */
            }
        """)
    
    def end_manual_offset(self):
        """End manual offset mode"""
        if not self.manual_offset_active:
            return
            
        # Re-lock offset null transforms (handle different naming)
        offset_name = None
        if "_CTRL" in self.manual_offset_marker.Name:
            offset_name = self.manual_offset_marker.Name.replace("_CTRL", "_OFFSET")
        else:
            offset_name = self.manual_offset_marker.Name + "_OFFSET"
            
        offset_null = None
        for component in FBSystem().Scene.Components:
            if component.Name == offset_name and component.ClassName() == "FBModelNull":
                offset_null = component
                break
                
        if offset_null:
            # Check if the offset null has been scaled
            scale = FBVector3d()
            offset_null.GetVector(scale, FBModelTransformationType.kModelScaling, False)
            
            # If scaled (not 1,1,1), apply the scale to the marker size
            if scale[0] != 1.0 or scale[1] != 1.0 or scale[2] != 1.0:
                # Get the average scale factor
                scale_factor = (scale[0] + scale[1] + scale[2]) / 3.0
                
                # Apply scale to the marker size
                current_marker_size = self.manual_offset_marker.Size
                new_marker_size = current_marker_size * scale_factor
                self.manual_offset_marker.Size = new_marker_size
                
                # Reset the offset null scale to 1,1,1
                offset_null.SetVector(FBVector3d(1.0, 1.0, 1.0), FBModelTransformationType.kModelScaling, False)
                
                print(f"Applied scale factor {scale_factor} to marker size: {current_marker_size} -> {new_marker_size}")
            
            offset_null.PropertyList.Find('Translation').SetLocked(True)
            offset_null.PropertyList.Find('Rotation').SetLocked(True)
            offset_null.PropertyList.Find('Scaling').SetLocked(True)
        
        # Re-enable and snap all constraints
        if hasattr(self, 'manual_offset_constraints'):
            for constraint in self.manual_offset_constraints:
                if constraint:
                    constraint.Snap()
                    constraint.Active = True
        
        # Clear selection by setting all components to unselected
        for component in FBSystem().Scene.Components:
            component.Selected = False
        
        # Update state
        self.manual_offset_active = False
        self.manual_offset_marker = None
        self.manual_offset_constraints = None
        self.manual_offset_button.setText("Manual Offset")
        # Reset button style to default
        self.manual_offset_button.setStyleSheet("")
        
        # Reset offset UI values to 0
        self.reset_translation()
        self.reset_rotation()
    
    def update_ui_from_offset_null(self):
        """Update UI offset values from the selected offset null"""
        if not self.manual_offset_active:
            return
            
        # Get the offset name based on the marker type
        offset_name = None
        if "_CTRL" in self.manual_offset_marker.Name:
            offset_name = self.manual_offset_marker.Name.replace("_CTRL", "_OFFSET")
        else:
            offset_name = self.manual_offset_marker.Name + "_OFFSET"
            
        offset_null = None
        for component in FBSystem().Scene.Components:
            if component.Name == offset_name and component.ClassName() == "FBModelNull":
                offset_null = component
                break
                
        if offset_null:
            # Get local transformation values
            trans = FBVector3d()
            rot = FBVector3d()
            offset_null.GetVector(trans, FBModelTransformationType.kModelTranslation, False)
            offset_null.GetVector(rot, FBModelTransformationType.kModelRotation, False)
            
            # Update UI without triggering change events
            self.offset_trans_x.blockSignals(True)
            self.offset_trans_y.blockSignals(True)
            self.offset_trans_z.blockSignals(True)
            self.offset_rot_x.blockSignals(True)
            self.offset_rot_y.blockSignals(True)
            self.offset_rot_z.blockSignals(True)
            
            self.offset_trans_x.setValue(trans[0])
            self.offset_trans_y.setValue(trans[1])
            self.offset_trans_z.setValue(trans[2])
            self.offset_rot_x.setValue(rot[0])
            self.offset_rot_y.setValue(rot[1])
            self.offset_rot_z.setValue(rot[2])
            
            self.offset_trans_x.blockSignals(False)
            self.offset_trans_y.blockSignals(False)
            self.offset_trans_z.blockSignals(False)
            self.offset_rot_x.blockSignals(False)
            self.offset_rot_y.blockSignals(False)
            self.offset_rot_z.blockSignals(False)
    
    def delete_controls(self):
        """Delete selected control rigs"""
        selected_models = FBModelList()
        FBGetSelectedModels(selected_models)
        
        # Get all selected markers
        selected_markers = []
        for model in selected_models:
            if model.ClassName() == "FBModelMarker" and "_CTRL" in model.Name:
                selected_markers.append(model)
        
        if not selected_markers:
            return
            
        # Confirm deletion
        result = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete {len(selected_markers)} control{'s' if len(selected_markers) > 1 else ''}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
            
        # Track CTRL_parent nulls to check for deletion
        ctrl_parents_to_check = set()
            
        # Delete each control rig
        deleted_count = 0
        for marker in selected_markers:
            # Determine the constraint type from the marker name
            constraint_suffix = ""
            base_name = marker.Name
            if "_R_CTRL" in base_name:
                constraint_suffix = "_R"
                base_name = base_name.replace("_R_CTRL", "")
            elif "_P_CTRL" in base_name:
                constraint_suffix = "_P"
                base_name = base_name.replace("_P_CTRL", "")
            elif "_A_CTRL" in base_name:
                constraint_suffix = "_A"
                base_name = base_name.replace("_A_CTRL", "")
            else:
                # Parent constraint has no suffix
                base_name = base_name.replace("_CTRL", "")
            
            # Find the specific offset parent for this constraint type
            offset_parent = None
            offset_parent_name = f"{base_name}{constraint_suffix}_OFFSET_PARENT"
            for component in FBSystem().Scene.Components:
                if component.Name == offset_parent_name:
                    offset_parent = component
                    # Track parent control if this offset parent has one
                    if offset_parent.Parent and offset_parent.Parent.Name.endswith("_CTRL_parent"):
                        ctrl_parents_to_check.add(offset_parent.Parent)
                    break
            
            # Find and delete only components specific to this constraint chain
            components_to_delete = []
            
            # Find nulls specific to this constraint type
            specific_names = [
                f"{base_name}{constraint_suffix}_OFFSET_PARENT",
                f"{base_name}{constraint_suffix}_OFFSET",
                f"{base_name}{constraint_suffix}_NULL"
            ]
            
            for component in FBSystem().Scene.Components:
                if component.Name in specific_names:
                    components_to_delete.append(component)
            
            # Find constraints specific to this control
            for constraint in FBSystem().Scene.Constraints:
                # Be more specific - only delete if it's the exact constraint for this controller
                if constraint.Name == f"{base_name}{constraint_suffix}_Rotation_Constraint" or \
                   constraint.Name == f"{base_name}{constraint_suffix}_Position_Constraint" or \
                   constraint.Name == f"{base_name}{constraint_suffix}_Parent_Child_Constraint" or \
                   constraint.Name == f"{base_name}{constraint_suffix}_Aim_Constraint" or \
                   constraint.Name == f"{base_name}{constraint_suffix}_Scale_Scale_Constraint":
                    components_to_delete.append(constraint)
                # Also check for offset parent position constraint for rotation controls
                elif constraint_suffix == "_R" and constraint.Name == f"{base_name}{constraint_suffix}_OffsetParent_Position_Constraint":
                    components_to_delete.append(constraint)
            
            # Add the marker itself
            components_to_delete.append(marker)
            
            # Delete all components
            for component in components_to_delete:
                try:
                    print(f"Deleting: {component.Name}")
                    component.FBDelete()
                except:
                    pass
                    
            deleted_count += 1
        
        # After deletion, check each CTRL_parent to see if it still has children
        for ctrl_parent in ctrl_parents_to_check:
            try:
                # Skip if already deleted
                if not ctrl_parent or not hasattr(ctrl_parent, 'Name'):
                    continue
                    
                # Check if the parent still has children
                has_children = False
                for obj in FBSystem().Scene.Components:
                    try:
                        if obj.Parent == ctrl_parent:
                            has_children = True
                            break
                    except:
                        continue
                
                if not has_children:
                    print(f"Found orphaned parent control: {ctrl_parent.Name}")
                    
                    # Find and delete all constraints that reference this parent
                    constraints_to_delete = []
                    for constraint in FBSystem().Scene.Constraints:
                        try:
                            ref_group_count = constraint.ReferenceGroupGetCount()
                            found_ref = False
                            for i in range(ref_group_count):
                                ref_count = constraint.ReferenceGetCount(i)
                                for j in range(ref_count):
                                    if constraint.ReferenceGet(i, j) == ctrl_parent:
                                        constraints_to_delete.append(constraint)
                                        found_ref = True
                                        break
                                if found_ref:
                                    break
                        except:
                            continue
                    
                    # Delete all found constraints
                    for constraint in constraints_to_delete:
                        try:
                            print(f"Deleting constraint: {constraint.Name}")
                            constraint.FBDelete()
                        except Exception as e:
                            print(f"Failed to delete constraint: {e}")
                            
                    # Delete the parent control
                    try:
                        print(f"Deleting parent control: {ctrl_parent.Name}")
                        ctrl_parent.FBDelete()
                    except Exception as e:
                        print(f"Failed to delete parent control: {e}")
                        
            except Exception as e:
                print(f"Error checking parent control: {str(e)}")
        
        self.status_label.setText(f"Deleted {deleted_count} control rig{'s' if deleted_count > 1 else ''}")
    
    def showEvent(self, event):
        """Override show event to handle focus issues in MotionBuilder"""
        super().showEvent(event)
        # Ensure the window stays on top when shown
        self.activateWindow()
        self.raise_()
    
    def closeEvent(self, event):
        """Handle window close event"""
        self.cleanup_previews()
        self.preview_timer.stop()
        self.selection_timer.stop()
        if self.manual_offset_active:
            self.end_manual_offset()
        event.accept()
    
    def show_info_dialog(self):
        """Show information dialog about the script"""
        info_dialog = QDialog(self)
        info_dialog.setWindowTitle("Controlify Information")
        info_dialog.setWindowFlags(info_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        info_dialog.setMinimumWidth(400)
        info_dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout()
        info_dialog.setLayout(layout)
        
        # Create text widget with formatted information
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setHtml("""
<p>============== "Morris" 2025 ヽ(◔◡◉)ﾉ =============</p>        

<h2>Controlify</h2>

<p>Creates control markers for animating objects with constraints.</p>

<h3>Creating a Controller:</h3>
<ol>
<li>Select object(s) in the scene</li>
<li>Choose constraint type (Parent, Position, Rotation, or Aim)</li>
<li>Adjust marker appearance if needed</li>
<li>Click "Controlify"</li>
</ol>

<p>The controller marker will be created and constrained to your object. You can animate the marker to control the object's movement.</p>

<h3>Manual Offset:</h3>
<p>To reposition a created controller:</p>
<ol>
<li>Select the controller marker</li>
<li>Click "Manual Offset"</li>
<li>Move/rotate/scale the offset null in the viewport</li>
<li>Click "Set Manual Offset" to apply</li>
</ol>

<p><b>Tip:</b> Scaling the offset null changes the marker size.</p>

<h3>Right/Left Coloring:</h3>
<p>Enable to automatically color markers based on object names:<br>
- Left (_l_, _left_, etc.) = Red<br>
- Right (_r_, _right_, etc.) = Blue<br>
You can customize these colors with the picker buttons.</p>

        """)
        
        layout.addWidget(info_text)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(info_dialog.close)
        layout.addWidget(close_button)
        
        info_dialog.exec_()


def show_dialog():
    """Show the dialog"""
    # In MotionBuilder, we don't need to create a QApplication or call exec()
    # We just need to create and show our dialog
    try:
        dialog = ControlifyDialog()
        dialog.show()
        # Store a reference to prevent garbage collection
        global controlify_dialog
        controlify_dialog = dialog
        print("Dialog created and shown successfully")
    except Exception as e:
        print(f"Error showing dialog: {str(e)}")
        traceback.print_exc()


# When script is run directly, create and show the dialog
# This is the entry point for MotionBuilder
try:
    print("Starting Controlify script...")
    show_dialog()
    print("Controlify dialog initialized")
except Exception as e:
    print(f"Critical error: {str(e)}")
    traceback.print_exc()