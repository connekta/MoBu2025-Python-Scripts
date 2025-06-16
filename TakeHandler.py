import os
import sys
import json
import re
from pyfbsdk import *
from pyfbsdk_additions import *
import PySide6
from PySide6.QtWidgets import (QApplication, QMainWindow, QListWidget, QListWidgetItem, 
                               QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QMenu, 
                               QDialog, QLabel, QLineEdit, QInputDialog,
                               QMessageBox, QStyledItemDelegate, QStyle, QSizePolicy,
                               QSizeGrip)
from PySide6.QtGui import QColor, QBrush, QPainter, QPen, QPolygon, QCursor, QFont
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QRect, QPoint

def get_motionbuilder_main_window():
    """Find the main MotionBuilder window/QWidget."""
    from PySide6.QtWidgets import QApplication
    
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

# Helper: strip numerical prefix from take names.
def strip_prefix(name):
    return re.sub(r'^\d+\s*-\s*', '', name)

# Helper: check if a take is a group take
def is_group_take(take_name):
    """Check if a take name indicates a group take (starts with == or --)."""
    return take_name.startswith('==') or take_name.startswith('--')

def get_settings_path():
    """Get the global settings path for window geometry"""
    base_dir = os.path.expanduser("C:/Users/morri/Documents/MB/CustomPythonSaveData/TakesManager")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    return os.path.join(base_dir, "window_settings.json")

def save_window_settings(window):
    """Save window position and size"""
    settings_path = get_settings_path()
    pos = window.pos()
    size = window.size()
    settings = {
        'pos_x': pos.x(),
        'pos_y': pos.y(),
        'width': size.width(),
        'height': size.height()
    }
    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f)
    except Exception as e:
        pass  # Error saving window settings

def load_window_settings(window):
    """Load window position and size"""
    settings_path = get_settings_path()
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                window.move(settings.get('pos_x', 100), settings.get('pos_y', 100))
                window.resize(settings.get('width', 400), settings.get('height', 500))
        except Exception as e:
            pass  # Error loading window settings
            window.move(100, 100)
            window.resize(400, 500)

class TakeChangeMonitor(QObject):
    """Monitor changes in the scene's takes."""
    takeChanged = Signal()
    currentTakeChanged = Signal()  # New signal specifically for current take changes
    
    def __init__(self):
        super(TakeChangeMonitor, self).__init__()
        self.system = FBSystem()
        self.last_take_count = len(self.system.Scene.Takes)
        self.last_take_names = [self.system.Scene.Takes[i].Name for i in range(len(self.system.Scene.Takes))]
        self.last_current_take = self.system.CurrentTake.Name if self.system.CurrentTake else None
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_takes)
        self.timer.start(500)  # Check every 500ms to reduce monitor spam
    
    def check_takes(self):
        system = FBSystem()
        
        # Quick check for current take change (most common case)
        current_current_take = system.CurrentTake.Name if system.CurrentTake else None
        if current_current_take != self.last_current_take:
            # Current take changed
            self.last_current_take = current_current_take
            self.currentTakeChanged.emit()  # Emit specific signal for current take changes
            return
            
        # Less frequent check for take count/names changes
        current_take_count = len(system.Scene.Takes)
        if current_take_count != self.last_take_count:
            # Take count changed
            self.last_take_count = current_take_count
            current_take_names = [system.Scene.Takes[i].Name for i in range(len(system.Scene.Takes))]
            self.last_take_names = current_take_names.copy()  # Always make a copy
            self.takeChanged.emit()
            return
            
        # Full check for name changes (most expensive) - only if count hasn't changed
        current_take_names = [system.Scene.Takes[i].Name for i in range(len(system.Scene.Takes))]
        if current_take_names != self.last_take_names:
            # Take names changed - make sure we create a proper independent copy
            self.last_take_names = [name for name in current_take_names]  # Create a new list with copied elements
            self.takeChanged.emit()

class TagDialog(QDialog):
    """Dialog for setting take tags with preset colors."""
    PRESET_COLORS = [
        QColor(255, 0, 0), QColor(0, 255, 0), QColor(0, 0, 255),
        QColor(255, 255, 0), QColor(255, 0, 255), QColor(0, 255, 255),
        QColor(255, 128, 0), QColor(128, 0, 255)
    ]
    
    def __init__(self, take_name, current_tag="", current_color=None, parent=None):
        super(TagDialog, self).__init__(parent)
        self.take_name = take_name
        self.tag = current_tag
        self.color = current_color or self.PRESET_COLORS[0]
        self.setWindowTitle(f"Set Tag for {take_name}")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        tag_layout = QHBoxLayout()
        tag_label = QLabel("Tag:")
        self.tag_edit = QLineEdit(current_tag)
        tag_layout.addWidget(tag_label)
        tag_layout.addWidget(self.tag_edit)
        layout.addLayout(tag_layout)
        
        layout.addWidget(QLabel("Color:"))
        color_layout = QHBoxLayout()
        self.color_buttons = []
        for preset_color in self.PRESET_COLORS:
            button = QPushButton()
            button.setFixedSize(20, 20)
            button.setStyleSheet(f"background-color: {preset_color.name()}; border: 1px solid black;")
            button.clicked.connect(lambda checked=False, c=preset_color: self._set_color(c))
            if preset_color.name() == self.color.name():
                button.setStyleSheet(f"background-color: {preset_color.name()}; border: 3px solid white;")
            color_layout.addWidget(button)
            self.color_buttons.append(button)
        layout.addLayout(color_layout)
        
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
    
    def _set_color(self, color):
        self.color = color
        for i, preset_color in enumerate(self.PRESET_COLORS):
            if preset_color.name() == color.name():
                self.color_buttons[i].setStyleSheet(f"background-color: {preset_color.name()}; border: 3px solid white;")
            else:
                self.color_buttons[i].setStyleSheet(f"background-color: {preset_color.name()}; border: 1px solid black;")
    
    def get_values(self):
        self.tag = self.tag_edit.text()
        return self.tag, self.color

class TakeListItem(QListWidgetItem):
    """Custom list item for takes."""
    def __init__(self, take_name, is_current=False, tag="", color=None, is_favorite=False, parent_group=None, visible=True):
        super(TakeListItem, self).__init__()
        self.take_name = take_name  # This is the stripped (original) name.
        self.tag = tag
        self.color = color or QColor(200, 200, 200)
        self.is_favorite = is_favorite
        self.is_group = is_group_take(take_name)
        self.parent_group = parent_group  # Name of the parent group take
        self.visible = visible  # Whether this take should be visible based on group collapse
        self.update_display(is_current)
    
    def update_display(self, is_current=False):
        self.setText(self.take_name)
        font = self.font()
        font.setBold(is_current or self.is_group)  # Make group takes bold
        self.setFont(font)
        self.setData(Qt.UserRole, self.color)
        if self.is_favorite:
            self.setData(Qt.UserRole + 1, True)
        self.setData(Qt.UserRole + 2, bool(self.tag))
        self.setData(Qt.UserRole + 3, self.is_group)  # Store group status for delegate
        self.setHidden(not self.visible)  # Hide/show based on group collapse state

