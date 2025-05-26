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
    # print("MotionBuilder SDK loaded successfully")
except ImportError:
    MOBU_AVAILABLE = False
    # print("Warning: pyfbsdk not found. Running in development mode.")

# Import PySide6 modules
try:
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QRadioButton, QPushButton, QMessageBox, QLabel, QSpinBox,
        QComboBox, QColorDialog, QDoubleSpinBox, QGridLayout, QCheckBox,
        QSizePolicy, QTextEdit, QWidget, QLineEdit
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor
    # print("PySide6 modules imported successfully")
except ImportError as e:
    # print(f"Error importing PySide6: {str(e)}")
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
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        
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
        
        # Track selection order for object-to-object constraints
        self.selection_order_list = []  # Will store exactly 2 objects in selection order
        self.last_selection_state = set()  # Track what was selected last frame
        self.setup_selection_tracking()
        
        # Create the main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # Add preview checkbox at the top
        self.create_preview_checkbox(main_layout)
        
        # Constrain object to object checkbox (moved above constraint type)
        self.manual_pairing_cb = QCheckBox("Constrain object to object")
        self.manual_pairing_cb.setToolTip("Create constraints directly between two selected objects (First = Source, Second = Target)")
        self.manual_pairing_cb.setStyleSheet("""
            QCheckBox:checked {
                font-weight: bold;
                color: #00AA00;
            }
        """)
        self.manual_pairing_cb.toggled.connect(self.on_manual_pairing_toggled)
        main_layout.addWidget(self.manual_pairing_cb)
        
        # Add constraint type selection
        self.create_constraint_group(main_layout)
        
        # Add Character Extension controls
        self.create_character_extension_group(main_layout)
        
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
        
        # Temporary Constraint button (hidden by default)
        temp_layout = QHBoxLayout()
        temp_layout.addStretch()
        
        self.temp_constraint_button = QPushButton("Temporary Constraint")
        self.temp_constraint_button.clicked.connect(self.create_temporary_constraint)
        self.temp_constraint_button.setVisible(False)
        self.temp_constraint_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.temp_constraint_button.setMaximumHeight(30)  # Fixed height
        temp_layout.addWidget(self.temp_constraint_button)
        
        temp_layout.addStretch()
        main_layout.addLayout(temp_layout)
        
        # Create custom constraints folder on initialization
        self.ensure_custom_constraints_folder_exists()
        
        # Set up preview timer
        self.setup_preview_timer()
        
        # Connect closeEvent to clean up previews
        self.destroyed.connect(self.cleanup_previews)
        
        # Track current selection to avoid unnecessary updates
        self.last_selection = []
        
        # Start preview immediately since it's on by default
        if self.preview_enabled:
            self.toggle_preview(True)
    
    def get_custom_constraints_folder(self):
        """Get or create the custom constraints folder"""
        folder_name = "Custom_Constraints"
        found_folder = None
        
        # Check if the folder already exists in the scene
        scene = FBSystem().Scene
        for component in scene.Components:
            if component.Name == folder_name and component.ClassName() == "FBFolder":
                found_folder = component
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
                # Create the folder with a reference to the Constraints component
                found_folder = FBFolder(folder_name, constraints_component)
        
        return found_folder
    
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
                    # print(f"Found existing folder: {folder_name}")
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
                    # print(f"Created new folder: {folder_name}")
                else:
                    pass  # Could not find Constraints component in scene
            
            # Store reference to the folder
            self.custom_folder = found_folder
            
        except Exception as e:
            # print(f"Error creating custom folder: {str(e)}")
            # traceback.print_exc()
            pass
            self.custom_folder = None
    
    def get_collapsible_group_style(self):
        """Get the style for collapsible group boxes"""
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
    
    def create_constraint_group(self, parent_layout):
        """Create the constraint type selection group"""
        # Create collapsible group
        group_box = QGroupBox("▼ Constraint Type")
        group_box.setStyleSheet(self.get_collapsible_group_style())
        group_box.mousePressEvent = lambda event: self.on_constraint_group_clicked()
        
        self.constraint_group = group_box
        self.constraint_group_expanded = True
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
        
        # Create container widget to hold the radio buttons
        radio_container = QWidget()
        radio_container.setLayout(group_layout)
        self.constraint_radio_container = radio_container
        
        # Main group layout
        main_group_layout = QVBoxLayout()
        main_group_layout.addWidget(radio_container)
        
        # Set group layout
        group_box.setLayout(main_group_layout)
        
        # Add to parent layout
        parent_layout.addWidget(group_box)
        
        # Connect the radio buttons to the preview update function
        self.rb_parent.toggled.connect(self.on_settings_changed)
        self.rb_rotation.toggled.connect(self.on_settings_changed)
        self.rb_position.toggled.connect(self.on_settings_changed)
        self.rb_aim.toggled.connect(self.on_settings_changed)
    
    def create_offset_group(self, parent_layout):
        """Create the controller offset settings group"""
        # Create collapsible group (collapsed by default)
        group_box = QGroupBox("► Controller Offset")
        group_box.setStyleSheet(self.get_collapsible_group_style())
        group_box.mousePressEvent = lambda event: self.on_controller_offset_clicked()
        
        self.controller_offset_group = group_box  # Store reference
        self.controller_offset_expanded = False
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
        
        # Create container widget to hold all controls
        controls_container = QWidget()
        controls_container.setLayout(group_layout)
        self.controller_offset_container = controls_container
        
        # Main group layout
        main_group_layout = QVBoxLayout()
        main_group_layout.addWidget(controls_container)
        
        group_box.setLayout(main_group_layout)
        
        # Set initial collapsed state
        controls_container.setVisible(False)
        group_box.setFixedHeight(30)
        
        parent_layout.addWidget(group_box)
        
        # Initialize manual offset state
        self.manual_offset_active = False
        self.manual_offset_marker = None
        self.manual_offset_constraint = None
        self.drag_operation_timer = None
        
        # Set up selection change monitoring
        self.selection_timer = QTimer(self)
        self.selection_timer.timeout.connect(self.check_selection)
        self.selection_timer.start(200)  # Check every 200ms
    
    def create_character_extension_group(self, parent_layout):
        """Create the Character Extension settings group"""
        # Create collapsible group (collapsed by default)
        group_box = QGroupBox("► Character Extension")
        group_box.setStyleSheet(self.get_collapsible_group_style())
        group_box.mousePressEvent = lambda event: self.on_character_extension_clicked()
        
        self.character_extension_group = group_box  # Store reference
        self.character_extension_expanded = False
        
        # Main group layout with minimal spacing
        main_group_layout = QVBoxLayout()
        main_group_layout.setContentsMargins(5, 5, 5, 5)  # Reduce margins
        main_group_layout.setSpacing(2)  # Minimal spacing between items
        
        # Checkbox to enable/disable Character Extension functionality
        self.char_ext_checkbox = QCheckBox("Add to Character Extension")
        self.char_ext_checkbox.setChecked(False)
        self.char_ext_checkbox.toggled.connect(self.on_char_ext_toggled)
        main_group_layout.addWidget(self.char_ext_checkbox)
        
        # Container for dropdown and name input (hidden by default)
        self.char_ext_controls_container = QWidget()
        controls_layout = QGridLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)  # No margins
        controls_layout.setSpacing(2)  # Minimal spacing
        
        # Character Extension dropdown
        self.ext_label = QLabel("Extension:")
        self.ext_label.setFixedWidth(80)  # Fixed width for label
        controls_layout.addWidget(self.ext_label, 0, 0)
        
        self.char_ext_combo = QComboBox()
        self.char_ext_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Allow expansion
        self.populate_character_extensions()
        controls_layout.addWidget(self.char_ext_combo, 0, 1)
        self.char_ext_combo.currentIndexChanged.connect(self.on_char_ext_selection_changed)
        
        # Extension name input (for new extensions)
        self.name_label = QLabel("Extension Name:")
        self.name_label.setFixedWidth(80)  # Same fixed width as extension label
        controls_layout.addWidget(self.name_label, 1, 0)
        
        self.char_ext_name_input = QLineEdit()
        self.char_ext_name_input.setPlaceholderText("Enter new extension name...")
        # Set placeholder text color to white
        self.char_ext_name_input.setStyleSheet("QLineEdit { color: white; } QLineEdit::placeholder { color: white; }")
        self.char_ext_name_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Allow expansion
        controls_layout.addWidget(self.char_ext_name_input, 1, 1)
        
        # Set column stretch factors to maintain consistent sizing
        controls_layout.setColumnStretch(0, 0)  # Labels don't stretch
        controls_layout.setColumnStretch(1, 1)  # Input controls stretch
        
        # Initially hide name input row
        self.name_label.setVisible(False)
        self.char_ext_name_input.setVisible(False)
        
        self.char_ext_controls_container.setLayout(controls_layout)
        main_group_layout.addWidget(self.char_ext_controls_container)
        
        # Hide controls by default
        self.char_ext_controls_container.setVisible(False)
        
        # Create main container
        self.character_extension_container = QWidget()
        self.character_extension_container.setLayout(main_group_layout)
        
        # Overall group layout
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.addWidget(self.character_extension_container)
        group_box.setLayout(group_layout)
        
        # Set initial collapsed state
        self.character_extension_container.setVisible(False)
        group_box.setFixedHeight(30)
        
        parent_layout.addWidget(group_box)
    
    def create_marker_appearance_group(self, parent_layout):
        """Create the marker appearance settings group"""
        # Create collapsible group (collapsed by default)
        group_box = QGroupBox("► Marker Appearance")
        group_box.setStyleSheet(self.get_collapsible_group_style())
        group_box.mousePressEvent = lambda event: self.on_marker_appearance_clicked()
        
        self.marker_appearance_group = group_box  # Store reference
        self.marker_appearance_expanded = False
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
        self.marker_size_spin.valueChanged.connect(self.on_marker_size_changed)
        
        
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
        
        # Create container widget to hold all controls
        controls_container = QWidget()
        controls_container.setLayout(group_layout)
        self.marker_appearance_container = controls_container
        
        # Main group layout
        main_group_layout = QVBoxLayout()
        main_group_layout.addWidget(controls_container)
        
        # Set the group layout
        group_box.setLayout(main_group_layout)
        
        # Set initial collapsed state
        controls_container.setVisible(False)
        group_box.setFixedHeight(30)
        
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
    
    def on_manual_pairing_toggled(self, checked):
        """Handle manual pairing checkbox toggle"""
        if checked:
            # Store preview state before disabling
            self.preview_was_enabled = self.preview_enabled
            # Store group states
            self.marker_appearance_was_expanded = self.marker_appearance_expanded
            self.controller_offset_was_expanded = self.controller_offset_expanded
            self.character_extension_was_expanded = self.character_extension_expanded
            
            # Store Character Extension checkbox state
            self.char_ext_was_enabled = self.char_ext_checkbox.isChecked()
            
            # Disable preview and gray it out
            if self.preview_enabled:
                self.preview_checkbox.setChecked(False)
            self.preview_checkbox.setEnabled(False)
            
            # Disable Character Extension checkbox and hide group completely
            self.char_ext_checkbox.setChecked(False)
            self.char_ext_checkbox.setEnabled(False)
            self.character_extension_group.setVisible(False)
            
            # Hide marker appearance and controller offset groups completely
            self.marker_appearance_group.setVisible(False)
            self.controller_offset_group.setVisible(False)
            
            # Clear selection tracking when entering manual pairing mode
            self.selection_order_list = []
            self.last_selection_state = set()
            
            # Update status label
            self.status_label.setText("Constrain object to object: Select 2 objects (First = Source, Second = Target)")
            
            # Adjust window size
            QTimer.singleShot(10, self.adjustSize)
        else:
            # Re-enable preview checkbox
            self.preview_checkbox.setEnabled(True)
            # Restore preview state if it was enabled before
            if hasattr(self, 'preview_was_enabled') and self.preview_was_enabled:
                self.preview_checkbox.setChecked(True)
            
            # Re-enable Character Extension checkbox and show group
            self.char_ext_checkbox.setEnabled(True)
            self.character_extension_group.setVisible(True)
            # Restore Character Extension checkbox state
            if hasattr(self, 'char_ext_was_enabled') and self.char_ext_was_enabled:
                self.char_ext_checkbox.setChecked(True)
            
            # Show marker appearance and controller offset groups with restored state
            self.marker_appearance_group.setVisible(True)
            self.controller_offset_group.setVisible(True)
            
            # Restore expanded states
            if hasattr(self, 'character_extension_was_expanded'):
                self.character_extension_expanded = self.character_extension_was_expanded
                self.character_extension_container.setVisible(self.character_extension_expanded)
                if not self.character_extension_expanded:
                    self.character_extension_group.setFixedHeight(30)
                    
            if hasattr(self, 'marker_appearance_was_expanded'):
                self.marker_appearance_expanded = self.marker_appearance_was_expanded
                self.marker_appearance_container.setVisible(self.marker_appearance_expanded)
                if not self.marker_appearance_expanded:
                    self.marker_appearance_group.setFixedHeight(30)
                
            if hasattr(self, 'controller_offset_was_expanded'):
                self.controller_offset_expanded = self.controller_offset_was_expanded
                self.controller_offset_container.setVisible(self.controller_offset_expanded)
                if not self.controller_offset_expanded:
                    self.controller_offset_group.setFixedHeight(30)
            
            # Reset status label
            self.status_label.setText("Select objects and press Controlify")
            
            # Adjust window size
            QTimer.singleShot(10, self.adjustSize)
    
    def on_constraint_group_clicked(self):
        """Handle constraint group collapse/expand"""
        self.constraint_group_expanded = not self.constraint_group_expanded
        self.constraint_radio_container.setVisible(self.constraint_group_expanded)
        
        # Update arrow indicator
        title = self.constraint_group.title()
        if self.constraint_group_expanded:
            self.constraint_group.setTitle(title.replace("►", "▼"))
        else:
            self.constraint_group.setTitle(title.replace("▼", "►"))
        
        if not self.constraint_group_expanded:
            self.constraint_group.setFixedHeight(30)
        else:
            self.constraint_group.setMaximumHeight(16777215)
            self.constraint_group.setMinimumHeight(0)
        
        # Adjust window size
        QTimer.singleShot(10, self.adjustSize)
    
    def on_marker_appearance_clicked(self):
        """Handle marker appearance group collapse/expand"""
        self.marker_appearance_expanded = not self.marker_appearance_expanded
        self.marker_appearance_container.setVisible(self.marker_appearance_expanded)
        
        # Update arrow indicator
        title = self.marker_appearance_group.title()
        if self.marker_appearance_expanded:
            self.marker_appearance_group.setTitle(title.replace("►", "▼"))
        else:
            self.marker_appearance_group.setTitle(title.replace("▼", "►"))
        
        if not self.marker_appearance_expanded:
            self.marker_appearance_group.setFixedHeight(30)
        else:
            self.marker_appearance_group.setMaximumHeight(16777215)
            self.marker_appearance_group.setMinimumHeight(0)
        
        # Adjust window size
        QTimer.singleShot(10, self.adjustSize)
    
    def on_controller_offset_clicked(self):
        """Handle controller offset group collapse/expand"""
        self.controller_offset_expanded = not self.controller_offset_expanded
        self.controller_offset_container.setVisible(self.controller_offset_expanded)
        
        # Update arrow indicator
        title = self.controller_offset_group.title()
        if self.controller_offset_expanded:
            self.controller_offset_group.setTitle(title.replace("►", "▼"))
        else:
            self.controller_offset_group.setTitle(title.replace("▼", "►"))
        
        if not self.controller_offset_expanded:
            self.controller_offset_group.setFixedHeight(30)
        else:
            self.controller_offset_group.setMaximumHeight(16777215)
            self.controller_offset_group.setMinimumHeight(0)
        
        # Adjust window size
        QTimer.singleShot(10, self.adjustSize)
    
    def on_character_extension_clicked(self):
        """Toggle character extension group visibility"""
        if self.character_extension_expanded:
            # Collapse
            self.character_extension_container.setVisible(False)
            self.character_extension_group.setFixedHeight(30)
            self.character_extension_group.setTitle("► Character Extension")
            self.character_extension_expanded = False
        else:
            # Expand
            self.character_extension_container.setVisible(True)
            # Calculate height based on current content
            self.update_character_extension_height()
            self.character_extension_group.setTitle("▼ Character Extension")
            self.character_extension_expanded = True
        
        # Adjust window size
        QTimer.singleShot(10, self.adjustSize)
    
    def on_char_ext_toggled(self, checked):
        """Toggle Character Extension controls based on checkbox"""
        self.char_ext_controls_container.setVisible(checked)
        if checked:
            # Refresh the dropdown when enabled
            self.populate_character_extensions()
            # Show/hide name input based on current selection
            self.on_char_ext_selection_changed()
        
        # Update height when expanded
        if self.character_extension_expanded:
            self.update_character_extension_height()
        
        # Adjust window size
        QTimer.singleShot(10, self.adjustSize)
    
    def on_char_ext_selection_changed(self):
        """Handle Character Extension dropdown selection changes"""
        if not self.char_ext_checkbox.isChecked():
            return
            
        current_text = self.char_ext_combo.currentText()
        is_create_new = current_text == "Create New Extension"
        
        # Show/hide name input row
        self.name_label.setVisible(is_create_new)
        self.char_ext_name_input.setVisible(is_create_new)
        
        if is_create_new:
            self.char_ext_name_input.setFocus()
        
        # Update height when expanded
        if self.character_extension_expanded:
            self.update_character_extension_height()
        
        # Adjust window size
        QTimer.singleShot(10, self.adjustSize)
    
    def update_character_extension_height(self):
        """Update the Character Extension group height based on content"""
        base_height = 50  # Base height for checkbox
        
        if self.char_ext_checkbox.isChecked():
            base_height += 25  # Add height for extension dropdown
            
            if self.name_label.isVisible():
                base_height += 25  # Add height for name input
        
        self.character_extension_group.setFixedHeight(base_height)
    
    def on_marker_size_changed(self, value):
        """Handle marker size changes, especially during manual offset mode"""
        # During manual offset mode, apply size changes directly to the marker
        if self.manual_offset_active and self.manual_offset_marker:
            self.manual_offset_marker.Size = value
        else:
            # Otherwise just treat it as a regular settings change
            self.on_settings_changed()
    
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
            
            # Debug logging commented out to reduce log spam
            # print(f"\nChecking constraints for model {model.Name}:")
            # print(f"  Current radio selection: {current_constraint_type}")
            # print(f"  Constraints found: {constraints_found}")
            # print(f"  Has Parent: {has_parent}, Has Position: {has_position}, Has Rotation: {has_rotation}")
            
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
        
        # Update last selection to prevent recreating on next update
        self.last_selection = [model.Name for model in selected_models]
    
    def update_preview_markers(self):
        """Update existing preview markers with current settings"""
        if not self.preview_enabled:
            return
            
        # First check if the selection has changed
        selected_models = FBModelList()
        FBGetSelectedModels(selected_models)
        
        # Create a list of selected model names for comparison
        current_selection = [model.Name for model in selected_models]
        
        # If selection is a single marker, don't show preview
        if len(selected_models) == 1 and selected_models[0].ClassName() == "FBModelMarker":
            self.cleanup_previews()
            self.last_selection = current_selection
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
        
        # Check if selection has actually changed
        if current_selection != self.last_selection:
            # Selection changed, recreate preview markers
            self.create_preview_markers()
            self.last_selection = current_selection
            return
        
        # If preview markers count doesn't match valid objects, recreate
        # Note: We now have 3 previews per model (marker + offset null + offset parent)
        if valid_model_count * 3 != len(self.preview_markers):
            self.create_preview_markers()
            self.last_selection = current_selection
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
                    pass  # Failed to delete object directly
        
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
            
            # Check if manual pairing is enabled
            if self.manual_pairing_cb.isChecked():
                # Manual pairing mode - require exactly 2 objects
                if len(selected_models) != 2:
                    QMessageBox.warning(self, "Selection Error", 
                                      "Manual Pairing requires exactly 2 objects.\n"
                                      "First object = Source, Second object = Target")
                    return
                
                # Use our selection tracking to get the proper order
                source, target = self.get_ordered_selection()
                
                # Verify we have valid selection order
                if not source or not target:
                    # Fallback to selected models (shouldn't happen with proper tracking)
                    source = selected_models[0]
                    target = selected_models[1]
                
                
                constraint_type = self.get_selected_constraint_type()
                
                constraint = self.create_direct_constraint(source, target, constraint_type)
                if constraint:
                    # Lock the constraint (Snap is already done in create_direct_constraint)
                    lock_prop = constraint.PropertyList.Find('Lock')
                    if lock_prop:
                        lock_prop.Data = True
                    
                    self.status_label.setText(f"Created {constraint_type} constraint: {source.Name} → {target.Name}")
                else:
                    self.status_label.setText("Failed to create constraint")
                return
            
            # Normal mode - create control rigs
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
            
            # Add markers to Character Extension if enabled
            if self.char_ext_checkbox.isChecked() and created_markers:
                success = self.add_markers_to_character_extension(created_markers)
                if success:
                    # Update status to include Character Extension info
                    current_selection = self.char_ext_combo.currentText()
                    if current_selection == "Create New Extension":
                        extension_name = self.char_ext_name_input.text().strip()
                        if self.lr_color_checkbox.isChecked():
                            self.status_label.setText(f"Created {created_count} control rig(s) and added to new Character Extensions '{extension_name}_left' and '{extension_name}_right'")
                        else:
                            self.status_label.setText(f"Created {created_count} control rig(s) and added to new Character Extension '{extension_name}'")
                    else:
                        self.status_label.setText(f"Created {created_count} control rig(s) and added to Character Extension '{current_selection}'")
                    
                    # Refresh the dropdown for next time
                    current_selection = self.char_ext_combo.currentText()
                    
                    # If we created a new extension, switch to that extension instead of "Create New Extension"
                    if current_selection == "Create New Extension":
                        extension_name = self.char_ext_name_input.text().strip()
                        if self.lr_color_checkbox.isChecked():
                            # For left/right extensions, keep "Create New Extension" selected with name preserved
                            target_selection = "Create New Extension"
                        else:
                            # For single extensions, switch to the newly created extension
                            target_selection = extension_name
                    else:
                        # For existing extensions, remember the current selection
                        target_selection = current_selection
                    
                    self.populate_character_extensions()
                    
                    # Set the dropdown to the target selection
                    index = self.char_ext_combo.findText(target_selection)
                    if index >= 0:
                        self.char_ext_combo.setCurrentIndex(index)
                else:
                    self.status_label.setText(f"Created {created_count} control rig(s) but failed to add to Character Extension")
            else:
                # Update status
                self.status_label.setText(f"Created {created_count} control rig(s)")
            
            # Reset offset values for next creation
            self.reset_translation()
            self.reset_rotation()
            
            # MOTIONBUILDER QUIRK FIX: Force hierarchy evaluation by selecting/deselecting skeleton root
            # This prevents glitching issues with end joints
            self.force_skeleton_evaluation(selected_models)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            traceback.print_exc()
    
    def create_direct_constraint(self, source, target, constraint_type):
        """Create a direct constraint between two objects"""
        try:
            # Debug: Print what we're trying to constrain (only if debug mode is enabled)
            debug_mode = False  # Set to True to enable debug prints
            if debug_mode:
                print(f"Creating {constraint_type} constraint: {source.Name} ({source.ClassName()}) -> {target.Name} ({target.ClassName()})")
            
            # Create the constraint
            constraint_manager = FBConstraintManager()
            constraint = None
            
            # Special handling for markers - they seem to have issues with reference ordering
            # When a marker is the source, we need to handle the constraint creation differently
            source_is_marker = source.ClassName() == "FBModelMarker"
            target_is_marker = target.ClassName() == "FBModelMarker"
            
            if debug_mode and (source_is_marker or target_is_marker):
                print(f"Marker detected - Source is marker: {source_is_marker}, Target is marker: {target_is_marker}")
            
            # Create appropriate constraint based on type
            if constraint_type == "Parent/Child":
                constraint = constraint_manager.TypeCreateConstraint("Parent/Child")
                # Standard order: Target is constrained by Source
                constraint.ReferenceAdd(0, target)  # Child (constrained)
                constraint.ReferenceAdd(1, source)  # Parent (source)
            
            elif constraint_type == "Position":
                constraint = constraint_manager.TypeCreateConstraint("Position")
                constraint.ReferenceAdd(0, target)  # Constrained
                constraint.ReferenceAdd(1, source)  # Source
            elif constraint_type == "Rotation":
                constraint = constraint_manager.TypeCreateConstraint("Rotation")
                constraint.ReferenceAdd(0, target)  # Constrained
                constraint.ReferenceAdd(1, source)  # Source
            elif constraint_type == "Aim":
                constraint = constraint_manager.TypeCreateConstraint("Aim")
                constraint.ReferenceAdd(0, target)  # Constrained
                constraint.ReferenceAdd(1, source)  # Aim At
            else:
                return None
            
            # IMPORTANT FIX: After adding references, check if they were assigned correctly
            # MotionBuilder sometimes reassigns references incorrectly with markers
            # Note: ReferenceGetCount() requires a group index argument
            ref_count = constraint.ReferenceGroupGetCount()
            if debug_mode:
                print(f"Reference group count: {ref_count}")
            
            if ref_count > 0:
                # Get the count for the first reference group (usually 0)
                count = constraint.ReferenceGetCount(0)
                if debug_mode:
                    print(f"References in group 0: {count}")
                
                if count >= 2:
                    ref0 = constraint.ReferenceGet(0, 0)  # Group 0, Index 0
                    ref1 = constraint.ReferenceGet(0, 1)  # Group 0, Index 1
                    
                    if debug_mode:
                        print(f"Ref0: {ref0.Name if ref0 else 'None'} ({ref0.ClassName() if ref0 else 'None'})")
                        print(f"Ref1: {ref1.Name if ref1 else 'None'} ({ref1.ClassName() if ref1 else 'None'})")
                    
                    # If the source (which should be at index 1) ended up at index 0, swap them
                    if ref0 and ref1:
                        if ref0 == source and ref1 == target:
                            # They're backwards! Remove and re-add in correct order
                            if debug_mode:
                                print(f"References were reversed! Fixing...")
                            
                            # Remove all references first
                            while constraint.ReferenceGetCount(0) > 0:
                                constraint.ReferenceRemove(0, 0)
                            
                            # Re-add in correct order
                            constraint.ReferenceAdd(0, target)
                            constraint.ReferenceAdd(1, source)
                            
                            if debug_mode:
                                print(f"Fixed reference order")
            
            # Debug: Verify the final references
            if debug_mode and ref_count > 0:
                print(f"Final constraint references:")
                for i in range(constraint.ReferenceGetCount(0)):
                    ref = constraint.ReferenceGet(0, i)
                    if ref:
                        print(f"  Reference {i}: {ref.Name} ({ref.ClassName()})")
                    else:
                        print(f"  Reference {i}: None")
            
            # Name the constraint appropriately
            constraint.Name = f"{source.Name}_to_{target.Name}_{constraint_type}_Constraint"
            
            # Set constraint properties
            constraint.Snap = True
            constraint.Active = True
            
            # Move constraint to custom folder
            if constraint and self.custom_folder:
                self.add_constraint_to_folder(constraint)
            
            return constraint
            
        except Exception as e:
            print(f"Error creating direct constraint: {e}")
            return None
    
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
                # print(f"Found existing parent control: {parent_control_name}")
                existing_parent_control = component
                break
        
        if existing_parent_control:
            return existing_parent_control
        
        # Create new parent control
        # print(f"Creating new parent control: {parent_control_name}")
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
        
        # Parent the parent control to the master null for organization
        master_null = self.get_or_create_master_null()
        if master_null:
            parent_control.Parent = master_null
        
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
                # print(f"Added constraint {constraint.Name} to custom folder")
            else:
                pass  # No custom folder available
        except Exception as e:
            # print(f"Error adding constraint to folder: {str(e)}")
            # traceback.print_exc()
            pass
    
    def create_constraint(self, constraint_type, source, target, model_name, use_snap=True):
        """Create a constraint between two objects
        
        The constraint will be automatically locked after activation to prevent
        unintentional changes.
        """
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
                
                # Lock the constraint after activation
                lock_prop = constraint.PropertyList.Find('Lock')
                if lock_prop:
                    lock_prop.Data = True
                    # print(f"Locked constraint: {constraint.Name}")
                
                # print(f"Created constraint: {constraint.Name} (snap={use_snap})")
                return constraint
                
        except Exception as e:
            # print(f"Error creating constraint: {str(e)}")
            # traceback.print_exc()
            pass
            return None
    
    def create_temporary_constraint(self):
        """Create or delete a temporary parent constraint for the selected object"""
        try:
            # Get selected object
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            
            if len(selected_models) != 1:
                QMessageBox.warning(self, "Selection Error", "Please select exactly one object.")
                return
            
            target_obj = selected_models[0]
            
            # Check if this is a delete operation
            if self.temp_constraint_button.text() == "Delete Temp Constraint":
                # Use the stored references to find the constraint
                constraint_to_delete = None
                
                # Find the constraint to delete - check both object and null
                for constraint in FBSystem().Scene.Constraints:
                    if "Temporary_Parent_Constraint" in constraint.Name:
                        ref_count_0 = constraint.ReferenceGetCount(0) if constraint.ReferenceGroupGetCount() > 0 else 0
                        ref_count_1 = constraint.ReferenceGetCount(1) if constraint.ReferenceGroupGetCount() > 1 else 0
                        
                        # Check if this constraint involves our stored object or null
                        constraint_found = False
                        
                        # Check first reference group (constrained object)
                        for j in range(ref_count_0):
                            ref_obj = constraint.ReferenceGet(0, j)
                            if ref_obj and (ref_obj == target_obj or 
                                          (hasattr(self, 'temp_constraint_object') and ref_obj == self.temp_constraint_object)):
                                constraint_found = True
                                break
                        
                        # Check second reference group (temp null)
                        if not constraint_found:
                            for k in range(ref_count_1):
                                ref_obj = constraint.ReferenceGet(1, k)
                                if ref_obj and (ref_obj == target_obj or
                                              (hasattr(self, 'temp_constraint_null') and ref_obj == self.temp_constraint_null)):
                                    constraint_found = True
                                    break
                        
                        if constraint_found:
                            constraint_to_delete = constraint
                            break
                
                if constraint_to_delete:
                    # Get the name for status message before deletion
                    object_name = target_obj.Name
                    if hasattr(self, 'temp_constraint_object') and self.temp_constraint_object:
                        object_name = self.temp_constraint_object.Name
                    
                    # Deselect everything first to avoid unbound wrapper error
                    for component in FBSystem().Scene.Components:
                        component.Selected = False
                    
                    # Delete the constraint
                    constraint_to_delete.FBDelete()
                    
                    # Delete the temp null
                    if hasattr(self, 'temp_constraint_null') and self.temp_constraint_null:
                        self.temp_constraint_null.FBDelete()
                    
                    self.status_label.setText(f"Deleted temporary constraint for {object_name}")
                else:
                    self.status_label.setText("No temporary constraint found to delete")
                return
            
            # Create operation - Check if object is already constrained
            for constraint in FBSystem().Scene.Constraints:
                ref_group_count = constraint.ReferenceGroupGetCount()
                is_constrained = False
                
                if ref_group_count > 0:
                    ref_count = constraint.ReferenceGetCount(0)
                    for j in range(ref_count):
                        ref_obj = constraint.ReferenceGet(0, j)
                        if ref_obj and ref_obj == target_obj:
                            is_constrained = True
                            break
                
                if is_constrained and "_Parent_Child_Constraint" in constraint.Name and "Temporary" not in constraint.Name:
                    QMessageBox.warning(self, "Constraint Error", 
                                      "Object already has a parent constraint. Cannot create temporary constraint.")
                    return
            
            # Create null at object's position
            null_name = f"{target_obj.Name}_TEMP_NULL"
            temp_null = FBModelNull(null_name)
            temp_null.Show = True
            temp_null.Size = 1000  # Set size to 1000 as requested
            
            # Copy the transform of the target object to the null
            target_matrix = FBMatrix()
            target_obj.GetMatrix(target_matrix)
            temp_null.SetMatrix(target_matrix)
            
            # Create parent constraint with null as parent and object as child
            constraint_manager = FBConstraintManager()
            constraint = constraint_manager.TypeCreateConstraint("Parent/Child")
            
            if constraint:
                # Name the constraint appropriately
                constraint.Name = f"{null_name}_to_{target_obj.Name}_Temporary_Parent_Constraint"
                
                # Add references (object is child, null is parent)
                constraint.ReferenceAdd(0, target_obj)  # Child (constrained)
                constraint.ReferenceAdd(1, temp_null)   # Parent (source)
                
                # Snap to maintain current offset
                constraint.Snap()
                constraint.Active = True
                
                # Lock the constraint
                lock_prop = constraint.PropertyList.Find('Lock')
                if lock_prop:
                    lock_prop.Data = True
                
                # Move constraint to custom folder
                if constraint and self.custom_folder:
                    self.add_constraint_to_folder(constraint)
                
                # Clear selection and select the new null
                for component in FBSystem().Scene.Components:
                    component.Selected = False
                temp_null.Selected = True
                
                self.status_label.setText(f"Created temporary constraint for {target_obj.Name}")
            else:
                self.status_label.setText("Failed to create temporary constraint")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            traceback.print_exc()
    
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
            
            # Check if any objects are selected
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            
            # If anything other than the offset null is selected
            if len(selected_models) > 0:
                # Check if only the offset null is selected
                if len(selected_models) == 1 and selected_models[0] == offset_null:
                    # Perfect, cancel any pending timer
                    if self.drag_operation_timer:
                        self.drag_operation_timer.stop()
                    return
                
                # Something else is selected - set a timer to reselect offset null
                if not self.drag_operation_timer or not self.drag_operation_timer.isActive():
                    self.drag_operation_timer = QTimer(self)
                    self.drag_operation_timer.setSingleShot(True)
                    self.drag_operation_timer.timeout.connect(self.force_reselect_offset_null)
                    self.drag_operation_timer.start(500)  # Wait 0.5 seconds before forcing reselection
                    return
            
            # Nothing is selected, reselect offset null immediately
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
        else:
            self.manual_offset_button.setVisible(False)
        
        # Show temporary constraint button for single object selection (including markers)
        if len(selected_models) == 1:
            obj = selected_models[0]
            # Check if this object already has a temporary constraint
            has_temp_constraint = False
            temp_null = None
            constrained_object = None
            
            # Check if selected object is a temp null
            if obj.ClassName() == "FBModelNull" and "_TEMP_NULL" in obj.Name:
                # Find the constraint that uses this temp null
                for constraint in FBSystem().Scene.Constraints:
                    if "Temporary_Parent_Constraint" in constraint.Name:
                        # Check if this temp null is the parent in the constraint
                        if constraint.ReferenceGroupGetCount() > 1:
                            ref_count_1 = constraint.ReferenceGetCount(1)
                            for k in range(ref_count_1):
                                ref_obj_1 = constraint.ReferenceGet(1, k)
                                if ref_obj_1 == obj:
                                    temp_null = obj
                                    has_temp_constraint = True
                                    # Find the constrained object
                                    ref_count_0 = constraint.ReferenceGetCount(0)
                                    for j in range(ref_count_0):
                                        constrained_object = constraint.ReferenceGet(0, j)
                                        if constrained_object:
                                            break
                                    break
                    if has_temp_constraint:
                        break
            else:
                # Normal object selection - check if it has a temp constraint
                for constraint in FBSystem().Scene.Constraints:
                    if "Temporary_Parent_Constraint" in constraint.Name:
                        # Check if this constraint is for our selected object
                        ref_count = constraint.ReferenceGetCount(0) if constraint.ReferenceGroupGetCount() > 0 else 0
                        for j in range(ref_count):
                            ref_obj = constraint.ReferenceGet(0, j)
                            if ref_obj == obj:
                                has_temp_constraint = True
                                constrained_object = obj
                                # Find the associated temp null
                                if constraint.ReferenceGroupGetCount() > 1:
                                    ref_count_1 = constraint.ReferenceGetCount(1)
                                    for k in range(ref_count_1):
                                        ref_obj_1 = constraint.ReferenceGet(1, k)
                                        if ref_obj_1 and "_TEMP_NULL" in ref_obj_1.Name:
                                            temp_null = ref_obj_1
                                            break
                                break
                    if has_temp_constraint:
                        break
            
            self.temp_constraint_button.setVisible(True)
            if has_temp_constraint:
                self.temp_constraint_button.setText("Delete Temp Constraint")
                self.temp_constraint_null = temp_null  # Store reference for deletion
                self.temp_constraint_object = constrained_object  # Store reference to constrained object
            else:
                self.temp_constraint_button.setText("Temporary Constraint")
                self.temp_constraint_null = None
                self.temp_constraint_object = None
        else:
            self.temp_constraint_button.setVisible(False)
            
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
        
        # Store the current marker size in the UI
        self.marker_size_spin.setValue(int(marker.Size))
        
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
        
        # Disable and unlock all found constraints
        for constraint in constraints_to_disable:
            # First unlock the constraint
            lock_prop = constraint.PropertyList.Find('Lock')
            if lock_prop:
                lock_prop.Data = False
                # print(f"Unlocked constraint: {constraint.Name}")
            constraint.Active = False
            
        # Unlock offset null transforms except scaling (keep scaling locked)
        offset_null.PropertyList.Find('Translation').SetLocked(False)
        offset_null.PropertyList.Find('Rotation').SetLocked(False)
        # Keep scaling locked to prevent accidental scaling of the null
        # Users should scale the marker size directly instead
        offset_null.PropertyList.Find('Scaling').SetLocked(True)
        
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
    
    def force_reselect_offset_null(self):
        """Force reselection of the offset null after timer expires"""
        if self.manual_offset_active:
            # Find the offset null
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
                # Clear all selections
                for component in FBSystem().Scene.Components:
                    component.Selected = False
                # Reselect only the offset null
                offset_null.Selected = True
    
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
            # Re-lock all transforms
            offset_null.PropertyList.Find('Translation').SetLocked(True)
            offset_null.PropertyList.Find('Rotation').SetLocked(True)
            offset_null.PropertyList.Find('Scaling').SetLocked(True)
        
        # Re-enable, snap, and lock all constraints
        if hasattr(self, 'manual_offset_constraints'):
            for constraint in self.manual_offset_constraints:
                if constraint:
                    constraint.Snap()
                    constraint.Active = True
                    # Re-lock the constraint
                    lock_prop = constraint.PropertyList.Find('Lock')
                    if lock_prop:
                        lock_prop.Data = True
                        # print(f"Re-locked constraint: {constraint.Name}")
        
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
        
        # Clean up any drag operation timer
        if self.drag_operation_timer:
            self.drag_operation_timer.stop()
            self.drag_operation_timer = None
        
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
                    # print(f"Deleting: {component.Name}")
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
                    # print(f"Found orphaned parent control: {ctrl_parent.Name}")
                    pass
                    
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
                            # print(f"Deleting constraint: {constraint.Name}")
                            constraint.FBDelete()
                        except Exception as e:
                            pass  # Failed to delete constraint
                            
                    # Delete the parent control
                    try:
                        # print(f"Deleting parent control: {ctrl_parent.Name}")
                        ctrl_parent.FBDelete()
                    except Exception as e:
                        pass  # Failed to delete parent control
                        
            except Exception as e:
                pass  # Error checking parent control
        
        self.status_label.setText(f"Deleted {deleted_count} control rig{'s' if deleted_count > 1 else ''}")
    
    def populate_character_extensions(self):
        """Populate the Character Extension dropdown with existing extensions"""
        if not MOBU_AVAILABLE:
            return
            
        self.char_ext_combo.clear()
        self.char_ext_combo.addItem("Create New Extension")
        
        # Find existing Character Extensions in the scene
        try:
            for component in FBSystem().Scene.Components:
                if component.ClassName() == "FBCharacterExtension":
                    self.char_ext_combo.addItem(component.Name)
        except Exception as e:
            pass  # Silently handle any errors
    
    def get_or_create_master_null(self):
        """Get or create the master null that will parent all _CTRL_parent nulls"""
        if not MOBU_AVAILABLE:
            return None
            
        master_null_name = "Controlify_CTRLs_parent"
        
        # Check if master null already exists
        for component in FBSystem().Scene.Components:
            if component.Name == master_null_name and component.ClassName() == "FBModelNull":
                return component
        
        # Create new master null
        master_null = FBModelNull(master_null_name)
        master_null.Show = True
        master_null.Size = 15
        
        # Set null properties
        null_prop = master_null.PropertyList.Find('Look')
        if null_prop:
            null_prop.Data = 10  # 10 = None (invisible)
            
        # Make it invisible but keep it selectable
        master_null.Visibility = False
        
        return master_null
    
    def add_markers_to_character_extension(self, markers):
        """Add the created markers to the selected Character Extension"""
        if not MOBU_AVAILABLE or not self.char_ext_checkbox.isChecked():
            return False
            
        try:
            current_selection = self.char_ext_combo.currentText()
            
            if current_selection == "Create New Extension":
                # Create new Character Extension
                extension_name = self.char_ext_name_input.text().strip()
                if not extension_name:
                    QMessageBox.warning(self, "Warning", "No Character Extension name set. Markers were not added to an extension.")
                    return False
                
                # Check if Right/Left colors are enabled
                if self.lr_color_checkbox.isChecked():
                    # Get or create separate left and right extensions
                    left_name = f"{extension_name}_left"
                    right_name = f"{extension_name}_right"
                    
                    # Check if left extension already exists
                    left_extension = None
                    for component in FBSystem().Scene.Components:
                        if component.ClassName() == "FBCharacterExtension" and component.Name == left_name:
                            left_extension = component
                            break
                    
                    # Create left extension if it doesn't exist
                    if not left_extension:
                        left_extension = FBCharacterExtension(left_name)
                        left_extension.Show = True
                        self.add_extension_to_character_if_single(left_extension)
                    
                    # Check if right extension already exists
                    right_extension = None
                    for component in FBSystem().Scene.Components:
                        if component.ClassName() == "FBCharacterExtension" and component.Name == right_name:
                            right_extension = component
                            break
                    
                    # Create right extension if it doesn't exist
                    if not right_extension:
                        right_extension = FBCharacterExtension(right_name)
                        right_extension.Show = True
                        self.add_extension_to_character_if_single(right_extension)
                    
                    # Sort markers into left and right based on naming patterns
                    for marker in markers:
                        if marker and marker.ClassName() == "FBModelMarker":
                            marker_name = marker.Name.lower()
                            
                            # Check for right side patterns
                            if any(pattern in marker_name for pattern in ["_r_", "_right_", "_rgt_", "_r.", "_right.", "_rgt.", 
                                                                        "_r", "_right", "_rgt"]):
                                right_extension.ConnectSrc(marker)
                            # Check for left side patterns
                            elif any(pattern in marker_name for pattern in ["_l_", "_left_", "_lft_", "_l.", "_left.", "_lft.",
                                                                          "_l", "_left", "_lft"]):
                                left_extension.ConnectSrc(marker)
                            else:
                                # Default to left extension if no pattern found
                                left_extension.ConnectSrc(marker)
                else:
                    # Get or create single Character Extension
                    char_extension = None
                    for component in FBSystem().Scene.Components:
                        if component.ClassName() == "FBCharacterExtension" and component.Name == extension_name:
                            char_extension = component
                            break
                    
                    # Create extension if it doesn't exist
                    if not char_extension:
                        char_extension = FBCharacterExtension(extension_name)
                        char_extension.Show = True
                        self.add_extension_to_character_if_single(char_extension)
                    
                    # Add all markers to the single extension
                    for marker in markers:
                        if marker and marker.ClassName() == "FBModelMarker":
                            char_extension.ConnectSrc(marker)
                
            else:
                # Find existing Character Extension
                char_extension = None
                for component in FBSystem().Scene.Components:
                    if component.ClassName() == "FBCharacterExtension" and component.Name == current_selection:
                        char_extension = component
                        break
                
                if not char_extension:
                    QMessageBox.warning(self, "Error", f"Character Extension '{current_selection}' not found.")
                    return False
                
                # Add markers to the existing extension
                for marker in markers:
                    if marker and marker.ClassName() == "FBModelMarker":
                        char_extension.ConnectSrc(marker)
            
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add markers to Character Extension: {str(e)}")
            return False
    
    def add_extension_to_character_if_single(self, extension):
        """Add the extension to a character if only one character exists in the scene"""
        if not MOBU_AVAILABLE:
            return
            
        try:
            # Find all characters in the scene
            characters = []
            for component in FBSystem().Scene.Components:
                if component.ClassName() == "FBCharacter":
                    characters.append(component)
            
            # Only add to character if exactly one character exists
            if len(characters) == 1:
                character = characters[0]
                # Add the extension to the character's extension list
                character.CharacterExtensions.append(extension)
        except Exception as e:
            # Silently handle any errors - this is a nice-to-have feature
            pass
    
    def force_skeleton_evaluation(self, models):
        """Force MotionBuilder to properly evaluate skeleton hierarchy by selecting/deselecting root"""
        if not MOBU_AVAILABLE or not models:
            return
            
        try:
            # Find the root(s) of the skeleton hierarchy
            skeleton_roots = set()
            
            for model in models:
                # Walk up the hierarchy to find the root
                current = model
                while current.Parent:
                    current = current.Parent
                skeleton_roots.add(current)
            
            # Force evaluation by selecting and immediately deselecting each root
            for root in skeleton_roots:
                root.Selected = True
                # Force scene evaluation
                FBSystem().Scene.Evaluate()
                root.Selected = False
                
        except Exception as e:
            # Silently handle any errors - this is just a workaround
            pass
    
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

