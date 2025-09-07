import os
import sys
import json
import re
from pyfbsdk import *
from pyfbsdk_additions import *
import PySide6
from PySide6.QtWidgets import (QApplication, QMainWindow, QListWidget, QListWidgetItem, 
                               QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QMenu, 
                               QDialog, QLabel, QLineEdit, QInputDialog, QTextEdit,
                               QMessageBox, QStyledItemDelegate, QStyle, QSizePolicy,
                               QSizeGrip, QGroupBox, QCheckBox, QGridLayout, QButtonGroup,
                               QColorDialog)
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
    base_dir = os.path.expanduser("~/Documents/MB/CustomPythonSaveData/TakesManager")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    return os.path.join(base_dir, "window_settings.json")

def get_global_settings_path():
    """Get the global settings path for script settings"""
    base_dir = os.path.expanduser("~/Documents/MB/CustomPythonSaveData")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    return os.path.join(base_dir, "PythonScriptGlobalSettings.json")

def load_global_settings():
    """Load global script settings"""
    settings_path = get_global_settings_path()
    default_settings = {
        "naming_convention": {
            "first_capital_letter": False,
            "no_capital_letters": False,
            "no_spaces": False,
            "direction_style": "none"  # "none", "short", "full", "mixed", "single"
        },
        "accessibility": {
            "current_take_color": "yellow"
        }
    }
    
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return default_settings

def save_global_settings(settings):
    """Save global script settings"""
    settings_path = get_global_settings_path()
    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
    except IOError:
        pass

def apply_naming_convention(take_name, settings=None):
    """Apply naming convention rules to a take name"""
    if settings is None:
        settings = load_global_settings()
    
    # Skip naming convention for group takes
    if is_group_take(take_name):
        return take_name
    
    naming = settings.get("naming_convention", {})
    result = take_name
    
    # Check if this is an unfinished take (ends with " [X]")
    is_unfinished = result.endswith(" [X]")
    unfinished_marker = ""
    
    if is_unfinished:
        # Temporarily remove the unfinished marker for processing
        unfinished_marker = " [X]"
        result = result[:-4]
    
    # Apply direction replacements first
    direction_style = naming.get("direction_style", "none")
    if direction_style != "none":
        result = apply_direction_replacements(result, direction_style, naming)
    
    # Apply no spaces rule
    if naming.get("no_spaces", False):
        result = result.replace(" ", "_")
    
    # Apply capitalization rules
    if naming.get("first_capital_letter", False):
        result = apply_first_capital_letter(result)
    elif naming.get("no_capital_letters", False):
        result = result.lower()
    
    # Re-add the unfinished marker with preserved space
    if is_unfinished:
        result += unfinished_marker
    
    return result

def apply_direction_replacements(text, style, naming_settings):
    """Apply direction word replacements based on style"""
    # Define all variations to catch
    variations = {
        "right": ["rgt", "right", "r"],
        "left": ["lft", "left", "l"], 
        "forward": ["fwd", "forward", "forwd", "forwrd", "f"],
        "backward": ["bwd", "backward", "backwd", "backwrd", "b"]
    }
    
    # Define base replacement mappings based on style
    base_replacements = {}
    if style == "short":  # Rgt, Lft, Fwd, Bwd
        base_replacements = {"right": "Rgt", "left": "Lft", "forward": "Fwd", "backward": "Bwd"}
    elif style == "full":  # Right, Left, Forward, Backward
        base_replacements = {"right": "Right", "left": "Left", "forward": "Forward", "backward": "Backward"}
    elif style == "mixed":  # Right, Left, Fwd, Bwd
        base_replacements = {"right": "Right", "left": "Left", "forward": "Fwd", "backward": "Bwd"}
    elif style == "single":  # r, l, f, b
        base_replacements = {"right": "r", "left": "l", "forward": "f", "backward": "b"}
    
    # Apply capitalization rules to the replacements
    replacements = {}
    for direction, target in base_replacements.items():
        if naming_settings.get("no_capital_letters", False):
            replacements[direction] = target.lower()
        elif naming_settings.get("first_capital_letter", False):
            replacements[direction] = target.capitalize()
        else:
            replacements[direction] = target
    
    result = text
    
    # Define custom word boundaries (space, dot, comma, underscore, dash, start/end of string)
    boundary_chars = r'[ \.,_\-]'
    
    # Build a comprehensive pattern that matches all variations at once
    # This prevents overlapping replacements where replaced text gets processed again
    all_patterns = []
    variation_to_target = {}
    
    for direction, target in replacements.items():
        for variation in variations[direction]:
            # Store the mapping for replacement
            variation_to_target[variation.lower()] = target
            # Add to the comprehensive pattern
            all_patterns.append(re.escape(variation))
    
    if all_patterns:
        # Simple approach: replace each direction word one by one, longest first
        # Sort by length (longest first) to prevent shorter matches from interfering
        all_patterns.sort(key=len, reverse=True)
        
        # Process each pattern individually to avoid overlapping issues
        for pattern in all_patterns:
            target = variation_to_target.get(pattern.lower(), pattern)
            # Use word boundaries and custom boundary chars
            pattern_regex = r'(?<![a-zA-Z])' + re.escape(pattern) + r'(?![a-zA-Z])'
            
            # Replace all instances of this pattern
            result = re.sub(pattern_regex, target, result, flags=re.IGNORECASE)
    
    return result

def apply_first_capital_letter(text):
    """Capitalize first letter of each word after space or underscore"""
    result = ""
    capitalize_next = True
    
    for char in text:
        if char in [" ", "_"]:
            result += char
            capitalize_next = True
        elif capitalize_next and char.isalpha():
            result += char.upper()
            capitalize_next = False
        else:
            result += char
            capitalize_next = False
    
    return result

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