class DraggableListWidget(QListWidget):
    """List widget with drag and drop support and in-place editing."""
    def __init__(self, window=None, parent=None):
        super(DraggableListWidget, self).__init__(parent)
        self.window = window  # Store a reference to the main window
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(False)
        self.internal_drop = False
        
        # Custom drop indicator
        self.drop_indicator_position = -1
        
        # For in-place editing
        self.editing_item = None
        self.editor = None
    
    def mousePressEvent(self, event):
        """Handle mouse press - clear selection when clicking empty space"""
        super(DraggableListWidget, self).mousePressEvent(event)
        # Check if clicked on empty space - use position() instead of deprecated pos()
        if not self.indexAt(event.position().toPoint()).isValid():
            self.clearSelection()
    
    def dragMoveEvent(self, event):
        """Override drag move to show custom single drop indicator"""
        # Find the closest item for drop position
        drop_y = event.position().toPoint().y()
        closest_row = -1
        closest_distance = float('inf')
        
        for i in range(self.count()):
            item = self.item(i)
            if item and not item.isHidden():
                item_rect = self.visualItemRect(item)
                item_center_y = item_rect.center().y()
                distance = abs(drop_y - item_center_y)
                
                if distance < closest_distance:
                    closest_distance = distance
                    closest_row = i
        
        # Update drop indicator position
        if closest_row != self.drop_indicator_position:
            self.drop_indicator_position = closest_row
            self.viewport().update()
            
        super(DraggableListWidget, self).dragMoveEvent(event)
    
    def dragLeaveEvent(self, event):
        """Clear drop indicator when drag leaves widget"""
        self.drop_indicator_position = -1
        self.viewport().update()
        super(DraggableListWidget, self).dragLeaveEvent(event)
    
    def paintEvent(self, event):
        """Paint the list and custom drop indicator"""
        super(DraggableListWidget, self).paintEvent(event)
        
        # Draw custom drop indicator if dragging
        if self.drop_indicator_position >= 0:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Set pen for drop indicator line
            pen = QPen(QColor(100, 150, 255), 2)  # Blue line, 2px thick
            painter.setPen(pen)
            
            # Get the item rectangle for the drop position
            item = self.item(self.drop_indicator_position)
            if item:
                item_rect = self.visualItemRect(item)
                # Draw line below the target item (indicating insert position)
                y_pos = item_rect.bottom()
                painter.drawLine(item_rect.left(), y_pos, item_rect.right(), y_pos)
                
            painter.end()
    
    def dropEvent(self, event):
        # Get all selected items for multi-take movement
        selected_items = self.selectedItems()
        
        # Use the drop indicator position directly
        target_row = self.drop_indicator_position
        target_item = self.item(target_row) if target_row >= 0 else None
        target_take_name = target_item.take_name if target_item else None
        
        # Clear drop indicator immediately
        self.drop_indicator_position = -1
        self.viewport().update()
        
        # Don't call Qt's dropEvent to avoid conflicts - handle everything ourselves
        event.accept()
        
        # Perform the move using our backend logic
        if self.window and selected_items and target_take_name:
            # Temporarily stop monitors
            monitor_was_running = False
            if hasattr(self.window, 'monitor') and hasattr(self.window.monitor, 'timer'):
                monitor_was_running = self.window.monitor.timer.isActive()
                if monitor_was_running:
                    self.window.monitor.timer.stop()
            
            # Handle multi-take movement
            if hasattr(self.window, "move_multiple_takes"):
                selected_take_names = [item.take_name for item in selected_items if hasattr(item, 'take_name')]
                self.window.move_multiple_takes(selected_take_names, target_take_name)
            
            # Full refresh needed after move to show new order
            if hasattr(self.window, "update_take_list"):
                self.window.update_take_list()
                
            # Update monitor state to match current reality BEFORE restarting
            if hasattr(self.window, 'monitor'):
                system = FBSystem()
                current_take_names = [system.Scene.Takes[i].Name for i in range(len(system.Scene.Takes))]
                self.window.monitor.last_take_count = len(system.Scene.Takes)
                self.window.monitor.last_take_names = current_take_names[:]  # Make a proper copy
                
            # Find and select the moved takes in their new positions
            def select_moved_takes():
                selected_take_names = [item.take_name for item in selected_items if hasattr(item, 'take_name')]
                # Clear current selection
                self.clearSelection()
                # Select all moved takes
                for i in range(self.count()):
                    item = self.item(i)
                    if item and hasattr(item, 'take_name') and item.take_name in selected_take_names:
                        item.setSelected(True)
            
            QTimer.singleShot(10, select_moved_takes)
            
            # Restart the monitor after a delay with proper state sync timing
            if monitor_was_running:
                def restart_monitor():
                    if hasattr(self.window, 'monitor') and hasattr(self.window.monitor, 'timer'):
                        self.window.monitor.timer.start(500)
                
                # Give extra time to ensure everything is settled before restart
                QTimer.singleShot(500, restart_monitor)
        
    def editItem(self, item):
        """Start editing a list item in-place"""
        if not item or getattr(item, 'is_group', False):  # Don't edit group items in-place
            return
            
        try:
            # Create an editor if we don't have one
            if not self.editor:
                self.editor = QLineEdit(self)
                self.editor.setFrame(True)  # Add a frame to make it more visible
                self.editor.setStyleSheet("background-color: #3C3C50; color: white; border: 1px solid #3A539B;")
                self.editor.editingFinished.connect(self._finishEditing)
                
            # Position the editor over the item
            rect = self.visualItemRect(item)
            
            # Adjust the editor's position and size based on the item's properties
            # This needs to match the TakeListDelegate's paint method formatting
            offset = 0
            
            # Check for group indentation (though we shouldn't edit groups)
            if getattr(item, 'is_group', False):
                offset += 18
                
            # Check for tag color indicator
            if getattr(item, 'tag', '') and not getattr(item, 'is_group', False):
                offset += 10
                
            # Adjust the rectangle with the proper offset
            extra_height = 4  # Make editor taller by 4 pixels
            
            # Fixed right margin for text to avoid overlap with tag/star
            right_margin = 16
                
            editor_rect = QRect(
                rect.left() + offset,
                rect.top() - extra_height//2,  # Move up slightly to center vertically
                rect.width() - offset - right_margin,  # Account for right-side controls
                rect.height() + extra_height  # Make editor taller
            )
            
            self.editor.setGeometry(editor_rect)
            self.editor.setText(item.take_name)
            self.editor.selectAll()
            self.editor.show()
            self.editor.setFocus()
            self.editing_item = item
        except RuntimeError as e:
            pass  # Error starting inline edit
            self.editing_item = None
        
    def _finishEditing(self):
        """Complete the editing process"""
        try:
            if not self.editing_item:
                return
                
            new_name = self.editor.text().strip()
            old_name = getattr(self.editing_item, 'take_name', '')
            if new_name and new_name != old_name:
                # Only notify if name actually changed
                if hasattr(self.window, '_rename_take_inline'):
                    self.window._rename_take_inline(old_name, new_name)
                
        except Exception as e:
            pass  # Error finishing edit
        finally:
            if self.editor:
                self.editor.hide()
            self.editing_item = None

