"""
Reset Scaling Multi-Take Tool
Reset scaling to 1,1,1 on selected joints/objects in all takes
"""

import sys

# Tool metadata
DISPLAY_NAME = "Reset Scaling Multi-Take"
DESCRIPTION = "Reset scaling to 1,1,1 on selected joints/objects in all takes"

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


def _process_scaling_property(property_obj, take):
    """Process scaling property for a take - Replace mode only"""
    
    if not property_obj:
        return
    
    # Get the animation node for this property
    anim_node = property_obj.GetAnimationNode()
    if not anim_node:
        return
    
    # Get the start time of the take
    start_time = take.LocalTimeSpan.GetStart()
    
    # Clear existing keys on all components (X, Y, Z)
    for i in range(3):  # 0=X, 1=Y, 2=Z
        try:
            # Get individual component FCurves through the Nodes collection
            if hasattr(anim_node, 'Nodes') and len(anim_node.Nodes) > i:
                component_node = anim_node.Nodes[i]
                if hasattr(component_node, 'FCurve') and component_node.FCurve:
                    fcurve = component_node.FCurve
                    if len(fcurve.Keys) > 0:
                        fcurve.EditClear()
        except Exception as e:
            pass
    
    # Add new key with 1,1,1 scaling
    try:
        anim_node.KeyAdd(start_time, [1.0, 1.0, 1.0])
    except Exception as e:
        pass


