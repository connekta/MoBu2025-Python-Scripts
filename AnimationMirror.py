"""
Animation Mirror Script for MotionBuilder 2025
Mirrors HIK animations using the plot to skeleton -> mirror -> plot back workflow
"""

from pyfbsdk import *

def validate_character():
    """Validate that a character is selected and has proper HIK setup"""
    character = FBApplication().CurrentCharacter
    
    if not character:
        FBMessageBox("Error", "No character is currently selected in the Character tool.", "OK")
        return None
    
    if not character.ActiveInput:
        FBMessageBox("Error", "Character does not have an active input. Make sure HIK is properly set up.", "OK")
        return None
    
    return character

def create_mirror_take(original_take_name):
    """Create a new take for the mirrored animation"""
    new_take_name = f"{original_take_name}_Mirrored"
    
    # Check if mirror take already exists
    for take in FBSystem().Scene.Takes:
        if take.Name == new_take_name:
            # Ask user if they want to replace it
            result = FBMessageBox("Take Exists", 
                                  f"Take '{new_take_name}' already exists. Replace it?", 
                                  "Yes", "No")
            if result == 1:  # Yes
                take.FBDelete()
                break
            else:
                return None
    
    # Create new take by copying current
    new_take = FBSystem().CurrentTake.CopyTake(new_take_name)
    FBSystem().CurrentTake = new_take
    
    return new_take

def setup_plot_options():
    """Configure plot options for animation plotting"""
    plot_options = FBPlotOptions()
    plot_options.ConstantKeyReducerKeepOneKey = False
    plot_options.PlotAllTakes = False
    plot_options.PlotOnFrame = True
    plot_options.PlotPeriod = FBTime(0, 0, 0, 1)
    plot_options.PlotTranslationOnRootOnly = False
    plot_options.PreciseTimeDiscontinuities = False
    plot_options.RotationFilterToApply = FBRotationFilter.kFBRotationFilterNone
    plot_options.UseConstantKeyReducer = False
    
    return plot_options

def mirror_animation():
    """Main function to mirror the animation"""
    # Validate character
    character = validate_character()
    if not character:
        return
    
    # Store original take
    original_take = FBSystem().CurrentTake
    original_take_name = original_take.Name
    
    # Create new take for mirrored animation
    print(f"Creating mirror take from '{original_take_name}'...")
    mirror_take = create_mirror_take(original_take_name)
    if not mirror_take:
        return
    
    # Setup plot options
    plot_options = setup_plot_options()
    
    try:
        # Step 1: Plot from Control Rig to Skeleton
        print("Plotting from Control Rig to Skeleton...")
        character.PlotAnimation(FBCharacterPlotWhere.kFBCharacterPlotOnSkeleton, plot_options)
        
        # Step 2: Enable Mirror Mode
        print("Enabling Mirror Mode...")
        character.MirrorMode = True
        
        # Step 3: Plot from Skeleton back to Control Rig
        print("Plotting from Skeleton back to Control Rig...")
        character.PlotAnimation(FBCharacterPlotWhere.kFBCharacterPlotOnControlRig, plot_options)
        
        # Step 4: Disable Mirror Mode
        print("Disabling Mirror Mode...")
        character.MirrorMode = False
        
        print(f"Successfully created mirrored animation in take '{mirror_take.Name}'")
        FBMessageBox("Success", f"Animation mirrored successfully!\nNew take: {mirror_take.Name}", "OK")
        
    except Exception as e:
        # If something goes wrong, try to clean up
        character.MirrorMode = False
        FBSystem().CurrentTake = original_take
        
        error_msg = f"Error during mirroring: {str(e)}"
        print(error_msg)
        FBMessageBox("Error", error_msg, "OK")
        
        # Optionally delete the failed mirror take
        try:
            mirror_take.FBDelete()
        except:
            pass

# Run the script
if __name__ == "__main__":
    mirror_animation()