class TakeHandlerWindow(QMainWindow):
    """Custom Take Handler window."""
    def __init__(self, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        # Use a more standard window but with minimal decoration
        super(TakeHandlerWindow, self).__init__(parent, 
            Qt.Tool  # Tool windows are more compact but retain resize capability
        )
        self.setWindowTitle("Take Handler")
        
        # Set a compact style that maintains resize functionality
        self.setStyleSheet("""
            QMainWindow::title {
                height: 12px;  /* Reduce title bar height */
            }
        """)
        
        self.setMinimumSize(100, 100)
        self.system = FBSystem()
        self.take_data = {}  # Config data keyed by the take's original (stripped) name.
        self.config_path = self._get_config_path()
        self.monitor = TakeChangeMonitor()
        self.monitor.takeChanged.connect(self.update_take_list)
        self.monitor.currentTakeChanged.connect(self.update_current_take_only)  # Connect the fast update for current take changes
        
        # Track expanded/collapsed state of groups
        self.expanded_groups = {}
        
        # Create a central widget with default system styling
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(1, 1, 1, 1)  # Minimal margins
        main_layout.setSpacing(0)
        
        self.take_list = DraggableListWidget(window=self)  # Pass self as the window parameter
        self.take_list.setSelectionMode(QListWidget.ExtendedSelection)  # Allow multi-select
        self.take_list.itemDoubleClicked.connect(self.on_item_double_click)
        self.take_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.take_list.customContextMenuRequested.connect(self._show_context_menu)
        self.take_list.clicked.connect(self._on_item_clicked)
        main_layout.addWidget(self.take_list)
        
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(2, 0, 2, 2)  # Minimal padding
        
        # Create a small green + button
        self.new_take_button = QPushButton("+")
        self.new_take_button.setToolTip("Create New Take")
        self.new_take_button.setFixedSize(18, 18)  # Smaller square button
        self.new_take_button.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                border-radius: 0px;
                border: none;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:pressed {
                background-color: #1f8b4c;
            }
        """)
        self.new_take_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.new_take_button.clicked.connect(self._create_new_take)
        
        button_layout.addWidget(self.new_take_button)
        button_layout.addStretch()
        
        # Create a small sort button with sort symbol, aligned to the right
        self.sort_button = QPushButton("≡")
        self.sort_button.setToolTip("Sort takes A→Z (multiple selected: sort selected only, single/none: sort all)")
        self.sort_button.setFixedSize(18, 18)  # Same size as + button
        self.sort_button.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: white;
                font-weight: bold;
                border-radius: 0px;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #6c7b7d;
            }
            QPushButton:pressed {
                background-color: #5a6061;
            }
        """)
        self.sort_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.sort_button.clicked.connect(self._sort_takes_alphabetically)
        
        button_layout.addWidget(self.sort_button)
        main_layout.addLayout(button_layout)
        
        # The window can still be resized using the window edges
        # without needing an explicit size grip
        
        self._load_config()
        self.update_take_list()
    
    def _get_config_path(self):
        base_dir = os.path.expanduser("C:/Users/morri/Documents/MB/CustomPythonSaveData/TakesManager")
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        app = FBApplication()
        scene_path = app.FBXFileName if app.FBXFileName else "unsaved_scene"
        scene_path = os.path.basename(scene_path)
        clean_name = ''.join(c if c.isalnum() else '_' for c in scene_path)
        return os.path.join(base_dir, f"{clean_name}.json")
    
    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    saved_data = json.load(f)
                    for take_name, data in saved_data.items():
                        if 'color' in data:
                            color_dict = data['color']
                            data['color'] = QColor(color_dict['r'], color_dict['g'], color_dict['b'])
                    self.take_data = saved_data
                    
                    # Load expanded state if available
                    if 'expanded_groups' in saved_data:
                        self.expanded_groups = saved_data['expanded_groups']
                    else:
                        # Default to expanded
                        self.expanded_groups = {}
            except Exception as e:
                pass  # Error loading configuration
    
    def _save_config(self):
        save_data = {}
        for take_name, data in self.take_data.items():
            save_data[take_name] = data.copy()
            if 'color' in data and isinstance(data['color'], QColor):
                save_data[take_name]['color'] = {
                    'r': data['color'].red(),
                    'g': data['color'].green(),
                    'b': data['color'].blue()
                }
                
        # Save expanded state
        save_data['expanded_groups'] = self.expanded_groups
        
        try:
            with open(self.config_path, 'w') as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            pass  # Error saving configuration
    
    def _get_all_tags(self):
        tags = set()
        for data in self.take_data.values():
            tag = data.get('tag', '')
            if tag:
                tags.add(tag)
        return sorted(list(tags))
    
    def reorder_takes(self, source_row, target_row):
        """Reorder takes using the MotionBuilder plug system to match Navigator's order with our UI."""
        try:
            if source_row == target_row:
                return
                
            system = FBSystem()
            scene = system.Scene
            
            # DEBUG: Print UI order before move
            print(f"\n=== REORDER DEBUG START ===")
            print(f"UI Move: row {source_row} -> row {target_row}")
            print("UI Take Order BEFORE move:")
            for i in range(self.take_list.count()):
                item = self.take_list.item(i)
                if item and not item.isHidden():
                    print(f"  UI[{i}]: {item.take_name}")
            
            # DEBUG: Print native order before move
            print("Native Take Order BEFORE move:")
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                print(f"  Native[{i}]: {strip_prefix(take.Name)}")
            
            # Get the take names from UI positions (handles hidden takes correctly)
            source_item = self.take_list.item(source_row)
            target_item = self.take_list.item(target_row)
            
            if not source_item or not target_item:
                print("ERROR: Could not get source or target items")
                return
                
            source_take_name = source_item.take_name
            target_take_name = target_item.take_name
            print(f"Moving: '{source_take_name}' to position of '{target_take_name}'")
            
            # Find the actual scene positions for these takes
            source_scene_pos = -1
            target_scene_pos = -1
            source_take = None
            target_take = None
            
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                take_name_clean = strip_prefix(take.Name)
                if take_name_clean == source_take_name:
                    source_scene_pos = i
                    source_take = take
                elif take_name_clean == target_take_name:
                    target_scene_pos = i
                    target_take = take
                    
            if source_scene_pos == -1 or target_scene_pos == -1 or not source_take:
                print(f"ERROR: Could not find takes in scene. Source pos: {source_scene_pos}, Target pos: {target_scene_pos}")
                return
            
            print(f"Scene positions: source at [{source_scene_pos}], target at [{target_scene_pos}]")
            
            # Remember the current take
            current_take = system.CurrentTake
            
            # Get the Takes List from the first take's destination
            first_take = scene.Takes[0]
            takes_list = first_take.GetDst(1)  # This is the Takes List folder
            
            # Find the Source ID (current position of our take in the takes list)
            src_id = -1
            for i in range(takes_list.GetSrcCount()):
                src = takes_list.GetSrc(i)
                if src == source_take:
                    src_id = i
                    break
            
            if src_id == -1:
                print("ERROR: Could not find take in the takes list sources")
                raise Exception("Could not find take in the takes list sources")
            
            # Calculate the destination ID using the target take's scene position
            dst_id = target_scene_pos
            print(f"MoveSrcAt: moving from source_id[{src_id}] to dest_id[{dst_id}]")
            
            # Now use MoveSrcAt as recommended
            takes_list.MoveSrcAt(src_id, dst_id)
            
            # Update the scene
            scene.Evaluate()
            
            # DEBUG: Print native order after move
            print("Native Take Order AFTER move:")
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                print(f"  Native[{i}]: {strip_prefix(take.Name)}")
            
            # Restore the current take
            system.CurrentTake = current_take
            
            self.update_take_list()
            
        except Exception as e:
            print(f"ERROR in reorder_takes: {e}")
            pass  # Error reordering takes
            QMessageBox.warning(self, "Error", f"Failed to reorder takes: {e}")
            self.update_take_list()
    
    def reorder_takes_by_name(self, source_take_name, target_take_name):
        """Reorder takes using take names instead of UI positions."""
        try:
            if not source_take_name or not target_take_name or source_take_name == target_take_name:
                return
                
            system = FBSystem()
            scene = system.Scene
            
            
            # Find the actual scene positions for these takes
            source_scene_pos = -1
            target_scene_pos = -1
            source_take = None
            target_take = None
            
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                take_name_clean = strip_prefix(take.Name)
                if take_name_clean == source_take_name:
                    source_scene_pos = i
                    source_take = take
                elif take_name_clean == target_take_name:
                    target_scene_pos = i
                    target_take = take
                    
            if source_scene_pos == -1 or target_scene_pos == -1 or not source_take:
                print(f"ERROR: Could not find takes in scene. Source pos: {source_scene_pos}, Target pos: {target_scene_pos}")
                return
            
            # Remember the current take
            current_take = system.CurrentTake
            
            # Get the Takes List from the first take's destination
            first_take = scene.Takes[0]
            takes_list = first_take.GetDst(1)  # This is the Takes List folder
            
            # Find the Source ID (current position of our take in the takes list)
            src_id = -1
            for i in range(takes_list.GetSrcCount()):
                src = takes_list.GetSrc(i)
                if src == source_take:
                    src_id = i
                    break
            
            if src_id == -1:
                print("ERROR: Could not find take in the takes list sources")
                # Try alternative approach - look for it by name
                for i in range(takes_list.GetSrcCount()):
                    src = takes_list.GetSrc(i)
                    if hasattr(src, 'Name') and strip_prefix(src.Name) == source_take_name:
                        src_id = i
                        break
                
                if src_id == -1:
                    raise Exception("Could not find take in the takes list sources")
            
            # Find where the target take is in the takes list
            target_id = -1
            for i in range(takes_list.GetSrcCount()):
                src = takes_list.GetSrc(i)
                if src == target_take:
                    target_id = i
                    break
            
            if target_id == -1:
                # Try by name
                for i in range(takes_list.GetSrcCount()):
                    src = takes_list.GetSrc(i)
                    if hasattr(src, 'Name') and strip_prefix(src.Name) == target_take_name:
                        target_id = i
                        break
                        
                if target_id == -1:
                    raise Exception("Could not find target take in the takes list sources")
            
            # Calculate final target position accounting for direction of movement
            # When moving down, we need to account for the source take being removed first
            if src_id < target_scene_pos:
                # Moving down: target position shifts down by 1 when source is removed
                final_target_id = target_scene_pos  # target_scene_pos + 1 - 1
            else:
                # Moving up: target position stays the same
                final_target_id = target_scene_pos + 1
            
            # Ensure we don't exceed bounds
            if final_target_id > takes_list.GetSrcCount():
                final_target_id = takes_list.GetSrcCount()
            takes_list.MoveSrcAt(src_id, final_target_id)
            
            # Update the scene
            scene.Evaluate()
            
            # Restore the current take
            system.CurrentTake = current_take
            
        except Exception as e:
            print(f"ERROR in reorder_takes_by_name: {e}")
            pass  # Error reordering takes
            QMessageBox.warning(self, "Error", f"Failed to reorder takes: {e}")
    
    def move_multiple_takes(self, take_names, target_take_name):
        """Move multiple takes as a group to a new position."""
        try:
            if not take_names or not target_take_name:
                return
            
            system = FBSystem()
            scene = system.Scene
            
            # Find target position
            target_scene_pos = -1
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                if strip_prefix(take.Name) == target_take_name:
                    target_scene_pos = i
                    break
            
            if target_scene_pos == -1:
                return
            
            # Remember the current take
            current_take = system.CurrentTake
            
            # Get the Takes List
            first_take = scene.Takes[0]
            takes_list = first_take.GetDst(1) if len(scene.Takes) > 0 else None
            
            if not takes_list:
                return
            
            # Find all source takes and their current positions
            source_takes = []
            for take_name in take_names:
                for i in range(len(scene.Takes)):
                    take = scene.Takes[i]
                    if strip_prefix(take.Name) == take_name:
                        source_takes.append((take, take_name, i))
                        break
            
            if not source_takes:
                return
            
            # Sort source takes by their current position (reverse order for moving)
            source_takes.sort(key=lambda x: x[2], reverse=True)
            
            # Move each take to the position after the target (where the line appears)
            # Start from the last take and work backwards to maintain relative order
            moves_completed = 0
            for i, (take_obj, take_name, old_pos) in enumerate(source_takes):
                # Find current source ID in takes list
                src_id = -1
                for j in range(takes_list.GetSrcCount()):
                    src = takes_list.GetSrc(j)
                    if src == take_obj:
                        src_id = j
                        break
                
                if src_id >= 0:
                    # Calculate final target position accounting for direction of movement
                    # When moving down, we need to account for the source takes being removed first
                    if src_id < target_scene_pos:
                        # Moving down: target position shifts down by number of takes already moved
                        final_target_id = target_scene_pos - moves_completed + i
                    else:
                        # Moving up: target position stays the same
                        final_target_id = target_scene_pos + 1 + i
                    
                    # Ensure we don't exceed bounds
                    if final_target_id > takes_list.GetSrcCount():
                        final_target_id = takes_list.GetSrcCount()
                    takes_list.MoveSrcAt(src_id, final_target_id)
                    moves_completed += 1
            
            # Update the scene
            scene.Evaluate()
            
            # Restore the current take
            system.CurrentTake = current_take
            
        except Exception as e:
            print(f"ERROR in move_multiple_takes: {e}")
            QMessageBox.warning(self, "Error", f"Failed to move takes: {e}")
    
    def move_group_with_contents(self, source_group_name, target_take_name):
        """Move a group and all its contents to a new position, auto-grouping orphaned takes."""
        try:
            system = FBSystem()
            scene = system.Scene
            
            # Remember the current take
            current_take = system.CurrentTake
            
            # Get all takes and analyze group structure
            all_takes = []
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                take_name = strip_prefix(take.Name)
                all_takes.append((take, take_name, i))
            
            # Find the source group and its contents
            source_group = None
            source_group_contents = []
            
            groups = self._analyze_take_groups(all_takes)
            for group in groups:
                if group['header'] and group['header'][1] == source_group_name:
                    source_group = group
                    source_group_contents = [group['header']] + group['members']
                    break
            
            if not source_group:
                # Fallback to regular move if group not found
                self.reorder_takes_by_name(source_group_name, target_take_name)
                return
            
            # Find target position
            target_position = -1
            for take, take_name, position in all_takes:
                if take_name == target_take_name:
                    target_position = position
                    break
            
            if target_position == -1:
                return
            
            # Check if moving the group would leave ungrouped takes that need auto-grouping
            orphaned_takes = self._find_orphaned_takes_after_group_move(groups, source_group, target_position)
            
            # Get the takes list for manipulation
            first_take = scene.Takes[0]
            takes_list = first_take.GetDst(1)
            
            if not takes_list:
                return
            
            # Step 1: Create auto-group for orphaned takes if needed
            auto_group_take = None
            if orphaned_takes:
                auto_group_take = self._create_auto_group(orphaned_takes)
                if auto_group_take:
                    # Refresh our takes list since we added a new take
                    all_takes = []
                    for i in range(len(scene.Takes)):
                        take = scene.Takes[i]
                        take_name = strip_prefix(take.Name)
                        all_takes.append((take, take_name, i))
                    
                    # Find the new target position (might have shifted due to auto-group creation)
                    for take, take_name, position in all_takes:
                        if take_name == target_take_name:
                            target_position = position
                            break
            
            # Step 2: Move the entire group to new position using individual moves
            self._move_group_sequentially(takes_list, source_group_contents, target_position)
            
            # Update the scene
            scene.Evaluate()
            
            # Restore the current take
            if current_take:
                system.CurrentTake = current_take
            
        except Exception as e:
            print(f"ERROR in move_group_with_contents: {e}")
            QMessageBox.warning(self, "Error", f"Failed to move group: {e}")
    
    def _find_orphaned_takes_after_group_move(self, groups, moving_group, target_position):
        """Find takes that would become orphaned after moving a group."""
        orphaned = []
        
        # Find the index of the moving group
        moving_group_index = -1
        for i, group in enumerate(groups):
            if group == moving_group:
                moving_group_index = i
                break
        
        if moving_group_index == -1:
            return orphaned
        
        # Find where the group is moving to
        target_group_index = -1
        for i, group in enumerate(groups):
            if group['header']:
                if group['header'][2] <= target_position <= group['header'][2] + len(group['members']):
                    target_group_index = i
                    break
            else:
                # Ungrouped section
                for member in group['members']:
                    if member[2] == target_position:
                        target_group_index = i
                        break
                if target_group_index != -1:
                    break
        
        # Determine what gets orphaned based on movement direction
        if target_group_index > moving_group_index:
            # Moving down - check for ungrouped takes immediately after the moving group
            if moving_group_index + 1 < len(groups):
                next_group = groups[moving_group_index + 1]
                if next_group['header'] is None:  # Ungrouped takes
                    orphaned = next_group['members']
        else:
            # Moving up - check for ungrouped takes at the target location
            if target_group_index != -1 and target_group_index < len(groups):
                target_group = groups[target_group_index]
                if target_group['header'] is None:  # Target is ungrouped takes
                    orphaned = target_group['members']
        
        return orphaned
    
    def _create_auto_group(self, orphaned_takes):
        """Create an auto-group for orphaned takes."""
        try:
            system = FBSystem()
            
            # Generate a unique group name
            group_counter = 1
            while True:
                group_name = f"== Group{group_counter:02d} =="
                # Check if this name already exists
                name_exists = False
                for i in range(len(system.Scene.Takes)):
                    take = system.Scene.Takes[i]
                    if strip_prefix(take.Name) == strip_prefix(group_name):
                        name_exists = True
                        break
                
                if not name_exists:
                    break
                group_counter += 1
            
            # Create the group take and insert it before the first orphaned take
            if orphaned_takes:
                first_orphaned_pos = orphaned_takes[0][2]  # Position of first orphaned take
                
                # Create the group take
                auto_group_take = FBTake(group_name)
                system.Scene.Takes.append(auto_group_take)
                
                # Move it to the correct position (before first orphaned take)
                first_take = system.Scene.Takes[0]
                takes_list = first_take.GetDst(1)
                
                if takes_list:
                    # Find the auto group in the takes list (it's at the end)
                    auto_group_src_id = -1
                    for i in range(takes_list.GetSrcCount()):
                        src = takes_list.GetSrc(i)
                        if src == auto_group_take:
                            auto_group_src_id = i
                            break
                    
                    if auto_group_src_id >= 0:
                        takes_list.MoveSrcAt(auto_group_src_id, first_orphaned_pos)
                        system.Scene.Evaluate()
                
                return auto_group_take
                
        except Exception as e:
            print(f"ERROR creating auto-group: {e}")
            
        return None
    
    def _move_group_sequentially(self, takes_list, group_contents, target_position):
        """Move group contents one by one to the target position."""
        try:
            # Sort group contents by their original position
            group_contents.sort(key=lambda x: x[2])
            
            # Move each take in the group, starting from the header
            for i, (take_obj, take_name, old_pos) in enumerate(group_contents):
                # Find current source ID in takes list
                src_id = -1
                for j in range(takes_list.GetSrcCount()):
                    src = takes_list.GetSrc(j)
                    if src == take_obj:
                        src_id = j
                        break
                
                if src_id >= 0:
                    # Calculate target ID for this specific take
                    # The first take (group header) goes to target_position
                    # Subsequent takes go immediately after
                    final_target_id = target_position + i
                    
                    # Ensure we don't exceed bounds
                    max_pos = takes_list.GetSrcCount() - 1
                    if final_target_id > max_pos:
                        final_target_id = max_pos
                    
                    # Only move if the position is different
                    if src_id != final_target_id:
                        takes_list.MoveSrcAt(src_id, final_target_id)
                        
        except Exception as e:
            print(f"ERROR in _move_group_sequentially: {e}")
    
    def _sort_takes_alphabetically(self):
        """Sort takes alphabetically in ascending order (A to Z). If multiple takes are selected, sort only those. If only one take is selected, sort all takes."""
        system = FBSystem()
        
        # Remember the current take to restore it later
        current_take = system.CurrentTake
        
        # Get selected items
        selected_items = self.take_list.selectedItems()
        
        # Show confirmation popup
        if len(selected_items) > 1:
            count_text = f"{len(selected_items)} selected takes"
        else:
            total_takes = len(system.Scene.Takes)
            count_text = f"all {total_takes} takes"
        
        result = QMessageBox.question(
            self, 
            "Sort Takes", 
            f"Do you want to sort {count_text}?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.Yes
        )
        
        if result != QMessageBox.Yes:
            return
        
        try:
            # Get all takes and analyze group structure
            all_scene_takes = []
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                take_name = strip_prefix(take.Name)
                all_scene_takes.append((take, take_name, i))
            
            # Determine which takes to sort
            if len(selected_items) > 1:
                # Sort only selected takes when multiple are selected
                selected_take_names = [item.take_name for item in selected_items]
                takes_to_sort = [t for t in all_scene_takes if t[1] in selected_take_names]
            else:
                # Sort all takes (when no selection or only one take selected)
                takes_to_sort = all_scene_takes
            
            # Group-aware sorting logic
            groups = self._analyze_take_groups(all_scene_takes)
            
            sorted_operations = self._get_group_aware_sort_operations(groups, takes_to_sort)
            
            # Execute the sorting operations
            if sorted_operations and len(system.Scene.Takes) > 0:
                first_take = system.Scene.Takes[0]
                takes_list = first_take.GetDst(1)
                
                if takes_list:
                    # Apply all sorting operations
                    for take_obj, target_position in sorted_operations:
                        # Find current position of this take in the takes list
                        src_id = -1
                        for j in range(takes_list.GetSrcCount()):
                            src = takes_list.GetSrc(j)
                            if src == take_obj:
                                src_id = j
                                break
                        
                        if src_id >= 0 and src_id != target_position:
                            takes_list.MoveSrcAt(src_id, target_position)
                    
                    system.Scene.Evaluate()
            
            # Restore the original current take
            if current_take:
                system.CurrentTake = current_take
            
            self.update_take_list()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to sort takes: {e}")
            self.update_take_list()
    
    def _analyze_take_groups(self, all_takes):
        """Analyze the take structure to identify groups and their members."""
        groups = []
        current_group = None
        ungrouped_takes = []
        
        for take_obj, take_name, position in all_takes:
            if is_group_take(take_name):
                # This is a group header
                # First, add any accumulated ungrouped takes as a virtual group
                if ungrouped_takes:
                    groups.append({
                        'header': None,
                        'members': ungrouped_takes[:]
                    })
                    ungrouped_takes = []
                
                # Close previous group if any
                if current_group:
                    groups.append(current_group)
                
                # Start new group
                current_group = {
                    'header': (take_obj, take_name, position),
                    'members': []
                }
            else:
                # This is a regular take
                if current_group:
                    # Add to current group
                    current_group['members'].append((take_obj, take_name, position))
                else:
                    # No current group - add to ungrouped takes
                    ungrouped_takes.append((take_obj, take_name, position))
        
        # Add any remaining ungrouped takes
        if ungrouped_takes:
            groups.append({
                'header': None,
                'members': ungrouped_takes[:]
            })
        
        # Don't forget the last group
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def _get_group_aware_sort_operations(self, groups, takes_to_sort):
        """Generate sorting operations that respect group boundaries."""
        operations = []
        takes_to_sort_set = {t[0] for t in takes_to_sort}  # Convert to set of take objects for fast lookup
        
        for group in groups:
            # Sort takes within this group that are in our sort list
            group_takes_to_sort = []
            
            # Check if group header needs sorting
            if group['header'] and group['header'][0] in takes_to_sort_set:
                group_takes_to_sort.append(group['header'])
            
            # Check which members need sorting
            members_to_sort = [member for member in group['members'] if member[0] in takes_to_sort_set]
            
            if members_to_sort:
                # Sort the members alphabetically
                members_to_sort.sort(key=lambda x: x[1].lower())
                
                # Determine where to place the sorted members
                if group['header']:
                    # Group has a header - members go right after the header
                    start_position = group['header'][2] + 1
                    
                    # Add header to operations if it's being sorted
                    if group['header'][0] in takes_to_sort_set:
                        operations.append((group['header'][0], group['header'][2]))
                    
                    # Add sorted members
                    for i, member in enumerate(members_to_sort):
                        target_pos = start_position + i
                        operations.append((member[0], target_pos))
                else:
                    # No group header - these are ungrouped takes, maintain their relative positions
                    # but sort them within their section
                    if group['members']:
                        original_positions = [member[2] for member in group['members']]
                        original_positions.sort()
                        
                        for i, member in enumerate(members_to_sort):
                            if i < len(original_positions):
                                operations.append((member[0], original_positions[i]))
        
        return operations
    
    def _create_new_take(self):
        name, ok = QInputDialog.getText(self, "New Take", "Enter take name:")
        if ok and name.strip():
            try:
                system = FBSystem()
                # When creating a new take, do not add a prefix.
                new_take = FBTake(name.strip())
                system.Scene.Takes.append(new_take)
                self.update_take_list()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to create take: {e}")
                
    def _create_new_group(self):
        name, ok = QInputDialog.getText(self, "New Group", "Enter group name (without == or -- prefix):")
        if ok and name.strip():
            try:
                system = FBSystem()
                # Add group prefix to name
                group_name = f"== {name.strip()}"
                new_take = FBTake(group_name)
                system.Scene.Takes.append(new_take)
                self.update_take_list()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to create group: {e}")
    
    def _open_takes_renamer(self):
        try:
            script_path = r"C:\Program Files\Autodesk\MotionBuilder 2025\bin\config\PythonCustomScripts\TakeRenamer.py"
            if os.path.exists(script_path):
                namespace = {
                    'QtWidgets': PySide6.QtWidgets,
                    'QtCore': PySide6.QtCore, 
                    'QtGui': PySide6.QtGui,
                    'FBSystem': FBSystem,
                    'FBApplication': FBApplication
                }
                namespace.update(globals())
                with open(script_path, 'r') as script_file:
                    script_code = script_file.read()
                    exec(script_code, namespace)
            else:
                QMessageBox.warning(self, "Error", f"Script not found: {script_path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to run Takes Renamer: {e}")
            import traceback
            traceback.print_exc()
    
    def _get_take_data(self, take_name):
        """Using the stripped name as key."""
        if take_name not in self.take_data:
            self.take_data[take_name] = {
                'tag': '',
                'color': QColor(200, 200, 200),
                'favorite': False
            }
        return self.take_data[take_name]
    
    def _show_context_menu(self, position):
        selected_items = self.take_list.selectedItems()
        
        # If no items are selected, show the empty area context menu
        if not selected_items:
            empty_menu = QMenu(self)
            add_take_action = empty_menu.addAction("Add new Take")
            action = empty_menu.exec(self.take_list.mapToGlobal(position))
            
            if action == add_take_action:
                self._add_take_at_end()
            return
        
        # Multi-select context menu
        if len(selected_items) > 1:
            menu = QMenu(self)
            
            # Tag operations for multiple items
            set_tag_menu = QMenu("Set Tag for All", self)
            menu.addMenu(set_tag_menu)
            
            existing_tags = self._get_all_tags()
            multi_tag_actions = []
            none_action = set_tag_menu.addAction("None")
            
            if existing_tags:
                set_tag_menu.addSeparator()
                for tag in existing_tags:
                    action = set_tag_menu.addAction(tag)
                    multi_tag_actions.append((action, tag))
            
            set_tag_menu.addSeparator()
            add_new_tag_action = set_tag_menu.addAction("Add new tag...")
            
            # Favorite actions
            add_to_favorites = menu.addAction("Add All to Favorites")
            remove_from_favorites = menu.addAction("Remove All from Favorites")
            
            menu.addSeparator()
            
            # Operations on multiple takes
            create_group_action = menu.addAction(f"Create Group for {len(selected_items)} Takes")
            menu.addSeparator()
            duplicate_action = menu.addAction(f"Duplicate {len(selected_items)} Takes")
            rename_action = menu.addAction(f"Rename {len(selected_items)} Takes")
            menu.addSeparator()
            delete_action = menu.addAction(f"Delete {len(selected_items)} Takes")
            
            action = menu.exec(self.take_list.mapToGlobal(position))
            
            if action == add_new_tag_action:
                self._set_tag_for_multiple(selected_items)
            elif action == none_action:
                self._remove_tag_from_multiple(selected_items)
            elif action in [a for a, _ in multi_tag_actions]:
                for act, tag in multi_tag_actions:
                    if action == act:
                        self._apply_tag_to_multiple(selected_items, tag)
                        break
            elif action == add_to_favorites:
                self._set_favorite_for_multiple(selected_items, True)
            elif action == remove_from_favorites:
                self._set_favorite_for_multiple(selected_items, False)
            elif action == create_group_action:
                self._create_group_for_selected(selected_items)
            elif action == duplicate_action:
                self._duplicate_takes(selected_items)
            elif action == rename_action:
                self._rename_takes(selected_items)
            elif action == delete_action:
                self._delete_takes(selected_items)
                
            return
        
        # Single item context menu (original logic)
        item = selected_items[0]
        menu = QMenu(self)
        take_name = item.take_name  # This is the stripped name.
        take_data = self._get_take_data(take_name)
        set_tag_menu = QMenu("Set Tag", self)
        menu.addMenu(set_tag_menu)
        existing_tags = self._get_all_tags()
        tag_actions = []
        if take_data.get('tag', ''):
            none_action = set_tag_menu.addAction("None")
            set_tag_menu.addSeparator()
        else:
            none_action = None
        for tag in existing_tags:
            action = set_tag_menu.addAction(tag)
            tag_actions.append((action, tag))
        if existing_tags:
            set_tag_menu.addSeparator()
        add_new_tag_action = set_tag_menu.addAction("Add new tag...")
        remove_tag_actions = []
        if existing_tags:
            set_tag_menu.addSeparator()
            for tag in existing_tags:
                action = set_tag_menu.addAction(f"Remove tag: {tag}")
                remove_tag_actions.append((action, tag))
        if take_data.get('favorite', False):
            favorite_action = menu.addAction("Remove from Favorites")
        else:
            favorite_action = menu.addAction("Add to Favorites")
        menu.addSeparator()
        duplicate_action = menu.addAction("Duplicate Take")
        add_take_below_action = menu.addAction("Add new Take below")
        rename_action = menu.addAction("Rename Take")
        menu.addSeparator()
        delete_action = menu.addAction("Delete Take")
        action = menu.exec(self.take_list.mapToGlobal(position))
        if action == add_new_tag_action:
            self._set_take_tag(take_name)
        elif action == none_action:
            take_data['tag'] = ''
            self._save_config()
            self.update_take_list()
        elif action in [a for a, _ in tag_actions]:
            for act, tag in tag_actions:
                if action == act:
                    color = None
                    for data in self.take_data.values():
                        if data.get('tag') == tag:
                            color = data.get('color')
                            break
                    if not color:
                        color = TagDialog.PRESET_COLORS[0]
                    take_data['tag'] = tag
                    take_data['color'] = color
                    self._save_config()
                    self.update_take_list()
                    break
        elif action in [a for a, _ in remove_tag_actions]:
            for act, tag in remove_tag_actions:
                if action == act:
                    for key, data in self.take_data.items():
                        if data.get('tag') == tag:
                            data['tag'] = ''
                    self._save_config()
                    self.update_take_list()
                    break
        elif action == favorite_action:
            take_data['favorite'] = not take_data.get('favorite', False)
            self._save_config()
            self.update_take_list()
        elif action == duplicate_action:
            self._duplicate_take(take_name)
        elif action == add_take_below_action:
            self._add_take_below(take_name)
        elif action == rename_action:
            # Store the take name instead of the item reference which might be deleted
            self._start_inline_rename(take_name)
        elif action == delete_action:
            self._delete_take(take_name)
    
    # Methods for setting tags on multiple takes
    def _set_tag_for_multiple(self, items):
        if not items:
            return
            
        dialog = TagDialog("Multiple Takes", current_tag="", current_color=None, parent=self)
        if dialog.exec() == QDialog.Accepted:
            tag, color = dialog.get_values()
            
            for item in items:
                take_name = item.take_name
                take_data = self._get_take_data(take_name)
                take_data['tag'] = tag
                take_data['color'] = color
            
            self._save_config()
            self.update_take_list()
            
    def _apply_tag_to_multiple(self, items, tag):
        # Find an existing color for this tag
        color = None
        for data in self.take_data.values():
            if data.get('tag') == tag:
                color = data.get('color')
                break
                
        if not color:
            color = TagDialog.PRESET_COLORS[0]
        
        for item in items:
            take_name = item.take_name
            take_data = self._get_take_data(take_name)
            take_data['tag'] = tag
            take_data['color'] = color
        
        self._save_config()
        self.update_take_list()
        
    def _remove_tag_from_multiple(self, items):
        for item in items:
            take_name = item.take_name
            take_data = self._get_take_data(take_name)
            take_data['tag'] = ''
        
        self._save_config()
        self.update_take_list()
        
    def _set_favorite_for_multiple(self, items, is_favorite):
        for item in items:
            take_name = item.take_name
            take_data = self._get_take_data(take_name)
            take_data['favorite'] = is_favorite
        
        self._save_config()
        self.update_take_list()
    
    # Methods for handling multiple takes
    def _create_group_for_selected(self, items):
        """Create a new group for the selected takes."""
        try:
            system = FBSystem()
            scene = system.Scene
            
            # Find the earliest position among selected takes
            earliest_pos = float('inf')
            selected_take_names = []
            
            for item in items:
                if not getattr(item, 'is_group', False):  # Only process actual takes, not groups
                    take_name = item.take_name
                    selected_take_names.append(take_name)
                    
                    # Find position in scene
                    for i in range(len(scene.Takes)):
                        take = scene.Takes[i]
                        if hasattr(take, 'Name') and strip_prefix(take.Name) == take_name:
                            earliest_pos = min(earliest_pos, i)
                            break
            
            if not selected_take_names:
                return
            
            # Analyze selected take names to find most common word
            all_words = []
            for take_name in selected_take_names:
                # Split by common separators and filter out very short words
                words = re.split(r'[_\-\s]+', take_name.lower())
                words = [word.strip() for word in words if len(word) >= 2]
                all_words.extend(words)
            
            # Find most common word
            if all_words:
                word_counts = {}
                for word in all_words:
                    word_counts[word] = word_counts.get(word, 0) + 1
                
                # Sort words by count (descending)
                sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
                most_common_word = sorted_words[0][0]
                base_group_name = most_common_word.upper()
            else:
                # Fallback to generic name if no words found
                base_group_name = "GROUP"
                sorted_words = []
            
            # Generate unique group name
            group_name = f"== {base_group_name} =="
            group_num = 1
            
            # Check if base name exists
            exists = False
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                if hasattr(take, 'Name') and strip_prefix(take.Name) == group_name:
                    exists = True
                    break
            
            # If it exists, try to find a second common word before using numbers
            if exists and len(sorted_words) > 1:
                num_takes = len(selected_take_names)
                
                # Look for second most common word with >40% occurrence
                for word, count in sorted_words[1:]:
                    occurrence_rate = count / num_takes
                    if occurrence_rate > 0.4:  # More than 40% occurrence
                        second_word = word.upper()
                        candidate_name = f"== {base_group_name} {second_word} =="
                        
                        # Check if this combination exists
                        candidate_exists = False
                        for i in range(len(scene.Takes)):
                            take = scene.Takes[i]
                            if hasattr(take, 'Name') and strip_prefix(take.Name) == candidate_name:
                                candidate_exists = True
                                break
                        
                        if not candidate_exists:
                            group_name = candidate_name
                            exists = False
                            break
            
            # If still exists or no good second word found, use numbered variants
            if exists:
                while True:
                    group_name = f"== {base_group_name} {group_num:02d} =="
                    exists = False
                    for i in range(len(scene.Takes)):
                        take = scene.Takes[i]
                        if hasattr(take, 'Name') and strip_prefix(take.Name) == group_name:
                            exists = True
                            break
                    
                    if not exists:
                        break
                    group_num += 1
            
            # Create the group take
            new_take = FBTake(group_name)
            scene.Takes.append(new_take)
            
            # Move the group take to the correct position
            if len(scene.Takes) > 0:
                first_take = scene.Takes[0]
                takes_list = first_take.GetDst(1)
                
                if takes_list:
                    # Find the new group take in the takes list (it's at the end)
                    group_src_id = -1
                    for i in range(takes_list.GetSrcCount()):
                        src = takes_list.GetSrc(i)
                        if src == new_take:
                            group_src_id = i
                            break
                    
                    if group_src_id >= 0:
                        takes_list.MoveSrcAt(group_src_id, earliest_pos)
                        scene.Evaluate()
            
            # Mark this as a group in our data
            self.take_data[group_name] = {'is_group': True}
            
            # Group the selected takes under this group
            for take_name in selected_take_names:
                if take_name not in self.take_data:
                    self.take_data[take_name] = {}
                self.take_data[take_name]['group'] = group_name
            
            # Expand the group by default
            self.expanded_groups[group_name] = True
            
            self._save_config()
            self.update_take_list()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create group: {e}")

    def _duplicate_takes(self, items):
        system = FBSystem()
        
        # Remember the current take to restore it later
        current_take = system.CurrentTake
        
        # Create a list to track original takes and their duplicates for positioning
        duplicate_pairs = []
        
        # First pass: Create all duplicates
        for item in items:
            take_name = item.take_name
            original_take = None
            
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                if strip_prefix(take.Name) == take_name:
                    original_take = take
                    break
                    
            if original_take:
                new_name = f"{take_name}_copy"
                try:
                    # Use CopyTake to properly duplicate the take with all animation data
                    new_take = original_take.CopyTake(new_name)
                    duplicate_pairs.append((original_take, new_take))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to duplicate take {take_name}: {e}")
        
        # Second pass: Position all duplicates correctly
        if duplicate_pairs:
            # Get the Takes List
            first_take = system.Scene.Takes[0]
            takes_list = first_take.GetDst(1) if len(system.Scene.Takes) > 0 else None
            
            if takes_list:
                # We need to position duplicates in reverse order to avoid index shifting issues
                # Start from the last selected item and work backwards
                for original_take, new_take in reversed(duplicate_pairs):
                    try:
                        # Find current positions of both takes
                        original_pos = -1
                        new_take_pos = -1
                        
                        for i in range(len(system.Scene.Takes)):
                            take = system.Scene.Takes[i]
                            if take == original_take:
                                original_pos = i
                            elif take == new_take:
                                new_take_pos = i
                                
                        # Only move if we found both takes and the new take isn't already in the right position
                        if original_pos >= 0 and new_take_pos >= 0 and new_take_pos != original_pos + 1:
                            # Find the source ID in the takes list
                            src_id = -1
                            for i in range(takes_list.GetSrcCount()):
                                src = takes_list.GetSrc(i)
                                if src == new_take:
                                    src_id = i
                                    break
                            
                            if src_id >= 0:
                                # Target position is right after the original take
                                target_id = original_pos + 1
                                # Make sure target_id doesn't exceed the list bounds
                                if target_id > takes_list.GetSrcCount():
                                    target_id = takes_list.GetSrcCount()
                                    
                                takes_list.MoveSrcAt(src_id, target_id)
                                
                    except Exception as e:
                        # Continue with other duplicates even if one fails
                        continue
                
                # Evaluate the scene after all moves
                system.Scene.Evaluate()
        
        # Restore the original current take
        if current_take:
            system.CurrentTake = current_take
        
        self.update_take_list()
        
    def _rename_takes(self, items):
        if not items:
            return
            
        # Get the base name for the renamed takes
        base_name, ok = QInputDialog.getText(self, "Rename Takes", 
                                         "Enter new base name for takes:", 
                                         QLineEdit.Normal, 
                                         items[0].take_name)
        if not ok or not base_name.strip():
            return
        
        system = FBSystem()
        
        # Rename each take with an incrementing suffix for all but the first one
        for i, item in enumerate(items):
            take_name = item.take_name
            take_to_rename = None
            
            for j in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[j]
                if strip_prefix(take.Name) == take_name:
                    take_to_rename = take
                    break
                    
            if take_to_rename:
                try:
                    # First take just gets the base name, others get base_name_1, base_name_2, etc.
                    is_group = is_group_take(take_name)
                    new_name = base_name if i == 0 else f"{base_name}_{i}"
                    
                    # Preserve group prefix if needed
                    if is_group:
                        if take_name.startswith('=='):
                            new_name = f"== {new_name}"
                        elif take_name.startswith('--'):
                            new_name = f"-- {new_name}"
                    
                    if take_name in self.take_data:
                        self.take_data[new_name] = self.take_data[take_name]
                        del self.take_data[take_name]
                    
                    take_to_rename.Name = new_name
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to rename take {take_name}: {e}")
        
        self._save_config()
        self.update_take_list()
        
    def _delete_takes(self, items):
        result = QMessageBox.question(self, "Delete Takes", 
                                     f"Are you sure you want to delete {len(items)} takes?",
                                     QMessageBox.Yes | QMessageBox.No, 
                                     QMessageBox.No)
        
        if result != QMessageBox.Yes:
            return
            
        system = FBSystem()
        takes_to_delete = []
        
        # First collect all takes to delete (in reverse order to avoid index shifts)
        for item in items:
            take_name = item.take_name
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                if strip_prefix(take.Name) == take_name:
                    takes_to_delete.append((i, take_name, take))
                    break
        
        # Check if we're deleting the current take
        current_take = system.CurrentTake
        need_new_current = False
        current_take_index = -1
        
        for i, take_name, take in takes_to_delete:
            if take == current_take:
                need_new_current = True
                current_take_index = i
                break
        
        # Find a new current take if needed
        if need_new_current and len(system.Scene.Takes) > len(takes_to_delete):
            # Set first take that isn't being deleted as current
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                if not any(idx == i for idx, _, _ in takes_to_delete):
                    system.CurrentTake = take
                    break
        
        # Sort by index in reverse order to remove from the end first
        takes_to_delete.sort(reverse=True, key=lambda x: x[0])
        
        for index, take_name, take in takes_to_delete:
            try:
                # Use the alternative approach - use the component directly
                # Get the Takes List component
                takes_list = None
                for i in range(take.GetDstCount()):
                    dst = take.GetDst(i)
                    if isinstance(dst, FBFolder):
                        takes_list = dst
                        break
                
                if takes_list:
                    # Disconnect the take from the takes list
                    take.DisconnectDst(takes_list)
                    
                    # Also disconnect from the scene if needed
                    take.DisconnectDst(system.Scene)
                else:
                    # Fallback to .remove method
                    system.Scene.Takes.remove(index)
                
                # Update our take data
                if take_name in self.take_data:
                    del self.take_data[take_name]
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete take {take_name}: {e}")
        
        self._save_config()
        self.update_take_list()
    
    def _delete_take(self, take_name):
        result = QMessageBox.question(self, "Delete Take", f"Are you sure you want to delete the take '{take_name}'?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if result == QMessageBox.Yes:
            system = FBSystem()
            scene = system.Scene
            take_to_delete = None
            take_index = -1
            
            # Find the take
            for i in range(len(scene.Takes)):
                take = scene.Takes[i]
                clean_name = strip_prefix(take.Name)
                if clean_name == take_name:
                    take_to_delete = take
                    take_index = i
                    break
            
            if take_to_delete:
                try:
                    pass  # Deleting take
                    
                    # Make sure we're not deleting the current take
                    if system.CurrentTake == take_to_delete and len(scene.Takes) > 1:
                        # Find another take to set as current before deleting
                        for i in range(len(scene.Takes)):
                            if i != take_index:
                                pass  # Setting new current take
                                system.CurrentTake = scene.Takes[i]
                                break
                    
                    # Now use the alternative approach - use the component directly
                    # Get the Takes List component
                    takes_list = None
                    for i in range(take_to_delete.GetDstCount()):
                        dst = take_to_delete.GetDst(i)
                        if isinstance(dst, FBFolder):
                            takes_list = dst
                            break
                    
                    if takes_list:
                        pass  # Found takes list component
                        # Disconnect the take from the takes list
                        take_to_delete.DisconnectDst(takes_list)
                        
                        # Also disconnect from the scene if needed
                        take_to_delete.DisconnectDst(scene)
                        
                        pass  # Take disconnected successfully
                    else:
                        pass  # Could not find takes list component
                        scene.Takes.remove(take_index)
                    
                    # Update our take data
                    if take_name in self.take_data:
                        del self.take_data[take_name]
                    
                    # Save and update
                    self._save_config()
                    self.update_take_list()
                    
                    pass  # Take deletion complete
                except Exception as e:
                    pass  # Error details
                    QMessageBox.warning(self, "Error", f"Failed to delete take: {e}")
    
    def _set_take_tag(self, take_name):
        take_data = self._get_take_data(take_name)
        dialog = TagDialog(take_name, current_tag=take_data.get('tag', ''), current_color=take_data.get('color'), parent=self)
        if dialog.exec() == QDialog.Accepted:
            tag, color = dialog.get_values()
            take_data['tag'] = tag
            take_data['color'] = color
            self._save_config()
            self.update_take_list()
    
    def _add_take_at_end(self):
        """Add a new take at the end of the takes list, with group handling"""
        system = FBSystem()
        
        # Check if the last group is collapsed
        last_group_collapsed = False
        last_group_name = None
        
        # Find the last group in the takes list
        for i in range(len(system.Scene.Takes) - 1, -1, -1):  # Iterate backwards
            take = system.Scene.Takes[i]
            take_name = strip_prefix(take.Name)
            if is_group_take(take.Name):
                last_group_name = take_name
                last_group_collapsed = self.expanded_groups.get(take_name, True) == False
                break
        
        # If the last group is collapsed, create a new group + take
        if last_group_collapsed:
            # Create a new group take
            group_base_name = "Group"
            group_num = 1
            
            # Get all existing take names to avoid duplicates
            all_take_names = [strip_prefix(system.Scene.Takes[i].Name) for i in range(len(system.Scene.Takes))]
            
            # Find an available group name
            while True:
                group_name = f"{group_base_name}{group_num:02d}"
                if group_name not in all_take_names:
                    break
                group_num += 1
            
            try:
                # Create the new group take with == prefix
                full_group_name = f"== {group_name}"
                group_take = FBTake(full_group_name)
                system.Scene.Takes.append(group_take)
                
                # Mark the new group as expanded
                self.expanded_groups[group_name] = True
                
                # Now create a regular take
                take_base_name = "Take"
                take_num = 1
                
                # Find an available take name
                all_take_names = [strip_prefix(system.Scene.Takes[i].Name) for i in range(len(system.Scene.Takes))]
                while True:
                    take_name = f"{take_base_name}{take_num:02d}"
                    if take_name not in all_take_names:
                        break
                    take_num += 1
                
                # Create the regular take
                regular_take = FBTake(take_name)
                system.Scene.Takes.append(regular_take)
                
                # Save the expanded state
                self._save_config()
                
                # Update UI
                self.update_take_list()
                
            except Exception as e:
                pass  # Error adding new take structure
                QMessageBox.warning(self, "Error", f"Failed to add takes: {e}")
            
        else:
            # Just add a single regular take at the end (original behavior)
            # Generate a base take name with incremental number
            base_name = "Take"
            take_num = 1
            
            # Check if the name already exists, and increment if needed
            all_take_names = [strip_prefix(system.Scene.Takes[i].Name) for i in range(len(system.Scene.Takes))]
            
            while True:
                new_name = f"{base_name}{take_num:02d}"  # Format as Take01, Take02, etc.
                if new_name not in all_take_names:
                    break
                take_num += 1
                
            try:
                # Create the new take
                new_take = FBTake(new_name)
                system.Scene.Takes.append(new_take)
                
                # Update the UI
                self.update_take_list()
                
            except Exception as e:
                pass  # Error adding new take
                QMessageBox.warning(self, "Error", f"Failed to add take: {e}")
    
    def _add_take_below(self, take_name):
        """Add a new take after the selected take with an incremental name (Take01, Take02, etc.)"""
        system = FBSystem()
        selected_take_index = -1
        
        # Find the index of the selected take
        for i in range(len(system.Scene.Takes)):
            take = system.Scene.Takes[i]
            if strip_prefix(take.Name) == take_name:
                selected_take_index = i
                break
                
        if selected_take_index == -1:
            return
            
        # Generate a base take name with incremental number
        base_name = "Take"
        take_num = 1
        
        # Check if the name already exists, and increment if needed
        all_take_names = [strip_prefix(system.Scene.Takes[i].Name) for i in range(len(system.Scene.Takes))]
        
        while True:
            new_name = f"{base_name}{take_num:02d}"  # Format as Take01, Take02, etc.
            if new_name not in all_take_names:
                break
            take_num += 1
            
        try:
            # Create the new take
            new_take = FBTake(new_name)
            
            # Add it to the system
            system.Scene.Takes.append(new_take)
            
            # Find the index of the newly added take (it's at the end)
            new_index = len(system.Scene.Takes) - 1
            
            # Get the Takes List from the first take's destination
            first_take = system.Scene.Takes[0]
            takes_list = first_take.GetDst(1)  # This is the Takes List folder
            
            # Reorder it to be after the selected take
            if takes_list and new_index != selected_take_index + 1:
                src_id = new_index
                dst_id = selected_take_index + 1
                takes_list.MoveSrcAt(src_id, dst_id)
                
            # Update the scene
            system.Scene.Evaluate()
            
            self.update_take_list()
            
        except Exception as e:
            pass  # Error adding take below
            QMessageBox.warning(self, "Error", f"Failed to add take: {e}")
    
    def _duplicate_take(self, take_name):
        system = FBSystem()
        original_take = None
        
        # Remember the current take to restore it later
        current_take = system.CurrentTake
        
        # Find the original take
        for i in range(len(system.Scene.Takes)):
            take = system.Scene.Takes[i]
            if strip_prefix(take.Name) == take_name:
                original_take = take
                break
                
        if not original_take:
            return
            
        try:
            # Auto-generate name without popup
            new_name = f"{take_name}_copy"
            
            # Use CopyTake to properly duplicate the take with all animation data
            new_take = original_take.CopyTake(new_name)
            
            # Now find both takes' positions AFTER the duplication
            original_pos = -1
            new_take_pos = -1
            
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                take_clean_name = strip_prefix(take.Name)
                if take == original_take:
                    original_pos = i
                elif take == new_take:
                    new_take_pos = i
                    
            # Only move if we found both takes and the new take isn't already in the right position
            if original_pos >= 0 and new_take_pos >= 0 and new_take_pos != original_pos + 1:
                # Get the Takes List from the first take's destination
                first_take = system.Scene.Takes[0]
                takes_list = first_take.GetDst(1)  # This is the Takes List folder
                
                if takes_list:
                    # Find the source and destination IDs in the takes list
                    src_id = -1
                    for i in range(takes_list.GetSrcCount()):
                        src = takes_list.GetSrc(i)
                        if src == new_take:
                            src_id = i
                            break
                    
                    if src_id >= 0:
                        # Target position is right after the original take
                        target_id = original_pos + 1
                        # Make sure target_id doesn't exceed the list bounds
                        if target_id > takes_list.GetSrcCount():
                            target_id = takes_list.GetSrcCount()
                            
                        takes_list.MoveSrcAt(src_id, target_id)
                        system.Scene.Evaluate()
            
            # Restore the original current take
            if current_take:
                system.CurrentTake = current_take
            
            self.update_take_list()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to duplicate take: {e}")
            # Make sure UI is updated even if there was an error
            self.update_take_list()
    
    def _rename_take_inline(self, take_name, new_name):
        """Rename a take using the inline editor input"""
        if not new_name or new_name == take_name:
            return
            
        system = FBSystem()
        take_to_rename = None
        
        for i in range(len(system.Scene.Takes)):
            take = system.Scene.Takes[i]
            if strip_prefix(take.Name) == take_name:
                take_to_rename = take
                break
                
        if take_to_rename:
            try:
                # Preserve group prefix if needed
                is_group = is_group_take(take_name)
                new_name_with_prefix = new_name.strip()
                if is_group:
                    if take_name.startswith('=='):
                        new_name_with_prefix = f"== {new_name.strip()}"
                    elif take_name.startswith('--'):
                        new_name_with_prefix = f"-- {new_name.strip()}"
                
                if take_name in self.take_data:
                    self.take_data[new_name_with_prefix] = self.take_data[take_name]
                    del self.take_data[take_name]
                
                take_to_rename.Name = new_name_with_prefix
                self._save_config()
                self.update_take_list()
            except Exception as e:
                pass  # Error renaming take
                QMessageBox.warning(self, "Error", f"Failed to rename take: {e}")
                
    def _start_inline_rename(self, take_name):
        """Safely start the inline rename by finding the item from the take name"""
        # Find the item by take name rather than using the direct reference
        for i in range(self.take_list.count()):
            item = self.take_list.item(i)
            if item and item.take_name == take_name and not item.isHidden():
                self.take_list.editItem(item)
                break
    
    def _rename_take(self, take_name):
        """Legacy dialog-based rename method (kept for reference or multi-selection)"""
        system = FBSystem()
        take_to_rename = None
        for i in range(len(system.Scene.Takes)):
            take = system.Scene.Takes[i]
            if strip_prefix(take.Name) == take_name:
                take_to_rename = take
                break
        if take_to_rename:
            new_name, ok = QInputDialog.getText(self, "Rename Take", "Enter new take name:", QLineEdit.Normal, take_name)
            if ok and new_name.strip():
                try:
                    # Preserve group prefix if needed
                    is_group = is_group_take(take_name)
                    new_name_with_prefix = new_name.strip()
                    if is_group:
                        if take_name.startswith('=='):
                            new_name_with_prefix = f"== {new_name.strip()}"
                        elif take_name.startswith('--'):
                            new_name_with_prefix = f"-- {new_name.strip()}"
                    
                    if take_name in self.take_data:
                        self.take_data[new_name_with_prefix] = self.take_data[take_name]
                        del self.take_data[take_name]
                    
                    take_to_rename.Name = new_name_with_prefix
                    self._save_config()
                    # Preserve scroll position using deferred restoration
                    scrollbar = self.take_list.verticalScrollBar()
                    scroll_value = scrollbar.value()
                    self.update_take_list()
                    # Use QTimer to restore scroll position after UI update completes
                    QTimer.singleShot(10, lambda: scrollbar.setValue(scroll_value))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to rename take: {e}")
    
    def update_current_take_only(self):
        """Fast update method that only updates the current take highlighting."""
        system = FBSystem()
        current_take_clean = ""
        if system.CurrentTake:
            current_take_clean = strip_prefix(system.CurrentTake.Name)
            
        # Go through all items and update their display
        for i in range(self.take_list.count()):
            item = self.take_list.item(i)
            if item:
                is_current = (item.take_name == current_take_clean)
                item.update_display(is_current)
                
    def update_take_list(self, preserve_scroll=True):
        """Update the custom UI list using the stripped names for display."""
        selected_row = self.take_list.currentRow()
        if hasattr(self.take_list, 'internal_drop') and self.take_list.internal_drop:
            return
        
        # Save scroll position before clearing
        scroll_value = 0
        if preserve_scroll:
            scrollbar = self.take_list.verticalScrollBar()
            scroll_value = scrollbar.value()
        
        self.take_list.clear()
        system = FBSystem()
        current_take_clean = ""
        if system.CurrentTake:
            current_take_clean = strip_prefix(system.CurrentTake.Name)
        
        # First pass: collect all takes and identify group takes
        all_takes = []
        current_group = None
        for i in range(len(system.Scene.Takes)):
            take = system.Scene.Takes[i]
            take_name_clean = strip_prefix(take.Name)
            take_data = self._get_take_data(take_name_clean)
            
            # If this is a group take, start a new group
            if is_group_take(take_name_clean):
                current_group = take_name_clean
                # Initialize group expanded state if not already set
                if current_group not in self.expanded_groups:
                    self.expanded_groups[current_group] = True  # Default to expanded
            
            # Determine if take should be visible based on its group's state
            visible = True
            if current_group and take_name_clean != current_group:  # Child of a group
                visible = self.expanded_groups.get(current_group, True)
            
            # Create item with additional group info
            item = TakeListItem(
                take_name_clean,
                is_current=(take_name_clean == current_take_clean),
                tag=take_data.get('tag', ''),
                color=take_data.get('color'),
                is_favorite=take_data.get('favorite', False),
                parent_group=current_group if take_name_clean != current_group else None,
                visible=visible
            )
            
            all_takes.append(item)
        
        # Add all takes to the list and ensure visibility is set correctly
        for item in all_takes:
            self.take_list.addItem(item)
            if not item.visible:
                item.setHidden(True)
        
        # Don't restore selection to avoid interfering with the list
        # Selection will be handled by the dropEvent's delayed selection
        
        # Restore scroll position if requested
        if preserve_scroll and scroll_value > 0:
            scrollbar = self.take_list.verticalScrollBar()
            QTimer.singleShot(0, lambda: scrollbar.setValue(scroll_value))
            
    def _on_item_clicked(self, index):
        """Handle clicks on take items, specifically for collapsing/expanding groups."""
        # Get the item from the index row
        item = self.take_list.item(index.row())
        if not item or not item.is_group:
            return
            
        # Check if the click was in the toggle area
        # Get the rect of the item
        rect = self.take_list.visualItemRect(item)
        # Define the toggle area (first 20 pixels)
        toggle_rect = QRect(rect.left(), rect.top(), 20, rect.height())
        
        # Check if the click was in the toggle area
        mouse_pos = self.take_list.mapFromGlobal(QCursor.pos())
        if toggle_rect.contains(mouse_pos):
            # Toggle the expanded state
            group_name = item.take_name
            self.expanded_groups[group_name] = not self.expanded_groups.get(group_name, True)
            
            # Update the visibility of child items
            for i in range(self.take_list.count()):
                child_item = self.take_list.item(i)
                if child_item and child_item.parent_group == group_name:
                    child_item.visible = self.expanded_groups[group_name]
                    child_item.setHidden(not child_item.visible)
            
            # Save the expanded state
            self._save_config()
    
    def on_item_double_click(self, item):
        """Set the current take or toggle group expansion based on double-click."""
        # Debug logging removed
        
        if not item:
            return
            
        # If this is a group item, toggle its expanded state
        if item.is_group:
            group_name = item.take_name
            self.expanded_groups[group_name] = not self.expanded_groups.get(group_name, True)
            
            # Update the visibility of child items
            for i in range(self.take_list.count()):
                child_item = self.take_list.item(i)
                if child_item and child_item.parent_group == group_name:
                    child_item.visible = self.expanded_groups[group_name]
                    child_item.setHidden(not child_item.visible)
            
            # Save the expanded state
            self._save_config()
        else:
            # For non-group takes, set as current take (original behavior)
            selected_take_clean = item.take_name
            system = FBSystem()
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                if strip_prefix(take.Name) == selected_take_clean:
                    system.CurrentTake = take
                    # Force deselection by setting current item to None after update
                    def deselect_after_update():
                        self.take_list.setCurrentItem(None)
                        self.take_list.clearSelection()
                    
                    # Schedule deselection after update completes
                    QTimer.singleShot(100, deselect_after_update)
                    # Use the fast update method to preserve scrollbar position
                    self.update_current_take_only()
                    break
    
    def closeEvent(self, event):
        self._save_config()
        save_window_settings(self)
        event.accept()

class TakeListDelegate(QStyledItemDelegate):
    """Custom delegate for drawing list items."""
    def __init__(self, window=None, parent=None):
        super(TakeListDelegate, self).__init__(parent)
        self.window = window  # Store a reference to the window for accessing expanded_groups
    
    def paint(self, painter, option, index):
        color = index.data(Qt.UserRole)
        is_favorite = index.data(Qt.UserRole + 1)
        has_tag = index.data(Qt.UserRole + 2)
        is_group = index.data(Qt.UserRole + 3)
        
        # Get the take item to check if it's the current take
        item = self.window.take_list.item(index.row())
        is_current = False
        if item:
            current_take = self.window.system.CurrentTake
            current_take_name = ''
            if current_take:
                current_take_name = strip_prefix(current_take.Name)
            is_current = (item.take_name == current_take_name)
        
        painter.save()
        
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        
        offset = 0
        
        # Draw minimalistic expand/collapse indicator for group takes
        if is_group:
            expanded = self.window.expanded_groups.get(item.take_name, True)
            
            # Save original font
            original_font = painter.font()
            
            # Set text color to white
            if option.state & QStyle.State_Selected:
                painter.setPen(option.palette.highlightedText().color())
            else:
                painter.setPen(Qt.white)
            
            # Use small arrow symbols as indicators, positioned at the left edge with no padding
            indicator_rect = QRect(option.rect.left() + 0, option.rect.top(), 16, option.rect.height())
            
            if expanded:
                # Down arrow for expanded - make it smaller
                smaller_font = QFont(original_font)
                smaller_font.setPointSizeF(original_font.pointSizeF() * 0.6)  # Make down arrow 60% of normal size
                painter.setFont(smaller_font)
                painter.drawText(indicator_rect, Qt.AlignCenter, "▼")
            else:
                # Right arrow for collapsed - keep current size
                painter.drawText(indicator_rect, Qt.AlignCenter, "▶")
            
            # Restore original font for text
            painter.setFont(original_font)
            
            offset = 18  # Space for the indicator
        
        # Draw color tag for non-group items only - now on the far right
        right_margin = 16  # Fixed right margin for text
        
        # Draw the tag color box (if applicable)
        if has_tag and color and not is_group:
            # Position the color box at the far right edge
            tag_rect = QRect(option.rect.right() - 10, option.rect.top() + 2, 8, option.rect.height() - 4)
            painter.fillRect(tag_rect, QBrush(color))
            painter.setPen(Qt.black)
            painter.drawRect(tag_rect)
        
        # Adjust text rect to account for controls on both sides
        text_rect = option.rect.adjusted(offset, 0, -right_margin, 0)
        text = index.data(Qt.DisplayRole)
        
        # Set text color - prioritize current take (yellow) over other coloring
        if is_current:
            # Current take gets yellow text
            painter.setPen(QColor(255, 255, 0))  # Bright yellow
        elif option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            if is_group:
                # Use tag color for group take text if it has a tag, otherwise use dark gray
                if has_tag and color:
                    painter.setPen(color)
                else:
                    painter.setPen(QColor(80, 80, 80))  # Dark gray for group takes without tags
            else:
                painter.setPen(option.palette.text().color())
        
        painter.drawText(text_rect, Qt.AlignVCenter, text)
        
        # Draw star on top of everything else
        if is_favorite:
            painter.setPen(QColor(255, 215, 0))
            star_rect = QRect(option.rect.right() - 15, option.rect.top(), 15, option.rect.height())
            painter.drawText(star_rect, Qt.AlignCenter, "★")
        
        painter.restore()

def show_take_handler():
    """Show the Take Handler window."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    # Get the MotionBuilder main window as parent
    mb_parent = get_motionbuilder_main_window()
    window = TakeHandlerWindow(parent=mb_parent)
    window.setMinimumSize(100, 100)  # Ensure minimal usable size
    load_window_settings(window)
    window.show()
    delegate = TakeListDelegate(window=window)
    window.take_list.setItemDelegate(delegate)
    return window

# Global reference
take_handler_window = None

def main():
    global take_handler_window
    take_handler_window = show_take_handler()

main()