class ResetScalingConfirmationDialog(QDialog):
    """Non-modal dialog for Reset Scaling Multi-Take tool"""
    
    def __init__(self, initial_object_data, parent=None):
        if parent is None:
            parent = get_motionbuilder_main_window()
        
        super(ResetScalingConfirmationDialog, self).__init__(parent)
        
        self.setWindowTitle("Reset Scaling Multi-Take")
        self.setMinimumWidth(450)
        
        # Make it non-modal
        self.setModal(False)
        
        # Window flags - same as main toolbox
        if parent:
            self.setWindowFlags(Qt.Dialog)
        else:
            self.setWindowFlags(Qt.Window)
        
        # Store initial data
        self.current_object_data = initial_object_data
        
        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header info
        header_label = QLabel("Selected Objects (will reset scaling to 1,1,1):")
        header_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)
        
        # Create scrollable area for object info - use full window height
        self.object_scroll = QScrollArea()
        self.object_scroll.setWidgetResizable(True)
        self.object_content = QWidget()
        self.object_layout = QVBoxLayout()
        self.object_content.setLayout(self.object_layout)
        self.object_scroll.setWidget(self.object_content)
        layout.addWidget(self.object_scroll)
        
        # Update the object display
        self.update_object_display()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Apply to Selected Takes button (left side)
        self.apply_selected_button = QPushButton("Apply to Selected Takes")
        self.apply_selected_button.clicked.connect(self.apply_to_selected_takes)
        button_layout.addWidget(self.apply_selected_button)
        
        button_layout.addStretch()
        
        # Apply to All Takes button (right side)
        self.apply_button = QPushButton("Apply to All Takes")
        self.apply_button.clicked.connect(self.apply_to_takes)
        button_layout.addWidget(self.apply_button)
        
        # Update button states based on initial selection
        self.update_apply_button_state()
        self.update_selected_takes_button()
        
        layout.addLayout(button_layout)
        
        # Set up timer for automatic selection updates
        self.selection_timer = QTimer()
        self.selection_timer.timeout.connect(self.check_selection_changes)
        self.selection_timer.start(500)  # Check every 500ms for more responsive updates
        
        # Set up timer for Take Handler monitoring
        self.take_handler_timer = QTimer()
        self.take_handler_timer.timeout.connect(self.update_selected_takes_button)
        self.take_handler_timer.start(1000)  # Check every second for Take Handler
    
    def update_apply_button_state(self):
        """Update the apply button state and styling based on selection"""
        has_objects = bool(self.current_object_data)
        self.apply_button.setEnabled(has_objects)
        
        if has_objects:
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
    
    def update_object_display(self):
        """Update the display of current object selection"""
        # Clear existing widgets
        for i in reversed(range(self.object_layout.count())):
            self.object_layout.itemAt(i).widget().setParent(None)
        
        if not self.current_object_data:
            no_selection_label = QLabel("No objects selected")
            no_selection_label.setStyleSheet("color: #aaa; font-style: italic; margin: 10px;")
            self.object_layout.addWidget(no_selection_label)
        else:
            for obj in self.current_object_data:
                info_text = obj['name']
                
                info_label = QLabel(info_text)
                info_label.setStyleSheet("margin-left: 10px; margin-bottom: 2px;")
                self.object_layout.addWidget(info_label)
    
    def check_selection_changes(self):
        """Check if selection has changed or values have changed and update if needed"""
        if not MOBU_AVAILABLE:
            return
        
        try:
            # Get current selection
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            
            # Check if selection is different from current data
            current_names = [o['name'] for o in self.current_object_data]
            new_names = [model.Name for model in selected_models]
            
            selection_changed = set(current_names) != set(new_names)
            
            # Check if values have changed for existing selection
            values_changed = False
            if not selection_changed and self.current_object_data:
                for obj in self.current_object_data:
                    # Check if scale values have changed
                    if obj['scaling_prop']:
                        try:
                            current_scaling = obj['scaling_prop'].Data
                            old_scaling = obj['current_scaling']
                            if (abs(current_scaling[0] - old_scaling[0]) > 0.001 or
                                abs(current_scaling[1] - old_scaling[1]) > 0.001 or
                                abs(current_scaling[2] - old_scaling[2]) > 0.001):
                                values_changed = True
                                break
                        except:
                            pass
            
            if selection_changed or values_changed:
                self.refresh_selection()
        except:
            pass  # Ignore errors during background checking
    
    def refresh_selection(self):
        """Refresh the object data from current selection"""
        if not MOBU_AVAILABLE:
            return
        
        try:
            # Get fresh selection data
            selected_models = FBModelList()
            FBGetSelectedModels(selected_models)
            
            new_object_data = []
            for model in selected_models:
                # Get scale properties
                scale_x_prop = None
                scale_y_prop = None
                scale_z_prop = None
                
                # Look for Lcl Scaling property (MotionBuilder standard)
                scaling_prop = None
                
                # Try to find the Lcl Scaling property
                scaling_prop = model.PropertyList.Find('Lcl Scaling')
                if not scaling_prop:
                    # Try alternative names
                    scaling_prop = model.PropertyList.Find('Scaling')
                
                # If we have a scaling property, get its current value
                current_scaling = None
                if scaling_prop:
                    try:
                        current_scaling = scaling_prop.Data
                    except Exception as e:
                        # Try direct model scaling access as fallback
                        try:
                            current_scaling = model.Scaling
                        except Exception as e2:
                            pass
                
                # If we found scaling property, add to the list
                if scaling_prop or current_scaling:
                    data = {
                        'model': model,
                        'name': model.Name,
                        'scaling_prop': scaling_prop,
                        'current_scaling': current_scaling if current_scaling else FBVector3d(1.0, 1.0, 1.0)
                    }
                    new_object_data.append(data)
            
            self.current_object_data = new_object_data
            self.update_object_display()
            self.update_apply_button_state()
            self.update_selected_takes_button()
            
        except Exception as e:
            pass  # Ignore errors during refresh
    
    def apply_to_takes(self):
        """Apply the scaling reset to all takes"""
        if not self.current_object_data:
            # This shouldn't happen since button should be disabled, but just in case
            return
        
        # Refresh selection one more time to ensure latest values
        self.refresh_selection()
        
        # Ensure there are keys on the selected objects in the current take
        # This prevents issues when objects have no existing keys
        self._ensure_initial_keys()
        
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
                
                # Process each object
                for obj in self.current_object_data:
                    # Process scaling property (if it exists)
                    if obj['scaling_prop']:
                        _process_scaling_property(obj['scaling_prop'], take)
                
                # Force scene evaluation after processing this take
                FBSystem().Scene.Evaluate()
                
                processed_takes += 1
            
            # Restore original take
            if current_take:
                system.CurrentTake = current_take
            
            # Show completion message with detailed values
            object_details = []
            for obj in self.current_object_data:
                detail = f"• {obj['name']} (Reset to Scale: 1.00, 1.00, 1.00)"
                object_details.append(detail)
            
            FBMessageBox(
                "Reset Scaling Multi-Take Complete", 
                f"Successfully processed {processed_takes} takes.\n\n"
                f"Objects processed:\n" + "\n".join(object_details), 
                "OK"
            )
            
            # Close the dialog after showing completion message
            self.close()
            
        except Exception as e:
            # Restore original take on error
            if current_take:
                system.CurrentTake = current_take
            FBMessageBox("Error", f"Error processing takes: {str(e)}", "OK")
    
    def _ensure_initial_keys(self):
        """Ensure there are keys on the selected objects in the current take"""
        if not MOBU_AVAILABLE or not self.current_object_data:
            return
        
        system = FBSystem()
        current_take = system.CurrentTake
        
        if not current_take:
            return
        
        try:
            # Get the current time
            current_time = system.LocalTime
            
            # Process each object to ensure it has keys
            for obj in self.current_object_data:
                # Process scaling property
                if obj['scaling_prop']:
                    self._ensure_property_has_key(obj['scaling_prop'], current_time)
            
            # Force scene evaluation
            system.Scene.Evaluate()
            
        except Exception as e:
            pass  # Ignore errors during key creation
    
    def _ensure_property_has_key(self, property_obj, time):
        """Ensure a property has at least one key"""
        if not property_obj:
            return
        
        try:
            # Check if property already has animation
            anim_node = property_obj.GetAnimationNode()
            
            has_existing_keys = False
            if anim_node and anim_node.FCurve:
                existing_keys = len(anim_node.FCurve.Keys)
                has_existing_keys = existing_keys > 0
            
            if not has_existing_keys:
                # Use the Key() method to create a key directly on the property
                # This will automatically create animation nodes and FCurves as needed
                property_obj.Key()
        
        except Exception as e:
            pass  # Ignore errors during key creation
    
    def get_selected_takes_from_take_handler(self):
        """Get selected takes from Take Handler if it's open"""
        try:
            # Look for Take Handler window in Qt application
            app = QApplication.instance()
            if not app:
                return []
            
            selected_takes = []
            
            # Search through all top-level widgets to find Take Handler
            for widget in app.topLevelWidgets():
                if (hasattr(widget, 'windowTitle') and 
                    'Take Handler' in widget.windowTitle() and 
                    widget.isVisible()):
                    
                    # Found Take Handler window, try to get selected items
                    if hasattr(widget, 'take_list'):
                        take_list = widget.take_list
                        if hasattr(take_list, 'selectedItems'):
                            selected_items = take_list.selectedItems()
                            for item in selected_items:
                                if hasattr(item, 'text'):
                                    take_name = item.text()
                                    # Get the actual take object from MotionBuilder
                                    system = FBSystem()
                                    for take in system.Scene.Takes:
                                        if take.Name == take_name:
                                            selected_takes.append(take)
                                            break
                    break
            
            return selected_takes
        except:
            return []
    
    def is_take_handler_open(self):
        """Check if Take Handler window is open"""
        try:
            app = QApplication.instance()
            if not app:
                return False
            
            for widget in app.topLevelWidgets():
                if (hasattr(widget, 'windowTitle') and 
                    'Take Handler' in widget.windowTitle() and 
                    widget.isVisible()):
                    return True
            return False
        except:
            return False
    
    def update_selected_takes_button(self):
        """Update the selected takes button visibility and text"""
        if not self.is_take_handler_open():
            self.apply_selected_button.setVisible(False)
            return
        
        selected_takes = self.get_selected_takes_from_take_handler()
        take_count = len(selected_takes)
        
        if take_count > 0:
            self.apply_selected_button.setVisible(True)
            self.apply_selected_button.setText(f"Apply to {take_count} Take{'s' if take_count != 1 else ''}")
            
            # Enable/disable based on object selection
            has_objects = bool(self.current_object_data)
            self.apply_selected_button.setEnabled(has_objects)
            
            if has_objects:
                # Enabled state - green button
                self.apply_selected_button.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        font-weight: bold;
                        padding: 8px 16px;
                        border: none;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                """)
            else:
                # Disabled state - grayed out button
                self.apply_selected_button.setStyleSheet("""
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
        else:
            self.apply_selected_button.setVisible(False)
    
    def apply_to_selected_takes(self):
        """Apply the scaling reset to selected takes from Take Handler"""
        if not self.current_object_data:
            return
        
        selected_takes = self.get_selected_takes_from_take_handler()
        if not selected_takes:
            FBMessageBox("No Takes Selected", "Please select takes in the Take Handler first.", "OK")
            return
        
        # Refresh selection one more time to ensure latest values
        self.refresh_selection()
        
        # Ensure there are keys on the selected objects in the current take
        self._ensure_initial_keys()
        
        # Process only selected takes
        system = FBSystem()
        current_take = system.CurrentTake
        processed_takes = 0
        
        try:
            for take in selected_takes:
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
                
                # Process each object
                for obj in self.current_object_data:
                    # Process scaling property (if it exists)
                    if obj['scaling_prop']:
                        _process_scaling_property(obj['scaling_prop'], take)
                
                # Force scene evaluation after processing this take
                FBSystem().Scene.Evaluate()
                
                processed_takes += 1
            
            # Restore original take
            if current_take:
                system.CurrentTake = current_take
            
            # Show completion message with detailed values
            object_details = []
            for obj in self.current_object_data:
                detail = f"• {obj['name']} (Reset to Scale: 1.00, 1.00, 1.00)"
                object_details.append(detail)
            
            take_names = [take.Name for take in selected_takes]
            
            FBMessageBox(
                "Reset Scaling Selected Takes Complete", 
                f"Successfully processed {processed_takes} selected takes.\n\n"
                f"Takes processed:\n" + "\n".join([f"• {name}" for name in take_names]) + "\n\n"
                f"Objects processed:\n" + "\n".join(object_details), 
                "OK"
            )
            
            # Close the dialog after showing completion message
            self.close()
            
        except Exception as e:
            # Restore original take on error
            if current_take:
                system.CurrentTake = current_take
            FBMessageBox("Error", f"Error processing selected takes: {str(e)}", "OK")
    
    def closeEvent(self, event):
        """Clean up timers when dialog is closed"""
        if hasattr(self, 'selection_timer'):
            self.selection_timer.stop()
        if hasattr(self, 'take_handler_timer'):
            self.take_handler_timer.stop()
        super().closeEvent(event)


