import json
import os
import sqlite3
from modules import scripts

path_recorder_file = os.path.join(scripts.basedir(), "path_recorder.txt")
aes_cache_file = os.path.join(scripts.basedir(), "aes_scores.json")
exif_cache_file = os.path.join(scripts.basedir(), "exif_data.json")
ranking_file = os.path.join(scripts.basedir(), "ranking.json")
archive = os.path.join(scripts.basedir(), "archive")
db_file = os.path.join(scripts.basedir(), "wib.sqlite3")
np = "Negative prompt: "
st = "Steps: "

def create_db(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS db_data (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS path_recorder (
            path TEXT PRIMARY KEY,
            depth INT,
            path_display TEXT,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TRIGGER path_recorder_tr 
        AFTER UPDATE ON path_recorder
        BEGIN
            UPDATE path_recorder SET updated = CURRENT_TIMESTAMP WHERE path = OLD.path;
        END;
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exif_data (
            file TEXT,
            key TEXT,
            value TEXT,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (file, key)
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS exif_data_key ON exif_data (key)
    ''')

    cursor.execute('''
        CREATE TRIGGER exif_data_tr 
        AFTER UPDATE ON exif_data
        BEGIN
            UPDATE exif_data SET updated = CURRENT_TIMESTAMP WHERE file = OLD.file AND key = OLD.key;
        END;
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ranking (
            file TEXT PRIMARY KEY,
            ranking TEXT,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TRIGGER ranking_tr 
        AFTER UPDATE ON ranking
        BEGIN
            UPDATE ranking SET updated = CURRENT_TIMESTAMP WHERE file = OLD.file;
        END;
    ''')

    return

def migrate_path_recorder(cursor):
    if os.path.exists(path_recorder_file):
        try:
            with open(path_recorder_file) as f:
                # json-version
                path_recorder = json.load(f)
            for path, values in path_recorder.items():
                depth = values["depth"]
                path_display = values["path_display"]
                cursor.execute('''
                INSERT INTO path_recorder (path, depth, path_display)
                VALUES (?, ?, ?)
                ''', (path, depth, path_display))
        except json.JSONDecodeError:
            with open(path_recorder_file) as f:
                # old txt-version
                path = f.readline().rstrip("\n")
                while len(path) > 0:
                    cursor.execute('''
                    INSERT INTO path_recorder (path, depth, path_display)
                    VALUES (?, ?, ?)
                    ''', (path, 0, f"{path} [0]"))
                    path = f.readline().rstrip("\n")

    return

def update_exif_data(cursor, file, info):
    prompt = "0"
    negative_prompt = "0"
    key_values = "0: 0"
    if info != "0":
        info_list = info.split("\n")
        prompt = ""
        negative_prompt = ""
        key_values = ""
        for info_item in info_list:
            if info_item.startswith(st):
                key_values = info_item
            elif info_item.startswith(np):
                negative_prompt = info_item.replace(np, "")
            else:
                prompt = info_item
    if key_values != "":
        key_value_pairs = []
        key_value = ""
        quote_open = False
        for char in key_values + ",":
            key_value += char
            if char == '"':
                quote_open = not quote_open
            if char == "," and not quote_open:
                try:
                    k, v = key_value.strip(" ,").split(": ")
                except ValueError:
                    k = key_value.strip(" ,").split(": ")[0]
                    v = ""
                key_value_pairs.append((k, v))
                key_value = ""

                try:
                    cursor.execute('''
                    INSERT INTO exif_data (file, key, value)
                    VALUES (?, ?, ?)
                    ''', (file, "prompt", prompt))
                except sqlite3.IntegrityError:
                    # Duplicate, delete all "file" entries and try again
                    cursor.execute('''
                    DELETE FROM exif_data
                    WHERE file = ?
                    ''', (file,))

                    cursor.execute('''
                    INSERT INTO exif_data (file, key, value)
                    VALUES (?, ?, ?)
                    ''', (file, "prompt", prompt))

                cursor.execute('''
                INSERT INTO exif_data (file, key, value)
                VALUES (?, ?, ?)
                ''', (file, "negative_prompt", negative_prompt))
                
                for (key, value) in key_value_pairs:
                    try:
                        cursor.execute('''
                        INSERT INTO exif_data (file, key, value)
                        VALUES (?, ?, ?)
                        ''', (file, key, value))
                    except sqlite3.IntegrityError:
                        pass
    
    return

def migrate_exif_data(cursor):
    if os.path.exists(exif_cache_file):
        with open(exif_cache_file, 'r') as file:
        #with open("c:\\tools\\ai\\stable-diffusion-webui\\extensions\\stable-diffusion-webui-images-browser\\test.json ", 'r') as file:
            exif_cache = json.load(file)
        
        for file, info in exif_cache.items():
            update_exif_data(cursor, file, info)
    
    return

def migrate_ranking(cursor):
    if os.path.exists(ranking_file):
        with open(ranking_file, 'r') as file:
            ranking = json.load(file)
        for file, info in ranking.items():
            if info != "None":
                cursor.execute('''
                INSERT INTO ranking (file, ranking)
                VALUES (?, ?)
                ''', (file, info))

    return

def update_db_data(cursor, key, value):
    cursor.execute('''
    INSERT OR REPLACE
    INTO db_data (key, value)
    VALUES (?, ?)
    ''', (key, value))
    
    return

def check():
    if not os.path.exists(db_file):
        conn, cursor = transaction_begin()
        create_db(cursor)
        update_db_data(cursor, "version", "1")
        migrate_path_recorder(cursor)
        migrate_exif_data(cursor)
        migrate_ranking(cursor)
        transaction_end(conn, cursor)

    return

def load_path_recorder():
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT path, depth, path_display
        FROM path_recorder
        ''')
        path_recorder = {path: {"depth": depth, "path_display": path_display} for path, depth, path_display in cursor.fetchall()}

    return path_recorder

def select_ranking(filename):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT ranking
        FROM ranking
        WHERE file = ?
        ''', (filename,))
        ranking_value = cursor.fetchone()

    if ranking_value is None:
        ranking_value = ["0"]
    return ranking_value[0]

def update_ranking(file, ranking):
    if ranking != "0":
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE
            INTO ranking (file, ranking)
            VALUES (?, ?)
            ''', (file, ranking))
    
    return

def update_path_recorder(path, depth, path_display):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT OR REPLACE
        INTO path_recorder (path, depth, path_display)
        VALUES (?, ?, ?)
        ''', (path, depth, path_display))
    
    return

def delete_path_recorder(path):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        DELETE FROM path_recorder
        WHERE path = ?
        ''', (path,))
    
    return

def transaction_begin():
    conn = sqlite3.connect(db_file)
    conn.isolation_level = None
    cursor = conn.cursor()
    cursor.execute("BEGIN")
    return conn, cursor

def transaction_end(conn, cursor):
    cursor.execute("COMMIT")
    conn.close()
    return

def update_aes_data(cursor, file, value):
    key = "aesthetic_score"

    cursor.execute('''
    INSERT OR REPLACE
    INTO exif_data (file, key, value)
    VALUES (?, ?, ?)
    ''', (file, key, value))

    return

def load_exif_data(exif_cache):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT file, group_concat(
            case when key = 'prompt' or key = 'negative_prompt' then key || ': ' || value || '\n'
            else key || ': ' || value
            end, ', ') AS string
        FROM (
            SELECT *
            FROM exif_data
            ORDER BY
                CASE WHEN key = 'prompt' THEN 0
                    WHEN key = 'negative_prompt' THEN 1
                    ELSE 2 END,
                key
        )
        GROUP BY file
        ''')

        rows = cursor.fetchall()
    for row in rows:
        exif_cache[row[0]] = row[1]

    return exif_cache

def load_aes_data(aes_cache):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT file, value
        FROM exif_data
        WHERE key in ("aesthetic_score", "Score")
        ''')

        rows = cursor.fetchall()
    for row in rows:
        aes_cache[row[0]] = row[1]

    return aes_cache
