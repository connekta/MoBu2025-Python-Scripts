import os
import tkinter as tk
from tkinter import filedialog
from pyfbsdk import FBApplication, FBSystem, FBMessageBox

def select_folder():
    # Create a hidden Tkinter root window
    root = tk.Tk()
    root.withdraw()
    
    # Try to get the current MotionBuilder scene file's folder.
    current_scene = FBSystem().Scene
    current_file = current_scene.FullName if current_scene and current_scene.FullName else None
    if current_file:
        initial_dir = os.path.dirname(current_file)
    else:
        initial_dir = "C:/"
    
    # Open the folder selection dialog, starting at the determined initial folder.
    folder = filedialog.askdirectory(initialdir=initial_dir, title="Select folder containing FBX files")
    root.destroy()
    return folder

def import_fbx_files(folder):
    if not os.path.isdir(folder):
        FBMessageBox("Error", "The selected folder does not exist.", "OK")
        return

    # List all .fbx files (case-insensitive)
    fbx_files = [f for f in os.listdir(folder) if f.lower().endswith(".fbx")]
    if not fbx_files:
        FBMessageBox("Info", "No FBX files found in the folder.", "OK")
        return

    for fbx_file in fbx_files:
        file_path = os.path.join(folder, fbx_file)
        # Import the FBX file as a new take.
        FBApplication().FileImport(file_path, True)
        current_take = FBSystem().CurrentTake
        new_take_name = os.path.splitext(fbx_file)[0]
        current_take.Name = new_take_name
        print("Imported and renamed take:", new_take_name)
    
    FBMessageBox("Complete", "Import process finished.", "OK")

# Main execution:
folder = select_folder()
if folder:
    response = FBMessageBox("Confirm Import", 
                            "Import all FBX files from:\n\n" + folder + "\n\nStart Import?",
                            "Yes", "No")
    if response == 1:
        import_fbx_files(folder)
else:
    FBMessageBox("Cancelled", "No folder was selected.", "OK")