class NotesDialog(QDialog):
    """Dialog for creating/editing take notes."""
    def __init__(self, take_name, current_note="", parent=None):
        super(NotesDialog, self).__init__(parent)
        self.setWindowTitle(f"Note for {take_name}")
        self.setFixedSize(400, 200)
        self.setModal(True)
        
        # Set dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: white;
            }
            QLabel {
                color: white;
            }
            QTextEdit {
                background-color: #3C3C50;
                color: white;
                border: 1px solid #3A539B;
                padding: 5px;
            }
            QPushButton {
                background-color: #3A539B;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #4A649B;
            }
            QPushButton:pressed {
                background-color: #2A439B;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Note text area
        layout.addWidget(QLabel("Note text:"))
        self.note_edit = QTextEdit()
        self.note_edit.setPlainText(current_note)
        layout.addWidget(self.note_edit)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        ok_button = QPushButton("Create" if not current_note else "Update")
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        # Focus on text area
        self.note_edit.setFocus()
    
    def get_values(self):
        """Return the note text."""
        return self.note_edit.toPlainText().strip()

class TakeListItem(QListWidgetItem):
    """Custom list item for takes."""
    def __init__(self, take_name, is_current=False, tag="", color=None, is_favorite=False, parent_group=None, visible=True, note="", note_color=None):
        super(TakeListItem, self).__init__()
        self.take_name = take_name  # This is the stripped (original) name.
        self.tag = tag
        self.color = color or QColor(200, 200, 200)
        self.is_favorite = is_favorite
        self.is_group = is_group_take(take_name)
        self.parent_group = parent_group  # Name of the parent group take
        self.visible = visible  # Whether this take should be visible based on group collapse
        self.note = note
        self.note_color = note_color or QColor(255, 255, 255)
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
        self.setData(Qt.UserRole + 4, bool(self.note))  # Has note
        self.setData(Qt.UserRole + 5, self.note_color)  # Note color
        self.setData(Qt.UserRole + 6, self.note)  # Note text for tooltip
        
        # Set tooltip if there's a note
        if self.note:
            self.setToolTip(self.note)
        else:
            self.setToolTip("")
            
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
        if not item:
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

class NamingToast(QWidget):
    """Toast notification widget for naming convention changes"""
    
    def __init__(self, parent, original_name, processed_name):
        super(NamingToast, self).__init__(parent)
        self.parent_window = parent
        self.original_name = original_name
        self.processed_name = processed_name
        
        # Set window flags for overlay behavior
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Create the toast content
        self.setup_ui()
        
        # Auto-hide timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_toast)
        
    def setup_ui(self):
        """Set up the toast UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create the message with character-level highlighting
        message_widget = self.create_highlighted_message()
        layout.addWidget(message_widget)
        
        # Style the toast with better visibility
        self.setStyleSheet("""
            NamingToast {
                background-color: rgba(35, 35, 35, 255);
                border: 2px solid #777;
                border-radius: 8px;
            }
            QLabel {
                background-color: rgba(50, 50, 50, 255);
                padding: 4px 8px;
                border-radius: 4px;
            }
        """)
        
        # Size to content
        self.adjustSize()
    
    def create_highlighted_message(self):
        """Create a widget with the highlighted before/after message"""
        from PySide6.QtWidgets import QLabel
        
        # Generate character-level differences
        char_changes = self.get_character_differences()
        
        # Build HTML with orange highlighting for changed characters
        html_parts = []
        
        # Add "Renamed: " prefix
        html_parts.append('<span style="color: #dcdcdc;">Renamed: \'</span>')
        
        # Add original name (normal color)
        html_parts.append(f'<span style="color: #dcdcdc;">{self.original_name}</span>')
        
        # Add arrow
        html_parts.append('<span style="color: #dcdcdc;"> → </span>')
        
        # Add processed name with highlighting
        for char, is_changed in char_changes:
            if is_changed:
                html_parts.append(f'<span style="color: orange; font-weight: bold;">{char}</span>')
            else:
                html_parts.append(f'<span style="color: #dcdcdc;">{char}</span>')
        
        # Close quote
        html_parts.append('<span style="color: #dcdcdc;">\'</span>')
        
        html_content = ''.join(html_parts)
        
        label = QLabel()
        label.setText(html_content)
        # Style will be applied by the main stylesheet
        
        return label
    
    def get_character_differences(self):
        """Get list of (character, is_changed) tuples for highlighting"""
        char_changes = []
        
        # Compare character by character
        max_len = max(len(self.original_name), len(self.processed_name))
        for i in range(max_len):
            orig_char = self.original_name[i] if i < len(self.original_name) else ""
            proc_char = self.processed_name[i] if i < len(self.processed_name) else ""
            
            if proc_char:  # Only add if processed character exists
                is_changed = (orig_char != proc_char)
                char_changes.append((proc_char, is_changed))
        
        return char_changes
    
    def show(self):
        """Show the toast positioned next to the + button at the bottom"""
        if not self.parent_window:
            return
        
        # Position at the very left edge over the + button
        if hasattr(self.parent_window, 'new_take_button'):
            button = self.parent_window.new_take_button
            # Get button position in global coordinates
            button_pos = button.mapToGlobal(button.rect().topLeft())
            # Position toast at the very left edge of window, at button level
            parent_left = self.parent_window.mapToGlobal(self.parent_window.rect().topLeft()).x()
            self.move(parent_left, button_pos.y() - 5)
        else:
            # Fallback: position at bottom left of parent window
            parent_pos = self.parent_window.mapToGlobal(self.parent_window.rect().bottomLeft())
            self.move(parent_pos.x(), parent_pos.y() - 50)
        
        # Show the toast
        super().show()
        
        # Start the hide timer (3 seconds for toast)
        self.hide_timer.start(3000)
    
    def hide_toast(self):
        """Hide and clean up the toast"""
        self.hide()
        self.deleteLater()

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
        
        # Create a small settings button with cog icon
        self.settings_button = QPushButton("⚙️")
        self.settings_button.setToolTip("Take Handler Settings")
        self.settings_button.setFixedSize(18, 18)  # Same size as other buttons
        self.settings_button.setStyleSheet("""
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
        self.settings_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.settings_button.clicked.connect(self._open_settings)
        
        button_layout.addWidget(self.settings_button)
        
        # Add small spacing between settings and sort button
        button_layout.addSpacing(3)
        
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
        base_dir = os.path.expanduser("~/Documents/MB/CustomPythonSaveData/TakesManager")
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
                        if 'color' in data and isinstance(data['color'], dict):
                            color_dict = data['color']
                            data['color'] = QColor(color_dict['r'], color_dict['g'], color_dict['b'])
                        if 'note_color' in data and isinstance(data['note_color'], dict):
                            note_color_dict = data['note_color']
                            data['note_color'] = QColor(note_color_dict['r'], note_color_dict['g'], note_color_dict['b'])
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
            if 'note_color' in data and isinstance(data['note_color'], QColor):
                save_data[take_name]['note_color'] = {
                    'r': data['note_color'].red(),
                    'g': data['note_color'].green(),
                    'b': data['note_color'].blue()
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
    
    def _get_next_group_color(self):
        """Generate a muted, pleasant color for a new group with maximum distinction between adjacent colors."""
        # Define a palette ordered for maximum visual distinction between adjacent colors
        muted_colors = [
            QColor(150, 200, 170),  # Muted green (start with green)
            QColor(200, 150, 180),  # Muted pink (opposite hue)
            QColor(150, 180, 200),  # Muted blue (cool)
            QColor(200, 170, 150),  # Muted orange/brown (warm)
            QColor(180, 150, 200),  # Muted purple (violet)
            QColor(200, 200, 150),  # Muted beige/yellow (light)
            QColor(150, 200, 200),  # Muted cyan (blue-green)
            QColor(200, 180, 150),  # Muted yellow/tan (yellow-orange)
            QColor(170, 170, 200),  # Muted lavender (purple-blue)
            QColor(180, 200, 150),  # Muted lime (yellow-green)
        ]
        
        # Count existing groups with assigned colors to determine which color to use next
        group_count = 0
        for take_name, data in self.take_data.items():
            if data.get('is_group', False) and data.get('color'):
                group_count += 1
        
        # Cycle through colors
        color_index = group_count % len(muted_colors)
        return muted_colors[color_index]
    
    def show_naming_toast(self, original_name, processed_name):
        """Show a toast notification for naming convention changes"""
        if original_name == processed_name:
            return  # No change, no toast needed
        
        # Create and show toast with character-level highlighting
        toast = NamingToast(self, original_name, processed_name)
        toast.show()
    
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
    
    def _sort_group_takes(self, group_name):
        """Sort takes within a specific group alphabetically."""
        system = FBSystem()
        
        # Remember the current take to restore it later
        current_take = system.CurrentTake
        
        try:
            # Get all takes and analyze group structure
            all_scene_takes = []
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                take_name = strip_prefix(take.Name)
                all_scene_takes.append((take, take_name, i))
            
            # Analyze groups to find the target group
            groups = self._analyze_take_groups(all_scene_takes)
            target_group = None
            
            for group in groups:
                if group['header'] and group['header'][1] == group_name:
                    target_group = group
                    break
            
            if not target_group or not target_group['members']:
                return  # Nothing to sort
            
            # Get only the takes that belong to this group for sorting
            takes_to_sort = target_group['members'][:]
            
            # Generate sorting operations using the same logic as main sort
            sorted_operations = self._get_group_aware_sort_operations(groups, takes_to_sort)
            
            # Execute the sorting operations using the same method as main sort
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
            
            # Update the UI
            self.update_take_list()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to sort group takes: {e}")
            self.update_take_list()
    
    def _open_settings(self):
        """Open the Take Handler Settings dialog"""
        settings_dialog = TakeHandlerSettings(self)
        settings_dialog.exec_()
    
    def _create_new_take(self):
        name, ok = QInputDialog.getText(self, "New Take", "Enter take name:")
        if ok and name.strip():
            try:
                system = FBSystem()
                # Apply naming convention to the new take name
                original_name = name.strip()
                processed_name = apply_naming_convention(original_name)
                new_take = FBTake(processed_name)
                system.Scene.Takes.append(new_take)
                
                # Show toast if the name was changed by naming convention
                if original_name != processed_name:
                    QTimer.singleShot(250, lambda o=original_name, p=processed_name: self.show_naming_toast(o, p))
                
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
            # For group takes, assign auto-color, for regular takes use default gray
            if is_group_take(take_name):
                self.take_data[take_name] = {
                    'tag': '',
                    'color': self._get_next_group_color(),
                    'favorite': False,
                    'is_group': True
                }
            else:
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
            
            # Check if any selected takes are unfinished
            unfinished_takes = [item for item in selected_items if item.take_name.endswith(" [X]")]
            finished_takes = [item for item in selected_items if not item.take_name.endswith(" [X]")]
            
            if unfinished_takes and finished_takes:
                mark_unfinished_action = menu.addAction(f"Mark All {len(selected_items)} as Unfinished")
                unmark_unfinished_action = menu.addAction(f"Remove Unfinished Mark from All")
            elif unfinished_takes:
                unmark_unfinished_action = menu.addAction(f"Remove Unfinished Mark from {len(selected_items)} Takes")
                mark_unfinished_action = None
            else:
                mark_unfinished_action = menu.addAction(f"Mark {len(selected_items)} as Unfinished")
                unmark_unfinished_action = None
            
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
            elif action == mark_unfinished_action:
                self._toggle_unfinished_marker_for_multiple(selected_items, mark_as_unfinished=True)
            elif action == unmark_unfinished_action:
                self._toggle_unfinished_marker_for_multiple(selected_items, mark_as_unfinished=False)
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
        
        # Notes menu
        menu.addSeparator()
        if take_data.get('note', ''):
            edit_note_action = menu.addAction("Edit Note")
            delete_note_action = menu.addAction("Delete Note")
        else:
            create_note_action = menu.addAction("Create Note")
            edit_note_action = None
            delete_note_action = None
        
        menu.addSeparator()
        duplicate_action = menu.addAction("Duplicate Take")
        add_take_below_action = menu.addAction("Add new Take below")
        rename_action = menu.addAction("Rename Take")
        menu.addSeparator()
        create_group_action = menu.addAction("Create Group for Take")
        
        # Add "Sort Group Takes" option if this is a group take
        if is_group_take(take_name):
            sort_group_action = menu.addAction("Sort Group Takes")
            menu.addSeparator()
        else:
            sort_group_action = None
            menu.addSeparator()
        
        # Mark as Unfinished option (just before delete)
        if take_name.endswith(" [X]"):
            mark_unfinished_action = menu.addAction("Remove Unfinished Mark")
        else:
            mark_unfinished_action = menu.addAction("Mark as Unfinished")
        
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
        elif action and hasattr(action, 'text') and action.text() == "Create Note":
            self._create_note(take_name)
        elif action and hasattr(action, 'text') and action.text() == "Edit Note":
            self._edit_note(take_name)
        elif action and hasattr(action, 'text') and action.text() == "Delete Note":
            self._delete_note(take_name)
        elif action == duplicate_action:
            self._duplicate_take(take_name)
        elif action == add_take_below_action:
            self._add_take_below(take_name)
        elif action == rename_action:
            # Store the take name instead of the item reference which might be deleted
            self._start_inline_rename(take_name)
        elif action == create_group_action:
            self._create_group_for_selected([item])
        elif action == sort_group_action and is_group_take(take_name):
            self._sort_group_takes(take_name)
        elif action == mark_unfinished_action:
            self._toggle_unfinished_marker(take_name)
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
            
            # Mark this as a group in our data and assign a color
            self.take_data[group_name] = {
                'is_group': True,
                'color': self._get_next_group_color()
            }
            
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
                # Apply naming convention to the copy name
                processed_name = apply_naming_convention(new_name)
                try:
                    # Use CopyTake to properly duplicate the take with all animation data
                    new_take = original_take.CopyTake(processed_name)
                    duplicate_pairs.append((original_take, new_take))
                    
                    # Show toast if the name was changed by naming convention
                    if new_name != processed_name:
                        QTimer.singleShot(300, lambda o=new_name, p=processed_name: self.show_naming_toast(o, p))
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
                    
                    # Apply naming convention to the new name
                    processed_name = apply_naming_convention(new_name)
                    take_to_rename.Name = processed_name
                    
                    # Highlight the take if the name was changed by naming convention (with delay for UI update)
                    if new_name != processed_name:
                        QTimer.singleShot(100, lambda o=new_name, p=processed_name: self.show_naming_toast(o, p))
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
    
    def _toggle_unfinished_marker_for_multiple(self, items, mark_as_unfinished=True):
        """Toggle the [X] unfinished marker for multiple takes."""
        system = FBSystem()
        
        for item in items:
            take_name = item.take_name
            target_take = None
            
            # Find the take
            for i in range(len(system.Scene.Takes)):
                take = system.Scene.Takes[i]
                if strip_prefix(take.Name) == take_name:
                    target_take = take
                    break
            
            if not target_take:
                continue
                
            try:
                # Determine new name based on action requested
                if mark_as_unfinished:
                    # Add unfinished marker if not already present
                    if not take_name.endswith(" [X]"):
                        new_name = f"{take_name} [X]"
                    else:
                        new_name = take_name  # Already marked, no change
                else:
                    # Remove unfinished marker if present
                    if take_name.endswith(" [X]"):
                        new_name = take_name[:-4]  # Remove " [X]"
                    else:
                        new_name = take_name  # Not marked, no change
                
                # Only update if name actually changed
                if new_name != take_name:
                    # Transfer take data if it exists
                    if take_name in self.take_data:
                        self.take_data[new_name] = self.take_data[take_name]
                        del self.take_data[take_name]
                    
                    # Update the take name in MotionBuilder
                    # Apply naming convention to the new name
                    processed_name = apply_naming_convention(new_name)
                    target_take.Name = processed_name
                    
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to toggle unfinished marker for take {take_name}: {e}")
        
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
    
    def _create_note(self, take_name):
        """Create a new note for a take."""
        dialog = NotesDialog(take_name, parent=self)
        if dialog.exec() == QDialog.Accepted:
            note_text = dialog.get_values()
            if note_text:  # Only save if there's actual text
                take_data = self._get_take_data(take_name)
                take_data['note'] = note_text
                self._save_config()
                self.update_take_list()
    
    def _edit_note(self, take_name):
        """Edit an existing note for a take."""
        take_data = self._get_take_data(take_name)
        current_note = take_data.get('note', '')
        
        dialog = NotesDialog(take_name, current_note, parent=self)
        if dialog.exec() == QDialog.Accepted:
            note_text = dialog.get_values()
            if note_text:  # Only save if there's actual text
                take_data['note'] = note_text
            else:
                # Remove note if text is empty
                if 'note' in take_data:
                    del take_data['note']
            self._save_config()
            self.update_take_list()
    
    def _delete_note(self, take_name):
        """Delete a note from a take."""
        take_data = self._get_take_data(take_name)
        if 'note' in take_data:
            del take_data['note']
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
            if takes_list:
                # Find the new take in the takes list (it's at the end)
                new_take_src_id = -1
                for i in range(takes_list.GetSrcCount()):
                    src = takes_list.GetSrc(i)
                    if src == new_take:
                        new_take_src_id = i
                        break
                
                if new_take_src_id >= 0:
                    # Place it right after the selected take
                    target_position = selected_take_index + 1
                    takes_list.MoveSrcAt(new_take_src_id, target_position)
                
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
            # Apply naming convention to the copy name
            processed_name = apply_naming_convention(new_name)
            
            # Use CopyTake to properly duplicate the take with all animation data
            new_take = original_take.CopyTake(processed_name)
            
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
                # Use the exact name as provided by user - no automatic prefixes
                new_name_with_prefix = new_name.strip()
                
                # Check if this is becoming a group take
                is_becoming_group = is_group_take(new_name_with_prefix)
                was_group = is_group_take(take_name)
                
                if take_name in self.take_data:
                    # Copy existing data
                    self.take_data[new_name_with_prefix] = self.take_data[take_name].copy()
                    del self.take_data[take_name]
                else:
                    # Create new data entry
                    self.take_data[new_name_with_prefix] = {}
                
                # If becoming a group take, ensure it has group properties
                if is_becoming_group and not was_group:
                    self.take_data[new_name_with_prefix]['is_group'] = True
                    # Always assign color for new groups
                    assigned_color = self._get_next_group_color()
                    self.take_data[new_name_with_prefix]['color'] = assigned_color
                
                # Apply naming convention to the new name
                processed_name = apply_naming_convention(new_name_with_prefix)
                take_to_rename.Name = processed_name
                
                # Show toast if the name was changed by naming convention (with delay for UI update)
                if new_name_with_prefix != processed_name:
                    QTimer.singleShot(200, lambda o=new_name_with_prefix, p=processed_name: self.show_naming_toast(o, p))
                
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
                    
                    # Apply naming convention to the new name
                    processed_name = apply_naming_convention(new_name)
                    take_to_rename.Name = processed_name
                    self._save_config()
                    # Preserve scroll position using deferred restoration
                    scrollbar = self.take_list.verticalScrollBar()
                    scroll_value = scrollbar.value()
                    self.update_take_list()
                    # Use QTimer to restore scroll position after UI update completes
                    QTimer.singleShot(10, lambda: scrollbar.setValue(scroll_value))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to rename take: {e}")
    
    def _toggle_unfinished_marker(self, take_name):
        """Toggle the [X] unfinished marker on a take name."""
        system = FBSystem()
        target_take = None
        
        # Find the take
        for i in range(len(system.Scene.Takes)):
            take = system.Scene.Takes[i]
            if strip_prefix(take.Name) == take_name:
                target_take = take
                break
        
        if not target_take:
            return
            
        try:
            # Check if take is currently marked as unfinished
            if take_name.endswith(" [X]"):
                # Remove unfinished marker
                new_name = take_name[:-4]  # Remove " [X]"
            else:
                # Add unfinished marker
                new_name = f"{take_name} [X]"
            
            # Transfer take data if it exists
            if take_name in self.take_data:
                self.take_data[new_name] = self.take_data[take_name]
                del self.take_data[take_name]
            
            # Update the take name in MotionBuilder
            # Apply naming convention to the new name
            processed_name = apply_naming_convention(new_name)
            target_take.Name = processed_name
            
            # Update the UI
            self.update_take_list()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to toggle unfinished marker: {e}")
    
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
                visible=visible,
                note=take_data.get('note', ''),
                note_color=take_data.get('note_color', QColor(255, 255, 255))
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
            # Check if Shift or Ctrl is pressed for all-groups toggle
            modifiers = QApplication.keyboardModifiers()
            shift_pressed = modifiers & Qt.ShiftModifier
            ctrl_pressed = modifiers & Qt.ControlModifier
            all_groups_toggle = shift_pressed or ctrl_pressed
            
            group_name = item.take_name
            
            if all_groups_toggle:
                # Shift+click: toggle ALL groups based on this group's current state
                current_state = self.expanded_groups.get(group_name, True)
                new_state = not current_state
                
                # Apply to all groups
                for i in range(self.take_list.count()):
                    list_item = self.take_list.item(i)
                    if list_item and getattr(list_item, 'is_group', False):
                        group_item_name = list_item.take_name
                        self.expanded_groups[group_item_name] = new_state
                        
                        # Update visibility of child items for this group
                        for j in range(self.take_list.count()):
                            child_item = self.take_list.item(j)
                            if child_item and getattr(child_item, 'parent_group', None) == group_item_name:
                                child_item.visible = new_state
                                child_item.setHidden(not new_state)
            else:
                # Normal click: toggle just this group
                self.expanded_groups[group_name] = not self.expanded_groups.get(group_name, True)
                
                # Update the visibility of child items for this group only
                for i in range(self.take_list.count()):
                    child_item = self.take_list.item(i)
                    if child_item and getattr(child_item, 'parent_group', None) == group_name:
                        child_item.visible = self.expanded_groups[group_name]
                        child_item.setHidden(not child_item.visible)
            
            # Deselect everything after all-groups toggle to avoid selection artifacts
            if all_groups_toggle:
                self.take_list.clearSelection()
            
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
        has_note = index.data(Qt.UserRole + 4)
        note_color = index.data(Qt.UserRole + 5)
        
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
        
        # Set text color - prioritize current take over other coloring
        if is_current:
            # Current take gets color from settings
            settings = load_global_settings()
            current_take_color = settings.get("accessibility", {}).get("current_take_color", "yellow")
            painter.setPen(QColor(current_take_color))
        elif text.endswith(" [X]"):
            # Unfinished takes get red tint (20% red, 80% normal)
            base_color = option.palette.text().color()
            red_tinted = QColor(
                int(base_color.red() * 0.8 + 255 * 0.2),
                int(base_color.green() * 0.8),
                int(base_color.blue() * 0.8)
            )
            painter.setPen(red_tinted)
        elif option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            if is_group:
                # Use tag color if available, otherwise use auto-assigned group color, fallback to dark gray
                if color:  # Color can be from tag or auto-assigned
                    painter.setPen(color)
                else:
                    painter.setPen(QColor(80, 80, 80))  # Dark gray fallback
            else:
                painter.setPen(option.palette.text().color())
        
        # Draw normal text
        painter.drawText(text_rect, Qt.AlignVCenter, text)
        
        # Draw note icon and star on top of everything else
        right_offset = 0
        
        # Draw note icon first (rightmost)
        if has_note:
            painter.setPen(QColor(255, 255, 255))  # White note icon
            note_rect = QRect(option.rect.right() - 15 - right_offset, option.rect.top(), 15, option.rect.height())
            painter.drawText(note_rect, Qt.AlignCenter, "📝")  # Note emoji
            right_offset += 15
        
        # Draw star (next to note if it exists)
        if is_favorite:
            painter.setPen(QColor(255, 215, 0))
            star_rect = QRect(option.rect.right() - 15 - right_offset, option.rect.top(), 15, option.rect.height())
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

class TakeHandlerSettings(QDialog):
    """Settings dialog for Take Handler with expandable sections"""
    
    def __init__(self, parent=None):
        super(TakeHandlerSettings, self).__init__(parent)
        self.setWindowTitle("Take Handler Settings")
        self.setMinimumSize(400, 300)
        
        # Track expansion states
        self.take_naming_expanded = True  # Expanded by default
        self.tags_expanded = False
        self.accessibility_expanded = False
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        """Set up the settings dialog UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        
        # Create the expandable sections
        self.create_take_naming_group(main_layout)
        self.create_tags_group(main_layout)
        self.create_accessibility_group(main_layout)
        
        # Add stretch to push everything to the top
        main_layout.addStretch()
        
        # Add Apply/Cancel buttons (centered)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        apply_button = QPushButton("Apply")
        apply_button.setDefault(True)
        apply_button.clicked.connect(self.apply_settings)
        button_layout.addWidget(apply_button)
        
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
    
    def create_take_naming_group(self, parent_layout):
        """Create the Take Naming Convention expandable group"""
        # Create collapsible group (collapsed by default)
        group_box = QGroupBox("► Take Naming Convention")
        group_box.setStyleSheet(self.get_collapsible_group_style())
        group_box.mousePressEvent = lambda event: self.on_take_naming_clicked()
        
        self.take_naming_group = group_box
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(5, 15, 5, 5)
        
        # Content container (hidden by default)
        self.take_naming_container = QWidget()
        container_layout = QGridLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(5)
        
        # Naming Convention Checkboxes
        self.first_capital_cb = QCheckBox("First Capital Letter")
        self.no_capitals_cb = QCheckBox("No Capital Letters")
        self.no_spaces_cb = QCheckBox("No Spaces")
        
        # Direction checkboxes
        self.rgt_lft_cb = QCheckBox("Rgt, Lft, Fwd, Bwd")
        self.right_left_cb = QCheckBox("Right, Left, Forward, Backward")
        self.right_left_fwd_cb = QCheckBox("Right, Left, Fwd, Bwd")
        self.single_letter_cb = QCheckBox("r, l, f, b")
        
        # Set up tooltips with examples
        self.setup_tooltips()
        
        # Add to grid layout - 2 columns for checkboxes
        container_layout.addWidget(self.first_capital_cb, 0, 0)
        container_layout.addWidget(self.no_capitals_cb, 0, 1)
        container_layout.addWidget(self.no_spaces_cb, 1, 0)
        container_layout.addWidget(self.rgt_lft_cb, 2, 0)
        container_layout.addWidget(self.right_left_cb, 2, 1)
        container_layout.addWidget(self.right_left_fwd_cb, 3, 0)
        container_layout.addWidget(self.single_letter_cb, 3, 1)
        
        # Set up button groups for mutually exclusive checkboxes
        self.capital_group = QButtonGroup()
        self.capital_group.addButton(self.first_capital_cb)
        self.capital_group.addButton(self.no_capitals_cb)
        self.capital_group.setExclusive(False)  # We'll handle exclusivity manually
        
        self.direction_group = QButtonGroup()
        self.direction_group.addButton(self.rgt_lft_cb)
        self.direction_group.addButton(self.right_left_cb)
        self.direction_group.addButton(self.right_left_fwd_cb)
        self.direction_group.addButton(self.single_letter_cb)
        self.direction_group.setExclusive(False)  # We'll handle exclusivity manually
        
        # Connect signals for mutual exclusivity
        self.first_capital_cb.toggled.connect(self.on_first_capital_toggled)
        self.no_capitals_cb.toggled.connect(self.on_no_capitals_toggled)
        
        self.rgt_lft_cb.toggled.connect(lambda checked: self.on_direction_toggled(checked, "short"))
        self.right_left_cb.toggled.connect(lambda checked: self.on_direction_toggled(checked, "full"))
        self.right_left_fwd_cb.toggled.connect(lambda checked: self.on_direction_toggled(checked, "mixed"))
        self.single_letter_cb.toggled.connect(lambda checked: self.on_direction_toggled(checked, "single"))
        
        self.take_naming_container.setLayout(container_layout)
        
        group_layout.addWidget(self.take_naming_container)
        group_box.setLayout(group_layout)
        
        # Set initial state (expanded by default)
        if self.take_naming_expanded:
            self.take_naming_container.setVisible(True)
            group_box.setFixedHeight(160)  # Expanded height
            group_box.setTitle("▼ Take Naming Convention")
        else:
            self.take_naming_container.setVisible(False)
            group_box.setFixedHeight(30)  # Collapsed height
            group_box.setTitle("► Take Naming Convention")
        
        parent_layout.addWidget(group_box)
    
    def create_tags_group(self, parent_layout):
        """Create the Tags expandable group"""
        # Create collapsible group (collapsed by default)
        group_box = QGroupBox("► Tags")
        group_box.setStyleSheet(self.get_collapsible_group_style())
        group_box.mousePressEvent = lambda event: self.on_tags_clicked()
        
        self.tags_group = group_box
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(5, 15, 5, 5)
        
        # Content container (hidden by default)
        self.tags_container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(3)
        
        # Tags list area
        self.tags_list_widget = QWidget()
        self.tags_list_layout = QVBoxLayout()
        self.tags_list_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_list_layout.setSpacing(2)
        self.tags_list_widget.setLayout(self.tags_list_layout)
        
        container_layout.addWidget(self.tags_list_widget)
        
        # Create Tag button at bottom
        create_tag_button = QPushButton("Create Tag")
        create_tag_button.clicked.connect(self.create_new_tag)
        container_layout.addWidget(create_tag_button)
        
        self.tags_container.setLayout(container_layout)
        self.tags_container.setVisible(False)  # Hidden by default
        
        group_layout.addWidget(self.tags_container)
        group_box.setLayout(group_layout)
        group_box.setFixedHeight(30)  # Collapsed height
        
        parent_layout.addWidget(group_box)
        
        # Populate existing tags
        self.populate_existing_tags()
    
    def get_collapsible_group_style(self):
        """Get the CSS style for collapsible groups (matching Controlify exactly)"""
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
    
    def populate_existing_tags(self):
        """Populate the tags list with existing tags"""
        # Get existing tags from the parent take handler
        if hasattr(self.parent(), '_get_existing_tags'):
            existing_tags = self.parent()._get_existing_tags()
            
            # Clear existing widgets
            while self.tags_list_layout.count():
                child = self.tags_list_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # Add each tag with edit button
            for tag_name in existing_tags:
                self.add_tag_to_list(tag_name)
    
    def add_tag_to_list(self, tag_name):
        """Add a tag to the list with edit button"""
        tag_widget = QWidget()
        tag_layout = QHBoxLayout()
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(5)
        
        # Tag name label
        tag_label = QLabel(tag_name)
        tag_layout.addWidget(tag_label)
        
        tag_layout.addStretch()
        
        # Edit button
        edit_button = QPushButton("Edit")
        edit_button.setFixedSize(40, 20)
        edit_button.clicked.connect(lambda: self.edit_tag(tag_name))
        tag_layout.addWidget(edit_button)
        
        tag_widget.setLayout(tag_layout)
        self.tags_list_layout.addWidget(tag_widget)
    
    def create_new_tag(self):
        """Create a new tag using the TagDialog"""
        dialog = TagDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            tag_name, tag_color = dialog.get_values()
            if tag_name:
                # Refresh the tags list
                self.populate_existing_tags()
                QMessageBox.information(self, "Tag Created", f"Tag '{tag_name}' has been created.")
    
    def edit_tag(self, tag_name):
        """Edit an existing tag using the TagDialog"""
        # Find the existing tag's color from the parent's take data
        existing_color = None
        if hasattr(self.parent(), 'take_data'):
            for data in self.parent().take_data.values():
                if data.get('tag') == tag_name:
                    existing_color = data.get('color')
                    break
        
        dialog = TagDialog(self, existing_tag=tag_name, existing_color=existing_color)
        if dialog.exec_() == QDialog.Accepted:
            new_tag_name, new_tag_color = dialog.get_values()
            if new_tag_name and new_tag_name != tag_name:
                # Update all takes with the old tag to use the new tag name
                if hasattr(self.parent(), 'take_data'):
                    for data in self.parent().take_data.values():
                        if data.get('tag') == tag_name:
                            data['tag'] = new_tag_name
                            data['color'] = new_tag_color
                    # Save changes and refresh
                    self.parent()._save_config()
                    self.parent().update_take_list()
                    self.populate_existing_tags()
                    QMessageBox.information(self, "Tag Updated", f"Tag '{tag_name}' has been updated to '{new_tag_name}'.")
            elif new_tag_name == tag_name:
                # Just color change
                if hasattr(self.parent(), 'take_data'):
                    for data in self.parent().take_data.values():
                        if data.get('tag') == tag_name:
                            data['color'] = new_tag_color
                    self.parent()._save_config()
                    self.parent().update_take_list()
                    QMessageBox.information(self, "Tag Updated", f"Tag '{tag_name}' color has been updated.")
    
    def create_accessibility_group(self, parent_layout):
        """Create the Accessibility expandable group"""
        # Create collapsible group (collapsed by default)
        group_box = QGroupBox("► Accessibility")
        group_box.setStyleSheet(self.get_collapsible_group_style())
        group_box.mousePressEvent = lambda event: self.on_accessibility_clicked()
        
        self.accessibility_group = group_box
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(5, 15, 5, 5)
        
        # Content container (hidden by default)
        self.accessibility_container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(5)
        
        # Current take color setting
        color_layout = QHBoxLayout()
        color_label = QLabel("Current take color:")
        color_layout.addWidget(color_label)
        
        # Color picker button - start with default yellow
        self.current_take_color_button = QPushButton()
        self.current_take_color_button.setFixedSize(30, 20)
        self.current_take_color_button.setStyleSheet("background-color: yellow; border: 1px solid #666;")
        self.current_take_color_button.clicked.connect(self.choose_current_take_color)
        color_layout.addWidget(self.current_take_color_button)
        
        color_layout.addStretch()
        container_layout.addLayout(color_layout)
        
        self.accessibility_container.setLayout(container_layout)
        self.accessibility_container.setVisible(False)  # Hidden by default
        
        group_layout.addWidget(self.accessibility_container)
        group_box.setLayout(group_layout)
        group_box.setFixedHeight(30)  # Collapsed height
        
        parent_layout.addWidget(group_box)
    
    def on_accessibility_clicked(self):
        """Toggle Accessibility group visibility"""
        if self.accessibility_expanded:
            # Collapse
            self.accessibility_container.setVisible(False)
            self.accessibility_group.setFixedHeight(30)
            self.accessibility_group.setTitle("► Accessibility")
            self.accessibility_expanded = False
        else:
            # Expand
            self.accessibility_container.setVisible(True)
            self.accessibility_group.setFixedHeight(70)  # Height for color picker
            self.accessibility_group.setTitle("▼ Accessibility")
            self.accessibility_expanded = True
        
        # Adjust dialog size
        QTimer.singleShot(10, self.adjustSize)
    
    def choose_current_take_color(self):
        """Open color picker for current take color"""
        
        # Get current color from button
        current_style = self.current_take_color_button.styleSheet()
        current_color = QColor("yellow")  # Default fallback
        
        # Try to extract color from stylesheet
        if "background-color:" in current_style:
            color_str = current_style.split("background-color:")[1].split(";")[0].strip()
            current_color = QColor(color_str)
        
        # Open color dialog
        color = QColorDialog.getColor(current_color, self, "Choose Current Take Color")
        if color.isValid():
            # Update button color
            color_name = color.name()
            self.current_take_color_button.setStyleSheet(f"background-color: {color_name}; border: 1px solid #666;")
    
    def on_take_naming_clicked(self):
        """Toggle Take Naming Convention group visibility"""
        if self.take_naming_expanded:
            # Collapse
            self.take_naming_container.setVisible(False)
            self.take_naming_group.setFixedHeight(30)
            self.take_naming_group.setTitle("► Take Naming Convention")
            self.take_naming_expanded = False
        else:
            # Expand
            self.take_naming_container.setVisible(True)
            self.take_naming_group.setFixedHeight(160)  # Height for 4 rows of content
            self.take_naming_group.setTitle("▼ Take Naming Convention")
            self.take_naming_expanded = True
        
        # Adjust dialog size
        QTimer.singleShot(10, self.adjustSize)
    
    def on_tags_clicked(self):
        """Toggle Tags group visibility"""
        if self.tags_expanded:
            # Collapse
            self.tags_container.setVisible(False)
            self.tags_group.setFixedHeight(30)
            self.tags_group.setTitle("► Tags")
            self.tags_expanded = False
        else:
            # Expand
            self.tags_container.setVisible(True)
            # Calculate height based on number of tags + create button
            tag_count = self.tags_list_layout.count()
            height = 60 + (tag_count * 25)  # Base height + tag rows
            self.tags_group.setFixedHeight(height)
            self.tags_group.setTitle("▼ Tags")
            self.tags_expanded = True
        
        # Adjust dialog size
        QTimer.singleShot(10, self.adjustSize)
    
    def setup_tooltips(self):
        """Set up tooltips for checkboxes with before/after examples"""
        example_name = "take_right_left_Forward_Backward"
        
        # First Capital Letter tooltip
        first_cap_result = "Take_right_left_Forward_Backward"
        first_cap_tooltip = self.create_tooltip_html(example_name, first_cap_result, [(0, 4)])  # "take" -> "Take"
        self.first_capital_cb.setToolTip(first_cap_tooltip)
        
        # No Capital Letters tooltip
        no_caps_result = "take_right_left_forward_backward"
        no_caps_tooltip = self.create_tooltip_html(example_name, no_caps_result, [(13, 20), (26, 34)])  # "Forward" -> "forward", "Backward" -> "backward"
        self.no_capitals_cb.setToolTip(no_caps_tooltip)
        
        # No Spaces tooltip
        no_spaces_result = "take_right_left_Forward_Backward"
        no_spaces_tooltip = self.create_tooltip_html(example_name, no_spaces_result, [])  # No changes for this example
        self.no_spaces_cb.setToolTip(no_spaces_tooltip)
        
        # Direction tooltips
        rgt_lft_result = "take_Rgt_Lft_Fwd_Bwd"
        rgt_lft_tooltip = self.create_tooltip_html(example_name, rgt_lft_result, [(5, 10), (11, 15), (16, 23), (24, 32)])  # All direction words
        self.rgt_lft_cb.setToolTip(rgt_lft_tooltip)
        
        right_left_result = "take_Right_Left_Forward_Backward"
        right_left_tooltip = self.create_tooltip_html(example_name, right_left_result, [(5, 10), (11, 15)])  # "right" -> "Right", "left" -> "Left"
        self.right_left_cb.setToolTip(right_left_tooltip)
        
        right_left_fwd_result = "take_Right_Left_Fwd_Bwd"
        right_left_fwd_tooltip = self.create_tooltip_html(example_name, right_left_fwd_result, [(5, 10), (11, 15), (16, 23), (24, 32)])  # All direction words
        self.right_left_fwd_cb.setToolTip(right_left_fwd_tooltip)
        
        single_letter_result = "take_r_l_f_b"
        single_letter_tooltip = self.create_tooltip_html(example_name, single_letter_result, [(5, 10), (11, 15), (16, 23), (24, 32)])  # All direction words
        self.single_letter_cb.setToolTip(single_letter_tooltip)
    
    def create_tooltip_html(self, original, result, highlight_ranges):
        """Create HTML tooltip with highlighted differences"""
        # Start with the result string
        highlighted_result = result
        
        # Apply highlighting in reverse order to avoid position shifts
        for start, end in reversed(highlight_ranges):
            if start < len(highlighted_result) and end <= len(highlighted_result):
                before = highlighted_result[:start]
                highlight = highlighted_result[start:end]
                after = highlighted_result[end:]
                highlighted_result = f"{before}<span style='background-color: yellow; color: black;'>{highlight}</span>{after}"
        
        return f"""
        <div style='font-family: monospace; font-size: 12px;'>
            <b>Before:</b> {original}<br>
            <b>After:</b> {highlighted_result}
        </div>
        """
    
    def load_settings(self):
        """Load settings from global settings file"""
        settings = load_global_settings()
        naming = settings.get("naming_convention", {})
        
        # Load checkbox states
        self.first_capital_cb.setChecked(naming.get("first_capital_letter", False))
        self.no_capitals_cb.setChecked(naming.get("no_capital_letters", False))
        self.no_spaces_cb.setChecked(naming.get("no_spaces", False))
        
        # Load direction style
        direction_style = naming.get("direction_style", "none")
        if direction_style == "short":
            self.rgt_lft_cb.setChecked(True)
        elif direction_style == "full":
            self.right_left_cb.setChecked(True)
        elif direction_style == "mixed":
            self.right_left_fwd_cb.setChecked(True)
        elif direction_style == "single":
            self.single_letter_cb.setChecked(True)
        
        # Load accessibility settings
        accessibility = settings.get("accessibility", {})
        current_take_color = accessibility.get("current_take_color", "yellow")
        if hasattr(self, 'current_take_color_button'):
            self.current_take_color_button.setStyleSheet(f"background-color: {current_take_color}; border: 1px solid #666;")
    
    def on_first_capital_toggled(self, checked):
        """Handle First Capital Letter checkbox toggle"""
        if checked and self.no_capitals_cb.isChecked():
            self.no_capitals_cb.setChecked(False)
    
    def on_no_capitals_toggled(self, checked):
        """Handle No Capital Letters checkbox toggle"""
        if checked and self.first_capital_cb.isChecked():
            self.first_capital_cb.setChecked(False)
    
    def on_direction_toggled(self, checked, style):
        """Handle direction checkbox toggle (mutual exclusivity)"""
        if checked:
            # Uncheck all other direction checkboxes
            if style != "short":
                self.rgt_lft_cb.setChecked(False)
            if style != "full":
                self.right_left_cb.setChecked(False)
            if style != "mixed":
                self.right_left_fwd_cb.setChecked(False)
            if style != "single":
                self.single_letter_cb.setChecked(False)
            
            # Set the current one back to checked
            if style == "short":
                self.rgt_lft_cb.setChecked(True)
            elif style == "full":
                self.right_left_cb.setChecked(True)
            elif style == "mixed":
                self.right_left_fwd_cb.setChecked(True)
            elif style == "single":
                self.single_letter_cb.setChecked(True)
    
    def get_current_settings(self):
        """Get current settings from the dialog"""
        direction_style = "none"
        if self.rgt_lft_cb.isChecked():
            direction_style = "short"
        elif self.right_left_cb.isChecked():
            direction_style = "full"
        elif self.right_left_fwd_cb.isChecked():
            direction_style = "mixed"
        elif self.single_letter_cb.isChecked():
            direction_style = "single"
        
        # Get current take color from button
        current_take_color = "yellow"  # Default
        if hasattr(self, 'current_take_color_button'):
            style = self.current_take_color_button.styleSheet()
            if "background-color:" in style:
                color_str = style.split("background-color:")[1].split(";")[0].strip()
                current_take_color = color_str
        
        return {
            "naming_convention": {
                "first_capital_letter": self.first_capital_cb.isChecked(),
                "no_capital_letters": self.no_capitals_cb.isChecked(),
                "no_spaces": self.no_spaces_cb.isChecked(),
                "direction_style": direction_style
            },
            "accessibility": {
                "current_take_color": current_take_color
            }
        }
    
    def settings_have_changed(self):
        """Check if settings have changed from what's saved"""
        current = self.get_current_settings()
        saved = load_global_settings()
        return current != saved
    
    def naming_convention_changed(self):
        """Check if only naming convention settings have changed"""
        current = self.get_current_settings()
        saved = load_global_settings()
        return current.get("naming_convention") != saved.get("naming_convention")
    
    def apply_settings(self):
        """Apply the settings"""
        if not self.settings_have_changed():
            self.accept()
            return
        
        # Check if naming convention changed - only show prompt for naming convention
        if self.naming_convention_changed():
            # Show application choice dialog for naming convention
            choice_dialog = QMessageBox(self)
            choice_dialog.setWindowTitle("Apply Settings")
            choice_dialog.setText("How would you like to apply these naming convention settings?")
            choice_dialog.setIcon(QMessageBox.Question)
            
            future_btn = choice_dialog.addButton("Apply for future takes", QMessageBox.AcceptRole)
            retroactive_btn = choice_dialog.addButton("Apply retroactively for all takes", QMessageBox.ApplyRole)
            cancel_btn = choice_dialog.addButton("Cancel", QMessageBox.RejectRole)
            
            choice_dialog.setDefaultButton(future_btn)
            choice_dialog.exec_()
            
            clicked_button = choice_dialog.clickedButton()
            
            if clicked_button == cancel_btn:
                return
            
            # Save the new settings
            new_settings = self.get_current_settings()
            save_global_settings(new_settings)
            
            if clicked_button == retroactive_btn:
                self.apply_retroactively()
        else:
            # Only non-naming convention settings changed, apply immediately
            new_settings = self.get_current_settings()
            save_global_settings(new_settings)
        
        self.accept()
    
    def apply_retroactively(self):
        """Apply naming convention to all existing takes"""
        try:
            system = FBSystem()
            renamed_takes = []
            current_settings = self.get_current_settings()
            
            # Go through all takes and check if they need renaming
            for take in system.Scene.Takes:
                original_name = take.Name
                # Remove numerical prefix for processing
                clean_name = strip_prefix(original_name)
                new_name = apply_naming_convention(clean_name, current_settings)
                
                # Add back the prefix if it existed
                if original_name != clean_name:
                    prefix = original_name[:len(original_name) - len(clean_name)]
                    new_name = prefix + new_name
                
                if original_name != new_name:
                    # Apply naming convention to the new name
                    processed_name = apply_naming_convention(new_name)
                    take.Name = processed_name
                    renamed_takes.append((original_name, processed_name))
            
            # Show results if any takes were renamed
            if renamed_takes:
                self.show_rename_results(renamed_takes)
            else:
                QMessageBox.information(self, "No Changes", "All takes already follow the naming convention.")
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply naming convention: {str(e)}")
    
    def show_rename_results(self, renamed_takes):
        """Show a dialog with all the renamed takes"""
        results_dialog = QDialog(self)
        results_dialog.setWindowTitle("Takes Renamed")
        results_dialog.setMinimumSize(500, 300)
        
        layout = QVBoxLayout(results_dialog)
        
        label = QLabel(f"Renamed {len(renamed_takes)} takes:")
        layout.addWidget(label)
        
        # Create text widget to show all changes
        text_widget = QTextEdit()
        text_widget.setReadOnly(True)
        
        text_content = ""
        for old_name, new_name in renamed_takes:
            text_content += f"{old_name} → {new_name}\n"
        
        text_widget.setPlainText(text_content)
        layout.addWidget(text_widget)
        
        # OK button
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(results_dialog.accept)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        results_dialog.exec_()


# Global reference
take_handler_window = None

def main():
    global take_handler_window
    take_handler_window = show_take_handler()

main()