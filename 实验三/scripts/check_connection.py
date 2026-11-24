"""通过SSH隧道检查驱动兼容性；不修改业务表。"""
import os
from getpass import getpass
import psycopg2

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', '127.0.0.1'),
    port=int(os.getenv('DB_PORT', '12600')),
    dbname=os.getenv('DB_NAME', 'music_platform'),
    user=os.getenv('DB_USER', 'jp'),
    password=os.getenv('DB_PASSWORD') or getpass('数据库密码（不回显）：'),
    connect_timeout=10,
)
try:
    with conn.cursor() as cur:
        cur.execute('SELECT version(), current_database(), current_user')
        print('连接信息：', cur.fetchone())
        cur.execute('SELECT song_id, song_title FROM music.song WHERE song_title = %s', ('Shelter',))
        print('参数化查询：', cur.fetchall())
        cur.execute('SELECT playlist_name FROM music.playlist WHERE playlist_name LIKE %s ORDER BY playlist_id', ('%音乐%',))
        print('中文查询：', cur.fetchall())
        cur.execute('CREATE TEMP TABLE lab3_connection_probe (id INTEGER) ON COMMIT PRESERVE ROWS')
    conn.commit()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO lab3_connection_probe VALUES (%s)', (1,))
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM lab3_connection_probe')
        assert cur.fetchone()[0] == 0, '回滚检查失败'
    print('事务回滚检查通过（仅使用会话临时表）。')
finally:
    conn.close()
