# init_project.py
import os
import sys

# Define the full project structure
project_files = [
    # Root files
    "main.py",
    "config.py",
    "__init__.py",

    # models/
    "models/__init__.py",
    "models/schemas.py",

    # prompts/
    "prompts/__init__.py",
    "prompts/team_identification.py",
    "prompts/lineup.py",
    "prompts/events.py",

    # nodes/
    "nodes/__init__.py",
    "nodes/cleaning.py",
    "nodes/team_identification.py",
    "nodes/processing.py",
    "nodes/composition.py",
    "nodes/validation.py",
    "nodes/compile.py",
    "nodes/normalization.py",

    # graph/
    "graph/__init__.py",
    "graph/workflow.py",

    # utils/
    "utils/__init__.py",
    "utils/arabic.py",
    "utils/db_utils.py",  # Already referenced; create empty stub

    # database/
    "database/teams_players.db",  # Placeholder for SQLite DB
]

def create_project_structure():
    """Creates the full directory and file structure for the soccer commentary analyzer."""
    print("🚀 Initializing project structure...\n")

    for file_path in project_files:
        # Create directory if it doesn't exist
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name)
            print(f"📁 Created directory: {dir_name}")

        # Create the file (even if it's empty)
        with open(file_path, 'a', encoding='utf-8') as f:
            pass  # Just create the file
        print(f"📄 Created empty file: {file_path}")

    # Create a placeholder for db_utils if it doesn't exist
    db_utils_content = '''
# utils/db_utils.py
# Placeholder for database utilities (to be implemented)
def get_all_team_names(db_path):
    return []

def get_all_player_names(db_path):
    return []

def get_canonical_player_name(name, db_path):
    return None

def find_best_player_match(name, candidates, threshold=80):
    return None, 0

def get_possible_teams_for_player(player_name, db_path):
    return []
'''
    db_utils_path = "utils/db_utils.py"
    if not os.path.exists(db_utils_path) or os.path.getsize(db_utils_path) == 0:
        with open(db_utils_path, 'w', encoding='utf-8') as f:
            f.write(db_utils_content.strip() + "\n")
        print(f"💡 Generated stub: {db_utils_path}")

    print("\n✅ Project structure initialized successfully!")
    print("💡 Next: Start populating files with modular code from your original script.")


if __name__ == "__main__":
    try:
        create_project_structure()
    except Exception as e:
        print(f"❌ Error while initializing project: {e}")
        sys.exit(1)