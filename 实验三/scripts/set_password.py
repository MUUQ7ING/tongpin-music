"""交互初始化一个已有账号的密码；不为历史用户批量分配默认密码。"""
import sys
from getpass import getpass
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from werkzeug.security import generate_password_hash
import py_opengauss
values = dict(line.split('=',1) for line in (Path(__file__).resolve().parent.parent/'.env').read_text().splitlines() if '=' in line)
username = input('需要初始化的用户名: ').strip()
password = getpass('新登录密码（8—128位）: ')
if not 8 <= len(password) <= 128 or password != getpass('再次输入: '):
    raise SystemExit('密码长度不符或两次输入不一致。')
c = py_opengauss.open('pq://music_web@127.0.0.1:%s/music_platform' % values['DB_PORT'],password=values['DB_PASSWORD'],sslmode='disable')
try:
    rows=c.prepare('UPDATE music.app_user SET password_hash=$1 WHERE username=$2 RETURNING user_id')(generate_password_hash(password),username)
    print('密码已更新。' if rows else '没有这个用户。')
finally:
    c.close()
