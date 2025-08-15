import requests
from bs4 import BeautifulSoup
import arabic_reshaper
from bidi.algorithm import get_display
import sqlite3
import os

def rtl_fix(text):
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

def get_team_name(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return None, f"Error fetching URL: {e}"

    soup = BeautifulSoup(response.text, 'html.parser')
    title_tag = soup.find('h1', id='firstHeading')
    if title_tag:
        full_title = title_tag.get_text(strip=True)
        if "تصنيف:لاعبو " in full_title:
            team_name = full_title.replace("تصنيف:لاعبو ", "")
        else:
            team_name = full_title
        return team_name, None
    return None, "Could not find the team name."

def get_player_names(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return [], f"Error fetching URL: {e}"

    soup = BeautifulSoup(response.text, 'html.parser')
    players = []
    category_groups = soup.find_all("div", class_="mw-category-group")

    for group in category_groups:
        links = group.find_all("a")
        for link in links:
            name = link.get_text(strip=True)
            players.append(name)

    return players, None

def init_db(db_path="teams_players.db"):
    if not os.path.exists(db_path):
        print("Creating new database...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Drop only the tables we’ll populate now
    c.execute('DROP TABLE IF EXISTS PlayerTeam')
    c.execute('DROP TABLE IF EXISTS Player')
    c.execute('DROP TABLE IF EXISTS Team')

    # Enums
    c.execute('''
        CREATE TABLE IF NOT EXISTS EventType (
            code TEXT PRIMARY KEY,
            description TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS PlayerPosition (
            code TEXT PRIMARY KEY,
            description TEXT NOT NULL
        )
    ''')

    # Core Tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS Team (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS Player (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS PlayerTeam (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            FOREIGN KEY (player_id) REFERENCES Player(id),
            FOREIGN KEY (team_id) REFERENCES Team(id),
            UNIQUE(player_id, team_id)
        )
    ''')

    # Match-related Tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS Match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            home_team_id INTEGER NOT NULL,
            away_team_id INTEGER NOT NULL,
            home_score INTEGER DEFAULT 0,
            away_score INTEGER DEFAULT 0,
            match_date DATETIME NOT NULL,
            FOREIGN KEY (home_team_id) REFERENCES Team(id),
            FOREIGN KEY (away_team_id) REFERENCES Team(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS MatchLineup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            jersey_number TEXT,
            position_code TEXT,
            FOREIGN KEY (match_id) REFERENCES Match(id),
            FOREIGN KEY (player_id) REFERENCES Player(id),
            FOREIGN KEY (team_id) REFERENCES Team(id),
            FOREIGN KEY (position_code) REFERENCES PlayerPosition(code),
            UNIQUE(match_id, player_id) ON CONFLICT REPLACE
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS MatchEvent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            player_id INTEGER,
            event_type_code TEXT NOT NULL,
            time TEXT NOT NULL,
            details TEXT,
            player_in_id INTEGER,
            player_out_id INTEGER,
            FOREIGN KEY (match_id) REFERENCES Match(id),
            FOREIGN KEY (player_id) REFERENCES Player(id),
            FOREIGN KEY (event_type_code) REFERENCES EventType(code),
            FOREIGN KEY (player_in_id) REFERENCES Player(id),
            FOREIGN KEY (player_out_id) REFERENCES Player(id)
        )
    ''')

    conn.commit()
    return conn

def insert_team_and_players(conn, team_name, player_names):
    c = conn.cursor()

    # Insert or ignore team
    c.execute("INSERT OR IGNORE INTO Team (name) VALUES (?)", (team_name,))
    conn.commit()

    # Get team_id
    c.execute("SELECT id FROM Team WHERE name = ?", (team_name,))
    team_id = c.fetchone()[0]

    for player in player_names:
        # Insert player if not exists
        c.execute("INSERT OR IGNORE INTO Player (name) VALUES (?)", (player,))
        conn.commit()

        # Get player_id
        c.execute("SELECT id FROM Player WHERE name = ?", (player,))
        player_id = c.fetchone()[0]

        # Insert into PlayerTeam
        c.execute(
            "INSERT OR IGNORE INTO PlayerTeam (player_id, team_id) VALUES (?, ?)",
            (player_id, team_id)
        )

    conn.commit()

if __name__ == "__main__":
    teams = [
        "المستقبل_الرياضي_بقابس", "النادي_الرياضي_الصفاقسي", "النادي_الإفريقي", 
        "الترجي_الرياضي_التونسي", "المستقبل_الرياضي_بالمرسى", "المستقبل_الرياضي_بسليمان",
        "النادي_الرياضي_البنزرتي", "النجم_الرياضي_بالمتلوي", "النجم_الرياضي_الساحلي",
        "الترجي_الرياضي_الجرجيسي", "الشبيبة_الرياضية_القيروانية", "الشبيبة_الرياضية_بالعمران",
        "الأولمبي_الباجي", "نادي_الملعب_التونسي", "الاتحاد_الرياضي_ببنقردان",
        "الاتحاد_الرياضي_المنستيري", "الجمعية_الرياضية_بجربة", "القصرين",
        "أولمبيك_سيدي_بوزيد", "الهلال_الرياضي_بمساكن", "الجمعية_الرياضية_بأريانة",
        "النجم_الرياضي_ببني_خلاد", "الاتحاد_الرياضي_ببنقردان", "جندوبة_الرياضية",
        "الملعب_الرياضي_الصفاقسي", "الأمل_الرياضي_بحمام_سوسة", "النادي_الرياضي_بقربة",
        "نادي_سكك_الحديد_الصفاقسي", "أولمبيك_الكاف", "النفيضة_الرياضية", "النادي_الأولمبي_للنقل"
    ]
    base_url = "https://ar.wikipedia.org/wiki/تصنيف:لاعبو_"

    db_conn = init_db()

    for team_slug in teams:
        team_url = base_url + team_slug
        print(f"\n🔍 Processing team: {team_slug}...")

        team_name, err = get_team_name(team_url)
        if err:
            print(err)
            continue

        players, err = get_player_names(team_url)
        if err:
            print(err)
            continue

        print(f"💾 Saving team: {rtl_fix(team_name)} with {len(players)} players")
        insert_team_and_players(db_conn, team_name, players)

    db_conn.close()
    print("\n✅ All teams processed and saved to SQLite.")
