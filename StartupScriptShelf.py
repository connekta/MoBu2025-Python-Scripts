import os
import sys
import json
import functools
from datetime import timedelta, datetime
import pyfbsdk
from PySide6 import QtWidgets, QtCore, QtGui

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

# =============================================================================
# Configuration Constants
# =============================================================================
LOG_INTERVAL = 1000  # 1 second
ICON_BASE_SIZE = 25       # Base size in pixels
ICON_SIZE_SCALE = 1.2     # Scale factor (1.2 = 20% bigger)

PRIMARY_SCRIPT_FOLDER = "C:/Program Files/Autodesk/MotionBuilder 2025/bin/config/PythonCustomScripts"
SECONDARY_SCRIPT_FOLDER = "C:/Program Files/Autodesk/MotionBuilder 2025/bin/config/PythonCustomScripts_Secondaries"
SAVE_BASE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "MB", "CustomPythonSaveData")
SHELF_SETTINGS_FILE = os.path.join(SAVE_BASE_DIR, "Script_Shelf_Settings.json")
WORKFILE_TIMES_FILE = os.path.join(SAVE_BASE_DIR, "Workfile_Times.json")

# =============================================================================
# Helper Functions
# =============================================================================
def make_label(label_text, time_text):
    return f'<p align="left">{label_text} <span style="display:inline-block; min-width:80px; text-align:center;">{time_text}</span></p>'

def format_duration(seconds):
    return str(timedelta(seconds=seconds))

def format_filename(filepath):
    if filepath == "Untitled":
        return "Untitled"
    filename = os.path.basename(filepath)
    filename = os.path.splitext(filename)[0]
    filename = filename.replace('_', ' ')
    return ' '.join(word.capitalize() for word in filename.split())

def load_all_scripts():
    all_scripts = {}
    if os.path.exists(PRIMARY_SCRIPT_FOLDER):
        for file in os.listdir(PRIMARY_SCRIPT_FOLDER):
            if file.endswith(".py"):
                name = os.path.splitext(file)[0]
                all_scripts[name] = os.path.join(PRIMARY_SCRIPT_FOLDER, file)
    if os.path.exists(SECONDARY_SCRIPT_FOLDER):
        for file in os.listdir(SECONDARY_SCRIPT_FOLDER):
            if file.endswith(".py"):
                name = os.path.splitext(file)[0]
                if name not in all_scripts:
                    all_scripts[name] = os.path.join(SECONDARY_SCRIPT_FOLDER, file)
    return all_scripts

# =============================================================================
# Custom UI Components
# =============================================================================
class HoverButton(QtWidgets.QPushButton):
    """Custom button that emits signals when hovered"""
    hover_entered = QtCore.Signal(str)
    hover_left = QtCore.Signal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)
        self._is_icon_mode = False
        
    def set_icon_mode(self, is_icon):
        """Update the icon mode status for hover styling"""
        self._is_icon_mode = is_icon
        
    def enterEvent(self, event):
        super().enterEvent(event)
        original_text = self.property("original_text")
        if original_text:
            self.hover_entered.emit(original_text)
        # Add highlight in icon mode
        if self._is_icon_mode:
            self.setStyleSheet("""
                QPushButton {
                    border: 3px solid #4a90e2;
                    border-radius: 4px;
                    background-color: rgba(74, 144, 226, 0.3);
                    padding: 2px;
                }
                QPushButton:pressed {
                    border: 3px solid #357abd;
                    background-color: rgba(53, 122, 189, 0.4);
                }
            """)
    
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hover_left.emit()
        # Remove highlight
        if self._is_icon_mode:
            self.setStyleSheet("")

class ClickableGroupBox(QtWidgets.QGroupBox):
    clicked = QtCore.Signal()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class SortableHeaderView(QtWidgets.QHeaderView):
    def __init__(self, orientation, parent=None):
        super(SortableHeaderView, self).__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)
        self.sort_orders = {}
    def setSort(self, section, order):
        self.sort_orders[section] = order
        self.setSortIndicator(section, order)

