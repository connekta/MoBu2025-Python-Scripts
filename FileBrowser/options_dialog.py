import os
from PySide6 import QtWidgets, QtCore, QtGui

class OptionsDialog(QtWidgets.QDialog):
    def __init__(self, root_directories, parent=None):
        super(OptionsDialog, self).__init__(parent)
        
        self.root_directories = root_directories.copy()
        
        self.setupUI()
        
    def setupUI(self):
        self.setWindowTitle("Options")
        self.setMinimumSize(500, 300)
        
        # Main layout
        layout = QtWidgets.QVBoxLayout(self)
        
        # Tab widget
        self.tabWidget = QtWidgets.QTabWidget()
        
        # Root directories tab
        self.rootDirTab = QtWidgets.QWidget()
        self.setupRootDirectoriesTab()
        self.tabWidget.addTab(self.rootDirTab, "Root Directories")
        
        # Add tab widget to main layout
        layout.addWidget(self.tabWidget)
        
        # Buttons
        buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | 
            QtWidgets.QDialogButtonBox.Cancel
        )
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        
        layout.addWidget(buttonBox)
    
    def setupRootDirectoriesTab(self):
        """Setup the root directories tab"""
        layout = QtWidgets.QVBoxLayout(self.rootDirTab)
        
        # List widget for root directories
        self.rootDirListWidget = QtWidgets.QListWidget()
        self.rootDirListWidget.setAlternatingRowColors(True)
        self.populateRootDirectories()
        
        # Buttons for adding/removing directories
        buttonLayout = QtWidgets.QHBoxLayout()
        
        self.addDirButton = QtWidgets.QPushButton("Add Directory")
        self.addDirButton.clicked.connect(self.addRootDirectory)
        
        self.removeDirButton = QtWidgets.QPushButton("Remove Directory")
        self.removeDirButton.clicked.connect(self.removeRootDirectory)
        
        buttonLayout.addWidget(self.addDirButton)
        buttonLayout.addWidget(self.removeDirButton)
        
        # Add widgets to layout
        layout.addWidget(QtWidgets.QLabel("Root directories to browse:"))
        layout.addWidget(self.rootDirListWidget)
        layout.addLayout(buttonLayout)
    
    def populateRootDirectories(self):
        """Populate the list widget with root directories"""
        self.rootDirListWidget.clear()
        
        for dir_path in self.root_directories:
            item = QtWidgets.QListWidgetItem(dir_path)
            # Set color based on whether the directory exists
            if not os.path.exists(dir_path):
                item.setForeground(QtGui.QColor(255, 0, 0))  # Red for non-existent paths
            self.rootDirListWidget.addItem(item)
    
    def addRootDirectory(self):
        """Add a new root directory"""
        dialog = QtWidgets.QFileDialog(self)
        dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            dirs = dialog.selectedFiles()
            if dirs:
                new_dir = dirs[0]
                # Only add if not already in the list
                if new_dir not in self.root_directories:
                    self.root_directories.append(new_dir)
                    self.populateRootDirectories()
    
    def removeRootDirectory(self):
        """Remove selected root directory"""
        selected_items = self.rootDirListWidget.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(
                self, 
                "Warning", 
                "Please select a directory to remove."
            )
            return
            
        dir_path = selected_items[0].text()
        
        # Confirm removal
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove this directory?\n\n{dir_path}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.root_directories.remove(dir_path)
            self.populateRootDirectories()
    
    def getRootDirectories(self):
        """Return the current list of root directories"""
        return self.root_directories
