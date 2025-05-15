"""
Test script for constraint detection in FBXexporter.py
Run this from within MotionBuilder to test the constraint detection functionality
"""

import pyfbsdk as fb
from FBXexporter import MotionBuilderExporter

def test_constraint_detection():
    """Test the constraint detection and restoration functionality"""
    scene = fb.FBSystem().Scene
    app = fb.FBApplication()
    
    print("=== Testing Constraint Detection ===")
    
    # Create test nodes
    root = fb.FBModelNull('TestRoot')
    constrainer1 = fb.FBModelNull('Constrainer1')
    constrainer2 = fb.FBModelNull('Constrainer2')
    
    # Create various constraint types
    print("\nCreating test constraints...")
    
    # Position constraint
    pos_constraint = fb.FBConstraintPosition('TestPosConstraint')
    pos_constraint.Constrained(0, root)
    pos_constraint.AddSource(constrainer1)
    pos_constraint.Active = True
    print(f"Created position constraint: {pos_constraint.Name}")
    
    # Aim constraint
    aim_constraint = fb.FBConstraintAim('TestAimConstraint')
    aim_constraint.Constrained(0, root)
    aim_constraint.AddSource(constrainer2)
    aim_constraint.Active = True
    print(f"Created aim constraint: {aim_constraint.Name}")
    
    # Relation constraint
    rel_constraint = fb.FBConstraintRelation('TestRelConstraint')
    box1 = rel_constraint.SetAsSource(root, 'Lcl Rotation')
    box2 = rel_constraint.SetAsSource(constrainer1, 'Lcl Rotation')
    rel_constraint.Active = True
    print(f"Created relation constraint: {rel_constraint.Name}")
    
    # Initialize exporter and test constraint detection
    print("\n=== Testing disable_root_constraints() ===")
    exporter = MotionBuilderExporter()
    
    # Set the root for testing
    exporter.root_joint = root
    
    # Test constraint detection
    disabled_constraints = exporter.disable_root_constraints()
    
    print(f"\nTotal constraints found and disabled: {len(disabled_constraints)}")
    
    # Test restoration
    print("\n=== Testing restore_constraints() ===")
    exporter.restore_constraints(disabled_constraints)
    
    # Verify constraints are active again
    print("\nConstraint states after restoration:")
    print(f"Position constraint active: {pos_constraint.Active}")
    print(f"Aim constraint active: {aim_constraint.Active}")
    print(f"Relation constraint active: {rel_constraint.Active}")
    
    # Cleanup
    print("\n=== Cleaning up test objects ===")
    root.FBDelete()
    constrainer1.FBDelete()
    constrainer2.FBDelete()
    print("Test complete!")

if __name__ == "__main__":
    test_constraint_detection()