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

def get_char_joint_from_slot_name(slotName):
    charSlotNameJointNameDict = get_character_template_as_dict("HIK.xml")
    charJointName = charSlotNameJointNameDict.get(slotName)
    
    if charJointName is None:
        return None
    
    charJointObj = FBFindModelByLabelName(charJointName)
    return charJointObj

def characterize_character(characterName):
    newCharacter = FBCharacter(characterName)
    charSlotNameJointNameDict = get_character_template_as_dict("HIK.xml")
    
    for slotName, jointName in charSlotNameJointNameDict.items():
        mappingSlot = newCharacter.PropertyList.Find(slotName + "Link")
        if mappingSlot is None:
            continue
        
        jointObj = FBFindModelByLabelName(jointName)
        if jointObj:
            mappingSlot.append(jointObj)
    
    characterized = newCharacter.SetCharacterizeOn(True)
    if characterized:
        FBApplication().CurrentCharacter = newCharacter
        return newCharacter
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