class TimeReportWindow(QtWidgets.QDialog):
    def __init__(self, parent=None, timer=None, time_tracker=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(TimeReportWindow, self).__init__(parent)
        self.setWindowTitle("Time Tracking")
        self.setMinimumSize(400, 500)
        self.parent_timer = timer
        self.parent_time_tracker = time_tracker
        if self.parent_timer:
            self.parent_timer.stop()
        self.current_file = ""
        if self.parent_time_tracker:
            self.current_file = self.parent_time_tracker.current_file
        self.workfile_times = {"total": {}, "daily": {}}
        self.load_workfile_times()
        self.setup_ui()
        self.populate_data()
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        self.tabs = QtWidgets.QTabWidget()
        # All Files tab
        self.all_files_tab = QtWidgets.QWidget()
        all_files_layout = QtWidgets.QVBoxLayout()
        self.all_files_tab.setLayout(all_files_layout)
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("Search:"))
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Filter by filename...")
        self.search_box.setStyleSheet("QLineEdit::placeholder { color: white; }")
        self.search_box.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.search_box)
        filter_layout.addStretch()
        self.refresh_btn = QtWidgets.QPushButton("↻")
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.clicked.connect(self.refresh_all_data)
        filter_layout.addWidget(self.refresh_btn)
        self.open_json_btn = QtWidgets.QPushButton("📁")
        self.open_json_btn.setFixedSize(24, 24)
        self.open_json_btn.clicked.connect(self.open_json_file)
        filter_layout.addWidget(self.open_json_btn)
        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.accept)
        filter_layout.addWidget(close_btn)
        all_files_layout.addLayout(filter_layout)
        self.files_table = QtWidgets.QTableWidget()
        self.files_table.setColumnCount(3)
        self.files_table.setHorizontalHeaderLabels(["File Name", "Total Time", "Today"])
        self.files_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.files_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.files_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.files_header = SortableHeaderView(QtCore.Qt.Horizontal, self.files_table)
        self.files_table.setHorizontalHeader(self.files_header)
        self.files_header.sectionClicked.connect(self.on_files_header_clicked)
        self.files_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.files_table.customContextMenuRequested.connect(self.show_files_context_menu)
        all_files_layout.addWidget(self.files_table)
        # Folders tab
        self.folders_tab = QtWidgets.QWidget()
        folders_layout = QtWidgets.QVBoxLayout()
        self.folders_tab.setLayout(folders_layout)
        self.folders_table = QtWidgets.QTableWidget()
        self.folders_table.setColumnCount(2)
        self.folders_table.setHorizontalHeaderLabels(["Folder", "Total Time"])
        self.folders_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.folders_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.folders_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.folders_header = SortableHeaderView(QtCore.Qt.Horizontal, self.folders_table)
        self.folders_table.setHorizontalHeader(self.folders_header)
        self.folders_header.sectionClicked.connect(self.on_folders_header_clicked)
        folders_layout.addWidget(self.folders_table)
        # Daily tab
        self.daily_tab = QtWidgets.QWidget()
        daily_layout = QtWidgets.QVBoxLayout()
        self.daily_tab.setLayout(daily_layout)
        date_layout = QtWidgets.QHBoxLayout()
        date_layout.addWidget(QtWidgets.QLabel("Date:"))
        self.date_combo = QtWidgets.QComboBox()
        date_layout.addWidget(self.date_combo)
        date_layout.addStretch()
        daily_layout.addLayout(date_layout)
        self.daily_table = QtWidgets.QTableWidget()
        self.daily_table.setColumnCount(2)
        self.daily_table.setHorizontalHeaderLabels(["File Name", "Time"])
        self.daily_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.daily_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.daily_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.daily_header = SortableHeaderView(QtCore.Qt.Horizontal, self.daily_table)
        self.daily_table.setHorizontalHeader(self.daily_header)
        self.daily_header.sectionClicked.connect(self.on_daily_header_clicked)
        self.daily_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.daily_table.customContextMenuRequested.connect(self.show_daily_context_menu)
        daily_layout.addWidget(self.daily_table)
        # Stats tab
        self.stats_tab = QtWidgets.QWidget()
        stats_layout = QtWidgets.QVBoxLayout()
        self.stats_tab.setLayout(stats_layout)
        self.stats_text = QtWidgets.QTextEdit()
        self.stats_text.setReadOnly(True)
        stats_layout.addWidget(self.stats_text)
        self.tabs.addTab(self.all_files_tab, "All Files")
        self.tabs.addTab(self.folders_tab, "By Folder")
        self.tabs.addTab(self.daily_tab, "Daily View")
        self.tabs.addTab(self.stats_tab, "Statistics")
        layout.addWidget(self.tabs)
        self.date_combo.currentIndexChanged.connect(self.update_daily_table)
    def load_workfile_times(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        if os.path.exists(WORKFILE_TIMES_FILE):
            try:
                with open(WORKFILE_TIMES_FILE, "r") as f:
                    self.workfile_times = json.load(f)
            except Exception:
                self.workfile_times = {"total": {}, "daily": {}}
        else:
            self.workfile_times = {"total": {}, "daily": {}}
        if "total" not in self.workfile_times:
            self.workfile_times["total"] = {}
        if "daily" not in self.workfile_times:
            self.workfile_times["daily"] = {}
    def save_workfile_times(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        with open(WORKFILE_TIMES_FILE, "w") as f:
            json.dump(self.workfile_times, f, indent=4)
        if self.parent_time_tracker:
            self.parent_time_tracker.workfile_times = self.workfile_times
    def populate_data(self):
        self.populate_files_table()
        self.populate_folders_table()
        self.populate_daily_data()
        self.populate_stats()
        self.files_table.setSortingEnabled(True)
        self.files_table.sortItems(1, QtCore.Qt.DescendingOrder)
        self.files_header.setSort(1, QtCore.Qt.DescendingOrder)
    def populate_files_table(self):
        self.files_table.setSortingEnabled(False)
        sort_column = self.files_header.sortIndicatorSection()
        sort_order = self.files_header.sortIndicatorOrder()
        self.files_table.setRowCount(0)
        today = datetime.today().strftime("%Y-%m-%d")
        file_data = []
        for file_path, total_time in self.workfile_times["total"].items():
            today_time = 0
            if file_path in self.workfile_times["daily"]:
                today_time = self.workfile_times["daily"][file_path].get(today, 0)
            display_name = format_filename(file_path)
            file_data.append((file_path, display_name, total_time, today_time))
        for row, (file_path, display_name, total_time, today_time) in enumerate(file_data):
            self.files_table.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(display_name)
            name_item.setData(QtCore.Qt.UserRole, file_path)
            self.files_table.setItem(row, 0, name_item)
            total_time_item = QtWidgets.QTableWidgetItem(format_duration(total_time))
            total_time_item.setData(QtCore.Qt.UserRole, total_time)
            self.files_table.setItem(row, 1, total_time_item)
            today_time_item = QtWidgets.QTableWidgetItem(format_duration(today_time))
            today_time_item.setData(QtCore.Qt.UserRole, today_time)
            self.files_table.setItem(row, 2, today_time_item)
            if file_path == self.current_file:
                brush = QtGui.QBrush(QtGui.QColor(60, 100, 150))
                name_item.setBackground(brush)
                total_time_item.setBackground(brush)
                today_time_item.setBackground(brush)
        if sort_column >= 0:
            self.files_table.sortItems(sort_column, sort_order)
            self.files_header.setSort(sort_column, sort_order)
    def populate_folders_table(self):
        sort_column = self.folders_header.sortIndicatorSection()
        sort_order = self.folders_header.sortIndicatorOrder()
        self.folders_table.setSortingEnabled(False)
        self.folders_table.setRowCount(0)
        folder_times = {}
        for file_path, total_time in self.workfile_times["total"].items():
            if file_path == "Untitled":
                continue
            folder_path = os.path.dirname(file_path)
            folder_times[folder_path] = folder_times.get(folder_path, 0) + total_time
        row = 0
        current_folder = ""
        if self.current_file != "Untitled":
            current_folder = os.path.dirname(self.current_file)
        for folder_path, total_time in folder_times.items():
            self.folders_table.insertRow(row)
            folder_name = os.path.basename(folder_path)
            name_item = QtWidgets.QTableWidgetItem(folder_name)
            name_item.setData(QtCore.Qt.UserRole, folder_path)
            self.folders_table.setItem(row, 0, name_item)
            total_time_item = QtWidgets.QTableWidgetItem(format_duration(total_time))
            total_time_item.setData(QtCore.Qt.UserRole, total_time)
            self.folders_table.setItem(row, 1, total_time_item)
            if folder_path == current_folder:
                brush = QtGui.QBrush(QtGui.QColor(60, 100, 150))
                name_item.setBackground(brush)
                total_time_item.setBackground(brush)
            row += 1
        self.folders_table.setSortingEnabled(True)
        if sort_column >= 0:
            self.folders_table.sortItems(sort_column, sort_order)
            self.folders_header.setSort(sort_column, sort_order)
        else:
            self.folders_table.sortItems(1, QtCore.Qt.DescendingOrder)
            self.folders_header.setSort(1, QtCore.Qt.DescendingOrder)
    def populate_daily_data(self):
        all_dates = set()
        for file_data in self.workfile_times["daily"].values():
            all_dates.update(file_data.keys())
        sorted_dates = sorted(list(all_dates), reverse=True)
        current_date = self.date_combo.currentText() if self.date_combo.count() > 0 else ""
        self.date_combo.clear()
        self.date_combo.addItems(sorted_dates)
        today = datetime.today().strftime("%Y-%m-%d")
        if current_date and current_date in sorted_dates:
            date_index = self.date_combo.findText(current_date)
            if date_index >= 0:
                self.date_combo.setCurrentIndex(date_index)
        elif today in sorted_dates:
            today_index = self.date_combo.findText(today)
            if today_index >= 0:
                self.date_combo.setCurrentIndex(today_index)
        elif self.date_combo.count() > 0:
            self.date_combo.setCurrentIndex(0)
        self.update_daily_table()
    def update_daily_table(self):
        sort_column = self.daily_header.sortIndicatorSection()
        sort_order = self.daily_header.sortIndicatorOrder()
        self.daily_table.setSortingEnabled(False)
        self.daily_table.setRowCount(0)
        if self.date_combo.count() == 0:
            return
        selected_date = self.date_combo.currentText()
        file_times = []
        for file_path, dates in self.workfile_times["daily"].items():
            if selected_date in dates:
                file_times.append((file_path, dates[selected_date]))
        for row, (file_path, time_spent) in enumerate(file_times):
            self.daily_table.insertRow(row)
            display_name = format_filename(file_path)
            name_item = QtWidgets.QTableWidgetItem(display_name)
            name_item.setData(QtCore.Qt.UserRole, file_path)
            self.daily_table.setItem(row, 0, name_item)
            time_item = QtWidgets.QTableWidgetItem(format_duration(time_spent))
            time_item.setData(QtCore.Qt.UserRole, time_spent)
            self.daily_table.setItem(row, 1, time_item)
            if file_path == self.current_file:
                brush = QtGui.QBrush(QtGui.QColor(60, 100, 150))
                name_item.setBackground(brush)
                time_item.setBackground(brush)
        self.daily_table.setSortingEnabled(True)
        if sort_column >= 0:
            self.daily_table.sortItems(sort_column, sort_order)
            self.daily_header.setSort(sort_column, sort_order)
        else:
            self.daily_table.sortItems(1, QtCore.Qt.DescendingOrder)
            self.daily_header.setSort(1, QtCore.Qt.DescendingOrder)
    def populate_stats(self):
        stats_text = ""
        total_seconds = sum(self.workfile_times["total"].values())
        stats_text += f"Total Time Tracked: {format_duration(total_seconds)}\n\n"
        daily_totals = {}
        for file_dates in self.workfile_times["daily"].values():
            for date, time_spent in file_dates.items():
                daily_totals[date] = daily_totals.get(date, 0) + time_spent
        if daily_totals:
            sorted_dates = sorted(daily_totals.keys(), reverse=True)
            stats_text += "Time per Day:\n"
            for date in sorted_dates[:10]:
                stats_text += f"{date}: {format_duration(daily_totals[date])}\n"
            avg_daily = sum(daily_totals.values()) / len(daily_totals)
            stats_text += f"\nAverage Daily Time: {format_duration(avg_daily)}\n"
            most_productive = max(daily_totals.items(), key=lambda x: x[1])
            stats_text += f"Most Productive Day: {most_productive[0]} ({format_duration(most_productive[1])})\n\n"
        if self.workfile_times["total"]:
            top_files = sorted(self.workfile_times["total"].items(), key=lambda x: x[1], reverse=True)[:5]
            stats_text += "Top Files by Time:\n"
            for file_path, time_spent in top_files:
                display_name = format_filename(file_path)
                stats_text += f"{display_name}: {format_duration(time_spent)}\n"
            stats_text += "\n"
        folder_times = {}
        for file_path, total_time in self.workfile_times["total"].items():
            if file_path == "Untitled":
                continue
            folder_path = os.path.dirname(file_path)
            folder_name = os.path.basename(folder_path)
            folder_times[folder_name] = folder_times.get(folder_name, 0) + total_time
        if folder_times:
            top_folders = sorted(folder_times.items(), key=lambda x: x[1], reverse=True)[:5]
            stats_text += "Top Folders by Time:\n"
            for folder_name, time_spent in top_folders:
                stats_text += f"{folder_name}: {format_duration(time_spent)}\n"
        self.stats_text.setText(stats_text)
    def on_files_header_clicked(self, section):
        if section == 0:
            order = QtCore.Qt.AscendingOrder
            if self.files_header.sortIndicatorSection() == section and self.files_header.sortIndicatorOrder() == QtCore.Qt.AscendingOrder:
                order = QtCore.Qt.DescendingOrder
            self.files_table.sortItems(section, order)
            self.files_header.setSort(section, order)
        else:
            order = QtCore.Qt.DescendingOrder
            if self.files_header.sortIndicatorSection() == section and self.files_header.sortIndicatorOrder() == QtCore.Qt.DescendingOrder:
                order = QtCore.Qt.AscendingOrder
            self.files_table.sortItems(section, order)
            self.files_header.setSort(section, order)
    def on_folders_header_clicked(self, section):
        if section == 0:
            order = QtCore.Qt.AscendingOrder
            if self.folders_header.sortIndicatorSection() == section and self.folders_header.sortIndicatorOrder() == QtCore.Qt.AscendingOrder:
                order = QtCore.Qt.DescendingOrder
            self.folders_table.sortItems(section, order)
            self.folders_header.setSort(section, order)
        else:
            order = QtCore.Qt.DescendingOrder
            if self.folders_header.sortIndicatorSection() == section and self.folders_header.sortIndicatorOrder() == QtCore.Qt.DescendingOrder:
                order = QtCore.Qt.AscendingOrder
            self.folders_table.sortItems(section, order)
            self.folders_header.setSort(section, order)
    def on_daily_header_clicked(self, section):
        if section == 0:
            order = QtCore.Qt.AscendingOrder
            if self.daily_header.sortIndicatorSection() == section and self.daily_header.sortIndicatorOrder() == QtCore.Qt.AscendingOrder:
                order = QtCore.Qt.DescendingOrder
            self.daily_table.sortItems(section, order)
            self.daily_header.setSort(section, order)
        else:
            order = QtCore.Qt.DescendingOrder
            if self.daily_header.sortIndicatorSection() == section and self.daily_header.sortIndicatorOrder() == QtCore.Qt.DescendingOrder:
                order = QtCore.Qt.AscendingOrder
            self.daily_table.sortItems(section, order)
            self.daily_header.setSort(section, order)
    def show_files_context_menu(self, pos):
        selected_items = self.files_table.selectedItems()
        if not selected_items:
            return
        menu = QtWidgets.QMenu()
        remove_action = menu.addAction("Remove Selected Files from Tracking")
        action = menu.exec_(self.files_table.mapToGlobal(pos))
        if action == remove_action:
            self.remove_selected_files()
    def show_daily_context_menu(self, pos):
        selected_items = self.daily_table.selectedItems()
        if not selected_items:
            return
        menu = QtWidgets.QMenu()
        remove_action = menu.addAction("Remove Selected Files from Tracking")
        action = menu.exec_(self.daily_table.mapToGlobal(pos))
        if action == remove_action:
            self.remove_selected_daily_files()
    def remove_selected_files(self):
        selected_rows = set()
        for item in self.files_table.selectedItems():
            selected_rows.add(item.row())
        files_to_remove = []
        for row in selected_rows:
            file_path = self.files_table.item(row, 0).data(QtCore.Qt.UserRole)
            files_to_remove.append(file_path)
        if files_to_remove:
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setIcon(QtWidgets.QMessageBox.Question)
            msg_box.setText(f"Remove {len(files_to_remove)} file(s) from tracking?")
            msg_box.setInformativeText("This will delete all time tracking data for these files.")
            msg_box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg_box.setDefaultButton(QtWidgets.QMessageBox.No)
            if msg_box.exec_() == QtWidgets.QMessageBox.Yes:
                for file_path in files_to_remove:
                    if file_path in self.workfile_times["total"]:
                        del self.workfile_times["total"][file_path]
                    if file_path in self.workfile_times["daily"]:
                        del self.workfile_times["daily"][file_path]
                self.save_workfile_times()
                self.refresh_all_data()
    def remove_selected_daily_files(self):
        selected_rows = set()
        for item in self.daily_table.selectedItems():
            selected_rows.add(item.row())
        files_to_remove = []
        for row in selected_rows:
            file_path = self.daily_table.item(row, 0).data(QtCore.Qt.UserRole)
            files_to_remove.append(file_path)
        if files_to_remove:
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setIcon(QtWidgets.QMessageBox.Question)
            msg_box.setText(f"Remove {len(files_to_remove)} file(s) from tracking?")
            msg_box.setInformativeText("This will delete all time tracking data for these files.")
            msg_box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg_box.setDefaultButton(QtWidgets.QMessageBox.No)
            if msg_box.exec_() == QtWidgets.QMessageBox.Yes:
                for file_path in files_to_remove:
                    if file_path in self.workfile_times["total"]:
                        del self.workfile_times["total"][file_path]
                    if file_path in self.workfile_times["daily"]:
                        del self.workfile_times["daily"][file_path]
                self.save_workfile_times()
                self.refresh_all_data()
    def apply_filters(self):
        sort_column = self.files_header.sortIndicatorSection()
        sort_order = self.files_header.sortIndicatorOrder()
        self.files_table.setSortingEnabled(False)
        search_text = self.search_box.text().lower()
        self.files_table.setRowCount(0)
        today = datetime.today().strftime("%Y-%m-%d")
        file_data = []
        for file_path, total_time in self.workfile_times["total"].items():
            display_name = format_filename(file_path)
            if search_text and search_text not in file_path.lower() and search_text not in display_name.lower():
                continue
            today_time = 0
            if file_path in self.workfile_times["daily"]:
                today_time = self.workfile_times["daily"][file_path].get(today, 0)
            file_data.append((file_path, display_name, total_time, today_time))
        for row, (file_path, display_name, total_time, today_time) in enumerate(file_data):
            self.files_table.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(display_name)
            name_item.setData(QtCore.Qt.UserRole, file_path)
            self.files_table.setItem(row, 0, name_item)
            total_time_item = QtWidgets.QTableWidgetItem(format_duration(total_time))
            total_time_item.setData(QtCore.Qt.UserRole, total_time)
            self.files_table.setItem(row, 1, total_time_item)
            today_time_item = QtWidgets.QTableWidgetItem(format_duration(today_time))
            today_time_item.setData(QtCore.Qt.UserRole, today_time)
            self.files_table.setItem(row, 2, today_time_item)
            if file_path == self.current_file:
                brush = QtGui.QBrush(QtGui.QColor(60, 100, 150))
                name_item.setBackground(brush)
                total_time_item.setBackground(brush)
                today_time_item.setBackground(brush)
        self.files_table.setSortingEnabled(True)
        if sort_column >= 0:
            self.files_table.sortItems(sort_column, sort_order)
            self.files_header.setSort(sort_column, sort_order)
        else:
            self.files_table.sortItems(1, QtCore.Qt.DescendingOrder)
            self.files_header.setSort(1, QtCore.Qt.DescendingOrder)
    def refresh_all_data(self):
        current_tab_index = self.tabs.currentIndex()
        search_filter = self.search_box.text()
        files_sort_column = self.files_header.sortIndicatorSection()
        files_sort_order = self.files_header.sortIndicatorOrder()
        folders_sort_column = self.folders_header.sortIndicatorSection()
        folders_sort_order = self.folders_header.sortIndicatorOrder()
        daily_sort_column = self.daily_header.sortIndicatorSection()
        daily_sort_order = self.daily_header.sortIndicatorOrder()
        self.files_table.setSortingEnabled(False)
        self.folders_table.setSortingEnabled(False)
        self.daily_table.setSortingEnabled(False)
        self.load_workfile_times()
        self.populate_files_table()
        self.populate_folders_table()
        self.populate_daily_data()
        self.populate_stats()
        self.files_table.setSortingEnabled(True)
        self.folders_table.setSortingEnabled(True)
        self.daily_table.setSortingEnabled(True)
        if files_sort_column >= 0:
            self.files_table.sortItems(files_sort_column, files_sort_order)
            self.files_header.setSort(files_sort_column, files_sort_order)
        if folders_sort_column >= 0:
            self.folders_table.sortItems(folders_sort_column, folders_sort_order)
            self.folders_header.setSort(folders_sort_column, folders_sort_order)
        if daily_sort_column >= 0:
            self.daily_table.sortItems(daily_sort_column, daily_sort_order)
            self.daily_header.setSort(daily_sort_column, daily_sort_order)
        if search_filter:
            self.apply_filters()
        status_label = QtWidgets.QLabel("Data refreshed!")
        status_label.setStyleSheet("background-color: rgba(50, 150, 50, 180); padding: 5px; border-radius: 3px;")
        status_label.setAlignment(QtCore.Qt.AlignCenter)
        status_label.setParent(self)
        status_label.setGeometry((self.width() - 150) // 2, (self.height() - 30) // 2, 150, 30)
        status_label.show()
        QtCore.QTimer.singleShot(1000, status_label.hide)
    def open_json_file(self):
        try:
            os.startfile(WORKFILE_TIMES_FILE)
        except Exception as e:
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setIcon(QtWidgets.QMessageBox.Warning)
            msg_box.setText(f"Unable to open JSON file: {str(e)}")
            msg_box.exec_()
    def done(self, result):
        if self.parent_timer and not self.parent_timer.isActive():
            self.parent_timer.start()
        super().done(result)
    def run_script(self, script_path):
        try:
            with open(script_path, 'r', encoding='utf-8') as file:
                exec(file.read(), {'__name__': '__main__', '__file__': script_path})
        except UnicodeDecodeError:
            pyfbsdk.FBMessageBox("Encoding Error", f"Error decoding {script_path}. Ensure it's saved as UTF-8.", "OK")
        except Exception as e:
            pyfbsdk.FBMessageBox("Script Error", f"Error executing {script_path}: {str(e)}", "OK")
    def load_shelf_settings(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        if os.path.exists(SHELF_SETTINGS_FILE):
            try:
                with open(SHELF_SETTINGS_FILE, "r") as f:
                    self.shelf_settings = json.load(f)
            except Exception:
                self.shelf_settings = {}
        else:
            self.shelf_settings = {}
        defaults = {
            "use_icons": False,
            "script_assignments": {},
            "primary_order": [],
            "secondary_order": []
        }
        for key, value in defaults.items():
            if key not in self.shelf_settings:
                self.shelf_settings[key] = value
    def save_shelf_settings(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        with open(SHELF_SETTINGS_FILE, "w") as f:
            json.dump(self.shelf_settings, f, indent=4)
    def closeEvent(self, event):
        self.log_timer.stop()
        add_to_python_tools_menu()
        event.accept()

# =============================================================================
# TimeTracker Module
# =============================================================================
class TimeTracker:
    def __init__(self):
        self.workfile_times = {"total": {}, "daily": {}}
        self.initial_daily_time = 0
        self.current_file = "Untitled"
        self.load_workfile_times()
    def get_current_file_path(self):
        try:
            app = pyfbsdk.FBApplication()
            file_path = app.FBXFileName
            if file_path and file_path.strip():
                return file_path
            else:
                return "Untitled"
        except Exception:
            return "Untitled"
    def log_time(self, seconds=1):
        current = self.get_current_file_path()
        self.current_file = current
        self.workfile_times["total"][current] = self.workfile_times["total"].get(current, 0) + seconds
        today = datetime.today().strftime("%Y-%m-%d")
        if current not in self.workfile_times["daily"]:
            self.workfile_times["daily"][current] = {}
        self.workfile_times["daily"][current][today] = self.workfile_times["daily"][current].get(today, 0) + seconds
        self.save_workfile_times()
        return current, today
    def get_folder_time(self, path):
        if path == "Untitled":
            return 0
        current_dir = os.path.normpath(os.path.dirname(path))
        folder_time = 0
        for key, secs in self.workfile_times["total"].items():
            if key == "Untitled":
                continue
            key_dir = os.path.normpath(os.path.dirname(key))
            if key_dir == current_dir:
                folder_time += secs
        return folder_time
    def get_parent_folder_time(self, path):
        if path == "Untitled":
            return 0, "N/A"
        current_dir = os.path.normpath(os.path.dirname(path))
        parent_dir = os.path.dirname(current_dir)
        parent_folder_name = os.path.basename(parent_dir) if parent_dir and parent_dir != current_dir else "N/A"
        parent_folder_time = 0
        for key, secs in self.workfile_times["total"].items():
            if key == "Untitled":
                continue
            key_dir = os.path.normpath(os.path.dirname(key))
            parent_key_dir = os.path.dirname(key_dir)
            parent_key_folder = os.path.basename(parent_key_dir)
            if parent_key_folder == parent_folder_name:
                parent_folder_time += secs
        return parent_folder_time, parent_folder_name
    def get_file_time(self, path, daily=False):
        if daily:
            today = datetime.today().strftime("%Y-%m-%d")
            return self.workfile_times["daily"].get(path, {}).get(today, 0)
        else:
            return self.workfile_times["total"].get(path, 0)
    def load_workfile_times(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        if os.path.exists(WORKFILE_TIMES_FILE):
            try:
                with open(WORKFILE_TIMES_FILE, "r") as f:
                    self.workfile_times = json.load(f)
            except Exception:
                self.workfile_times = {"total": {}, "daily": {}}
        else:
            self.workfile_times = {"total": {}, "daily": {}}
        if "total" not in self.workfile_times:
            self.workfile_times["total"] = {}
        if "daily" not in self.workfile_times:
            self.workfile_times["daily"] = {}
        self.current_file = self.get_current_file_path()
        today = datetime.today().strftime("%Y-%m-%d")
        self.initial_daily_time = self.workfile_times["daily"].get(self.current_file, {}).get(today, 0)
    def save_workfile_times(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        with open(WORKFILE_TIMES_FILE, "w") as f:
            json.dump(self.workfile_times, f, indent=4)
    def get_times_report(self):
        current = self.current_file
        total_time = self.get_file_time(current)
        today_time = self.get_file_time(current, daily=True)
        folder_time = self.get_folder_time(current)
        parent_time, parent_name = self.get_parent_folder_time(current)
        return {
            "file": current,
            "file_total": total_time,
            "file_today": today_time,
            "folder": os.path.basename(os.path.dirname(current)) if current != "Untitled" else "N/A",
            "folder_total": folder_time,
            "parent_folder": parent_name,
            "parent_folder_total": parent_time
        }

# =============================================================================
# FixedTimeReportWindow (ensuring parent's timer is restarted)
# =============================================================================
class FixedTimeReportWindow(TimeReportWindow):
    def closeEvent(self, event):
        if self.parent_timer and not self.parent_timer.isActive():
            self.parent_timer.start()
        event.accept()

# =============================================================================
# Global Functions for ScriptShelf
# =============================================================================
def show_shelf():
    global shelf_window
    try:
        shelf_window.close()
    except Exception:
        pass
    # Get the MotionBuilder main window as parent
    mb_parent = get_motionbuilder_main_window()
    shelf_window = ScriptShelf(parent=mb_parent)
    shelf_window.show()
    shelf_window.move_to_top_center()

def add_to_python_tools_menu():
    menu_mgr = pyfbsdk.FBMenuManager()
    menu_name = "Python Tools"
    submenu_name = "Open Script Shelf"
    def on_menu_click(control, event):
        show_shelf()
    if not menu_mgr.GetMenu(menu_name):
        menu_mgr.InsertAfter(None, menu_name)
    menu = menu_mgr.GetMenu(menu_name)
    if menu:
        for i in range(menu.GetDstCount()):
            if menu.GetDstLabel(i) == submenu_name:
                menu.Remove(i)
                break
        menu.InsertLast(submenu_name, 0)
        menu.OnMenuActivate.Add(on_menu_click)

# =============================================================================
# Options Window Class
# =============================================================================
class OptionsWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(OptionsWindow, self).__init__(parent)
        self.parent_shelf = parent
        self.setWindowTitle("Script Shelf Options")
        self.setWindowFlags(QtCore.Qt.Window)  # Use standard window flags
        self.setup_ui()
        
    def setup_ui(self):
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 10)  # Add margins for better spacing
        self.setLayout(self.layout)
        
        # Set a smaller default size for the window
        self.setMinimumSize(300, 200)
        self.resize(400, 300)
        
        # Secondary buttons section
        self.secondary_layout = QtWidgets.QHBoxLayout()
        self.secondary_layout.setSpacing(2)
        self.secondary_layout.setContentsMargins(0, 5, 0, 5)
        self.secondary_layout.setAlignment(QtCore.Qt.AlignLeft)
        self.layout.addLayout(self.secondary_layout)
        
        # Use Icons checkbox
        small_buttons_layout = QtWidgets.QHBoxLayout()
        small_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.checkbox = QtWidgets.QCheckBox("Use Icons?")
        self.checkbox.toggled.connect(self.on_small_buttons_toggled)
        if self.parent_shelf:
            self.checkbox.setChecked(self.parent_shelf.shelf_settings.get("use_icons", False))
        small_buttons_layout.addWidget(self.checkbox)
        small_buttons_layout.addStretch()
        self.layout.addLayout(small_buttons_layout)
        
        # Time tracking information with click hint
        self.time_group_box = ClickableGroupBox("📁 Time Spent In: (Click to open Time Tracker)")
        self.time_group_box.setStyleSheet("""
            QGroupBox {
                border: 1px solid #666;
                border-radius: 5px;
                margin-top: 5px;
                padding-top: 10px;
            }
            QGroupBox:hover {
                border: 2px solid #4a90e2;
                background-color: rgba(74, 144, 226, 0.1);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #4a90e2;
            }
        """)
        time_group_layout = QtWidgets.QVBoxLayout()
        time_group_layout.setContentsMargins(0, 0, 0, 0)
        self.time_group_box.setLayout(time_group_layout)
        
        self.current_file_label = QtWidgets.QLabel()
        self.current_file_label.setTextFormat(QtCore.Qt.RichText)
        self.current_file_today_label = QtWidgets.QLabel()
        self.current_file_today_label.setTextFormat(QtCore.Qt.RichText)
        self.folder_label = QtWidgets.QLabel()
        self.folder_label.setTextFormat(QtCore.Qt.RichText)
        self.parent_folder_label = QtWidgets.QLabel()
        self.parent_folder_label.setTextFormat(QtCore.Qt.RichText)
        
        time_group_layout.addWidget(self.current_file_label)
        time_group_layout.addWidget(self.current_file_today_label)
        time_group_layout.addWidget(self.folder_label)
        time_group_layout.addWidget(self.parent_folder_label)
        
        self.time_group_box.clicked.connect(self.show_time_report)
        self.layout.addWidget(self.time_group_box)
        
        # Set initial size
        self.setMinimumWidth(300)
        self.adjustSize()
        
    def on_small_buttons_toggled(self):
        if self.parent_shelf:
            self.parent_shelf.shelf_settings["use_icons"] = self.checkbox.isChecked()
            self.parent_shelf.update_all_button_labels()
            self.parent_shelf.save_shelf_settings()
            
    def update_time_labels(self):
        if self.parent_shelf:
            times = self.parent_shelf.time_tracker.get_times_report()
            display_name = format_filename(times["file"])
            self.current_file_label.setText(make_label("Current File:", format_duration(times["file_total"])))
            self.current_file_today_label.setText(make_label("Current File (Today):", format_duration(times["file_today"])))
            if times["file"] == "Untitled":
                self.folder_label.setText(make_label("Folder:", "N/A"))
                self.parent_folder_label.setText(make_label("Parent Folder:", "N/A"))
            else:
                self.folder_label.setText(make_label(f"/{times['folder']}/:", format_duration(times["folder_total"])))
                self.parent_folder_label.setText(make_label(f"/{times['parent_folder']}/:", format_duration(times["parent_folder_total"])))
                
    def show_time_report(self):
        if self.parent_shelf:
            report_window = FixedTimeReportWindow(self.parent_shelf, self.parent_shelf.log_timer, 
                                               self.parent_shelf.time_tracker)
            report_window.exec_()
            
    def add_secondary_button(self, btn):
        self.secondary_layout.addWidget(btn)
        
    def clear_secondary_buttons(self):
        while self.secondary_layout.count() > 0:
            item = self.secondary_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                
    def showEvent(self, event):
        super().showEvent(event)
        # Position the window below the main shelf
        if self.parent_shelf:
            self.move(self.parent_shelf.x(), self.parent_shelf.y() + self.parent_shelf.height() + 5)
    
    def closeEvent(self, event):
        # Reset the toggle button when options window is closed
        if self.parent_shelf and hasattr(self.parent_shelf, 'toggle_button'):
            self.parent_shelf.toggle_button.setText("↓")
        super().closeEvent(event)

# =============================================================================
# ScriptShelf Class
# =============================================================================
class ScriptShelf(QtWidgets.QWidget):
    def __init__(self, parent=None):
        # If no parent provided, try to get MotionBuilder main window
        if parent is None:
            parent = get_motionbuilder_main_window()
            
        super(ScriptShelf, self).__init__(parent)
        self.setWindowTitle("Script Shelf")
        self.setWindowFlags(QtCore.Qt.CustomizeWindowHint |
                           QtCore.Qt.WindowCloseButtonHint)
        self.time_tracker = TimeTracker()
        self.primary_buttons = []
        self.secondary_buttons = []
        self.shelf_settings = {
            "use_icons": False,
            "script_assignments": {},
            "primary_order": [],
            "secondary_order": []
        }
        self.load_shelf_settings()
        self.opened_time = datetime.now()
        self.options_window = None  # Will be created when needed
        self.setup_ui()
        self.log_timer = QtCore.QTimer(self)
        self.log_timer.timeout.connect(self.on_timer_tick)
        self.log_timer.start(LOG_INTERVAL)
        self.adjustSize()
        # Ensure minimum width while respecting content
        desired_width = max(450, self.sizeHint().width())
        self.resize(desired_width, self.sizeHint().height())
        self.setMinimumWidth(450)  # Prevent window from becoming too small
        self.move_to_top_center()
    def setup_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.setContentsMargins(5, 0, 5, 5)  # Remove top padding
        self.setLayout(self.main_layout)
        
        # Create a horizontal layout for the entire toolbar
        self.toolbar_layout = QtWidgets.QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addLayout(self.toolbar_layout)
        
        # Add a larger spacer at the beginning
        self.toolbar_layout.addSpacing(150)
        
        # Create the primary button layout (will contain only buttons)
        self.primary_layout = QtWidgets.QHBoxLayout()
        self.primary_layout.setSpacing(2)  # Add small spacing between buttons
        self.primary_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_layout.addLayout(self.primary_layout)
        
        # Add a small fixed spacer between buttons and toggle
        self.toolbar_layout.addSpacing(3)
        
        # Toggle button with hover effects
        self.toggle_button = QtWidgets.QPushButton("↓")
        self.toggle_button.setFixedSize(20, 20)
        self.toggle_button.setFlat(True)
        self.toggle_button.clicked.connect(self.toggle_options_group)
        self.toggle_button.setStyleSheet("")
        self.toggle_button.installEventFilter(self)  # Install event filter for hover
        self.toolbar_layout.addWidget(self.toggle_button)
        
        # Add smaller spacing between toggle and text
        self.toolbar_layout.addSpacing(5)
        
        # Add hover text label with fixed width
        self.hover_text = QtWidgets.QLabel("")
        self.hover_text.setFixedHeight(20)
        self.hover_text.setFixedWidth(200)  # Fixed width prevents resizing
        self.hover_text.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.hover_text.setStyleSheet("color: #888888;")
        self.toolbar_layout.addWidget(self.hover_text)
        
        self.load_all_buttons()
        self.update_all_button_labels()
    
    def on_button_hover(self, text):
        """Handle button hover enter - display text in brackets only when using icons"""
        if self.shelf_settings.get("use_icons", False):
            self.hover_text.setText(f"[{text}]")
    
    def on_button_hover_left(self):
        """Handle button hover leave - clear text"""
        self.hover_text.setText("")
    
    def eventFilter(self, obj, event):
        """Event filter to handle toggle button hover"""
        if obj == self.toggle_button:
            if event.type() == QtCore.QEvent.Enter:
                # On hover enter - show text and style
                self.hover_text.setText("[Shelf Options]")
                self.toggle_button.setStyleSheet("""
                    QPushButton {
                        color: #4a90e2;
                        font-weight: bold;
                        font-size: 16px;
                    }
                """)
            elif event.type() == QtCore.QEvent.Leave:
                # On hover leave - clear text and style
                self.hover_text.setText("")
                self.toggle_button.setStyleSheet("")
        return super().eventFilter(obj, event)
    
    def move_to_top_center(self):
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        window_size = self.geometry()
        x = (screen.width() - window_size.width()) // 2
        y = 0
        self.move(x, y)
    def load_all_buttons(self):
        all_scripts = load_all_scripts()
        for name, path in all_scripts.items():
            if name not in self.shelf_settings["script_assignments"]:
                if path.startswith(PRIMARY_SCRIPT_FOLDER):
                    self.shelf_settings["script_assignments"][name] = "primary"
                else:
                    self.shelf_settings["script_assignments"][name] = "secondary"
        primary_list = [name for name, grp in self.shelf_settings["script_assignments"].items() if grp == "primary"]
        secondary_list = [name for name, grp in self.shelf_settings["script_assignments"].items() if grp == "secondary"]
        if not self.shelf_settings["primary_order"]:
            self.shelf_settings["primary_order"] = sorted(primary_list)
        else:
            for name in primary_list:
                if name not in self.shelf_settings["primary_order"]:
                    self.shelf_settings["primary_order"].append(name)
        if not self.shelf_settings["secondary_order"]:
            self.shelf_settings["secondary_order"] = sorted(secondary_list)
        else:
            for name in secondary_list:
                if name not in self.shelf_settings["secondary_order"]:
                    self.shelf_settings["secondary_order"].append(name)
        self.primary_buttons = []
        self.secondary_buttons = []
        while self.primary_layout.count() > 0:
            item = self.primary_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        # Clear secondary buttons from options window if it exists
        if self.options_window:
            self.options_window.clear_secondary_buttons()
        for name in self.shelf_settings["primary_order"]:
            if name in all_scripts:
                btn = HoverButton(name)
                btn.clicked.connect(functools.partial(self.run_script, all_scripts[name]))
                btn.setProperty("original_text", name)
                btn.setProperty("script_path", all_scripts[name])
                btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(lambda pos, b=btn: self.show_button_context_menu(b, pos, "primary"))
                # Connect hover signals
                btn.hover_entered.connect(self.on_button_hover)
                btn.hover_left.connect(self.on_button_hover_left)
                self.primary_buttons.append(btn)
                # Set proper appearance based on icon mode
                use_icons = self.shelf_settings.get("use_icons", False)
                btn.set_icon_mode(use_icons)
                self.update_button_appearance(btn, False)
                self.primary_layout.addWidget(btn)
        # Don't add stretch here - it causes too much space before arrow
        for name in self.shelf_settings["secondary_order"]:
            if name in all_scripts:
                btn = HoverButton(name)
                btn.clicked.connect(functools.partial(self.run_script, all_scripts[name]))
                btn.setProperty("original_text", name)
                btn.setProperty("script_path", all_scripts[name])
                btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(lambda pos, b=btn: self.show_button_context_menu(b, pos, "secondary"))
                # Connect hover signals
                btn.hover_entered.connect(self.on_button_hover)
                btn.hover_left.connect(self.on_button_hover_left)
                self.secondary_buttons.append(btn)
                # Set proper appearance based on icon mode
                use_icons = self.shelf_settings.get("use_icons", False)
                btn.set_icon_mode(use_icons)
                self.update_button_appearance(btn, True)
                # Add to options window if it exists
                if self.options_window:
                    self.options_window.add_secondary_button(btn)
        if self.options_window:
            self.options_window.secondary_layout.addStretch()
        self.save_shelf_settings()
        
        # Force layout update to fix spacing
        self.primary_layout.invalidate()
        self.toolbar_layout.invalidate()
        self.main_layout.invalidate()
        self.adjustSize()
    def open_script_in_explorer(self, script_path):
        """Open the script's folder in Windows Explorer"""
        if script_path:
            script_dir = os.path.dirname(script_path)
            try:
                os.startfile(script_dir)
            except Exception as e:
                msg_box = QtWidgets.QMessageBox(self)
                msg_box.setIcon(QtWidgets.QMessageBox.Warning)
                msg_box.setText(f"Unable to open folder: {str(e)}")
                msg_box.exec_()
    def show_button_context_menu(self, btn, pos, group):
        menu = QtWidgets.QMenu()
        header = QtGui.QAction(btn.property("original_text"), menu)
        header.setDisabled(True)
        menu.addAction(header)
        menu.addSeparator()
        move_left_action = menu.addAction("Move Left")
        move_right_action = menu.addAction("Move Right")
        if group == "primary":
            transfer_action = menu.addAction("Send to Secondary")
        else:
            transfer_action = menu.addAction("Send to Primary")
            
        # Add new option to open in explorer
        open_in_explorer_action = menu.addAction("Open in Explorer")
        
        action = menu.exec_(btn.mapToGlobal(pos))
        if action == move_left_action:
            self.move_button_left(btn, group)
        elif action == move_right_action:
            self.move_button_right(btn, group)
        elif action == transfer_action:
            if group == "primary":
                self.transfer_button(btn, "primary", "secondary")
            else:
                self.transfer_button(btn, "secondary", "primary")
        elif action == open_in_explorer_action:
            self.open_script_in_explorer(btn.property("script_path"))
    def move_button_left(self, btn, group):
        if group == "primary":
            order = self.shelf_settings["primary_order"]
        else:
            order = self.shelf_settings["secondary_order"]
        script_name = btn.property("original_text")
        index = order.index(script_name)
        if index > 0:
            order[index], order[index-1] = order[index-1], order[index]
            self.save_shelf_settings()
            self.update_buttons_order(group)
    def move_button_right(self, btn, group):
        if group == "primary":
            order = self.shelf_settings["primary_order"]
        else:
            order = self.shelf_settings["secondary_order"]
        script_name = btn.property("original_text")
        index = order.index(script_name)
        if index < len(order) - 1:
            order[index], order[index+1] = order[index+1], order[index]
            self.save_shelf_settings()
            self.update_buttons_order(group)
    def transfer_button(self, btn, from_group, to_group):
        script_name = btn.property("original_text")
        self.shelf_settings["script_assignments"][script_name] = to_group
        
        # Update the order lists
        if from_group == "primary":
            if script_name in self.shelf_settings["primary_order"]:
                self.shelf_settings["primary_order"].remove(script_name)
            if script_name not in self.shelf_settings["secondary_order"]:
                self.shelf_settings["secondary_order"].append(script_name)
                
            # Remove button from primary and add to secondary  
            self.primary_layout.removeWidget(btn)
            self.primary_buttons.remove(btn)
            self.secondary_buttons.append(btn)
            
            # Disconnect old context menu and connect new one
            btn.customContextMenuRequested.disconnect()
            btn.customContextMenuRequested.connect(lambda pos, b=btn: self.show_button_context_menu(b, pos, "secondary"))
            
            # Ensure icon and text are properly set
            self.update_button_appearance(btn, True)  # Update for the secondary group
            
        else:  # from secondary to primary
            if script_name in self.shelf_settings["secondary_order"]:
                self.shelf_settings["secondary_order"].remove(script_name)
            if script_name not in self.shelf_settings["primary_order"]:
                self.shelf_settings["primary_order"].append(script_name)
                
            # Remove button from secondary and add to primary
            if self.options_window:
                self.options_window.secondary_layout.removeWidget(btn)
            self.secondary_buttons.remove(btn)
            self.primary_buttons.append(btn)
            self.primary_layout.addWidget(btn)
            
            # Disconnect old context menu and connect new one
            btn.customContextMenuRequested.disconnect()
            btn.customContextMenuRequested.connect(lambda pos, b=btn: self.show_button_context_menu(b, pos, "primary"))
            
            # Ensure icon and text are properly set
            self.update_button_appearance(btn, False)  # Update for the primary group
        
        self.save_shelf_settings()
        
        # Update button order in their respective groups
        self.update_buttons_order("primary")
        self.update_buttons_order("secondary")
        
        # If options window is open, refresh its display
        if self.options_window and self.options_window.isVisible():
            self.populate_options_window_buttons()
        
        # Force complete layout refresh
        self.primary_layout.invalidate()
        self.toolbar_layout.invalidate()
        self.main_layout.invalidate()
        self.adjustSize()
        
        # Final layout adjustment
        desired_width = max(450, self.sizeHint().width())
        self.resize(desired_width, self.sizeHint().height())
    def update_button_appearance(self, btn, is_secondary=False):
        """Update a single button's appearance based on icon mode setting"""
        use_icons = self.shelf_settings.get("use_icons", False)
        new_size = int(ICON_BASE_SIZE * ICON_SIZE_SCALE)  # Use scaled size like in original
        
        # Get the icon folder from settings or use default
        icon_folder = self.shelf_settings.get("icon_folder", r"C:\Program Files\Autodesk\MotionBuilder 2025\bin\config\PythonScriptIcons")
        
        original_text = btn.property("original_text")
        btn.set_icon_mode(use_icons)  # Set icon mode for hover styling
        
        if use_icons:
            icon_path = os.path.join(icon_folder, original_text + ".png")
            if os.path.exists(icon_path):
                btn.setIcon(QtGui.QIcon(icon_path))
                btn.setText("")
                btn.setIconSize(QtCore.QSize(new_size - 6, new_size - 6))  # Smaller to show border
            else:
                btn.setIcon(QtGui.QIcon())
                btn.setText(original_text)
                
            btn.setFixedSize(new_size, new_size)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        else:
            btn.setIcon(QtGui.QIcon())
            btn.setText(original_text)
            
            btn.setFixedHeight(25)
            btn.setMinimumWidth(0)
            btn.setMaximumWidth(16777215)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
    
    def update_buttons_order(self, group):
        if group == "primary":
            # Clean up order list to only include existing buttons
            existing_names = [btn.property("original_text") for btn in self.primary_buttons]
            self.shelf_settings["primary_order"] = [name for name in self.shelf_settings["primary_order"] if name in existing_names]
            
            # Add any new buttons not in the order to the end
            for name in existing_names:
                if name not in self.shelf_settings["primary_order"]:
                    self.shelf_settings["primary_order"].append(name)
            
            order = self.shelf_settings["primary_order"]
            self.primary_buttons.sort(key=lambda b: order.index(b.property("original_text")) if b.property("original_text") in order else 9999)
            
            # Remove buttons from layout without affecting their properties
            for btn in self.primary_buttons:
                self.primary_layout.removeWidget(btn)
            
            # Re-add buttons in new order
            for btn in self.primary_buttons:
                self.primary_layout.addWidget(btn)
            # Don't add stretch here - it causes too much space before arrow
        else:
            # Clean up order list to only include existing buttons
            existing_names = [btn.property("original_text") for btn in self.secondary_buttons]
            self.shelf_settings["secondary_order"] = [name for name in self.shelf_settings["secondary_order"] if name in existing_names]
            
            # Add any new buttons not in the order to the end
            for name in existing_names:
                if name not in self.shelf_settings["secondary_order"]:
                    self.shelf_settings["secondary_order"].append(name)
            
            order = self.shelf_settings["secondary_order"]
            self.secondary_buttons.sort(key=lambda b: order.index(b.property("original_text")) if b.property("original_text") in order else 9999)
            
            # Secondary buttons are in the options window
            if self.options_window:
                # Clear the entire layout first to remove stretch
                while self.options_window.secondary_layout.count():
                    item = self.options_window.secondary_layout.takeAt(0)
                    if item.widget() and item.widget() in self.secondary_buttons:
                        # Don't delete the button widgets, just remove from layout
                        pass
                
                # Re-add buttons in new order
                for btn in self.secondary_buttons:
                    self.options_window.secondary_layout.addWidget(btn)
                
                # Add stretch at the end
                self.options_window.secondary_layout.addStretch()
            
        # Save the cleaned up order lists
        self.save_shelf_settings()
        
        # Refresh button labels to ensure proper sizing
        self.update_all_button_labels()
        
        self.adjustSize()
        # Maintain consistent window width  
        desired_width = max(450, self.sizeHint().width())
        self.resize(desired_width, self.sizeHint().height())
    def toggle_options_group(self):
        if not self.options_window:
            self.options_window = OptionsWindow(self)
            self.options_window.update_time_labels()
            
        if not self.options_window.isVisible():
            self.options_window.update_time_labels()  # Update time labels
            # Clear and repopulate secondary buttons in the options window
            self.populate_options_window_buttons()
            # Force update of all button appearances after showing the window
            self.update_all_button_labels()
            self.options_window.show()
            self.toggle_button.setText("→")
        else:
            self.options_window.hide()
            self.toggle_button.setText("↓")
    
    def populate_options_window_buttons(self):
        """Populate options window with existing secondary buttons"""
        if not self.options_window:
            return
            
        # Clear existing layout including stretch
        while self.options_window.secondary_layout.count():
            item = self.options_window.secondary_layout.takeAt(0)
            # This will remove both widgets and stretch items
        
        # Sort secondary buttons according to saved order
        order = self.shelf_settings["secondary_order"]
        self.secondary_buttons.sort(key=lambda b: order.index(b.property("original_text")) if b.property("original_text") in order else 9999)
        
        # Get current icon mode settings from checkbox if available
        use_icons = self.shelf_settings.get("use_icons", False)
        if hasattr(self.options_window, 'checkbox'):
            # Make sure checkbox matches the shelf settings
            self.options_window.checkbox.setChecked(use_icons)
        
        # Add existing secondary buttons to the options window
        for btn in self.secondary_buttons:
            btn.setParent(self.options_window)  # Ensure proper parent
            self.options_window.secondary_layout.addWidget(btn)
            # Ensure button has correct icon mode flag
            btn.set_icon_mode(use_icons)
            # Update button appearance based on current mode
            self.update_button_appearance(btn, True)
        
        self.options_window.secondary_layout.addStretch()
        
        # Force layout update
        self.options_window.secondary_layout.invalidate()
        self.options_window.secondary_layout.update()
        
    def update_all_button_labels(self):
        use_icons = self.shelf_settings.get("use_icons", False)
        if self.options_window and hasattr(self.options_window, 'checkbox'):
            use_icons = self.options_window.checkbox.isChecked()
            # Ensure shelf settings match checkbox state
            self.shelf_settings["use_icons"] = use_icons
        
        # Update all primary buttons
        for btn in self.primary_buttons:
            btn.set_icon_mode(use_icons)
            self.update_button_appearance(btn, False)
        
        # Update all secondary buttons
        for btn in self.secondary_buttons:
            btn.set_icon_mode(use_icons)
            self.update_button_appearance(btn, True)
        
        # Force the primary layout to recalculate its size
        self.primary_layout.invalidate()
        self.primary_layout.update()
        
        self.adjustSize()
        # Maintain consistent window width  
        desired_width = max(450, self.sizeHint().width())
        self.resize(desired_width, self.sizeHint().height())
    def on_timer_tick(self):
        self.time_tracker.log_time(LOG_INTERVAL // 1000)
        self.update_time_labels()
    def update_time_labels(self):
        times = self.time_tracker.get_times_report()
        display_name = format_filename(times["file"])
        # Pass the time data to the options window if it exists
        if self.options_window:
            self.options_window.update_time_labels()
    def show_time_report(self):
        # Use FixedTimeReportWindow so that parent's timer is restarted properly.
        report_window = FixedTimeReportWindow(self, self.log_timer, self.time_tracker)
        report_window.exec_()
    def run_script(self, script_path):
        try:
            with open(script_path, 'r', encoding='utf-8') as file:
                exec(file.read(), {'__name__': '__main__', '__file__': script_path})
        except UnicodeDecodeError:
            pyfbsdk.FBMessageBox("Encoding Error", f"Error decoding {script_path}. Ensure it's saved as UTF-8.", "OK")
        except Exception as e:
            pyfbsdk.FBMessageBox("Script Error", f"Error executing {script_path}: {str(e)}", "OK")
    def load_shelf_settings(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        if os.path.exists(SHELF_SETTINGS_FILE):
            try:
                with open(SHELF_SETTINGS_FILE, "r") as f:
                    self.shelf_settings = json.load(f)
            except Exception:
                self.shelf_settings = {}
        else:
            self.shelf_settings = {}
        defaults = {
            "use_icons": False,
            "script_assignments": {},
            "primary_order": [],
            "secondary_order": []
        }
        for key, value in defaults.items():
            if key not in self.shelf_settings:
                self.shelf_settings[key] = value
    def save_shelf_settings(self):
        if not os.path.exists(SAVE_BASE_DIR):
            os.makedirs(SAVE_BASE_DIR)
        with open(SHELF_SETTINGS_FILE, "w") as f:
            json.dump(self.shelf_settings, f, indent=4)
    def closeEvent(self, event):
        self.log_timer.stop()
        add_to_python_tools_menu()
        event.accept()

# =============================================================================
# Global Functions for ScriptShelf
# =============================================================================
def show_shelf():
    global shelf_window
    try:
        shelf_window.close()
    except Exception:
        pass
    # Get the MotionBuilder main window as parent
    mb_parent = get_motionbuilder_main_window()
    shelf_window = ScriptShelf(parent=mb_parent)
    shelf_window.show()
    shelf_window.move_to_top_center()

def add_to_python_tools_menu():
    menu_mgr = pyfbsdk.FBMenuManager()
    menu_name = "Python Tools"
    submenu_name = "Open Script Shelf"
    def on_menu_click(control, event):
        show_shelf()
    if not menu_mgr.GetMenu(menu_name):
        menu_mgr.InsertAfter(None, menu_name)
    menu = menu_mgr.GetMenu(menu_name)
    if menu:
        for i in range(menu.GetDstCount()):
            if menu.GetDstLabel(i) == submenu_name:
                menu.Remove(i)
                break
        menu.InsertLast(submenu_name, 0)
        menu.OnMenuActivate.Add(on_menu_click)

# =============================================================================
# FixedTimeReportWindow (to restart parent's timer without error)
# =============================================================================
class FixedTimeReportWindow(TimeReportWindow):
    def closeEvent(self, event):
        if self.parent_timer and not self.parent_timer.isActive():
            self.parent_timer.start()
        event.accept()

# =============================================================================
# Start the Application
# =============================================================================
show_shelf()