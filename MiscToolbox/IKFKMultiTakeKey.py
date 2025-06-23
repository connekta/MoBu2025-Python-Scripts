"""
IK/FK Multi-Take Key Tool
Set IK/FK blend values from selected effectors to all takes in scene
"""

import sys

# Tool metadata
DISPLAY_NAME = "IK/FK Multi-Take Key"
DESCRIPTION = "Set IK/FK blend values from selected effectors to all takes in scene"

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


def _process_ik_blend_property(property_obj, target_value, mode, take):
    """Process a single IK Blend property for a take"""
    
    if not property_obj:
        return
    
    # Get the animation node for this property
    anim_node = property_obj.GetAnimationNode()
    if not anim_node:
        return
    
    # Get the FCurve
    fcurve = anim_node.FCurve
    if not fcurve:
        return
    
    # Check if there are existing keys
    keys_count = len(fcurve.Keys)
    has_keys = keys_count > 0
    
    if mode == "Add" and has_keys:
        # Skip if keys exist and mode is Add
        return
    elif mode == "Replace" and has_keys:
        # Remove all existing keys
        fcurve.EditClear()
    
    # Add new key at first frame of take
    start_time = take.LocalTimeSpan.GetStart()
    
    try:
        key_index = fcurve.KeyAdd(start_time, target_value)
    except Exception as e:
        pass
    
    # Force scene evaluation
    try:
        FBSystem().Scene.Evaluate()
    except Exception as e:
        pass


