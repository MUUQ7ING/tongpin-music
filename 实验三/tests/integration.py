"""真实 openGauss 集成检查。创建独立测试用户，finally 清理其业务记录。"""
import sys
import secrets
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import py_opengauss
from app import create_app
app=create_app({'TESTING':True})
cfg=app.config
admin=py_opengauss.open('pq://jp@127.0.0.1:%s/music_platform' % cfg['DB_PORT'],password=__import__('getpass').getpass('数据所有者密码（仅清理测试用户）: '),sslmode='disable')
users=[];pids=[]
# Deliberately fail after writing inside a request to verify automatic rollback.
from flask import g, abort
@app.post('/_test/rollback')
def rollback_probe():
    g.db.prepare('UPDATE music.app_user SET bio=$1 WHERE user_id=$2')('SHOULD_ROLL_BACK',g.user['user_id'])
    abort(400)


def scalar(sql,*args):
    return admin.prepare(sql)(*args)[0][0]

def post(client,path,data=None,status=302):
    with client.session_transaction() as s: csrf=s['csrf']
    r=client.post(path,data={'csrf':csrf,**(data or {})})
    assert r.status_code==status,(path,r.status_code,r.data.decode()[-500:])
    return r

def report(message): print('PASS',message,flush=True)
try:
    clients=[app.test_client(),app.test_client()]
    for i,c in enumerate(clients):
        c.get('/register');name='lab3_test_'+secrets.token_hex(6);users.append(name)
        post(c,'/register',{'username':name,'nickname':f'集成测试{i}','password':'Test-Music-Only-93!'})
        post(c,'/logout');c.get('/login')
        post(c,'/login',{'username':name,'password':'Test-Music-Only-93!'})
    a,b=clients
    ids=[scalar('SELECT user_id FROM music.app_user WHERE username=$1',n) for n in users]
    assert scalar('SELECT password_hash FROM music.app_user WHERE user_id=$1',ids[0]).startswith('scrypt:')
    report('注册、哈希存储、退出及密码登录')
    assert b.post('/me',data={'nickname':'伪造'}).status_code==400
    post(a,'/me',{'nickname':'中文测试听众','bio':'<script>alert(1)</script>'})
    assert b'<script>alert(1)</script>' not in a.get('/me').data
    report('CSRF 拒绝、资料更新及 HTML 转义')
    r=a.get('/songs?q=Madeon');assert r.data.decode().count('<strong>Shelter</strong>')==1
    assert '独立单曲' in r.data.decode()
    assert a.get('/songs?q=%27%20OR%201%3D1--').status_code==200
    report('合作曲不重复、NULL 专辑、参数化搜索')
    # A likes 1,2 and B likes 2,3: Jaccard 1/3; B recommends 3 to A.
    for c,sids in [(a,[1,2]),(b,[2,3])]:
        for sid in sids: post(c,f'/songs/{sid}/like');post(c,f'/songs/{sid}/like')
    assert scalar('SELECT count(*) FROM music.song_like WHERE user_id=$1',ids[0])==2
    post(a,'/songs/8/unlike');report('喜欢/取消幂等')
    r=post(a,'/playlists',{'playlist_name':'集成测试歌单','description':'仅用于验证','visibility':'public'})
    pid=int(r.location.rsplit('/',1)[-1]);pids.append(pid)
    for sid in [1,2,3]: post(a,f'/playlists/{pid}/songs',{'song_id':sid})
    post(a,f'/playlists/{pid}/songs',{'song_id':2})
    assert scalar('SELECT count(*) FROM music.playlist_song WHERE playlist_id=$1',pid)==3
    post(a,f'/playlists/{pid}/songs/3/move',{'direction':'up'})
    assert [r[0] for r in admin.prepare('SELECT song_id FROM music.playlist_song WHERE playlist_id=$1 ORDER BY position_no')(pid)]==[1,3,2]
    post(a,f'/playlists/{pid}/songs/1/remove')
    assert [r[0] for r in admin.prepare('SELECT position_no FROM music.playlist_song WHERE playlist_id=$1 ORDER BY position_no')(pid)]==[1,2]
    report('过程加歌、去重、排序与移除后位置连续')
    post(b,f'/playlists/{pid}/favorite');post(b,f'/playlists/{pid}/favorite')
    assert scalar('SELECT count(*) FROM music.playlist_favorite WHERE playlist_id=$1',pid)==1
    post(b,f'/playlists/{pid}/edit',{'playlist_name':'越权','description':'','visibility':'private'},403)
    post(b,f'/playlists/{pid}/songs',{'song_id':4},403)
    post(b,f'/playlists/{pid}/delete',status=403)
    report('公开分享、收藏幂等、拒绝跨用户修改及删除')
    post(a,f'/playlists/{pid}/edit',{'playlist_name':'集成测试歌单私密','description':'更新审计','visibility':'private'})
    assert scalar('SELECT count(*) FROM music.playlist_audit WHERE playlist_id=$1',pid)==1
    assert b.get(f'/playlists/{pid}').status_code==404
    assert app.test_client().get(f'/playlists/{pid}').status_code==404
    post(b,f'/playlists/{pid}/favorite',status=404)
    assert '集成测试歌单私密' not in b.get('/me').data.decode()
    report('审计触发器、私密直链及收藏列表隐藏')
    assert '33%' in a.get('/discover').data.decode()
    assert '新月余晖' in a.get('/discover').data.decode()
    report('Jaccard 1/3、候选推荐、历史无偏好用户空状态')
    post(a,'/_test/rollback',status=400)
    assert scalar('SELECT bio FROM music.app_user WHERE user_id=$1',ids[0])=='<script>alert(1)</script>'
    report('请求失败后整笔事务回滚')
    post(a,f'/playlists/{pid}/delete')
    assert scalar('SELECT count(*) FROM music.playlist WHERE playlist_id=$1',pid)==0
    assert scalar('SELECT count(*) FROM music.playlist_audit WHERE playlist_id=$1',pid)==1
    report('歌单删除清理关联并保留审计历史')
except AssertionError:
    raise
finally:
    for pid in pids:
        for table in ['playlist_favorite','playlist_song','playlist_audit','playlist']:
            admin.prepare(f'DELETE FROM music.{table} WHERE playlist_id=$1')(pid)
    for name in users:
        rows=admin.prepare('SELECT user_id FROM music.app_user WHERE username=$1')(name)
        if rows:
            user_id=rows[0][0]
            admin.prepare('DELETE FROM music.song_like WHERE user_id=$1')(user_id)
            admin.prepare('DELETE FROM music.app_user WHERE user_id=$1')(user_id)
    admin.close()
    print('测试业务记录已清理；序列保留正常递增。')
