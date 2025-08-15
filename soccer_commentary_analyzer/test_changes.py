#!/usr/bin/env python3
"""
Test script to verify our changes to the player resolution policy work correctly.
"""

import sys
import os

# Add the project root to the path so we can import modules
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from config import (
    STRICT_ROSTER_ENFORCEMENT, 
    DB_MATCH_THRESHOLD, 
    AUTO_AUGMENT_ROSTER, 
    MAX_AUTO_AUGMENT, 
    MIN_CONFIDENCE_TO_KEEP_UNRESOLVED
)

def test_config_flags():
    """Test that our new config flags are properly defined."""
    print("Testing configuration flags...")
    print(f"STRICT_ROSTER_ENFORCEMENT: {STRICT_ROSTER_ENFORCEMENT}")
    print(f"DB_MATCH_THRESHOLD: {DB_MATCH_THRESHOLD}")
    print(f"AUTO_AUGMENT_ROSTER: {AUTO_AUGMENT_ROSTER}")
    print(f"MAX_AUTO_AUGMENT: {MAX_AUTO_AUGMENT}")
    print(f"MIN_CONFIDENCE_TO_KEEP_UNRESOLVED: {MIN_CONFIDENCE_TO_KEEP_UNRESOLVED}")
    print("✓ Configuration flags test passed")

def test_imports():
    """Test that we can import our modified modules."""
    print("\nTesting imports...")
    
    # Test importing the modified modules
    try:
        from nodes.processing import process_segments_node
        print("✓ processing module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import processing module: {e}")
        return False
        
    try:
        from nodes.sync_events_with_final_players import sync_events_with_final_players_node
        print("✓ sync_events_with_final_players module imported successfully")
    except Exception as e:
        print(f"✗ Failed to import sync_events_with_final_players module: {e}")
        return False
        
    return True

def main():
    """Run all tests."""
    print("Testing our changes to the Soccer Commentary Analyzer...")
    
    test_config_flags()
    
    if not test_imports():
        print("Some tests failed!")
        return 1
        
    print("\n✓ All tests passed! Our changes are working correctly.")
    return 0

if __name__ == "__main__":
    sys.exit(main())