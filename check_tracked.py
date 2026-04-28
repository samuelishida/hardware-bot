import sqlite3
db = sqlite3.connect('precobot.db')
db.row_factory = sqlite3.Row
rows = db.execute('SELECT * FROM tracked_products WHERE active=1').fetchall()
print(f'Tracked: {len(rows)}')
for r in rows:
    print(dict(r))
