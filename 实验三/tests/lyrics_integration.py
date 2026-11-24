import io,os,sys,secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import create_app
from app.lyrics import parse_lrc,merge_lyrics
import py_opengauss
app=create_app({'TESTING':True});cfg=app.config
assert parse_lrc('[offset:1000]\n[00:02.50][00:04.500]测试')[0]=={'time':1.5,'text':'测试'}
assert len(parse_lrc('[00:01]甲\n[00:01]乙'))==1
assert parse_lrc('没有时间戳')==[]
assert merge_lyrics('[00:01.00]原文','[00:01.20]译文')[0]['translation']=='译文'
assert merge_lyrics('[00:01.00]原文','[00:09]不匹配')[0]['translation']==''
print('PASS LRC 多时间戳、精度、偏移、去重、翻译对齐与不匹配回退',flush=True)
c=py_opengauss.open('pq://jp@127.0.0.1:%s/music_platform'%cfg['DB_PORT'],password=os.getenv('DB_OWNER_PASSWORD') or __import__('getpass').getpass('jp 密码: '),sslmode='disable')
q=lambda sql,*args:c.prepare(sql)(*args)
sid=None;uid=None
try:
 admin=q('SELECT user_id FROM music.app_user WHERE username=$1','music_admin')[0][0]
 uid=q('INSERT INTO music.app_user(username,nickname) VALUES($1,$2) RETURNING user_id','lyrics_test_'+secrets.token_hex(5),'歌词测试')[0][0]
 sid=q('INSERT INTO music.song(song_title,duration_seconds,genre) VALUES($1,10,$2) RETURNING song_id','歌词验证临时曲','Test')[0][0]
 a,b=app.test_client(),app.test_client()
 for client,user in [(a,admin),(b,uid)]:
  with client.session_transaction() as sess:sess.update(uid=user,csrf='lyrics-test')
 def post(client,data,code=302):
  r=client.post(f'/admin/catalog/songs/{sid}/lyrics',data={'csrf':'lyrics-test',**data});assert r.status_code==code,(r.status_code,r.data.decode()[-600:]);return r
 assert a.get(f'/api/songs/{sid}/lyrics').get_json()['lines']==[]
 post(b,{'lyrics':(io.BytesIO(b'[00:01]test'),'test.lrc')},403)
 assert a.post(f'/admin/catalog/songs/{sid}/lyrics',data={}).status_code==400
 post(a,{'translation':(io.BytesIO('[00:01]译文'.encode()),'trans.lrc')},400)
 post(a,{'lyrics':(io.BytesIO(b'bad'),'bad.lrc')},400)
 post(a,{'lyrics':(io.BytesIO(b'[00:01]text'),'bad.txt')},400)
 post(a,{'lyrics':(io.BytesIO(b'x'*(1024*1024+1)),'large.lrc')},400)
 assert q('SELECT count(*) FROM music.song_lyrics WHERE song_id=$1',sid)[0][0]==0
 print('PASS 权限/CSRF、孤立翻译、无效格式与超限拒绝且无写入',flush=True)
 original='[00:01.00]日本語のテスト\n[00:03.00]<script>test</script>'
 post(a,{'lyrics':(io.BytesIO(original.encode('utf-16')),'日本語.lrc'),'translation':(io.BytesIO('[00:01.00]中文测试\n[00:03.00]第二句'.encode()),'translation.lrc')})
 data=app.test_client().get(f'/api/songs/{sid}/lyrics').get_json()
 assert data['has_translation'] and data['lines'][0]['text']=='日本語のテスト' and data['lines'][0]['translation']=='中文测试'
 assert data['lines'][1]['text']=='<script>test</script>'
 print('PASS UTF-16 日文、中文翻译、原文文本 JSON 输出及逐行合并',flush=True)
 post(a,{'lyrics':(io.BytesIO('[00:01]新版本'.encode()),'new.lrc')})
 assert not a.get(f'/api/songs/{sid}/lyrics').get_json()['has_translation']
 r=a.post(f'/admin/catalog/songs/{sid}/lyrics/remove',data={'csrf':'lyrics-test'});assert r.status_code==302
 assert a.get(f'/api/songs/{sid}/lyrics').get_json()['lines']==[]
 assert a.get('/api/songs/99999999/lyrics').status_code==404
 print('PASS 替换清理旧翻译、移除歌词、无歌词空状态与失效歌曲 404',flush=True)
finally:
 if sid:
  q('DELETE FROM music.song_lyrics WHERE song_id=$1',sid);q('DELETE FROM music.song WHERE song_id=$1',sid)
 if uid:q('DELETE FROM music.app_user WHERE user_id=$1',uid)
 c.close();print('歌词测试资料已清理。',flush=True)
