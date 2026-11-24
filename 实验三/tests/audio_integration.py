"""Real openGauss + audio files: authorization, upload rollback, range delivery and catalog creation."""
import io,json,os,secrets,sys,tempfile,wave,math,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import py_opengauss
from app import create_app
from werkzeug.security import generate_password_hash
ROOT=Path(__file__).resolve().parent.parent
config=dict(line.split('=',1) for line in (ROOT/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
owner=py_opengauss.open('pq://jp@127.0.0.1:%s/music_platform'%config['DB_PORT'],password=os.getenv('DB_OWNER_PASSWORD') or __import__('getpass').getpass('jp 密码: '),sslmode='disable')
def q(sql,*args):return owner.prepare(sql)(*args)
def wav_bytes(frequency=440):
    buf=io.BytesIO()
    with wave.open(buf,'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000)
        out.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*frequency*n/8000))) for n in range(16000)))
    return buf.getvalue()
user_ids=[];song_ids=[];artist_ids=[];album_ids=[];prefix='audio_test_'+secrets.token_hex(5)
with tempfile.TemporaryDirectory(prefix='tongpin-media-test-') as temp:
 app=create_app({'TESTING':True,'MEDIA_ROOT':temp})
 clients=[app.test_client(),app.test_client(),app.test_client()]
 def post(c,path,data=None,code=302):
    with c.session_transaction() as session:token=session['csrf']
    r=c.post(path,data={'csrf':token,**(data or {})})
    assert r.status_code==code,(path,r.status_code,r.data.decode()[-800:]);return r
 def report(message):print('PASS',message,flush=True)
 try:
    for i,admin in enumerate([True,False]):
        uid=q('INSERT INTO music.app_user(username,nickname,password_hash,is_admin) VALUES($1,$2,$3,$4) RETURNING user_id',prefix+str(i),'测试账号',generate_password_hash('Audio-Test-Password-87'),admin)[0][0];user_ids.append(uid)
        with clients[i].session_transaction() as session:session.update(uid=uid,csrf=secrets.token_hex(24))
    a,b,guest=clients
    assert guest.get('/admin/catalog').status_code==302
    assert b.get('/admin/catalog').status_code==403
    assert a.get('/admin/catalog').status_code==200
    post(b,'/admin/catalog/songs',{'song_title':'越权'},403)
    assert a.post('/admin/catalog/songs',data={'song_title':'无令牌'}).status_code==400
    report('管理员入口、普通用户与访客隔离、CSRF 拒绝')
    guest.get('/register')
    post(guest,'/register',{'username':prefix+'register','nickname':'注册测试','password':'Audio-Test-Password-87','is_admin':'true'})
    new=q('SELECT user_id,is_admin FROM music.app_user WHERE username=$1',prefix+'register')[0];user_ids.append(new[0]);assert new[1] is False
    assert guest.get('/admin/catalog').status_code==403
    post(guest,'/logout');guest.get('/register')
    r=post(guest,'/register',{'username':prefix+'register','nickname':'重复注册','password':'Audio-Test-Password-87'},200)
    assert '这个用户名已经有人使用了' in r.data.decode()
    report('注册不能自提管理员权限；重复用户名正确处理')
    base={'song_title':prefix+'日本語のテスト曲','genre':'Test','artist_name':prefix+'音楽人','artist_type':'solo','new_album_title':prefix+'专辑','duration_seconds':'2'}
    post(a,'/admin/catalog/songs',base)
    sid=q('SELECT song_id FROM music.song WHERE song_title=$1',base['song_title'])[0][0];song_ids.append(sid)
    artist_ids.extend(r[0] for r in q('SELECT artist_id FROM music.artist WHERE artist_name=$1',base['artist_name']))
    album_ids.extend(r[0] for r in q('SELECT album_id FROM music.album WHERE album_title=$1',base['new_album_title']))
    assert '日本語のテスト曲' in a.get('/songs?q='+prefix).data.decode()
    report('新增日文歌名、音乐人、专辑与资料检索')
    post(a,f'/admin/catalog/songs/{sid}/audio',{'audio':(io.BytesIO(b'not audio'), 'fake.mp3')},400)
    assert not list(Path(temp).iterdir())
    post(a,f'/admin/catalog/songs/{sid}/audio',{'audio':(io.BytesIO(wav_bytes()),'script.html')},400)
    app.config['MAX_AUDIO_BYTES']=100
    post(a,f'/admin/catalog/songs/{sid}/audio',{'audio':(io.BytesIO(wav_bytes()),'large.wav')},413)
    app.config['MAX_AUDIO_BYTES']=100*1024*1024
    assert not list(Path(temp).iterdir())
    report('伪音频、错误扩展名、超限文件均拒绝且清理文件')
    audio=wav_bytes()
    post(a,f'/admin/catalog/songs/{sid}/audio',{'audio':(io.BytesIO(audio),'../日本語の曲.wav')})
    media=q('SELECT storage_key,original_name,byte_size FROM music.song_media WHERE song_id=$1',sid)[0]
    assert media[1]=='日本語の曲.wav' and media[2]==len(audio)
    assert len(list(Path(temp).iterdir()))==1 and media[0].endswith('.wav')
    response=guest.get(f'/media/songs/{sid}');assert response.status_code==200 and response.data==audio
    part=guest.get(f'/media/songs/{sid}',headers={'Range':'bytes=0-31'});assert part.status_code==206 and part.data==audio[:32]
    assert guest.get(f'/media/songs/{sid}',headers={'Range':'bytes=999999999-'}).status_code==416
    assert guest.head(f'/media/songs/{sid}').status_code==200
    assert guest.get(f'/media/songs/{sid+999999}').status_code==404
    report('中文文件名、随机存储名、公开播放、HEAD 与 Range 206/416')
    old_key=media[0]
    post(a,f'/admin/catalog/songs/{sid}/audio',{'audio':(io.BytesIO(wav_bytes(660)),'replacement.wav')})
    assert not (Path(temp)/old_key).exists() and len(list(Path(temp).iterdir()))==1
    assert 'data-playable="true"' in a.get('/songs?q='+prefix).data.decode()
    post(a,'/admin/catalog/songs',{**base,'audio':(io.BytesIO(audio),'duplicate.wav')},409)
    assert len(list(Path(temp).iterdir()))==1
    assert q('SELECT count(*) FROM music.song WHERE song_title=$1',base['song_title'])[0][0]==1
    report('替换清理旧文件；重复歌曲回滚新文件及数据库改动')
    post(b,f'/admin/catalog/songs/{sid}/audio',{'audio':(io.BytesIO(audio),'denied.wav')},403)
    assert len(list(Path(temp).iterdir()))==1
    # Simulate a later database failure after a valid file has been written.
    from app.media_files import store_upload
    from flask import request,g
    # A fresh factory allows registering the test route before the first request.
    failure_app=create_app({'TESTING':True,'MEDIA_ROOT':temp})
    @failure_app.post('/_test/file-rollback')
    def fail_after_upload():
        store_upload(request.files['audio'])
        g.db.prepare('INSERT INTO music.song_like(user_id,song_id) VALUES($1,$2)')(user_ids[0],-987654321)
        return 'unreachable'
    failed=failure_app.test_client()
    with failed.session_transaction() as session:session.update(uid=user_ids[0],csrf='rollback-test')
    r=failed.post('/_test/file-rollback',data={'csrf':'rollback-test','audio':(io.BytesIO(audio),'rollback.wav')})
    assert r.status_code==503 and len(list(Path(temp).iterdir()))==1
    report('数据库失败后同时回滚音频文件；越权上传无写入')
    post(a,f'/admin/catalog/songs/{sid}/audio/remove')
    assert q('SELECT count(*) FROM music.song_media WHERE song_id=$1',sid)[0][0]==0
    assert not list(Path(temp).iterdir()) and guest.get(f'/media/songs/{sid}').status_code==404
    assert q('SELECT count(*) FROM music.song WHERE song_id=$1',sid)[0][0]==1
    report('移除音频保留歌曲资料；缺失音频返回 404')
    # Column grants must prevent app DB credentials from changing administrator flags.
    web=py_opengauss.open('pq://%s@127.0.0.1:%s/music_platform'%(config['DB_USER'],config['DB_PORT']),password=config['DB_PASSWORD'],sslmode='disable')
    try:
        web.prepare('UPDATE music.app_user SET is_admin=true WHERE user_id=$1')(user_ids[1]);raise AssertionError('privilege escalation')
    except py_opengauss.exceptions.InsufficientPrivilegeError:pass
    finally:web.close()
    report('应用数据库账号不能修改管理员标志')
 finally:
    for sid in song_ids:
        for table in ['song_media','song_artist','song_like']:q(f'DELETE FROM music.{table} WHERE song_id=$1',sid)
        q('DELETE FROM music.song WHERE song_id=$1',sid)
    for aid in artist_ids:q('DELETE FROM music.artist WHERE artist_id=$1',aid)
    for aid in album_ids:q('DELETE FROM music.album WHERE album_id=$1',aid)
    for uid in user_ids:q('DELETE FROM music.app_user WHERE user_id=$1',uid)
    owner.close();print('临时歌曲、账号与测试文件已清理。',flush=True)
