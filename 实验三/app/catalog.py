"""Administrator-only catalog maintenance and public same-origin audio delivery."""
import math
import unicodedata
from functools import wraps
from flask import Blueprint, abort, g, request, render_template, redirect, url_for, flash, send_file, jsonify
from .media_files import store_upload, media_path
from .lyrics import read_lrc_upload, merge_lyrics


def normalized(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def register_catalog(app, query, one, songs, field):
    bp = Blueprint('catalog', __name__)

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for('login'))
            if not g.user['is_admin']:
                abort(403, '只有曲库管理员可以维护歌曲资料和音频。')
            return view(*args, **kwargs)
        return wrapped

    def bind_audio(sid, media):
        old = one('SELECT storage_key FROM music.song_media WHERE song_id=$1', sid)
        values = [media[k] for k in ('storage_key','original_name','mime_type','byte_size','duration_seconds','sha256')]
        if old:
            query('''UPDATE music.song_media SET storage_key=$1,original_name=$2,mime_type=$3,
                byte_size=$4,duration_seconds=$5,sha256=$6,uploaded_by=$7,uploaded_at=CURRENT_TIMESTAMP
                WHERE song_id=$8''', *values, g.user['user_id'], sid)
            g.setdefault('old_media_files', []).append(media_path(old['storage_key']))
        else:
            query('''INSERT INTO music.song_media(storage_key,original_name,mime_type,byte_size,
                duration_seconds,sha256,uploaded_by,song_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8)''',
                *values, g.user['user_id'], sid)
        query('UPDATE music.song SET duration_seconds=$1 WHERE song_id=$2', max(1, math.ceil(media['duration_seconds'])), sid)

    def bind_lyrics(sid):
        original=request.files.get('lyrics')
        translated=request.files.get('translation')
        if not (original and original.filename) and not (translated and translated.filename):return False
        previous=one('SELECT original_lrc,original_name FROM music.song_lyrics WHERE song_id=$1',sid)
        if original and original.filename:
            text=read_lrc_upload(original)
            name=original.filename.replace('\\','/').rsplit('/',1)[-1][:255]
        elif previous:
            text=previous['original_lrc'];name=previous['original_name']
        else:abort(400,'请先上传原文歌词，再上传翻译。')
        trans=read_lrc_upload(translated) if translated and translated.filename else None
        if previous:
            query('UPDATE music.song_lyrics SET original_lrc=$1,translated_lrc=$2,original_name=$3,uploaded_by=$4,updated_at=CURRENT_TIMESTAMP WHERE song_id=$5',text,trans,name,g.user['user_id'],sid)
        else:
            query('INSERT INTO music.song_lyrics(original_lrc,translated_lrc,original_name,uploaded_by,song_id) VALUES($1,$2,$3,$4,$5)',text,trans,name,g.user['user_id'],sid)
        return True

    @bp.get('/admin/catalog')
    @admin_required
    def manage():
        return render_template('catalog.html', songs=songs(request.args.get('q','')[:150]),
            artists=query('SELECT * FROM music.artist ORDER BY artist_name'),
            albums=query('SELECT * FROM music.album ORDER BY album_title'), search=request.args.get('q','')[:150])

    @bp.post('/admin/catalog/songs')
    @admin_required
    def create_song():
        title = field('song_title',150)
        genre = field('genre',40)
        chosen = request.form.getlist('artist_ids')
        if any(not v.isdecimal() for v in chosen) or len(chosen) > 20:
            abort(400,'请选择有效的音乐人。')
        artist_ids = set(map(int,chosen))
        names = request.form.getlist('artist_name')
        types = request.form.getlist('artist_type')
        if len(names) != len(types) or len(names)>20:
            abort(400,'请检查新音乐人资料。')
        newcomers=[]
        for name,kind in zip(names,types):
            name=name.strip()
            if not name: continue
            if len(name)>100 or kind not in ('solo','band'):abort(400,'音乐人名称最长100字，类型须为个人或乐队。')
            newcomers.append((name,kind))
        if not artist_ids and not newcomers:abort(400,'至少选择或填写一位音乐人。')
        album_choice=request.form.get('album_id','')
        album_title=field('new_album_title',150,False)
        if album_choice and (not album_choice.isdecimal() or album_title):abort(400,'请选择已有专辑，或填写新专辑，不能同时指定。')
        upload=request.files.get('audio')
        media=store_upload(upload) if upload and upload.filename else None
        if media:
            seconds=max(1,math.ceil(media['duration_seconds']))
        else:
            raw=request.form.get('duration_seconds','')
            if not raw.isdecimal() or not 0<int(raw)<=86400:abort(400,'未上传音频时，请填写有效时长（1—86400秒）。')
            seconds=int(raw)
        # Serialize catalog creation to detect duplicate title + complete artist set.
        query('LOCK TABLE music.song, music.artist, music.album, music.song_artist IN SHARE ROW EXCLUSIVE MODE')
        existing_artists=query('SELECT artist_id,artist_name FROM music.artist')
        known={normalized(a['artist_name']):a['artist_id'] for a in existing_artists}
        if not artist_ids <= {a['artist_id'] for a in existing_artists}:abort(400,'选择的音乐人已不存在。')
        for name,kind in newcomers:
            key=normalized(name)
            if key not in known:
                known[key]=one('INSERT INTO music.artist(artist_name,artist_type) VALUES($1,$2) RETURNING artist_id',name,kind)['artist_id']
            artist_ids.add(known[key])
        if len(artist_ids)>20:abort(400,'单首歌曲最多关联20位音乐人。')
        for candidate in query('SELECT song_id,song_title FROM music.song'):
            if normalized(candidate['song_title'])==normalized(title):
                ids={r['artist_id'] for r in query('SELECT artist_id FROM music.song_artist WHERE song_id=$1',candidate['song_id'])}
                if ids==artist_ids:abort(409,'曲库里已有相同歌名与音乐人的歌曲，请在已有歌曲上绑定音频。')
        album_id=int(album_choice) if album_choice else None
        if album_id and not one('SELECT album_id FROM music.album WHERE album_id=$1',album_id):abort(400,'专辑不存在。')
        if album_title:
            album=next((a for a in query('SELECT album_id,album_title FROM music.album') if normalized(a['album_title'])==normalized(album_title)),None)
            album_id=album['album_id'] if album else one('INSERT INTO music.album(album_title) VALUES($1) RETURNING album_id',album_title)['album_id']
        sid=one('INSERT INTO music.song(song_title,album_id,duration_seconds,genre) VALUES($1,$2,$3,$4) RETURNING song_id',title,album_id,seconds,genre)['song_id']
        for aid in sorted(artist_ids):query('INSERT INTO music.song_artist(song_id,artist_id) VALUES($1,$2)',sid,aid)
        if media:bind_audio(sid,media)
        bind_lyrics(sid)
        flash('歌曲已加入曲库。'+('音频已就绪，可以播放。' if media else '稍后可为它上传音频。'))
        return redirect(url_for('catalog.manage'))

    @bp.post('/admin/catalog/songs/<int:sid>/audio')
    @admin_required
    def upload_audio(sid):
        if not one('SELECT song_id FROM music.song WHERE song_id=$1 FOR UPDATE',sid):abort(404,'歌曲不存在。')
        upload=request.files.get('audio')
        if not upload or not upload.filename:abort(400,'请选择音频文件。')
        media=store_upload(upload)
        bind_audio(sid,media)
        flash('音频已保存，歌曲时长也已按文件更新。')
        return redirect(url_for('catalog.manage'))

    @bp.post('/admin/catalog/songs/<int:sid>/audio/remove')
    @admin_required
    def remove_audio(sid):
        if not one('SELECT song_id FROM music.song WHERE song_id=$1 FOR UPDATE',sid):abort(404)
        old=one('SELECT storage_key FROM music.song_media WHERE song_id=$1',sid)
        if old:
            query('DELETE FROM music.song_media WHERE song_id=$1',sid)
            g.setdefault('old_media_files',[]).append(media_path(old['storage_key']))
        flash('音频已移除，歌曲资料及歌单关系保留。')
        return redirect(url_for('catalog.manage'))

    @bp.post('/admin/catalog/songs/<int:sid>/lyrics')
    @admin_required
    def upload_lyrics(sid):
        if not one('SELECT song_id FROM music.song WHERE song_id=$1 FOR UPDATE',sid):abort(404)
        if not bind_lyrics(sid):abort(400,'请选择原文歌词或中文翻译文件。')
        flash('歌词已保存，播放时可打开歌词面板。')
        return redirect(url_for('catalog.manage'))

    @bp.post('/admin/catalog/songs/<int:sid>/lyrics/remove')
    @admin_required
    def remove_lyrics(sid):
        if not one('SELECT song_id FROM music.song WHERE song_id=$1 FOR UPDATE',sid):abort(404)
        query('DELETE FROM music.song_lyrics WHERE song_id=$1',sid)
        flash('歌词已移除，音频保持不变。')
        return redirect(url_for('catalog.manage'))

    @bp.get('/api/songs/<int:sid>/lyrics')
    def lyrics(sid):
        if not one('SELECT song_id FROM music.song WHERE song_id=$1',sid):abort(404)
        row=one('SELECT original_lrc,translated_lrc FROM music.song_lyrics WHERE song_id=$1',sid)
        lines=merge_lyrics(row['original_lrc'],row['translated_lrc']) if row else []
        return jsonify(song_id=sid,lines=lines,has_translation=any(line['translation'] for line in lines))

    @bp.get('/media/songs/<int:sid>')
    def stream(sid):
        media=one('SELECT storage_key,mime_type FROM music.song_media WHERE song_id=$1',sid)
        if not media:abort(404,'这首歌曲还没有上传音频。')
        path=media_path(media['storage_key'])
        if not path.is_file():abort(404,'音频文件暂不可用，请联系管理员重新上传。')
        return send_file(path,mimetype=media['mime_type'],conditional=True,etag=True,max_age=0)

    app.register_blueprint(bp)
