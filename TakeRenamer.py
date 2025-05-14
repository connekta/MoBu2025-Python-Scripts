from pyfbsdk import *
from pyfbsdk_additions import *
import PySide6
from PySide6 import QtWidgets, QtCore, QtGui
import sys
import re
import json
import os

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

class TakeRenamerUI(QtWidgets.QDialog):
    def __init__(self, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(TakeRenamerUI, self).__init__(parent)
        
        self.setWindowTitle("Take Renamer")
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)
        
        # Initialize history for undo/redo
        self.history = []
        self.history_index = -1
        self.max_history = 20
        
        # Settings
        self.settings_file = os.path.join(os.path.expanduser("~"), "motionbuilder_take_renamer_settings.json")
        self.settings = self.load_settings()
        
        try:
            self.create_ui()
            self.populate_takes()
            
            # Save initial state for undo/redo
            self.capture_initial_state()
        except Exception as e:
            print(f"Error initializing UI: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def create_ui(self):
        # Main layout
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)
        
        # Splitter for resizable sections
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        main_layout.addWidget(splitter)
        
        # Top widget - Take list
        top_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_widget)
        splitter.addWidget(top_widget)
        
        # Filter and list controls
        filter_layout = QtWidgets.QHBoxLayout()
        filter_label = QtWidgets.QLabel("Filter:")
        self.filter_input = QtWidgets.QLineEdit()
        self.filter_input.setPlaceholderText("Type to filter takes...")
        self.filter_input.textChanged.connect(self.filter_takes)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_input)
        top_layout.addLayout(filter_layout)
        
        # Takes label
        takes_label = QtWidgets.QLabel("Takes in Scene:")
        top_layout.addWidget(takes_label)
        
        # Take list with selection counter
        self.takes_list = QtWidgets.QListWidget()
        self.takes_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.takes_list.setAlternatingRowColors(True)
        self.takes_list.itemSelectionChanged.connect(self.update_selection_info)
        top_layout.addWidget(self.takes_list)
        
        # Selection info layout
        self.selection_info = QtWidgets.QLabel("0 takes selected")
        top_layout.addWidget(self.selection_info)
        
        # Bottom widget - Rename controls
        bottom_widget = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_widget)
        splitter.addWidget(bottom_widget)
        
        # Tab widget for different renaming options
        tab_widget = QtWidgets.QTabWidget()
        bottom_layout.addWidget(tab_widget)
        
        # Make tabs match background
        tab_widget.setDocumentMode(True)
        
        # Tab 1: Simple rename
        simple_tab = QtWidgets.QWidget()
        simple_layout = QtWidgets.QVBoxLayout(simple_tab)
        
        simple_rename_layout = QtWidgets.QHBoxLayout()
        simple_rename_label = QtWidgets.QLabel("New Name:")
        self.rename_input = QtWidgets.QLineEdit()
        self.rename_input.setPlaceholderText("Enter new name")
        
        # Add preview button
        preview_button = QtWidgets.QPushButton("Preview")
        preview_button.clicked.connect(lambda: self.preview_rename("simple"))
        
        simple_rename_button = QtWidgets.QPushButton("Rename")
        simple_rename_button.clicked.connect(self.rename_takes)
        
        simple_rename_layout.addWidget(simple_rename_label)
        simple_rename_layout.addWidget(self.rename_input)
        simple_rename_layout.addWidget(preview_button)
        simple_rename_layout.addWidget(simple_rename_button)
        simple_layout.addLayout(simple_rename_layout)
        
        # Add numbering options
        numbering_group = QtWidgets.QGroupBox("Numbering Options")
        numbering_layout = QtWidgets.QGridLayout()
        
        self.use_numbering = QtWidgets.QCheckBox("Add Numbering")
        self.use_numbering.setChecked(False)
        
        start_at_label = QtWidgets.QLabel("Start at:")
        self.start_number = QtWidgets.QSpinBox()
        self.start_number.setRange(0, 9999)
        self.start_number.setValue(1)
        
        padding_label = QtWidgets.QLabel("Padding:")
        self.padding_digits = QtWidgets.QSpinBox()
        self.padding_digits.setRange(1, 6)
        self.padding_digits.setValue(2)
        
        separator_label = QtWidgets.QLabel("Separator:")
        self.number_separator = QtWidgets.QLineEdit("_")
        
        numbering_layout.addWidget(self.use_numbering, 0, 0, 1, 2)
        numbering_layout.addWidget(start_at_label, 1, 0)
        numbering_layout.addWidget(self.start_number, 1, 1)
        numbering_layout.addWidget(padding_label, 2, 0)
        numbering_layout.addWidget(self.padding_digits, 2, 1)
        numbering_layout.addWidget(separator_label, 3, 0)
        numbering_layout.addWidget(self.number_separator, 3, 1)
        
        numbering_group.setLayout(numbering_layout)
        simple_layout.addWidget(numbering_group)
        simple_layout.addStretch()
        
        tab_widget.addTab(simple_tab, "Simple Rename")
        
        # Tab 2: Find and Replace
        replace_tab = QtWidgets.QWidget()
        replace_layout = QtWidgets.QVBoxLayout(replace_tab)
        
        find_replace_layout = QtWidgets.QGridLayout()
        find_label = QtWidgets.QLabel("Find:")
        self.find_input = QtWidgets.QLineEdit()
        self.find_input.setPlaceholderText("Text to find")
        replace_label = QtWidgets.QLabel("Replace:")
        self.replace_input = QtWidgets.QLineEdit()
        self.replace_input.setPlaceholderText("Replace with")
        
        # Add regex option
        self.use_regex = QtWidgets.QCheckBox("Use Regular Expressions")
        self.use_regex.setToolTip("Enable regular expression pattern matching")
        
        # Add case sensitivity option
        self.case_sensitive = QtWidgets.QCheckBox("Case Sensitive")
        self.case_sensitive.setChecked(False)
        
        # Add option to search all takes
        self.search_all_takes = QtWidgets.QCheckBox("Search All Takes")
        self.search_all_takes.setChecked(True)
        self.search_all_takes.setToolTip("When checked, finds and replaces in all takes, not just selected ones")
        
        # Add capitalize button
        capitalize_button = QtWidgets.QPushButton("Capitalize Words")
        capitalize_button.setToolTip("Capitalize the first letter of each word")
        capitalize_button.clicked.connect(self.capitalize_words)
        
        # Add preview and replace buttons
        preview_replace_button = QtWidgets.QPushButton("Preview")
        preview_replace_button.clicked.connect(lambda: self.preview_rename("replace"))
        
        find_replace_button = QtWidgets.QPushButton("Replace")
        find_replace_button.clicked.connect(self.find_and_replace)
        
        find_replace_layout.addWidget(find_label, 0, 0)
        find_replace_layout.addWidget(self.find_input, 0, 1, 1, 2)
        find_replace_layout.addWidget(replace_label, 1, 0)
        find_replace_layout.addWidget(self.replace_input, 1, 1, 1, 2)
        find_replace_layout.addWidget(self.use_regex, 2, 0)
        find_replace_layout.addWidget(self.case_sensitive, 2, 1)
        find_replace_layout.addWidget(self.search_all_takes, 3, 0, 1, 2)
        
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(preview_replace_button)
        button_layout.addWidget(find_replace_button)
        button_layout.addWidget(capitalize_button)
        
        replace_layout.addLayout(find_replace_layout)
        replace_layout.addLayout(button_layout)
        replace_layout.addStretch()
        
        tab_widget.addTab(replace_tab, "Find and Replace")
        
        # Tab 3: Prefix/Suffix
        affix_tab = QtWidgets.QWidget()
        affix_layout = QtWidgets.QVBoxLayout(affix_tab)
        
        affix_form_layout = QtWidgets.QFormLayout()
        
        prefix_label = QtWidgets.QLabel("Prefix:")
        self.prefix_input = QtWidgets.QLineEdit()
        
        suffix_label = QtWidgets.QLabel("Suffix:")
        self.suffix_input = QtWidgets.QLineEdit()
        
        # Setup placeholder text color for prefix/suffix inputs
        self.prefix_input.setPlaceholderText("Text to add before name")
        self.suffix_input.setPlaceholderText("Text to add after name")
        
        # Use stylesheet to set placeholder text color to white
        placeholder_style = "QLineEdit { color: white; } QLineEdit::placeholder { color: white; opacity: 0.7; }"
        self.prefix_input.setStyleSheet(placeholder_style)
        self.suffix_input.setStyleSheet(placeholder_style)
        
        # Add preview and add buttons
        preview_affix_button = QtWidgets.QPushButton("Preview")
        preview_affix_button.clicked.connect(lambda: self.preview_rename("affix"))
        
        affix_button = QtWidgets.QPushButton("Add")
        affix_button.clicked.connect(self.add_affix)
        
        affix_form_layout.addRow(prefix_label, self.prefix_input)
        affix_form_layout.addRow(suffix_label, self.suffix_input)
        
        affix_button_layout = QtWidgets.QHBoxLayout()
        affix_button_layout.addWidget(preview_affix_button)
        affix_button_layout.addWidget(affix_button)
        
        affix_layout.addLayout(affix_form_layout)
        affix_layout.addLayout(affix_button_layout)
        affix_layout.addStretch()
        
        tab_widget.addTab(affix_tab, "Prefix/Suffix")
        
        # Preview area
        preview_group = QtWidgets.QGroupBox("Preview")
        preview_layout = QtWidgets.QVBoxLayout()
        self.preview_list = QtWidgets.QTableWidget()
        self.preview_list.setColumnCount(2)
        self.preview_list.setHorizontalHeaderLabels(["Original Name", "New Name"])
        self.preview_list.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.preview_list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.preview_list.setAlternatingRowColors(True)
        
        preview_layout.addWidget(self.preview_list)
        preview_group.setLayout(preview_layout)
        bottom_layout.addWidget(preview_group)
        
        # Buttons at the bottom
        button_layout = QtWidgets.QHBoxLayout()
        
        # Undo/Redo buttons
        self.undo_button = QtWidgets.QPushButton("Undo")
        self.undo_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowBack))
        self.undo_button.clicked.connect(self.undo)
        self.undo_button.setEnabled(False)
        
        self.redo_button = QtWidgets.QPushButton("Redo")
        self.redo_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowForward))
        self.redo_button.clicked.connect(self.redo)
        self.redo_button.setEnabled(False)
        
        refresh_button = QtWidgets.QPushButton("Refresh List")
        refresh_button.clicked.connect(self.populate_takes)
        
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.close)
        
        button_layout.addWidget(self.undo_button)
        button_layout.addWidget(self.redo_button)
        button_layout.addWidget(refresh_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        main_layout.addLayout(button_layout)
        
        # Set tab order for keyboard navigation
        self.setTabOrder(self.filter_input, self.takes_list)
        self.setTabOrder(self.takes_list, self.rename_input)
        
        # Set initial state for splitter
        splitter.setSizes([300, 300])
    
    def get_selected_takes(self):
        """Get the selected takes from the list"""
        selected_takes = []
        system = FBSystem()
        scene = system.Scene
        
        # Get selected takes from list widget
        selected_items = self.takes_list.selectedItems()
        if not selected_items:
            return []
        
        # Get the names of the selected takes
        selected_names = [item.text() for item in selected_items]
        
        # Iterate through all takes and find those with matching names
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            if take.Name in selected_names:
                selected_takes.append(take)
        
        return selected_takes
    
    def populate_takes(self):
        """Populate the list widget with all takes in the scene"""
        self.takes_list.clear()
        
        # Get the FBSystem
        system = FBSystem()
        scene = system.Scene
        
        # Get all takes in the scene
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            
            # Get additional metadata for tooltip
            duration = take.LocalTimeSpan.GetStop().GetSecondDouble() - take.LocalTimeSpan.GetStart().GetSecondDouble()
            
            item = QtWidgets.QListWidgetItem(take.Name)
            item.setData(QtCore.Qt.UserRole, take.Name)  # Store original name
            
            # Add tool tip with additional information
            tooltip = f"Name: {take.Name}\nDuration: {duration:.2f} seconds"
            item.setToolTip(tooltip)
            
            self.takes_list.addItem(item)
        
        # Filter takes based on filter text
        filter_text = self.filter_input.text().lower()
        if filter_text:
            for i in range(self.takes_list.count()-1, -1, -1):
                item = self.takes_list.item(i)
                if filter_text not in item.text().lower():
                    self.takes_list.takeItem(i)
        
        # Update selection info
        self.update_selection_info()
    
    def filter_takes(self):
        """Filter takes based on filter text"""
        self.populate_takes()
    
    def update_selection_info(self):
        """Update the selection info label"""
        selected_count = len(self.takes_list.selectedItems())
        total_count = self.takes_list.count()
        self.selection_info.setText(f"{selected_count} of {total_count} takes selected")
    
    def rename_takes(self):
        """Rename the selected takes with the new name"""
        new_name = self.rename_input.text().strip()
        if not new_name:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a new name.")
            return
        
        takes = self.get_selected_takes()
        if not takes:
            QtWidgets.QMessageBox.warning(self, "Warning", "No takes selected.")
            return
        
        # Ensure we have an initial state
        if len(self.history) == 0:
            self.capture_initial_state()
        
        # Save current state for undo before making changes
        self.save_state()
        
        # If only one take is selected, rename it directly
        if len(takes) == 1 and not self.use_numbering.isChecked():
            takes[0].Name = new_name
        # If multiple takes are selected, add numbering
        else:
            start_num = self.start_number.value()
            padding = self.padding_digits.value()
            separator = self.number_separator.text()
            
            for i, take in enumerate(takes):
                num = i + start_num
                if self.use_numbering.isChecked():
                    take.Name = f"{new_name}{separator}{str(num).zfill(padding)}"
                else:
                    take.Name = new_name
        
        # Refresh the list
        self.populate_takes()
        
        # Save the new state
        new_state = {}
        system = FBSystem()
        scene = system.Scene
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            new_state[i] = take.Name
            
        # Add the new state to history (only if different from last state)
        if len(self.history) == 0 or new_state != self.history[-1]:
            self.history.append(new_state)
            self.history_index = len(self.history) - 1
            print(f"Added rename state to history. Now at index {self.history_index} of {len(self.history)-1}")
        
        self.update_undo_redo_buttons()
    
    def find_and_replace(self):
        """Find and replace text in the selected take names"""
        find_text = self.find_input.text()
        replace_text = self.replace_input.text()
        
        # Determine which takes to process
        if self.search_all_takes.isChecked():
            system = FBSystem()
            scene = system.Scene
            takes = []
            take_count = len(scene.Takes)
            for i in range(take_count):
                takes.append(scene.Takes[i])
        else:
            takes = self.get_selected_takes()
            
        if not takes:
            QtWidgets.QMessageBox.warning(self, "Warning", "No takes selected.")
            return
        
        # Ensure we have an initial state
        if len(self.history) == 0:
            self.capture_initial_state()
        
        # Save current state for undo
        self.save_state()
        
        use_regex = self.use_regex.isChecked()
        case_sensitive = self.case_sensitive.isChecked()
        
        for take in takes:
            if use_regex:
                try:
                    if case_sensitive:
                        new_name = re.sub(find_text, replace_text, take.Name)
                    else:
                        new_name = re.sub(find_text, replace_text, take.Name, flags=re.IGNORECASE)
                except re.error as e:
                    QtWidgets.QMessageBox.warning(self, "RegEx Error", f"Invalid regular expression: {str(e)}")
                    return
            else:
                if case_sensitive:
                    new_name = take.Name.replace(find_text, replace_text)
                else:
                    new_name = re.sub(re.escape(find_text), replace_text, take.Name, flags=re.IGNORECASE)
            
            take.Name = new_name
        
        # Refresh the list
        self.populate_takes()
        
        # Save the new state
        new_state = {}
        system = FBSystem()
        scene = system.Scene
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            new_state[i] = take.Name
            
        # Add the new state to history (only if different from last state)
        if len(self.history) == 0 or new_state != self.history[-1]:
            self.history.append(new_state)
            self.history_index = len(self.history) - 1
            print(f"Added find/replace state to history. Now at index {self.history_index} of {len(self.history)-1}")
        
        self.update_undo_redo_buttons()
    
    def add_affix(self):
        """Add prefix and/or suffix to the selected take names"""
        prefix = self.prefix_input.text()
        suffix = self.suffix_input.text()
        
        takes = self.get_selected_takes()
        if not takes:
            QtWidgets.QMessageBox.warning(self, "Warning", "No takes selected.")
            return
        
        # Ensure we have an initial state
        if len(self.history) == 0:
            self.capture_initial_state()
        
        # Save current state for undo
        self.save_state()
        
        for take in takes:
            new_name = prefix + take.Name + suffix
            take.Name = new_name
        
        # Refresh the list
        self.populate_takes()
        
        # Save the new state
        new_state = {}
        system = FBSystem()
        scene = system.Scene
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            new_state[i] = take.Name
            
        # Add the new state to history (only if different from last state)
        if len(self.history) == 0 or new_state != self.history[-1]:
            self.history.append(new_state)
            self.history_index = len(self.history) - 1
            print(f"Added affix state to history. Now at index {self.history_index} of {len(self.history)-1}")
        
        self.update_undo_redo_buttons()
    
    def capitalize_words(self):
        """Capitalize the first letter of each word in the selected take names"""
        takes = self.get_selected_takes()
        if not takes:
            QtWidgets.QMessageBox.warning(self, "Warning", "No takes selected.")
            return
        
        # Ensure we have an initial state
        if len(self.history) == 0:
            self.capture_initial_state()
        
        # Save current state for undo
        self.save_state()
        
        for take in takes:
            # Title case splits words and capitalizes the first letter of each word
            new_name = take.Name.title()
            take.Name = new_name
        
        # Refresh the list
        self.populate_takes()
        
        # Save the new state
        new_state = {}
        system = FBSystem()
        scene = system.Scene
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            new_state[i] = take.Name
            
        # Add the new state to history (only if different from last state)
        if len(self.history) == 0 or new_state != self.history[-1]:
            self.history.append(new_state)
            self.history_index = len(self.history) - 1
            print(f"Added capitalize state to history. Now at index {self.history_index} of {len(self.history)-1}")
        
        self.update_undo_redo_buttons()
    
    def preview_rename(self, operation_type):
        """Preview renaming operations without applying them"""
        # Determine which takes to process
        if operation_type == "replace" and self.search_all_takes.isChecked():
            system = FBSystem()
            scene = system.Scene
            takes = []
            take_count = len(scene.Takes)
            for i in range(take_count):
                takes.append(scene.Takes[i])
        else:
            takes = self.get_selected_takes()
            
        if not takes:
            QtWidgets.QMessageBox.warning(self, "Warning", "No takes selected.")
            return
        
        # Clear previous preview
        self.preview_list.setRowCount(0)
        
        # Generate preview based on operation type
        preview_takes = []
        preview_names = []
        
        if operation_type == "simple":
            new_name = self.rename_input.text().strip()
            if not new_name:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a new name.")
                return
            
            if len(takes) == 1 and not self.use_numbering.isChecked():
                preview_takes = takes
                preview_names = [new_name]
            else:
                start_num = self.start_number.value()
                padding = self.padding_digits.value()
                separator = self.number_separator.text()
                
                preview_takes = takes
                for i in range(len(takes)):
                    num = i + start_num
                    if self.use_numbering.isChecked():
                        preview_names.append(f"{new_name}{separator}{str(num).zfill(padding)}")
                    else:
                        preview_names.append(new_name)
        
        elif operation_type == "replace":
            find_text = self.find_input.text()
            replace_text = self.replace_input.text()
            use_regex = self.use_regex.isChecked()
            case_sensitive = self.case_sensitive.isChecked()
            
            for take in takes:
                if use_regex:
                    try:
                        if case_sensitive:
                            new_name = re.sub(find_text, replace_text, take.Name)
                        else:
                            new_name = re.sub(find_text, replace_text, take.Name, flags=re.IGNORECASE)
                    except re.error as e:
                        QtWidgets.QMessageBox.warning(self, "RegEx Error", f"Invalid regular expression: {str(e)}")
                        return
                else:
                    if case_sensitive:
                        new_name = take.Name.replace(find_text, replace_text)
                    else:
                        new_name = re.sub(re.escape(find_text), replace_text, take.Name, flags=re.IGNORECASE)
                
                # Only add to preview if the name would actually change
                if new_name != take.Name:
                    preview_takes.append(take)
                    preview_names.append(new_name)
        
        elif operation_type == "affix":
            prefix = self.prefix_input.text()
            suffix = self.suffix_input.text()
            
            for take in takes:
                new_name = prefix + take.Name + suffix
                # Only add to preview if something would be added
                if prefix or suffix:
                    preview_takes.append(take)
                    preview_names.append(new_name)
        
        # Show message if no changes would be made
        if not preview_takes:
            self.preview_list.setRowCount(1)
            self.preview_list.setItem(0, 0, QtWidgets.QTableWidgetItem("No changes"))
            self.preview_list.setItem(0, 1, QtWidgets.QTableWidgetItem("No takes would be modified"))
            return
            
        # Populate preview list
        self.preview_list.setRowCount(len(preview_takes))
        for i, (take, new_name) in enumerate(zip(preview_takes, preview_names)):
            # Original name
            self.preview_list.setItem(i, 0, QtWidgets.QTableWidgetItem(take.Name))
            
            # New name
            self.preview_list.setItem(i, 1, QtWidgets.QTableWidgetItem(new_name))
    
    def capture_initial_state(self):
        """Capture the initial state of all takes for undo/redo"""
        system = FBSystem()
        scene = system.Scene
        
        initial_state = {}
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            initial_state[i] = take.Name
        
        # Reset history
        self.history = [initial_state]
        self.history_index = 0
        
        print(f"Initial state captured. History index: {self.history_index}, History size: {len(self.history)}")
        self.update_undo_redo_buttons()
    
    def save_state(self):
        """Save current take names for undo/redo"""
        system = FBSystem()
        scene = system.Scene
        
        # Create new state
        current_state = {}
        take_count = len(scene.Takes)
        for i in range(take_count):
            take = scene.Takes[i]
            current_state[i] = take.Name
        
        # If we're in the middle of the history, truncate it
        if self.history_index < len(self.history) - 1:
            print(f"Truncating history from {len(self.history)} to {self.history_index + 1}")
            self.history = self.history[:self.history_index + 1]
        
        # Check if the new state is different from the current state
        if self.history_index >= 0 and self.history[self.history_index] == current_state:
            print("State unchanged, not adding to history")
            return
        
        # Add new state to history
        self.history.append(current_state)
        self.history_index = len(self.history) - 1
        
        # Limit history size
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.history_index -= 1
        
        print(f"Saved new state. History index: {self.history_index}, History size: {len(self.history)}")
        self.update_undo_redo_buttons()
    
    def update_undo_redo_buttons(self):
        """Update undo/redo button states"""
        # Only enable undo if we have more than one state and aren't at the beginning
        self.undo_button.setEnabled(len(self.history) > 1 and self.history_index > 0)
        
        # Only enable redo if we're not at the end of history
        self.redo_button.setEnabled(self.history_index < len(self.history) - 1)
        
        print(f"Undo/Redo status: {self.history_index}/{len(self.history) - 1}")
        print(f"Undo enabled: {self.undo_button.isEnabled()}, Redo enabled: {self.redo_button.isEnabled()}")
    
    def undo(self):
        """Undo the last renaming operation"""
        if self.history_index <= 0 or len(self.history) <= 1:
            print("Nothing to undo")
            return
        
        print(f"Undoing: moving from state {self.history_index} to {self.history_index - 1}")
        self.history_index -= 1
        self.restore_state(self.history[self.history_index])
        self.update_undo_redo_buttons()
    
    def redo(self):
        """Redo the previously undone operation"""
        if self.history_index >= len(self.history) - 1:
            print("Nothing to redo")
            return
        
        print(f"Redoing: moving from state {self.history_index} to {self.history_index + 1}")
        self.history_index += 1
        self.restore_state(self.history[self.history_index])
        self.update_undo_redo_buttons()
    
    def restore_state(self, state):
        """Restore take names from a saved state"""
        system = FBSystem()
        scene = system.Scene
        
        take_count = len(scene.Takes)
        for i in range(take_count):
            if i in state:
                take = scene.Takes[i]
                take.Name = state[i]
        
        self.populate_takes()
    
    def show_help(self):
        """Show help information"""
        help_text = """
        <h2>Take Renamer Help</h2>
        
        <h3>Basic Usage</h3>
        <p>Select one or more takes from the list, then use one of the renaming methods in the tabs below.</p>
        
        <h3>Renaming Options</h3>
        <ul>
            <li><b>Simple Rename</b>: Change the name of the selected takes.</li>
            <li><b>Find and Replace</b>: Find text in take names and replace it.</li>
            <li><b>Prefix/Suffix</b>: Add text before or after the take names.</li>
        </ul>
        
        <h3>Preview</h3>
        <p>Click the Preview button to see how the changes will look before applying them.</p>
        
        <h3>Undo/Redo</h3>
        <p>Use the Undo and Redo buttons to revert or restore changes.</p>
        
        <h3>Keyboard Shortcuts</h3>
        <ul>
            <li><b>Ctrl+Z</b>: Undo</li>
            <li><b>Ctrl+Y</b>: Redo</li>
            <li><b>F5</b>: Refresh</li>
            <li><b>Ctrl+F</b>: Focus filter</li>
        </ul>
        """
        
        help_dialog = QtWidgets.QDialog(self)
        help_dialog.setWindowTitle("Take Renamer Help")
        help_dialog.setMinimumWidth(500)
        help_dialog.setMinimumHeight(400)
        
        layout = QtWidgets.QVBoxLayout(help_dialog)
        
        text_browser = QtWidgets.QTextBrowser()
        text_browser.setHtml(help_text)
        layout.addWidget(text_browser)
        
        button_layout = QtWidgets.QHBoxLayout()
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(help_dialog.close)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        help_dialog.exec_()
    
    def load_settings(self):
        """Load settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        
        # Default settings
        return {
            "window_size": [500, 600],
            "splitter_sizes": [300, 300]
        }
    
    def save_settings(self):
        """Save settings to file"""
        settings = {
            "window_size": [self.width(), self.height()],
            "splitter_sizes": [300, 300]  # TODO: Get actual splitter sizes
        }
        
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f)
        except Exception:
            pass
    
    def closeEvent(self, event):
        """Override close event to save settings"""
        self.save_settings()
        super(TakeRenamerUI, self).closeEvent(event)
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.matches(QtGui.QKeySequence.Undo):
            self.undo()
        elif event.matches(QtGui.QKeySequence.Redo):
            self.redo()
        elif event.key() == QtCore.Qt.Key_F5:
            self.populate_takes()
        elif event.matches(QtGui.QKeySequence.Find):
            self.filter_input.setFocus()
            self.filter_input.selectAll()
        else:
            super(TakeRenamerUI, self).keyPressEvent(event)


# Global reference to keep dialog alive
g_take_renamer_dialog = None

def show_take_renamer():
    """Show the Take Renamer UI"""
    global g_take_renamer_dialog
    
    try:
        # Get the MotionBuilder main window as parent  
        mb_parent = get_motionbuilder_main_window()
        
        g_take_renamer_dialog = TakeRenamerUI(parent=mb_parent)
        g_take_renamer_dialog.show()
    except Exception as e:
        print(f"Error opening Take Renamer: {str(e)}")
        import traceback
        traceback.print_exc()


# Run the application
if __name__ == "__main__":
    try:
        show_take_renamer()
    except Exception as e:
        print(f"Error in main script: {str(e)}")
        import traceback
        traceback.print_exc()