from pyfbsdk import *
import xml.etree.ElementTree as etree
import os

def get_character_template_as_dict(xmlFileName):
    xmlFilePath = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Autodesk", "HIKCharacterizationTool6", "template", xmlFileName)
    
    if not os.path.exists(xmlFilePath):
        return {}
    
    parsedXmlFile = etree.parse(xmlFilePath)
    xmlSlotNameJointDict = {}
    
    for line in parsedXmlFile.iter("item"):
        jointName = line.attrib.get("value")
        if jointName:
            slotName = line.attrib.get("key")
            xmlSlotNameJointDict[slotName] = jointName
    
    return xmlSlotNameJointDict

def find_joint_by_name(jointName):
    """Find a joint by name, handling namespaces"""
    # First try direct match (backward compatibility)
    jointObj = FBFindModelByLabelName(jointName)
    if jointObj:
        return jointObj
    
    # If not found, search through all scene components for suffix match
    # Focus on FBModelSkeleton objects (joints)
    for component in FBSystem().Scene.Components:
        if hasattr(component, 'LongName') and isinstance(component, FBModelSkeleton):
            # Extract the base name after the last colon
            baseName = component.LongName.rsplit(':', 1)[-1]
            if baseName == jointName:
                return component
    
    return None

def get_char_joint_from_slot_name(slotName):
    charSlotNameJointNameDict = get_character_template_as_dict("HIK.xml")
    charJointName = charSlotNameJointNameDict.get(slotName)
    
    if charJointName is None:
        return None
    
    charJointObj = find_joint_by_name(charJointName)
    return charJointObj

def characterize_character(characterName):
    newCharacter = FBCharacter(characterName)
    charSlotNameJointNameDict = get_character_template_as_dict("HIK.xml")
    
    successful_mappings = 0
    
    for slotName, jointName in charSlotNameJointNameDict.items():
        mappingSlot = newCharacter.PropertyList.Find(slotName + "Link")
        if mappingSlot is None:
            continue
        
        jointObj = find_joint_by_name(jointName)
        if jointObj:
            mappingSlot.append(jointObj)
            successful_mappings += 1
    
    print(f"Mapped {successful_mappings}/{len(charSlotNameJointNameDict)} joints")
    
    characterized = newCharacter.SetCharacterizeOn(True)
    if characterized:
        print(f"Character '{characterName}' successfully characterized!")
        FBApplication().CurrentCharacter = newCharacter
        return newCharacter
    else:
        print(f"Characterization failed - not enough joints mapped ({successful_mappings} found)")
        return None

def create_and_assign_control_rig(character):
    if not character:
        return False
    
    app = FBApplication()
    app.CurrentCharacter = character
    
    character.CreateControlRig(True)
    
    ctrlRig = character.GetCurrentControlSet()
    if ctrlRig:
        for prop in ["LeftLegIK", "RightLegIK", "LeftArmIK", "RightArmIK"]:
            ikProp = ctrlRig.PropertyList.Find(prop)
            if ikProp:
                ikProp.Data = True
            else:
                altProp = ctrlRig.PropertyList.Find(prop + "Blend")
                if altProp:
                    altProp.Data = 1.0
    
    FBSystem().Scene.Evaluate()
    
    character.ActiveInput = True
    
    FBSystem().Scene.Evaluate()
    
    return True

def main():
    FBSystem().Scene.Evaluate()
    
    character = characterize_character("Character")
    if character:
        create_and_assign_control_rig(character)

if __name__ == "__main__":
    main()