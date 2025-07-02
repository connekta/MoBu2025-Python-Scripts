import os
import json
import sys
from datetime import datetime, timedelta
from PySide6 import QtWidgets, QtCore, QtGui
from pyfbsdk import FBSystem, FBApplication

# Add the current directory to the path to find options_dialog
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from options_dialog import OptionsDialog

class MotionBuilderFileBrowser(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(MotionBuilderFileBrowser, self).__init__(parent)
        
        # Constants
        self.SAVE_BASE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "MB", "CustomPythonSaveData")
        self.RECENT_FILES_JSON = os.path.join(self.SAVE_BASE_DIR, "recent_files.json")
        self.FAVORITES_JSON = os.path.join(self.SAVE_BASE_DIR, "favorite_files.json")
        self.FAVORITE_FOLDERS_JSON = os.path.join(self.SAVE_BASE_DIR, "favorite_folders.json")
        self.HIDDEN_FOLDERS_JSON = os.path.join(self.SAVE_BASE_DIR, "hidden_folders.json")
        self.FOLDER_DISPLAY_NAMES_JSON = os.path.join(self.SAVE_BASE_DIR, "folder_display_names.json")
        self.ROOT_DIRECTORIES_JSON = os.path.join(self.SAVE_BASE_DIR, "root_directories.json")
        self.MAX_RECENT_FILES = 5
        
        # Create save directory if it doesn't exist
        if not os.path.exists(self.SAVE_BASE_DIR):
            os.makedirs(self.SAVE_BASE_DIR)
        
        # Load configurations
        self.favorites = self.loadFavorites()
        self.favoriteFolders = self.loadFavoriteFolders()
        self.hiddenFolders = self.loadHiddenFolders()
        self.folderDisplayNames = self.loadFolderDisplayNames()
        self.rootDirectories = self.loadRootDirectories()
        
        # Show hidden folders flag
        self.showHiddenFolders = False
        
        
        # Setup UI with dark mode style
        self.setWindowTitle("File Browser")
        self.setMinimumSize(450, 500)
        self.setupUI()
        self.loadRecentAndFavoriteFiles()
        
        # Expand all favourite folders by default
        for fav_folder in self.favoriteFolders:
            if os.path.exists(fav_folder):
                self.expandTreeToPath(fav_folder)
    
    def setupUI(self):
        # Use dark mode style sheet, with gold selection for list items
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #dcdcdc;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 1.5ex;
                padding-top: 1ex;
                background-color: #3c3c3c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
            QPushButton {
                border: 1px solid #666;
                border-radius: 4px;
                padding: 4px 12px;
                background-color: #4c4c4c;
                color: #dcdcdc;
            }
            QPushButton:hover {
                background-color: #5c5c5c;
            }
            QPushButton:pressed {
                background-color: #3c3c3c;
            }
            QLineEdit {
                border: 1px solid #666;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #3c3c3c;
                color: #dcdcdc;
            }
            QTreeWidget, QListWidget {
                border: 1px solid #555;
                border-radius: 2px;
                background-color: #3c3c3c;
                color: #dcdcdc;
            }
            /* Default (unselected) list items use the same dark background */
            QListWidget::item {
                background-color: #3c3c3c;
                color: #dcdcdc;
            }
            /* Selected items get a soft gold color */
            QListWidget::item:selected {
                background-color: #FAF5D7;
                color: #3c3c3c;
            }
        """)
        
        # Main layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Splitter for folder tree and recent files
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        
        # Folder structure group
        folderGroup = QtWidgets.QGroupBox("Folder Structure")
        folderLayout = QtWidgets.QVBoxLayout(folderGroup)
        folderLayout.setContentsMargins(8, 14, 8, 8)
        
        # Search field layout
        searchLayout = QtWidgets.QHBoxLayout()
        searchLayout.setSpacing(6)
        
        searchIcon = QtWidgets.QLabel("🔍")
        searchLayout.addWidget(searchIcon)
        
        self.searchField = QtWidgets.QLineEdit()
        self.searchField.setPlaceholderText("Search for .FBX files...")
        self.searchField.textChanged.connect(self.onSearchTextChanged)
        
        searchLayout.addWidget(self.searchField)
        folderLayout.addLayout(searchLayout)
        
        # Folder tree widget
        self.folderTree = QtWidgets.QTreeWidget()
        self.folderTree.setHeaderHidden(True)
        self.folderTree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.folderTree.customContextMenuRequested.connect(self.showFolderContextMenu)
        self.folderTree.itemClicked.connect(self.onFolderTreeItemClicked)
        self.folderTree.itemDoubleClicked.connect(self.onFolderTreeItemDoubleClicked)
        self.folderTree.itemExpanded.connect(self.onFolderTreeItemExpanded)
        self.folderTree.setAnimated(True)
        self.folderTree.setIndentation(20)
        folderLayout.addWidget(self.folderTree)
        
        # Recent files group
        recentGroup = QtWidgets.QGroupBox("Favorites & Recent Files")
        recentLayout = QtWidgets.QVBoxLayout(recentGroup)
        recentLayout.setContentsMargins(8, 14, 8, 8)
        
        self.recentFilesListWidget = QtWidgets.QListWidget()
        self.recentFilesListWidget.setAlternatingRowColors(False)
        self.recentFilesListWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.recentFilesListWidget.doubleClicked.connect(self.openRecentFile)
        self.recentFilesListWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.recentFilesListWidget.customContextMenuRequested.connect(self.showRecentFilesContextMenu)
        self.recentFilesListWidget.setIconSize(QtCore.QSize(16, 16))
        
        # Allow deselection by clicking on empty space
        self.recentFilesListWidget.viewport().installEventFilter(self)
        
        recentLayout.addWidget(self.recentFilesListWidget)
        
        # Add widgets to splitter
        self.splitter.addWidget(folderGroup)
        self.splitter.addWidget(recentGroup)
        self.splitter.setSizes([350, 150])
        
        # Buttons layout
        buttonLayout = QtWidgets.QHBoxLayout()
        buttonLayout.setSpacing(10)
        
        self.openButton = QtWidgets.QPushButton("Open")
        self.openButton.setMinimumWidth(80)
        self.openButton.setDefault(True)
        self.openButton.clicked.connect(self.openSelectedFile)
        
        self.optionsButton = QtWidgets.QPushButton("⚙️ Options")
        self.optionsButton.clicked.connect(self.showOptionsDialog)
        
        # Eye button made slightly larger so it doesn’t get cut off
        self.toggleHiddenButton = QtWidgets.QPushButton("👁️")
        self.toggleHiddenButton.setFixedSize(32, 32)
        self.toggleHiddenButton.setToolTip("Toggle hidden folders")
        self.toggleHiddenButton.clicked.connect(self.toggleHiddenFolders)
        
        self.closeButton = QtWidgets.QPushButton("Close")
        self.closeButton.setMinimumWidth(80)
        self.closeButton.clicked.connect(self.close)
        
        buttonLayout.addWidget(self.openButton)
        buttonLayout.addWidget(self.optionsButton)
        buttonLayout.addStretch()
        buttonLayout.addWidget(self.toggleHiddenButton)
        buttonLayout.addWidget(self.closeButton)
        
        layout.addWidget(self.splitter)
        layout.addLayout(buttonLayout)
        
        # Initialize folder tree
        self.populateRootFolders()
    
    # ---------------------------------------------------------
    # Event filter to allow deselecting items by clicking empty space
    # ---------------------------------------------------------
    def eventFilter(self, source, event):
        if (source == self.recentFilesListWidget.viewport() and 
            event.type() == QtCore.QEvent.MouseButtonPress):
            item = self.recentFilesListWidget.itemAt(event.pos())
            if not item:
                self.recentFilesListWidget.clearSelection()
        return super(MotionBuilderFileBrowser, self).eventFilter(source, event)
    
    # ---------------------------------------------------------
    # Load / Save Root Directories
    # ---------------------------------------------------------
    def loadRootDirectories(self):
        default_dirs = [
            r"C:\Morris\Gamedev\UnrealEngine_AssetPack_Exports",
            r"C:\Morris\Gamedev\P4VDepot\Source_offlineArt",
            r"C:\Morris\Gamedev\P4VDepot\Source_Content"
        ]
        if os.path.exists(self.ROOT_DIRECTORIES_JSON):
            try:
                with open(self.ROOT_DIRECTORIES_JSON, 'r') as f:
                    root_dirs = json.load(f)
                return root_dirs
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading root directories: {e}")
        try:
            with open(self.ROOT_DIRECTORIES_JSON, 'w') as f:
                json.dump(default_dirs, f)
        except IOError as e:
            print(f"Error saving root directories: {e}")
        return default_dirs
    
    def saveRootDirectories(self, directories):
        try:
            with open(self.ROOT_DIRECTORIES_JSON, 'w') as f:
                json.dump(directories, f)
            self.rootDirectories = directories
        except IOError as e:
            print(f"Error saving root directories: {e}")
    
    # ---------------------------------------------------------
    # Load / Save Folder Display Names
    # ---------------------------------------------------------
    def loadFolderDisplayNames(self):
        display_names = {}
        if os.path.exists(self.FOLDER_DISPLAY_NAMES_JSON):
            try:
                with open(self.FOLDER_DISPLAY_NAMES_JSON, 'r') as f:
                    display_names = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading folder display names: {e}")
        return display_names
    
    def saveFolderDisplayNames(self):
        try:
            with open(self.FOLDER_DISPLAY_NAMES_JSON, 'w') as f:
                json.dump(self.folderDisplayNames, f)
        except IOError as e:
            print(f"Error saving folder display names: {e}")
    
    def renameFolderDisplay(self, folder_path, new_name):
        self.folderDisplayNames[folder_path] = new_name
        self.saveFolderDisplayNames()
        self.refreshFolderTree()
    
    # ---------------------------------------------------------
    # Options Dialog
    # ---------------------------------------------------------
    def showOptionsDialog(self):
        dialog = OptionsDialog(self.rootDirectories, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            updated_dirs = dialog.getRootDirectories()
            self.saveRootDirectories(updated_dirs)
            self.populateRootFolders()
    
    # ---------------------------------------------------------
    # Hidden Folders
    # ---------------------------------------------------------
    def toggleHiddenFolders(self):
        self.showHiddenFolders = not self.showHiddenFolders
        if self.showHiddenFolders:
            self.toggleHiddenButton.setText("👁️‍🗨️")
        else:
            self.toggleHiddenButton.setText("👁️")
        self.refreshFolderTree()
    
    def loadHiddenFolders(self):
        hidden_folders = []
        if os.path.exists(self.HIDDEN_FOLDERS_JSON):
            try:
                with open(self.HIDDEN_FOLDERS_JSON, 'r') as f:
                    hidden_folders = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading hidden folders: {e}")
        return hidden_folders
    
    def saveHiddenFolders(self):
        try:
            with open(self.HIDDEN_FOLDERS_JSON, 'w') as f:
                json.dump(self.hiddenFolders, f)
        except IOError as e:
            print(f"Error saving hidden folders: {e}")
    
    def hideFolder(self, folder_path):
        if folder_path not in self.hiddenFolders:
            self.hiddenFolders.append(folder_path)
            self.saveHiddenFolders()
            self.refreshFolderTree()
    
    # ---------------------------------------------------------
    # Refresh Folder Tree
    # ---------------------------------------------------------
    def refreshFolderTree(self):
        expanded_paths = []
        for i in range(self.folderTree.topLevelItemCount()):
            top_item = self.folderTree.topLevelItem(i)
            if top_item.isExpanded():
                expanded_paths.append(top_item.data(0, QtCore.Qt.UserRole))
                self.collectExpandedItems(top_item, expanded_paths)
        self.populateRootFolders()
        if expanded_paths:
            for i in range(self.folderTree.topLevelItemCount()):
                top_item = self.folderTree.topLevelItem(i)
                path = top_item.data(0, QtCore.Qt.UserRole)
                if path in expanded_paths:
                    top_item.setExpanded(True)
                    self.expandChildItems(top_item, expanded_paths)
    
    def collectExpandedItems(self, parent_item, expanded_paths):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.childCount() > 0 and child.isExpanded():
                path = child.data(0, QtCore.Qt.UserRole)
                if path:
                    expanded_paths.append(path)
                    self.collectExpandedItems(child, expanded_paths)
    
    def expandChildItems(self, parent_item, expanded_paths):
        self.populateFolderItem(parent_item)
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            path = child.data(0, QtCore.Qt.UserRole)
            if path in expanded_paths:
                child.setExpanded(True)
                self.expandChildItems(child, expanded_paths)
    
    # ---------------------------------------------------------
    # Search Logic
    # ---------------------------------------------------------
    def onSearchTextChanged(self, text):
        """Search only from the selected folder (and its children).
           If no folder is selected, search from all root directories.
           Only starts searching after 2+ characters to avoid performance issues."""
        if text and len(text) > 2:
            self.folderTree.clear()
            self.performSearch(text.lower())
        elif not text:
            self.refreshFolderTree()
        # If text length is 1-2 characters, do nothing (keep current tree state)
    
    def performSearch(self, search_text):
        selected_items = self.folderTree.selectedItems()
        if selected_items:
            # Search only in the selected folder
            folder_path = selected_items[0].data(0, QtCore.Qt.UserRole)
            if folder_path and os.path.isdir(folder_path):
                self.searchDirectory(folder_path, search_text)
        else:
            # No folder selected; search all root directories
            for root_path in self.rootDirectories:
                if os.path.exists(root_path):
                    self.searchDirectory(root_path, search_text)
    
    def searchDirectory(self, directory, search_text):
        """Optimized search: only returns .FBX files using os.scandir for speed."""
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    entry_path = os.path.join(directory, entry.name)
                    
                    # Skip hidden folders unless showing
                    if entry.is_dir() and entry_path in self.hiddenFolders and not self.showHiddenFolders:
                        continue
                    # Skip known “junk” folders
                    if entry.is_dir() and (
                        entry.name.endswith('.fbm') or
                        entry.name.endswith('.bck') or
                        entry.name.endswith('.mayaSwatches')
                    ):
                        continue
                    
                    if entry.is_dir():
                        self.searchDirectory(entry_path, search_text)
                    elif entry.is_file() and entry.name.lower().endswith('.fbx'):
                        if search_text in entry.name.lower():
                            file_item = QtWidgets.QTreeWidgetItem(self.folderTree)
                            file_item.setText(0, self.formatFileName(entry.name))
                            file_item.setData(0, QtCore.Qt.UserRole, entry_path)
                            file_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
        except Exception as e:
            print(f"Error searching directory {directory}: {e}")
    
    # ---------------------------------------------------------
    # Folder Tree Population
    # ---------------------------------------------------------
    def populateRootFolders(self):
        self.folderTree.clear()
        for root_path in self.rootDirectories:
            if os.path.exists(root_path):
                root_item = QtWidgets.QTreeWidgetItem(self.folderTree)
                text = self.getFolderDisplayName(root_path)
                # Prepend a star if this folder is favourited
                if root_path in self.favoriteFolders and not text.startswith("★"):
                    text = "★ " + text
                root_item.setText(0, text)
                root_item.setData(0, QtCore.Qt.UserRole, root_path)
                dummy = QtWidgets.QTreeWidgetItem(root_item)
                dummy.setText(0, "Loading...")
    
    def populateFolderItem(self, item):
        folder_path = item.data(0, QtCore.Qt.UserRole)
        while item.childCount() > 0:
            item.removeChild(item.child(0))
        try:
            for entry in os.listdir(folder_path):
                entry_path = os.path.join(folder_path, entry)
                
                # Skip hidden
                if entry_path in self.hiddenFolders and not self.showHiddenFolders:
                    continue
                # Skip “junk” folders
                if (entry.endswith('.fbm') or
                    entry.endswith('.bck') or
                    entry.endswith('.mayaSwatches')):
                    continue
                
                if os.path.isdir(entry_path):
                    folder_item = QtWidgets.QTreeWidgetItem(item)
                    text = self.getFolderDisplayName(entry_path)
                    if entry_path in self.favoriteFolders and not text.startswith("★"):
                        text = "★ " + text
                    folder_item.setText(0, text)
                    folder_item.setData(0, QtCore.Qt.UserRole, entry_path)
                    
                    has_children = False
                    try:
                        for subentry in os.listdir(entry_path):
                            subentry_path = os.path.join(entry_path, subentry)
                            if (os.path.isdir(subentry_path) or 
                                (os.path.isfile(subentry_path) and subentry.lower().endswith('.fbx'))):
                                has_children = True
                                break
                    except Exception:
                        pass
                    if has_children:
                        dummy = QtWidgets.QTreeWidgetItem(folder_item)
                        dummy.setText(0, "Loading...")
                elif os.path.isfile(entry_path) and entry.lower().endswith('.fbx'):
                    file_item = QtWidgets.QTreeWidgetItem(item)
                    file_item.setText(0, self.formatFileName(entry))
                    file_item.setData(0, QtCore.Qt.UserRole, entry_path)
                    file_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
        except Exception as e:
            print(f"Error populating folder {folder_path}: {e}")
    
    def onFolderTreeItemExpanded(self, item):
        self.populateFolderItem(item)
    
    def onFolderTreeItemClicked(self, item, column):
        path = item.data(0, QtCore.Qt.UserRole)
        if path:
            # Clear search if user navigates to a folder
            self.searchField.setText("")
    
    def onFolderTreeItemDoubleClicked(self, item, column):
        path = item.data(0, QtCore.Qt.UserRole)
        # Only open if it's a valid .fbx file
        if path and os.path.isfile(path) and path.lower().endswith('.fbx'):
            self.openFile(path)
    
    # ---------------------------------------------------------
    # Favorite Folders
    # ---------------------------------------------------------
    def loadFavoriteFolders(self):
        fav_folders = []
        if os.path.exists(self.FAVORITE_FOLDERS_JSON):
            try:
                with open(self.FAVORITE_FOLDERS_JSON, 'r') as f:
                    fav_folders = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading favorite folders: {e}")
        return fav_folders
    
    def saveFavoriteFolders(self):
        try:
            with open(self.FAVORITE_FOLDERS_JSON, 'w') as f:
                json.dump(self.favoriteFolders, f)
        except IOError as e:
            print(f"Error saving favorite folders: {e}")
    
    def toggleFavoriteFolder(self, folder_path):
        if folder_path in self.favoriteFolders:
            self.favoriteFolders.remove(folder_path)
        else:
            self.favoriteFolders.append(folder_path)
        self.saveFavoriteFolders()
        # Immediately refresh so the star appears/disappears
        self.refreshFolderTree()
        # If newly favorited, expand to it
        if folder_path in self.favoriteFolders:
            self.expandTreeToPath(folder_path)
    
    # ---------------------------------------------------------
    # Folder Context Menu
    # ---------------------------------------------------------
    def showFolderContextMenu(self, position):
        item = self.folderTree.itemAt(position)
        if not item:
            return
        path = item.data(0, QtCore.Qt.UserRole)
        menu = QtWidgets.QMenu()
        if os.path.isdir(path):
            if path in self.favoriteFolders:
                favFolderAction = menu.addAction("Remove Folder from Favorites")
            else:
                favFolderAction = menu.addAction("Add Folder to Favorites")
            hideAction = menu.addAction("Hide Folder")
            renameDisplayAction = menu.addAction("Rename Display")
            action = menu.exec(self.folderTree.mapToGlobal(position))
            if action == favFolderAction:
                self.toggleFavoriteFolder(path)
            elif action == hideAction:
                self.hideFolder(path)
            elif action == renameDisplayAction:
                self.showRenameDialog(path)
        elif os.path.isfile(path) and path.lower().endswith('.fbx'):
            if path in self.favorites:
                favoriteAction = menu.addAction("Remove from Favorites")
            else:
                favoriteAction = menu.addAction("Add to Favorites")
            action = menu.exec(self.folderTree.mapToGlobal(position))
            if action == favoriteAction:
                self.toggleFavorite(path)
    
    def showRenameDialog(self, folder_path):
        current_name = self.getFolderDisplayName(folder_path)
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, 
            "Rename Display", 
            "Enter display name for folder:", 
            QtWidgets.QLineEdit.Normal, 
            current_name
        )
        if ok and new_name:
            self.renameFolderDisplay(folder_path, new_name)
    
    def getFolderDisplayName(self, folder_path):
        return self.folderDisplayNames.get(folder_path, os.path.basename(folder_path))
    
    # ---------------------------------------------------------
    # Files
    # ---------------------------------------------------------
    def formatFileName(self, fileName):
        if fileName.lower().endswith('.fbx'):
            fileName = fileName[:-4]
        return fileName.replace('_', ' ')
    
    # ---------------------------------------------------------
    # Favorites & Recent Files
    # ---------------------------------------------------------
    def loadFavorites(self):
        favorites = []
        if os.path.exists(self.FAVORITES_JSON):
            try:
                with open(self.FAVORITES_JSON, 'r') as f:
                    favorites = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading favorites: {e}")
        return favorites
    
    def saveFavorites(self):
        try:
            with open(self.FAVORITES_JSON, 'w') as f:
                json.dump(self.favorites, f)
        except IOError as e:
            print(f"Error saving favorites: {e}")
    
    def toggleFavorite(self, file_path):
        if file_path in self.favorites:
            self.favorites.remove(file_path)
        else:
            self.favorites.append(file_path)
        self.saveFavorites()
        self.loadRecentAndFavoriteFiles()
    
    def loadRecentAndFavoriteFiles(self):
        self.recentFilesListWidget.clear()
        recent_files = []
        
        # Safely load from JSON, skipping None entries
        if os.path.exists(self.RECENT_FILES_JSON):
            try:
                with open(self.RECENT_FILES_JSON, 'r') as f:
                    all_recent = json.load(f)
                # Filter out any None or invalid paths
                recent_files = [r for r in all_recent if isinstance(r, str)]
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading recent files: {e}")
        
        # Favorites header for files
        valid_favorites = [p for p in self.favorites if p and os.path.exists(p)]
        if valid_favorites:
            header_favorites = QtWidgets.QListWidgetItem("FAVORITES")
            header_favorites.setFlags(QtCore.Qt.NoItemFlags)
            header_favorites.setBackground(QtGui.QColor(60, 60, 80))
            header_favorites.setForeground(QtGui.QColor(255, 255, 255))
            font = QtGui.QFont()
            font.setBold(True)
            header_favorites.setFont(font)
            self.recentFilesListWidget.addItem(header_favorites)
            
            for file_path in valid_favorites:
                display_name = f"★  {self.formatFileName(os.path.basename(file_path))}"
                item = QtWidgets.QListWidgetItem(display_name)
                item.setData(QtCore.Qt.UserRole, file_path)
                item.setToolTip(file_path)
                item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                self.recentFilesListWidget.addItem(item)
        
        # Filter out any None or invalid paths from recent
        filtered_recent = [r for r in recent_files if r not in self.favorites and r and os.path.exists(r)]
        
        if filtered_recent:
            header_recent = QtWidgets.QListWidgetItem("RECENT FILES")
            header_recent.setFlags(QtCore.Qt.NoItemFlags)
            header_recent.setBackground(QtGui.QColor(60, 60, 80))
            header_recent.setForeground(QtGui.QColor(255, 255, 255))
            font = QtGui.QFont()
            font.setBold(True)
            header_recent.setFont(font)
            self.recentFilesListWidget.addItem(header_recent)
            
            count = 0
            for file_path in filtered_recent:
                if count >= self.MAX_RECENT_FILES:
                    break
                display_name = self.formatFileName(os.path.basename(file_path))
                item = QtWidgets.QListWidgetItem(display_name)
                item.setData(QtCore.Qt.UserRole, file_path)
                item.setToolTip(file_path)
                item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                self.recentFilesListWidget.addItem(item)
                count += 1
        
        if self.recentFilesListWidget.count() == 0:
            msg_item = QtWidgets.QListWidgetItem("No recent or favorite files")
            msg_item.setFlags(QtCore.Qt.NoItemFlags)
            msg_item.setForeground(QtGui.QColor(120, 120, 120))
            font = QtGui.QFont()
            font.setItalic(True)
            msg_item.setFont(font)
            self.recentFilesListWidget.addItem(msg_item)
    
    def showRecentFilesContextMenu(self, position):
        menu = QtWidgets.QMenu()
        selected_items = self.recentFilesListWidget.selectedItems()
        if not selected_items:
            return
        file_path = selected_items[0].data(QtCore.Qt.UserRole)
        
        # If there's no valid path, do nothing
        if not file_path:
            return
        
        # Toggle favorite
        if file_path in self.favorites:
            favoriteAction = menu.addAction("Remove from Favorites")
        else:
            favoriteAction = menu.addAction("Add to Favorites")
        
        # Remove from recent list
        removeAction = menu.addAction("Remove from List")
        
        action = menu.exec(self.recentFilesListWidget.mapToGlobal(position))
        if action == favoriteAction:
            self.toggleFavorite(file_path)
        elif action == removeAction:
            self.removeRecentFile(file_path)
    
    def removeRecentFile(self, file_path):
        try:
            if os.path.exists(self.RECENT_FILES_JSON):
                with open(self.RECENT_FILES_JSON, 'r') as f:
                    recent_files = json.load(f)
            else:
                recent_files = []
            if file_path in recent_files:
                recent_files.remove(file_path)
            with open(self.RECENT_FILES_JSON, 'w') as f:
                json.dump(recent_files, f)
            self.loadRecentAndFavoriteFiles()
        except Exception as e:
            print(f"Error removing recent file: {e}")
    
    def saveRecentFiles(self, file_path=None):
        """Save the list of recent files, ignoring any invalid or None paths."""
        recent_files = []
        if file_path and isinstance(file_path, str) and os.path.exists(file_path):
            recent_files.append(file_path)
        
        for i in range(self.recentFilesListWidget.count()):
            item = self.recentFilesListWidget.item(i)
            existing_path = item.data(QtCore.Qt.UserRole)
            if (existing_path 
                and existing_path != file_path 
                and existing_path not in self.favorites 
                and os.path.exists(existing_path)):
                recent_files.append(existing_path)
        
        # Trim to maximum number of recent files
        recent_files = recent_files[:self.MAX_RECENT_FILES]
        
        try:
            with open(self.RECENT_FILES_JSON, 'w') as f:
                json.dump(recent_files, f)
        except IOError as e:
            print(f"Error saving recent files: {e}")
        
        self.loadRecentAndFavoriteFiles()
    
    # ---------------------------------------------------------
    # Opening Files
    # ---------------------------------------------------------
    def openRecentFile(self):
        selected_items = self.recentFilesListWidget.selectedItems()
        if not selected_items:
            return
        file_path = selected_items[0].data(QtCore.Qt.UserRole)
        self.openFile(file_path)
    
    def openSelectedFile(self):
        selected_items = self.folderTree.selectedItems()
        if selected_items:
            path = selected_items[0].data(0, QtCore.Qt.UserRole)
            if path and os.path.isfile(path) and path.lower().endswith('.fbx'):
                self.openFile(path)
                return
        self.openRecentFile()
    
    def getCurrentFileName(self):
        """Get the current scene filename."""
        try:
            app = FBApplication()
            return app.FBXFileName if app.FBXFileName else None
        except Exception:
            return None
    
    def getSceneObjectCount(self):
        """Get count of objects in scene hierarchy (excluding root)."""
        try:
            system = FBSystem()
            return len(system.Scene.RootModel.Children)
        except Exception:
            return 0
    
    def getFileLastSavedTime(self, file_path):
        """Get when a file was last saved."""
        try:
            if file_path and os.path.exists(file_path):
                return datetime.fromtimestamp(os.path.getmtime(file_path))
        except Exception:
            pass
        return None
    
    def formatTimeSince(self, time_delta):
        """Format time elapsed in a readable way."""
        total_seconds = int(time_delta.total_seconds())
        
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 or len(parts) == 0:  # Always show minutes if it's the only unit
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        
        return ", ".join(parts)

    def shouldPromptForSave(self):
        """Check if we should prompt user about unsaved progress."""
        current_file = self.getCurrentFileName()
        
        # Case 1: New/Untitled scene
        if not current_file:
            # Check if scene has content
            if self.getSceneObjectCount() > 0:
                return True, "New/Untitled scene with content"
            else:
                return False, "Empty default scene"
        
        # Case 2: Saved file - check last save time
        last_saved = self.getFileLastSavedTime(current_file)
        if last_saved:
            time_since_save = datetime.now() - last_saved
            if time_since_save > timedelta(minutes=2):
                elapsed_text = self.formatTimeSince(time_since_save)
                formatted_time = last_saved.strftime("%Y-%m-%d %H:%M:%S")
                
                message = f"{elapsed_text} since last save\n\nLast saved at: {formatted_time}"
                return True, message
        
        return False, "Recently saved"
    
    def showUnsavedProgressDialog(self, message):
        """Show unsaved progress dialog with three options."""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("Got unsaved progress?")
        msg_box.setText(message)
        msg_box.setIcon(QtWidgets.QMessageBox.Question)
        
        # Create custom buttons
        save_and_open_btn = msg_box.addButton("Save and Open", QtWidgets.QMessageBox.AcceptRole)
        open_btn = msg_box.addButton("Open", QtWidgets.QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        
        msg_box.setDefaultButton(save_and_open_btn)
        
        # Apply dark theme to message box with centered text
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2b2b2b;
                color: #dcdcdc;
            }
            QMessageBox QLabel {
                color: #dcdcdc;
                text-align: center;
                qproperty-alignment: AlignCenter;
            }
            QMessageBox QPushButton {
                border: 1px solid #666;
                border-radius: 4px;
                padding: 6px 16px;
                background-color: #4c4c4c;
                color: #dcdcdc;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #5c5c5c;
            }
            QMessageBox QPushButton:pressed {
                background-color: #3c3c3c;
            }
        """)
        
        result = msg_box.exec_()
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == save_and_open_btn:
            return "save_and_open"
        elif clicked_button == open_btn:
            return "open"
        else:
            return "cancel"
    
    def saveCurrentScene(self):
        """Save the current scene. Returns True if successful."""
        try:
            app = FBApplication()
            current_file = self.getCurrentFileName()
            
            if current_file and os.path.exists(current_file):
                # Save existing file using FileSave with current filename
                result = app.FileSave(current_file)
                return result
            else:
                # New file - prompt for save location
                file_dialog = QtWidgets.QFileDialog()
                file_path, _ = file_dialog.getSaveFileName(
                    self, 
                    "Save Scene", 
                    "", 
                    "FBX Files (*.fbx);;All Files (*)"
                )
                if file_path:
                    if not file_path.lower().endswith('.fbx'):
                        file_path += '.fbx'
                    result = app.FileSave(file_path)
                    return result
                else:
                    return False
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Failed to save: {str(e)}")
            return False

    def openFile(self, file_path):
        # Ensure file_path is a valid string path
        if not file_path or not isinstance(file_path, (str, bytes, os.PathLike)):
            QtWidgets.QMessageBox.warning(self, "Warning", "Invalid file path.")
            return
        
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.warning(self, "Warning", f"File not found: {file_path}")
            return
        
        try:
            # Check if we should prompt about unsaved progress
            should_prompt, message = self.shouldPromptForSave()
            
            if should_prompt:
                choice = self.showUnsavedProgressDialog(message)
                
                if choice == "cancel":
                    return  # User cancelled, abort operation
                elif choice == "save_and_open":
                    # Save current scene first
                    if not self.saveCurrentScene():
                        return  # Save failed or cancelled, abort operation
                # For "open" choice, continue without saving
            
            # Open the new file
            app = FBApplication()
            app.FileOpen(file_path)
            self.saveRecentFiles(file_path)
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open file: {str(e)}")
    
    # ---------------------------------------------------------
    # Expand Tree to Path
    # ---------------------------------------------------------
    def expandTreeToPath(self, target_path):
        """Recursively expand the folder tree until the target_path is reached."""
        for i in range(self.folderTree.topLevelItemCount()):
            item = self.folderTree.topLevelItem(i)
            item_path = item.data(0, QtCore.Qt.UserRole)
            if item_path and os.path.normpath(target_path).startswith(os.path.normpath(item_path)):
                if self.expandItemToPath(item, target_path):
                    break
    
    def expandItemToPath(self, item, target_path):
        item_path = item.data(0, QtCore.Qt.UserRole)
        if os.path.normpath(item_path) == os.path.normpath(target_path):
            self.folderTree.setCurrentItem(item)
            return True
        if not item.isExpanded():
            item.setExpanded(True)
            self.populateFolderItem(item)
        for j in range(item.childCount()):
            child = item.child(j)
            child_path = child.data(0, QtCore.Qt.UserRole)
            if child_path and os.path.normpath(target_path).startswith(os.path.normpath(child_path)):
                if self.expandItemToPath(child, target_path):
                    return True
        return False
