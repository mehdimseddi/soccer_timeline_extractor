# utils/db_setup.py
import sqlite3
from ..config import DATABASE_PATH, logger

def setup_enum_tables():
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    # Event types
    event_types = [
        ('goal', 'Goal scored'),
        ('substitution', 'Player substitution'),
        ('yellow_card', 'Yellow card'),
        ('red_card', 'Red card'),
        # ('injury', 'Injury'),
        ('penalty', 'Penalty awarded'),
        # ('corner', 'Corner kick'),
        # ('foul', 'Foul committed')
    ]

    # Positions
    positions = [
    # Goalkeeper
    ('goalkeeper', 'protects the goal'),

    # Defenders
    ('right_back', 'defends the right side of the field'),
    ('left_back', 'defends the left side of the field'),
    ('center_back', 'defends the center of the field'),
    ('wing_back', 'defensive wide player who supports attack'),

    # Midfielders
    ('defensive_midfielder', 'protects defense and breaks up attacks'),
    ('central_midfielder', 'connects defense and attack in midfield'),
    ('attacking_midfielder', 'creates scoring opportunities'),

    # Forwards
    ('right_winger', 'attacks from the right side'),
    ('left_winger', 'attacks from the left side'),
    ('striker', 'primary goal scorer'),
    ('second_striker', 'supports striker and creates chances')
]




    cur.executemany("INSERT OR IGNORE INTO EventType (code, description) VALUES (?, ?)", event_types)
    cur.executemany("INSERT OR IGNORE INTO PlayerPosition (code, description) VALUES (?, ?)", positions)

    conn.commit()
    conn.close()

    logger.info("Enum tables initialized.")