<h3>Character Extensions:</h3>
<p>Organize markers into Character Extensions for animation workflows:<br>
- Check "Add to Character Extension"<br>
- Select existing extension or create new one<br>
- With Right/Left colors enabled, creates separate _left and _right extensions</p>

<h3>Temporary Constraint:</h3>
<p>Creates a temporary null parent for selected object:<br>
- Select null or joint and press "Temporary Constraint"<br>
- Creates null as parent of selected object<br>
- Use "Delete Temp Constraint" to remove</p>

<h3>Constrain Object to Object:</h3>
<p>Direct constraint creation without markers:<br>
- Enable "Constrain object to object"<br>
- Select two objects (first = source, second = target)<br>
- Creates constraint directly between objects</p>

        """)
        
        layout.addWidget(info_text)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(info_dialog.close)
        layout.addWidget(close_button)
        
        info_dialog.exec_()


    def setup_selection_tracking(self):
        """Set up tracking for selection order"""
        # Initialize selection tracking
        self.selection_order_list = []
        self.last_selection_state = set()
        
        # Set up a timer to monitor selection changes
        self.selection_monitor_timer = QTimer(self)
        self.selection_monitor_timer.timeout.connect(self.monitor_selection)
        self.selection_monitor_timer.setInterval(50)  # Check every 50ms
        self.selection_monitor_timer.start()
    
    def monitor_selection(self):
        """Monitor selection changes and maintain order"""
        if not MOBU_AVAILABLE:
            return
            
        # Only track if we're in manual pairing mode
        if not hasattr(self, 'manual_pairing_cb') or not self.manual_pairing_cb.isChecked():
            # Clear tracking if not in manual pairing mode
            if self.selection_order_list:
                self.selection_order_list = []
                self.last_selection_state = set()
            return
            
        # Get current selection
        current_selection = FBModelList()
        FBGetSelectedModels(current_selection)
        
        # Convert to set for comparison
        current_set = set()
        for i in range(len(current_selection)):
            current_set.add(current_selection[i])
        
        # Check what changed
        added = current_set - self.last_selection_state
        removed = self.last_selection_state - current_set
        
        # Handle additions
        for obj in added:
            if len(self.selection_order_list) < 2:
                self.selection_order_list.append(obj)
            else:
                # We already have 2 objects, replace the oldest one
                self.selection_order_list.pop(0)  # Remove first (oldest)
                self.selection_order_list.append(obj)  # Add new as second
        
        # Handle removals
        for obj in removed:
            if obj in self.selection_order_list:
                self.selection_order_list.remove(obj)
        
        # Update our tracking state
        self.last_selection_state = current_set
        
        # Update status if we have 2 objects
        if len(self.selection_order_list) == 2:
            self.status_label.setText(
                f"Ready to constrain: {self.selection_order_list[0].Name} → {self.selection_order_list[1].Name}"
            )
    
    def get_ordered_selection(self):
        """Get the selection in the order it was selected"""
        if len(self.selection_order_list) == 2:
            return self.selection_order_list[0], self.selection_order_list[1]
        return None, None


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
        # print("Dialog created and shown successfully")
    except Exception as e:
        # print(f"Error showing dialog: {str(e)}")
        # traceback.print_exc()
        pass


# When script is run directly, create and show the dialog
# This is the entry point for MotionBuilder
try:
    # print("Starting Controlify script...")
    show_dialog()
    # print("Controlify dialog initialized")
except Exception as e:
    # print(f"Critical error: {str(e)}")
    # traceback.print_exc()
    pass