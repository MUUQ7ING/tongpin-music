"""Mac通过受限SSH隧道测试openGauss，业务数据不变。"""
import os
from getpass import getpass
import py_opengauss
port=int(os.getenv('DB_PORT','12600'))
db=py_opengauss.open(
    'pq://jp@127.0.0.1:%d/music_platform' % port,
    password=os.getenv('DB_PASSWORD') or getpass('Database password: '),
    sslmode='disable',  # 仅限本机回环上的SSH加密隧道，不直接通过公网连接。
)
try:
    print('连接信息:',db.prepare('SELECT current_database(),current_user')())
    print('参数化查询:',db.prepare('SELECT song_id,song_title FROM music.song WHERE song_title=$1')('Shelter'))
    print('中文查询:',db.prepare('SELECT playlist_name FROM music.playlist WHERE playlist_name LIKE $1 ORDER BY playlist_id')('%音乐%'))
    db.execute('CREATE TEMP TABLE lab3_mac_probe (id INTEGER) ON COMMIT PRESERVE ROWS')
    db.execute('BEGIN')
    db.prepare('INSERT INTO lab3_mac_probe VALUES ($1)')(1)
    db.execute('ROLLBACK')
    assert db.prepare('SELECT COUNT(*) FROM lab3_mac_probe')()[0][0]==0
    print('事务回滚检查通过，业务表未修改。')
finally:
    db.close()
