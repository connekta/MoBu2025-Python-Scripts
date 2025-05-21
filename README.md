# MotionBuilder 2025 Python Scripts

This repository contains my custom Python scripts for Autodesk MotionBuilder 2025.
I've used ClaudeAI to assist me in creating these, so I'm not really the author of this. It's just scripts I've needed for my own workflows.

## Scripts Overview

- **StartupScriptShelf.py** - Custom shelf configuration 
- **Characterize.py** - Character setup and characterization. 
- **Controlify.py** - Control rig creation and management
- **FBXbatchImporter.py** - Batch import FBX files
- **FBXexporter.py** - Custom FBX exporter with take management
- **RigImporter.py** - Rig import utilities
- **TakeHandler.py** - Take management and manipulation
- **TakeRenamer.py** - Batch rename takes
- **fileOpen.py** - File opening utilities
- **FileBrowser/** - Custom file browser module related to fileOpen.py

## Scripts Explanation

- **StartupScriptShelf.py**
<img width="845" alt="image" src="https://github.com/user-attachments/assets/b90fbf6b-b2f6-465b-8222-1e5631f30f3c" />

**Move this to new folder if you want it to run on startup**
Adding all scripts within the folder "PythonCustomScripts" to the top center of Motionbuilder, next to the help-dropdown menu. Also has options to show Name or icons, and it also has an extra window that can be opened with additional buttons from other folders or manually moved there by right-clicking. Also has a Time tracker per file open, with statistics per day and so on if clicked.

It looks for icons with the same name as the script in the folder "C:\Program Files\Autodesk\MotionBuilder 2025\bin\config\**PythonScriptIcons**"

- **Characterize.py**

Oneclick set up HIK rig + characterize it, based on HIK templates of joint to rig names found in: C:\Users\[USER]\AppData\Roaming\Autodesk\HIKCharacterizationTool6\template\HIK.xml - Either change the values here or add your own template and link it.
- **Controlify.py**

![image](https://github.com/user-attachments/assets/d10959a9-431f-4e9f-aff5-fe79695b62bc)


Quick setup for Controls outside of HIK. Support for Parent, Aim, Position and Rotation Constraints. It will create a Marker with the set shape and size for each selected object - and then set up the correct null-hierarchy and constraints. Option to add offset either at creation or if selecting already created marker and then pressing Manual Offset button.
- **FBXbatchImporter.py**

Made in order to Merge all the animations in a folder onto the rig - WITH the take name being what the FBX is named.
- **FBXexporter.py**

![image](https://github.com/user-attachments/assets/4e0e3073-52f2-4b4b-9d95-738c488c4d5b)

Better handling for exporting the skeleton for takes selected through the UI. Supports adding export prefix, different export paths per take group, Axis conversion between Y and Z up. Only exports the joints in the character skeleton. Remembers export paths and exported takes between sessions.
- **RigImporter.py**

![image](https://github.com/user-attachments/assets/95f4ad12-2fc1-41cf-a983-607067dceb3d)

Simple Rig import UI. Save rig files with image in a list for easier import instead of having to manually find the right file and import it. Sort by groups, and take the image straight from Motionbuilder when adding the rig, or manually right click and take image.
- **TakeHandler.py**

![image](https://github.com/user-attachments/assets/6fe7dabe-0999-4b8b-b2ce-7bbd284fed31)

A separate minimalistic window for handling takes. Supports everything normal takes-window does, re-ordering (and mirrors order into base mobu as well), adding groups that can be folded/unfolded, favourites and color tagging. 
- **TakeRenamer.py**

![image](https://github.com/user-attachments/assets/c68d8738-b701-4624-9901-5ed06d7401da)

A more extensive setup for renaming a lot of takes. Supports adding Prefix/Suffix, adding numberings, simple renaming and Find and Replace. 
- **fileOpen.py**

![image](https://github.com/user-attachments/assets/3bbd4351-b5ee-4af3-a632-e82d883637de)

A more focused File opener where you can add manual Directories for it to show as a folder-structure to search within - instead of having the full system. Also supports adding files as favourites and shows recent files. Has a Search button that will only show .fbx files from within the added directories.

## Known Bugs

- TakeHandler's duplicate doesn't properly duplicate the take but instead just creates a new take with that set name.

## Requirements

- Autodesk MotionBuilder 2025
- Python 3.11 (included with MotionBuilder 2025)
- PySide6 (included with MotionBuilder 2025)

## Installation

1. Clone this repository to your MotionBuilder scripts folder:
   ```
   C:\Program Files\Autodesk\MotionBuilder 2025\bin\config\PythonCustomScripts
   ```
2. If you want the StartupScriptShelf to open on startup move it to bin\config\PythonStartup

3. Restart MotionBuilder or reload Python scripts

## Usage

Scripts can be executed from:
- MotionBuilder's Python Editor
- Custom shelf buttons
- Python console

## Saved Data

I'm writing a bunch of .json files to this location to save data in between sessions:
C:\Users\[USER]\Documents\MB\CustomPythonSaveData

## Contributing

Feel free to submit issues and enhancement requests!

## License

I dont know? I'm not really sharing this - but I also didn't really "make" it either so.. 🤷‍♂️