class IKFKConfirmationDialog(QDialog):
    """Non-modal dialog for IK/FK Multi-Take Key tool"""
    
    def __init__(self, initial_effector_data, parent=None):
        if parent is None:
            parent = get_motionbuilder_main_window()
        
        super(IKFKConfirmationDialog, self).__init__(parent)
        
        self.setWindowTitle("IK/FK Multi-Take Key")
        self.setMinimumWidth(450)
        
        # Make it non-modal
        self.setModal(False)
        
        # Window flags - same as main toolbox
        if parent:
            self.setWindowFlags(Qt.Dialog)
        else:
            self.setWindowFlags(Qt.Window)
        
        # Store initial data
        self.current_effector_data = initial_effector_data
        
        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header info
        header_label = QLabel("Selected IK Effectors and Current Values:")
        header_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)
        
        # Create scrollable area for effector info
        self.effector_scroll = QScrollArea()
        self.effector_scroll.setMaximumHeight(150)
        self.effector_scroll.setWidgetResizable(True)
        self.effector_content = QWidget()
        self.effector_layout = QVBoxLayout()
        self.effector_content.setLayout(self.effector_layout)
        self.effector_scroll.setWidget(self.effector_content)
        layout.addWidget(self.effector_scroll)
        
        # Update the effector display
        self.update_effector_display()
        
        # Mode selection with radio buttons
        mode_group = QGroupBox("Key Mode:")
        mode_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 3px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        mode_layout = QVBoxLayout()
        mode_group.setLayout(mode_layout)
        
        # Replace option with radio button
        replace_layout = QHBoxLayout()
        self.replace_radio = QRadioButton("Replace")
        self.replace_radio.setChecked(True)  # Default selection
        self.replace_radio.setStyleSheet("font-weight: bold;")
        replace_layout.addWidget(self.replace_radio)
        replace_layout.addStretch()
        mode_layout.addLayout(replace_layout)
        
        replace_desc = QLabel("Remove existing IK Reach keys and set new key with current values")
        replace_desc.setStyleSheet("color: #666; font-size: 10px; margin-left: 20px; margin-bottom: 10px;")
        mode_layout.addWidget(replace_desc)
        
        # Add option with radio button
        add_layout = QHBoxLayout()
        self.add_radio = QRadioButton("Add")
        self.add_radio.setStyleSheet("font-weight: bold;")
        add_layout.addWidget(self.add_radio)
        add_layout.addStretch()
        mode_layout.addLayout(add_layout)
        
        add_desc = QLabel("Only add key if no IK Reach keys exist (skip takes that already have keys)")
        add_desc.setStyleSheet("color: #666; font-size: 10px; margin-left: 20px;")
        mode_layout.addWidget(add_desc)
        
        layout.addWidget(mode_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        button_layout.addStretch()
        
        self.apply_button = QPushButton("Apply to All Takes")
        self.apply_button.clicked.connect(self.apply_to_takes)
        button_layout.addWidget(self.apply_button)
        
        # Update button state based on initial selection
        self.update_apply_button_state()
        
        layout.addLayout(button_layout)
        
        # Set up timer for automatic selection updates
        self.selection_timer = QTimer()
        self.selection_timer.timeout.connect(self.check_selection_changes)
        self.selection_timer.start(500)  # Check every 500ms for more responsive updates
    
    def update_apply_button_state(self):
        """Update the apply button state and styling based on selection"""
        has_effectors = bool(self.current_effector_data)
        self.apply_button.setEnabled(has_effectors)
        
        if has_effectors:
            # Enabled state - blue button
            self.apply_button.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
            """)
        else:
            # Disabled state - grayed out button
            self.apply_button.setStyleSheet("""
                QPushButton {
                    background-color: #808080;
                    color: #cccccc;
                    font-weight: bold;
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:disabled {
                    background-color: #606060;
                    color: #999999;
                }
            """)
    
    def update_effector_display(self):
        """Update the display of current effector selection"""
        # Clear existing widgets
        for i in reversed(range(self.effector_layout.count())):
            self.effector_layout.itemAt(i).widget().setParent(None)
        
        if not self.current_effector_data:
            no_selection_label = QLabel("No IK effectors selected")
            no_selection_label.setStyleSheet("color: #aaa; font-style: italic; margin: 10px;")
            self.effector_layout.addWidget(no_selection_label)
        else:
            for effector in self.current_effector_data:
                info_text = f"• {effector['name']}"
                if effector['ik_blend_t'] is not None:
                    info_text += f" (IK Reach Translation: {effector['ik_blend_t']:.1f})"
                if effector['ik_blend_r'] is not None:
                    info_text += f" (IK Reach Rotation: {effector['ik_blend_r']:.1f})"
                
                info_label = QLabel(info_text)
                info_label.setStyleSheet("margin-left: 10px; margin-bottom: 5px;")
                self.effector_layout.addWidget(info_label)
    
    def check_selection_changes(self):
        """Check if selection has changed or values have changed and update if needed"""
        if not MOBU_AVAILABLE:
            return
        
        try:
            # Get current selection
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            
            # Check if selection is different from current data
            current_names = [e['name'] for e in self.current_effector_data]
            new_names = [model.Name for model in selected_models]
            
            selection_changed = set(current_names) != set(new_names)
            
            # Check if values have changed for existing selection
            values_changed = False
            if not selection_changed and self.current_effector_data:
                for effector in self.current_effector_data:
                    # Check if IK blend values have changed
                    if effector['ik_blend_t_prop']:
                        current_t = effector['ik_blend_t_prop'].Data
                        if abs(current_t - effector['ik_blend_t']) > 0.001:
                            values_changed = True
                            break
                    if effector['ik_blend_r_prop']:
                        current_r = effector['ik_blend_r_prop'].Data
                        if abs(current_r - effector['ik_blend_r']) > 0.001:
                            values_changed = True
                            break
            
            if selection_changed or values_changed:
                self.refresh_selection()
        except:
            pass  # Ignore errors during background checking
    
    def refresh_selection(self):
        """Refresh the effector data from current selection"""
        if not MOBU_AVAILABLE:
            return
        
        try:
            # Get fresh selection data (reuse logic from main function)
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            
            new_effector_data = []
            for model in selected_models:
                ik_blend_t_prop = None
                ik_blend_r_prop = None
                
                for prop in model.PropertyList:
                    prop_name = prop.Name
                    if prop_name == "IK Reach Translation":
                        ik_blend_t_prop = prop
                    elif prop_name == "IK Reach Rotation":
                        ik_blend_r_prop = prop
                
                has_ik_properties = False
                for prop in model.PropertyList:
                    prop_name = prop.Name.lower()
                    if any(keyword in prop_name for keyword in ["ik", "reach", "effector", "blend"]):
                        has_ik_properties = True
                        break
                
                if ik_blend_t_prop or ik_blend_r_prop or has_ik_properties:
                    data = {
                        'model': model,
                        'name': model.Name,
                        'ik_blend_t': ik_blend_t_prop.Data if ik_blend_t_prop else None,
                        'ik_blend_r': ik_blend_r_prop.Data if ik_blend_r_prop else None,
                        'ik_blend_t_prop': ik_blend_t_prop,
                        'ik_blend_r_prop': ik_blend_r_prop,
                        'has_ik_properties': has_ik_properties
                    }
                    new_effector_data.append(data)
            
            self.current_effector_data = new_effector_data
            self.update_effector_display()
            self.update_apply_button_state()
            
        except Exception as e:
            pass  # Ignore errors during refresh
    
    def apply_to_takes(self):
        """Apply the IK/FK values to all takes"""
        if not self.current_effector_data:
            # This shouldn't happen since button should be disabled, but just in case
            return
        
        # Refresh selection one more time to ensure latest values
        self.refresh_selection()
        
        mode = "Replace" if self.replace_radio.isChecked() else "Add"
        
        # Process all takes
        system = FBSystem()
        current_take = system.CurrentTake
        processed_takes = 0
        
        try:
            for take in system.Scene.Takes:
                # Switch to this take
                system.CurrentTake = take
                
                # Get the BaseAnimation layer
                base_layer = None
                for i in range(take.GetLayerCount()):
                    layer = take.GetLayer(i)
                    if layer.Name == "BaseAnimation":
                        base_layer = layer
                        break
                
                if not base_layer:
                    continue
                
                # Process each effector
                for effector in self.current_effector_data:
                    # Process IK Blend T
                    if effector['ik_blend_t_prop']:
                        _process_ik_blend_property(
                            effector['ik_blend_t_prop'], 
                            effector['ik_blend_t'], 
                            mode, 
                            take
                        )
                    
                    # Process IK Blend R
                    if effector['ik_blend_r_prop']:
                        _process_ik_blend_property(
                            effector['ik_blend_r_prop'], 
                            effector['ik_blend_r'], 
                            mode, 
                            take
                        )
                
                processed_takes += 1
            
            # Restore original take
            if current_take:
                system.CurrentTake = current_take
            
            # Show completion message with detailed values
            effector_details = []
            for effector in self.current_effector_data:
                detail = f"• {effector['name']}"
                if effector['ik_blend_t'] is not None:
                    detail += f" (IK Reach Translation: {effector['ik_blend_t']:.1f})"
                if effector['ik_blend_r'] is not None:
                    detail += f" (IK Reach Rotation: {effector['ik_blend_r']:.1f})"
                effector_details.append(detail)
            
            FBMessageBox(
                "IK/FK Multi-Take Key Complete", 
                f"Successfully processed {processed_takes} takes.\n"
                f"Mode: {mode}\n\n"
                f"Values applied:\n" + "\n".join(effector_details), 
                "OK"
            )
            
            # Close the dialog after showing completion message
            self.close()
            
        except Exception as e:
            # Restore original take on error
            if current_take:
                system.CurrentTake = current_take
            FBMessageBox("Error", f"Error processing takes: {str(e)}", "OK")
    
    def closeEvent(self, event):
        """Clean up timer when dialog is closed"""
        if hasattr(self, 'selection_timer'):
            self.selection_timer.stop()
        super().closeEvent(event)


def run():
    """Main entry point for the IK/FK Multi-Take Key tool"""
    if not MOBU_AVAILABLE:
        return
    
    # Get selected models (allow opening without selection)
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models)
    
    # Find HIK effectors in selection and get their current IK Blend values
    effector_data = []
    for model in selected_models:
        # Check if this is an IK effector by looking for IK Blend properties
        ik_blend_t_prop = None
        ik_blend_r_prop = None
        
        # Look for various possible IK Blend property names
        for prop in model.PropertyList:
            prop_name = prop.Name
            # Check for exact MotionBuilder property names first
            if prop_name == "IK Reach Translation":
                ik_blend_t_prop = prop
            elif prop_name == "IK Reach Rotation":
                ik_blend_r_prop = prop
            # Also check for legacy names
            elif ("ik" in prop_name.lower() and "blend" in prop_name.lower() and "t" in prop_name.lower()) or "ikblendt" in prop_name.lower():
                ik_blend_t_prop = prop
            elif ("ik" in prop_name.lower() and "blend" in prop_name.lower() and "r" in prop_name.lower()) or "ikblendr" in prop_name.lower():
                ik_blend_r_prop = prop
            elif "ik blend t" in prop_name.lower():
                ik_blend_t_prop = prop
            elif "ik blend r" in prop_name.lower():
                ik_blend_r_prop = prop
        
        # Also check if this model has any properties that suggest it's an IK effector
        has_ik_properties = False
        ik_related_props = []
        for prop in model.PropertyList:
            prop_name = prop.Name.lower()
            if any(keyword in prop_name for keyword in ["ik", "reach", "effector", "blend"]):
                has_ik_properties = True
                ik_related_props.append(prop.Name)
        
        if ik_blend_t_prop or ik_blend_r_prop or has_ik_properties:
            data = {
                'model': model,
                'name': model.Name,
                'ik_blend_t': ik_blend_t_prop.Data if ik_blend_t_prop else None,
                'ik_blend_r': ik_blend_r_prop.Data if ik_blend_r_prop else None,
                'ik_blend_t_prop': ik_blend_t_prop,
                'ik_blend_r_prop': ik_blend_r_prop,
                'has_ik_properties': has_ik_properties
            }
            effector_data.append(data)
    
    # Allow opening even without effector data - the dialog will handle empty selection
    
    # Show confirmation dialog with Replace/Add options
    dialog = IKFKConfirmationDialog(effector_data)
    dialog.show()  # Show non-modal
    
    # Store reference to prevent garbage collection
    global ik_fk_dialog
    ik_fk_dialog = dialog


# Entry point when called directly or from toolbox
if __name__ == "__main__":
    run()