"""Regression checks against real openGauss; isolated users and playlists are cleaned.

Default cleanup uses the data owner password. On ECS, root may explicitly set
TEST_ADMIN_VIA_OMM=1 to clean fixtures through the existing OS omm account.
"""
import os
import re
import secrets
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import py_opengauss
from app import create_app

app = create_app({'TESTING': True})
cfg = app.config
connection = py_opengauss.open(
    f"pq://{cfg['DB_USER']}@127.0.0.1:{cfg['DB_PORT']}/{cfg['DB_NAME']}",
    password=cfg['DB_PASSWORD'], sslmode='disable')
query = lambda sql, *args: connection.prepare(sql)(*args)
users, playlists = [], []
owner = None
if os.environ.get('TEST_ADMIN_VIA_OMM') != '1':
    from getpass import getpass
    owner = py_opengauss.open(
        f"pq://jp@127.0.0.1:{cfg['DB_PORT']}/{cfg['DB_NAME']}",
        password=os.getenv('DB_OWNER_PASSWORD') or getpass('数据所有者密码（仅清理测试账号）: '),
        sslmode='disable')

class LikeForms(HTMLParser):
    def __init__(self):
        super().__init__(); self.forms = []; self.current = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.current = {} if re.fullmatch(r'/songs/\d+/(?:un)?like', attrs.get('action', '')) else None
        elif tag == 'input' and self.current is not None:
            self.current[attrs.get('name')] = attrs.get('value')
    def handle_endtag(self, tag):
        if tag == 'form' and self.current is not None:
            self.forms.append(self.current); self.current = None

try:
    clients = [app.test_client(), app.test_client()]
    for client in clients:
        client.get('/register')
        with client.session_transaction() as session: token = session['csrf']
        response = client.post('/register', data={
            'csrf': token, 'username': 'like_nav_' + secrets.token_hex(6),
            'nickname': '页面返回回归测试', 'password': secrets.token_urlsafe(18)})
        assert response.status_code == 302
        with client.session_transaction() as session: users.append(session['uid'])
    a, b = clients
    def post(client, path, **data):
        with client.session_transaction() as session: token = session['csrf']
        return client.post(path, data={'csrf': token, **data})
    for client, visibility in [(a, 'private'), (b, 'public')]:
        response = post(client, '/playlists', playlist_name='临时返回路径测试', description='', visibility=visibility)
        assert response.status_code == 302
        playlists.append(int(response.location.rsplit('/', 1)[1]))
        assert post(client, f'/playlists/{playlists[-1]}/songs', song_id='2').status_code == 302
    query('INSERT INTO music.song_like(user_id,song_id) VALUES($1,$2)', users[0], 1)
    origins = [f'/playlists/{playlists[1]}', '/discover', '/songs?q=Porter&view=all', '/me']
    for origin in origins:
        for action in ('like', 'like', 'unlike'):
            response = post(a, f'/songs/2/{action}', return_path=origin)
            assert response.status_code == 302 and response.location == origin, (origin, response.status_code, response.location)
            expected = 0 if action == 'unlike' else 1
            assert query('SELECT count(*) FROM music.song_like WHERE user_id=$1 AND song_id=2', users[0])[0][0] == expected
        html = a.get(origin).data.decode()
        forms = LikeForms(); forms.feed(html)
        assert forms.forms and all(form.get('return_path') == origin for form in forms.forms), origin
        print('PASS 喜欢/取消/重复提交及表单原页面回传：' + origin, flush=True)
    for target in ('https://example.com', '//example.com', '/\\example.com', '/admin/catalog', '/logout', '/songs#fragment', '/songs\r\nLocation: https://example.com', '/missing'):
        response = post(a, '/songs/2/like', return_path=target, q='Madeon')
        assert response.status_code == 302 and response.location == '/songs?q=Madeon', repr(target)
    assert post(a, '/songs/2/unlike', return_to='profile').location == '/me'
    print('PASS 外站/非法/非曲目页返回地址被拒绝；旧页面表单兼容', flush=True)
    assert a.post('/songs/2/like', data={'return_path': '/me'}).status_code == 400
    assert post(a, '/songs/0/like', return_path='/discover').status_code == 404
    guest = app.test_client(); guest.get('/songs')
    assert post(guest, '/songs/2/like', return_path='/discover').location == '/login'
    print('PASS CSRF、失效歌曲和未登录请求仍按原权限处理', flush=True)
finally:
    for pid in playlists:
        query('DELETE FROM music.playlist_favorite WHERE playlist_id=$1', pid)
        query('DELETE FROM music.playlist_song WHERE playlist_id=$1', pid)
        query('DELETE FROM music.playlist WHERE playlist_id=$1', pid)
    for uid in users:
        query('DELETE FROM music.song_like WHERE user_id=$1', uid)
        query('DELETE FROM music.playlist_favorite WHERE user_id=$1', uid)
        if owner:
            owner.prepare('DELETE FROM music.app_user WHERE user_id=$1')(uid)
        else:
            sql = f'DELETE FROM music.app_user WHERE user_id={int(uid)};'
            subprocess.run(['su', '-', 'omm', '-c',
                            f'gsql -p 26000 -d {cfg["DB_NAME"]} -v ON_ERROR_STOP=1'],
                           input=sql, text=True, stdout=subprocess.DEVNULL, check=True)
    connection.close()
    if owner: owner.close()
    print('临时用户、喜欢和歌单已清理。', flush=True)