def run():
    """Main entry point for the Reset Scaling Multi-Take tool"""
    if not MOBU_AVAILABLE:
        return
    
    # Get selected models (allow opening without selection)
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models)
    
    # Find objects with scaling properties and get their current scale values
    object_data = []
    for model in selected_models:
        # Get scale properties
        scale_x_prop = None
        scale_y_prop = None
        scale_z_prop = None
        
        # Look for Lcl Scaling property (MotionBuilder standard)
        scaling_prop = None
        
        # Try to find the Lcl Scaling property
        scaling_prop = model.PropertyList.Find('Lcl Scaling')
        if not scaling_prop:
            # Try alternative names
            scaling_prop = model.PropertyList.Find('Scaling')
        
        # If we have a scaling property, get its current value
        current_scaling = None
        if scaling_prop:
            try:
                current_scaling = scaling_prop.Data
            except Exception as e:
                # Try direct model scaling access as fallback
                try:
                    current_scaling = model.Scaling
                except Exception as e2:
                    pass
        
        # If we found scaling property, add to the list
        if scaling_prop or current_scaling:
            data = {
                'model': model,
                'name': model.Name,
                'scaling_prop': scaling_prop,
                'current_scaling': current_scaling if current_scaling else FBVector3d(1.0, 1.0, 1.0)
            }
            object_data.append(data)
    
    # Allow opening even without object data - the dialog will handle empty selection
    
    # Show confirmation dialog
    dialog = ResetScalingConfirmationDialog(object_data)
    dialog.show()  # Show non-modal
    
    # Store reference to prevent garbage collection
    global reset_scaling_dialog
    reset_scaling_dialog = dialog


# Entry point when called directly or from toolbox
if __name__ == "__main__":
    run()