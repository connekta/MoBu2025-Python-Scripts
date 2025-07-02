"""
Copy Animation Layer Tool
Copy animation layers in MotionBuilder - copy layers to multiple/all takes
"""

import sys

# Tool metadata
DISPLAY_NAME = "Copy Animation Layer"
DESCRIPTION = "Copy animation layers between multiple takes"

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


def get_unique_layer_name(target_take, base_name):
    """Get a unique layer name by adding suffix if needed"""
    if not target_take:
        return base_name
    
    # Check if base name exists
    existing_names = []
    for i in range(target_take.GetLayerCount()):
        layer = target_take.GetLayer(i)
        existing_names.append(layer.Name)
    
    if base_name not in existing_names:
        return base_name
    
    # Find unique name with suffix
    counter = 1
    while True:
        new_name = f"{base_name}_copy_{counter:02d}"
        if new_name not in existing_names:
            return new_name
        counter += 1


class CopyAnimationLayerDialog(QDialog):
    """Non-modal dialog for Copy Animation Layer tool"""
    
    def __init__(self, initial_layer_data, parent=None):
        if parent is None:
            parent = get_motionbuilder_main_window()
        
        super(CopyAnimationLayerDialog, self).__init__(parent)
        
        self.setWindowTitle("Copy Animation Layer")
        self.setMinimumWidth(450)
        
        # Make it non-modal
        self.setModal(False)
        
        # Window flags - same as main toolbox
        if parent:
            self.setWindowFlags(Qt.Dialog)
        else:
            self.setWindowFlags(Qt.Window)
        
        # Store initial data
        self.current_layer_data = initial_layer_data
        self.layer_checkboxes = []
        
        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header info
        header_label = QLabel("Selected Animation Layers:")
        header_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)
        
        # Create scrollable area for layer info
        self.layer_scroll = QScrollArea()
        self.layer_scroll.setMaximumHeight(150)
        self.layer_scroll.setWidgetResizable(True)
        self.layer_content = QWidget()
        self.layer_layout = QVBoxLayout()
        self.layer_content.setLayout(self.layer_layout)
        self.layer_scroll.setWidget(self.layer_content)
        layout.addWidget(self.layer_scroll)
        
        # Update the layer display
        self.update_layer_display()
        
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("margin: 10px 0px;")
        layout.addWidget(separator)
        
        # Instructions
        instructions_label = QLabel("Instructions:\n• Select animation layers while this window is open\n• Use Copy Layer to Takes to copy selected layers to all takes or selected takes")
        instructions_label.setStyleSheet("color: #666; font-size: 10px; margin-bottom: 10px;")
        layout.addWidget(instructions_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Copy to Selected Takes button (left side)
        self.copy_selected_button = QPushButton("Copy Layer to Selected Takes")
        self.copy_selected_button.clicked.connect(self.copy_to_selected_takes)
        button_layout.addWidget(self.copy_selected_button)
        
        button_layout.addStretch()
        
        # Copy to All Takes button (right side)
        self.copy_button = QPushButton("Copy Layer to Takes")
        self.copy_button.clicked.connect(self.copy_to_takes)
        button_layout.addWidget(self.copy_button)
        
        # Update button states based on initial selection
        self.update_copy_button_state()
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
    
    def update_copy_button_state(self):
        """Update the copy button state and styling based on selection"""
        # Check if any layers are selected for copying
        has_selected_layers = any(layer.get('selected_for_copy', False) for layer in self.current_layer_data)
        self.copy_button.setEnabled(has_selected_layers)
        
        if has_selected_layers:
            # Enabled state - blue button
            self.copy_button.setStyleSheet("""
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
            self.copy_button.setStyleSheet("""
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
    
    def update_layer_display(self):
        """Update the display of current layer selection with checkboxes"""
        # Clear existing widgets
        for i in reversed(range(self.layer_layout.count())):
            self.layer_layout.itemAt(i).widget().setParent(None)
        
        # Clear checkbox references
        self.layer_checkboxes = []
        
        if not self.current_layer_data:
            no_selection_label = QLabel("No animation layers found")
            no_selection_label.setStyleSheet("color: #aaa; font-style: italic; margin: 10px;")
            self.layer_layout.addWidget(no_selection_label)
        else:
            # Add header
            header_label = QLabel("Select layers to copy:")
            header_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
            self.layer_layout.addWidget(header_label)
            
            for i, layer_data in enumerate(self.current_layer_data):
                # Create horizontal layout for checkbox and info
                layer_widget = QWidget()
                layer_layout = QHBoxLayout()
                layer_layout.setContentsMargins(0, 0, 0, 0)
                layer_widget.setLayout(layer_layout)
                
                # Create checkbox
                checkbox = QCheckBox()
                checkbox.setChecked(layer_data.get('selected_for_copy', False))
                checkbox.stateChanged.connect(self.on_layer_selection_changed)
                
                # Store reference to layer data in checkbox
                checkbox.layer_data = layer_data
                checkbox.layer_index = i
                self.layer_checkboxes.append(checkbox)
                
                # Create info text
                info_text = f"{layer_data['name']}"
                if layer_data['weight'] != 100.0:
                    info_text += f" - Weight: {layer_data['weight']:.1f}%"
                if layer_data['mute']:
                    info_text += " - Muted"
                if layer_data['solo']:
                    info_text += " - Solo"
                if not layer_data.get('has_animation', True):
                    info_text += " - No animation"
                
                info_label = QLabel(info_text)
                info_label.setStyleSheet("margin-left: 5px; cursor: pointer;")
                
                # Make the label clickable to toggle the checkbox
                info_label.mousePressEvent = lambda event, cb=checkbox: self.toggle_checkbox(cb, event)
                
                # Add to layout
                layer_layout.addWidget(checkbox)
                layer_layout.addWidget(info_label)
                layer_layout.addStretch()
                
                self.layer_layout.addWidget(layer_widget)
    
    def toggle_checkbox(self, checkbox, event):
        """Toggle checkbox when label is clicked"""
        checkbox.setChecked(not checkbox.isChecked())
    
    def on_layer_selection_changed(self):
        """Called when layer checkbox selection changes"""
        # Update the selected_for_copy flag in layer data
        for checkbox in self.layer_checkboxes:
            if hasattr(checkbox, 'layer_data'):
                checkbox.layer_data['selected_for_copy'] = checkbox.isChecked()
        
        # Update button states
        self.update_copy_button_state()
        self.update_selected_takes_button()
    
    def check_selection_changes(self):
        """Check if layer selection has changed and update if needed"""
        if not MOBU_AVAILABLE:
            return
        
        try:
            # Get current layer selection from UI (without debug prints)
            current_layer_data = self.get_selected_layers_quiet()
            
            # Check if selection is different from current data
            current_names = [(l['name'], l['take_name']) for l in self.current_layer_data]
            new_names = [(l['name'], l['take_name']) for l in current_layer_data]
            
            selection_changed = set(current_names) != set(new_names)
            
            if selection_changed:
                self.refresh_selection()
        except:
            pass  # Ignore errors during background checking
    
    def get_selected_layers_quiet(self):
        """Get currently selected animation layers from MotionBuilder UI (no debug prints)"""
        if not MOBU_AVAILABLE:
            return []
        
        try:
            layer_data = []
            system = FBSystem()
            current_take = system.CurrentTake
            
            if not current_take:
                return []
            
            # Get all layers except BaseAnimation that have animation data
            current_layer_index = current_take.GetCurrentLayer()
            
            for i in range(current_take.GetLayerCount()):
                layer = current_take.GetLayer(i)
                if layer and layer.Name != "BaseAnimation":
                    # Check if this layer has any animation data
                    has_animation = self.layer_has_animation(layer, current_take)
                    
                    data = {
                        'layer': layer,
                        'name': layer.Name,
                        'take': current_take,
                        'take_name': current_take.Name,
                        'weight': layer.Weight,
                        'mute': layer.Mute,
                        'solo': layer.Solo,
                        'lock': layer.Lock,
                        'is_current': i == current_layer_index,
                        'has_animation': has_animation,
                        'selected_for_copy': i == current_layer_index  # Default to current layer selected
                    }
                    layer_data.append(data)
            
            return layer_data
            
        except Exception as e:
            return []
    
    def layer_has_animation(self, layer, take):
        """Check if a layer has any animation data"""
        try:
            system = FBSystem()
            original_take = system.CurrentTake
            original_layer = take.GetCurrentLayer()
            
            # Switch to the layer to check for animation
            system.CurrentTake = take
            layer_index = find_layer_index(take, layer.Name)
            if layer_index >= 0:
                take.SetCurrentLayer(layer_index)
                
                # Quick check - look for any components with animation nodes that have keys
                for component in system.Scene.Components:
                    if hasattr(component, 'AnimationNode') and component.AnimationNode:
                        if self.node_has_keys(component.AnimationNode):
                            # Restore original context
                            system.CurrentTake = original_take
                            if original_layer >= 0:
                                original_take.SetCurrentLayer(original_layer)
                            return True
            
            # Restore original context
            system.CurrentTake = original_take
            if original_layer >= 0:
                original_take.SetCurrentLayer(original_layer)
            return False
        except:
            return True  # Assume it has animation if we can't check
    
    def node_has_keys(self, node):
        """Recursively check if a node or its children have any keys"""
        try:
            # Check if this node has keys
            if hasattr(node, 'FCurve') and node.FCurve and len(node.FCurve.Keys) > 0:
                return True
            
            # Check child nodes
            if hasattr(node, 'Nodes') and node.Nodes:
                for i in range(min(len(node.Nodes), 5)):  # Limit depth for performance
                    if self.node_has_keys(node.Nodes[i]):
                        return True
            return False
        except:
            return False
    
    def refresh_selection(self):
        """Refresh the layer data from current selection while preserving user checkbox selections"""
        if not MOBU_AVAILABLE:
            return
        
        try:
            # Store current user selections before refreshing
            current_selections = {}
            for layer_data in self.current_layer_data:
                current_selections[layer_data['name']] = layer_data.get('selected_for_copy', False)
            
            # Get fresh layer data
            new_layer_data = self.get_selected_layers_quiet()
            
            # Restore user selections
            for layer_data in new_layer_data:
                if layer_data['name'] in current_selections:
                    layer_data['selected_for_copy'] = current_selections[layer_data['name']]
            
            self.current_layer_data = new_layer_data
            self.update_layer_display()
            self.update_copy_button_state()
            self.update_selected_takes_button()
            
        except Exception as e:
            pass  # Ignore errors during refresh
    
    def copy_to_takes(self):
        """Copy the selected layers to all takes"""
        if not self.current_layer_data:
            return
        
        # Don't refresh selection here as it would override user checkbox selections
        if not self.current_layer_data:
            return
        
        try:
            system = FBSystem()
            original_take = system.CurrentTake
            processed_takes = 0
            processed_layers = 0
            
            # Get list of selected layers for confirmation
            selected_layers = [layer_data for layer_data in self.current_layer_data if layer_data.get('selected_for_copy', False)]
            
            if not selected_layers:
                FBMessageBox("No Layers Selected", "Please select at least one layer to copy.", "OK")
                return
            
            # Process each selected layer
            for layer_data in selected_layers:
                source_layer = layer_data['layer']
                source_take = layer_data['take']
                
                # Copy to all other takes
                for take in system.Scene.Takes:
                    if take == source_take:
                        continue  # Skip source take
                    
                    if copy_layer_to_take(source_layer, take, source_take):
                        processed_takes += 1
                
                processed_layers += 1
            
            # Restore original take
            if original_take:
                system.CurrentTake = original_take
            
            # Show success message with layer details
            total_takes = len(list(system.Scene.Takes))
            target_takes = total_takes - 1  # Excluding source take
            
            layer_names = [layer_data['name'] for layer_data in selected_layers]
            
            FBMessageBox(
                "Layer Copy Complete", 
                f"Successfully copied {processed_layers} layer(s) to {target_takes} takes:\n\n" +
                "Layers copied:\n" + "\n".join([f"• {name}" for name in layer_names]), 
                "OK"
            )
            
            # Close the dialog
            self.close()
            
        except Exception as e:
            FBMessageBox("Error", f"Error copying layers: {str(e)}", "OK")
    
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
            self.copy_selected_button.setVisible(False)
            return
        
        selected_takes = self.get_selected_takes_from_take_handler()
        take_count = len(selected_takes)
        
        if take_count > 0:
            self.copy_selected_button.setVisible(True)
            self.copy_selected_button.setText(f"Copy Layer to {take_count} Take{'s' if take_count != 1 else ''}")
            
            # Enable/disable based on layer selection
            has_selected_layers = any(layer.get('selected_for_copy', False) for layer in self.current_layer_data)
            self.copy_selected_button.setEnabled(has_selected_layers)
            
            if has_selected_layers:
                # Enabled state - green button
                self.copy_selected_button.setStyleSheet("""
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
                self.copy_selected_button.setStyleSheet("""
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
            self.copy_selected_button.setVisible(False)
    
    def copy_to_selected_takes(self):
        """Copy the selected layers to selected takes from Take Handler"""
        if not self.current_layer_data:
            return
        
        selected_takes = self.get_selected_takes_from_take_handler()
        if not selected_takes:
            FBMessageBox("No Takes Selected", "Please select takes in the Take Handler first.", "OK")
            return
        
        # Don't refresh selection here as it would override user checkbox selections
        if not self.current_layer_data:
            return
        
        try:
            system = FBSystem()
            original_take = system.CurrentTake
            processed_takes = 0
            processed_layers = 0
            
            # Get list of selected layers for confirmation
            selected_layers = [layer_data for layer_data in self.current_layer_data if layer_data.get('selected_for_copy', False)]
            
            if not selected_layers:
                FBMessageBox("No Layers Selected", "Please select at least one layer to copy.", "OK")
                return
            
            # Process each selected layer
            for layer_data in selected_layers:
                source_layer = layer_data['layer']
                source_take = layer_data['take']
                
                # Copy to selected takes only
                for take in selected_takes:
                    if take == source_take:
                        continue  # Skip source take
                    
                    if copy_layer_to_take(source_layer, take, source_take):
                        processed_takes += 1
                
                processed_layers += 1
            
            # Restore original take
            if original_take:
                system.CurrentTake = original_take
            
            # Show success message with detailed values
            take_names = [take.Name for take in selected_takes]
            layer_names = [layer_data['name'] for layer_data in selected_layers]
            
            FBMessageBox(
                "Layer Copy to Selected Takes Complete", 
                f"Successfully copied {processed_layers} layer(s) to {len(selected_takes)} selected takes:\n\n" +
                "Takes processed:\n" + "\n".join([f"• {name}" for name in take_names]) + "\n\n" +
                "Layers copied:\n" + "\n".join([f"• {name}" for name in layer_names]), 
                "OK"
            )
            
            # Close the dialog
            self.close()
            
        except Exception as e:
            FBMessageBox("Error", f"Error copying layers to selected takes: {str(e)}", "OK")
    
    def closeEvent(self, event):
        """Clean up timers when dialog is closed"""
        if hasattr(self, 'selection_timer'):
            self.selection_timer.stop()
        if hasattr(self, 'take_handler_timer'):
            self.take_handler_timer.stop()
        super().closeEvent(event)


def copy_layer_to_take(source_layer, target_take, source_take):
    """Copy a layer from source take to target take using full FCurve serialization"""
    if not source_layer or not target_take or not source_take:
        return False
    
    system = FBSystem()
    original_take = system.CurrentTake
    
    try:
        # Step 1: Serialize animation data from source layer
        # Switch to source take and set source layer as current
        system.CurrentTake = source_take
        source_layer_index = find_layer_index(source_take, source_layer.Name)
        
        if source_layer_index < 0:
            return False
        
        source_take.SetCurrentLayer(source_layer_index)
        
        # Collect all animation data from this layer
        serialized_animation_data = serialize_layer_animation(system.Scene)
        
        # Step 2: Create new layer in target take
        system.CurrentTake = target_take
        
        # Get unique name for the layer in target take
        unique_name = get_unique_layer_name(target_take, source_layer.Name)
        
        # Create new layer in target take
        target_take.CreateNewLayer()
        layer_count = target_take.GetLayerCount()
        new_layer = target_take.GetLayer(layer_count - 1)
        
        if not new_layer:
            return False
        
        # Set layer name and copy properties
        new_layer.Name = unique_name
        new_layer.Weight = source_layer.Weight
        new_layer.Mute = source_layer.Mute
        new_layer.Solo = source_layer.Solo
        new_layer.Lock = source_layer.Lock
        
        # Copy layer modes if available
        try:
            new_layer.LayerMode = source_layer.LayerMode
        except:
            pass
        
        try:
            new_layer.LayerRotationMode = source_layer.LayerRotationMode
        except:
            pass
        
        # Step 3: Deserialize animation data to target layer
        if serialized_animation_data:
            # Set new layer as current to receive animation
            target_take.SetCurrentLayer(layer_count - 1)
            
            # Deserialize animation data
            copied_components = deserialize_layer_animation(system.Scene, serialized_animation_data)
        
        return True
        
    except Exception as e:
        return False
    finally:
        # Always restore original take
        if original_take:
            system.CurrentTake = original_take


def find_layer_index(take, layer_name):
    """Find the index of a layer by name in a take"""
    for i in range(take.GetLayerCount()):
        layer = take.GetLayer(i)
        if layer and layer.Name == layer_name:
            return i
    return -1


def serialize_layer_animation(scene):
    """Serialize all animation data from the current layer context"""
    animation_data = []
    
    try:
        for component in scene.Components:
            if hasattr(component, 'AnimationNode'):
                anim_node = component.AnimationNode
                if anim_node:
                    # Serialize FCurves for this component
                    component_data = serialize_component_fcurves(component, anim_node)
                    if component_data:
                        animation_data.append(component_data)
        
        return animation_data
    
    except Exception as e:
        return []


def serialize_curve(fcurve):
    """Serialize an FCurve following the GitHub AnimationLayersManager approach"""
    key_data_list = []
    
    for key in fcurve.Keys:
        try:
            key_data = {
                'time': key.Time.Get(),  # Use Get() method like GitHub project
                'value': key.Value,
                'interpolation': int(key.Interpolation),
                'tangent_mode': getattr(key, 'TangentMode', 0),
                'left_derivative': getattr(key, 'LeftDerivative', 0.0),
                'right_derivative': getattr(key, 'RightDerivative', 0.0)
            }
            key_data_list.append(key_data)
        except Exception as e:
            continue  # Skip problematic keys
    
    return key_data_list


def get_serialized_fcurves(component):
    """Get all serialized FCurves for a component"""
    curves = {}
    
    if not hasattr(component, 'AnimationNode') or not component.AnimationNode:
        return curves
    
    # Recursively traverse animation nodes
    def traverse_node(node, path=""):
        if hasattr(node, 'FCurve') and node.FCurve and len(node.FCurve.Keys) > 0:
            curve_data = serialize_curve(node.FCurve)
            if curve_data:
                curves[path] = curve_data
        
        # Traverse child nodes
        if hasattr(node, 'Nodes') and node.Nodes:
            try:
                for i in range(len(node.Nodes)):
                    child_path = f"{path}.{i}" if path else str(i)
                    traverse_node(node.Nodes[i], child_path)
            except:
                pass  # Skip if nodes not accessible
    
    traverse_node(component.AnimationNode)
    return curves


def serialize_component_fcurves(component, anim_node, path=""):
    """Simplified version that returns FCurves data directly"""
    curves = get_serialized_fcurves(component)
    if curves:
        return {
            'component_name': component.Name,
            'component_class': component.ClassName(),
            'fcurves': curves
        }
    return None


def deserialize_layer_animation(scene, animation_data):
    """Deserialize animation data to the current layer context"""
    copied_components = 0
    
    try:
        for component_data in animation_data:
            component_name = component_data['component_name']
            fcurves_data = component_data['fcurves']  # Now a dict with path -> key_data_list mapping
            
            # Find the corresponding component in the scene
            target_component = None
            for component in scene.Components:
                if component.Name == component_name:
                    target_component = component
                    break
            
            if target_component:
                # Deserialize FCurves for this component
                if deserialize_component_fcurves(target_component, fcurves_data):
                    copied_components += 1
        
        return copied_components
    
    except Exception as e:
        return 0


def deserialize_curve(fcurve, key_data_list):
    """Deserialize an FCurve following the GitHub AnimationLayersManager approach"""
    fcurve.EditClear()
    
    # Add keys
    for key_data in key_data_list:
        try:
            # Use simple FBTime constructor like GitHub project
            key_index = fcurve.KeyAdd(FBTime(key_data['time']), key_data['value'])
            if key_index >= 0:
                key = fcurve.Keys[key_index]
                
                # Set key properties
                try:
                    key.Interpolation = key_data['interpolation']
                except:
                    pass
                
                try:
                    key.TangentMode = key_data['tangent_mode']
                except:
                    pass
                
                try:
                    key.LeftDerivative = key_data['left_derivative']
                    key.RightDerivative = key_data['right_derivative']
                except:
                    pass
        except Exception as e:
            continue  # Skip problematic keys


def deserialize_component_fcurves(component, fcurves_data):
    """Deserialize FCurves to a component's animation nodes"""
    try:
        if not hasattr(component, 'AnimationNode') or not component.AnimationNode:
            return False
        
        success_count = 0
        
        # fcurves_data is now a dict with path -> key_data_list mapping
        for path, key_data_list in fcurves_data.items():
            # Navigate to the target animation node using the path
            target_node = get_animation_node_by_path(component.AnimationNode, path)
            if target_node:
                # Ensure FCurve exists
                if not target_node.FCurve:
                    # Create FCurve by adding a temporary key, then clear it
                    target_node.KeyAdd(FBTime(0), 0)
                    if target_node.FCurve:
                        target_node.FCurve.EditClear()
                
                if target_node.FCurve:
                    deserialize_curve(target_node.FCurve, key_data_list)
                    success_count += 1
        
        return success_count > 0
    
    except Exception as e:
        return False


def get_animation_node_by_path(root_node, path):
    """Navigate to an animation node using a path like '0.1.2'"""
    if not path:
        return root_node
    
    try:
        current_node = root_node
        path_parts = path.split('.')
        
        for part in path_parts:
            index = int(part)
            if index < len(current_node.Nodes):
                current_node = current_node.Nodes[index]
            else:
                return None
        
        return current_node
    
    except Exception as e:
        return None


def run():
    """Main entry point for the Copy Animation Layer tool"""
    if not MOBU_AVAILABLE:
        return
    
    # Get initial layer data (all layers except BaseAnimation)
    initial_layer_data = []
    try:
        system = FBSystem()
        current_take = system.CurrentTake
        
        if current_take:
            current_layer_index = current_take.GetCurrentLayer()
            
            # Get all layers except BaseAnimation
            for i in range(current_take.GetLayerCount()):
                layer = current_take.GetLayer(i)
                if layer and layer.Name != "BaseAnimation":
                    data = {
                        'layer': layer,
                        'name': layer.Name,
                        'take': current_take,
                        'take_name': current_take.Name,
                        'weight': layer.Weight,
                        'mute': layer.Mute,
                        'solo': layer.Solo,
                        'lock': layer.Lock,
                        'is_current': i == current_layer_index,
                        'has_animation': True,  # Assume true for initial load
                        'selected_for_copy': i == current_layer_index  # Default to current layer selected
                    }
                    initial_layer_data.append(data)
    except:
        pass  # Start with empty selection if there's an error
    
    # Show the copy animation layer dialog
    dialog = CopyAnimationLayerDialog(initial_layer_data)
    dialog.show()  # Show non-modal
    
    # Store reference to prevent garbage collection
    global copy_animation_layer_dialog
    copy_animation_layer_dialog = dialog


# Entry point when called directly or from toolbox
if __name__ == "__main__":
    run()