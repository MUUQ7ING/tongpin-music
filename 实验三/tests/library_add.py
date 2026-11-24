"""Library-to-owned-playlist flow against the real database; all fixtures are removed."""
import os,sys,secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import py_opengauss
from app import create_app
app=create_app({'TESTING':True});cfg=app.config
owner=py_opengauss.open('pq://jp@127.0.0.1:%s/music_platform'%cfg['DB_PORT'],password=os.getenv('DB_OWNER_PASSWORD') or __import__('getpass').getpass('jp 密码: '),sslmode='disable')
q=lambda sql,*args:owner.prepare(sql)(*args)
users=[];pids=[];prefix='library_test_'+secrets.token_hex(5)
try:
 for i in range(2):users.append(q('INSERT INTO music.app_user(username,nickname) VALUES($1,$2) RETURNING user_id',prefix+str(i),'添加功能测试'+str(i))[0][0])
 a,b,guest=[app.test_client() for _ in range(3)]
 for client,uid in [(a,users[0]),(b,users[1])]:
  with client.session_transaction() as session:session.update(uid=uid,csrf='library-test')
 def post(client,pid,sid=2,code=302):
  response=client.post(f'/playlists/{pid}/songs',data={'csrf':'library-test','song_id':sid,'return_to':'library','q':'Madeon'})
  assert response.status_code==code,(response.status_code,response.data.decode()[-500:]);return response
 assert '去创建歌单' in a.get('/songs').data.decode()
 assert '登录后将 Shelter 添加到歌单' in guest.get('/songs?q=Madeon').data.decode()
 print('PASS 访客登录提示、无歌单的创建入口',flush=True)
 for uid,name,visibility in [(users[0],'我的公开歌单','public'),(users[0],'我的私密歌单','private'),(users[1],'其他用户歌单','public')]:
  pids.append(q('INSERT INTO music.playlist(creator_id,playlist_name,visibility) VALUES($1,$2,$3) RETURNING playlist_id',uid,prefix+name,visibility)[0][0])
 page=a.get('/songs?q=Madeon').data.decode()
 assert prefix+'我的公开歌单' in page and prefix+'我的私密歌单' in page and prefix+'其他用户歌单' not in page
 print('PASS 选择框仅含自己的公开与私密歌单',flush=True)
 for pid in pids[:2]:
  response=post(a,pid);assert response.location.endswith('/songs?q=Madeon')
  html=a.get(response.location).data.decode();assert '已添加到' in html and 'value="Madeon"' in html
  assert q('SELECT song_id,position_no FROM music.playlist_song WHERE playlist_id=$1',pid)==[(2,1)]
  response=post(a,pid);assert '无需重复添加' in a.get(response.location).data.decode()
  assert q('SELECT count(*) FROM music.playlist_song WHERE playlist_id=$1',pid)[0][0]==1
 print('PASS 加入公开/私密歌单、返回保留搜索词、重复提交幂等',flush=True)
 post(a,pids[2],code=403);post(b,pids[1],code=404)
 assert q('SELECT count(*) FROM music.playlist_song WHERE playlist_id=$1',pids[2])[0][0]==0
 assert a.post(f'/playlists/{pids[0]}/songs',data={'song_id':1}).status_code==400
 post(a,pids[0],sid=-99999,code=404)
 assert guest.post(f'/playlists/{pids[0]}/songs').status_code==400
 assert q('SELECT count(*) FROM music.playlist_song WHERE playlist_id=$1',pids[0])[0][0]==1
 print('PASS 越权、CSRF、失效歌曲均拒绝且无额外写入',flush=True)
finally:
 for pid in pids:
  q('DELETE FROM music.playlist_song WHERE playlist_id=$1',pid)
  q('DELETE FROM music.playlist WHERE playlist_id=$1',pid)
 for uid in users:q('DELETE FROM music.app_user WHERE user_id=$1',uid)
 owner.close();print('临时用户和歌单已清理。',flush=True)
