import os
import secrets
import hmac
from functools import wraps
from urllib.parse import urlsplit
from werkzeug.exceptions import HTTPException
from pathlib import Path
from flask import Flask, g, request, session, redirect, url_for, render_template, flash, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import py_opengauss
from py_opengauss.exceptions import Error as DatabaseError, UniqueError
from .media_files import finish_files
from .catalog import register_catalog

ROOT = Path(__file__).resolve().parent.parent


def create_app(test_config=None):
    # Environment overrides the ignored local file.
    local = {}
    if (ROOT / '.env').exists():
        local = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                     if line and not line.startswith('#') and '=' in line)
    config = {**local, **os.environ}
    app = Flask(__name__)
    app.config.update(SECRET_KEY=config.get('SECRET_KEY'), DB_USER=config.get('DB_USER', 'music_web'),
                      DB_PASSWORD=config.get('DB_PASSWORD'), DB_PORT=int(config.get('DB_PORT', 12600)),
                      DB_NAME=config.get('DB_NAME', 'music_platform'),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      MEDIA_ROOT=str(ROOT / 'media'), MAX_AUDIO_BYTES=100*1024*1024,
                      MAX_CONTENT_LENGTH=103*1024*1024, MAX_FORM_MEMORY_SIZE=1024*1024,
                      FFPROBE_BIN=config.get('FFPROBE_BIN','ffprobe'))
    if config.get('MEDIA_ROOT'):
        app.config['MEDIA_ROOT']=config['MEDIA_ROOT']
    if test_config:
        app.config.update(test_config)
    if not app.config['SECRET_KEY'] or not app.config['DB_PASSWORD']:
        raise RuntimeError('请配置 SECRET_KEY 和 DB_PASSWORD，参见 README.md。')

    def db():
        if 'db' not in g:
            g.db = py_opengauss.open(
                f"pq://{app.config['DB_USER']}@127.0.0.1:{app.config['DB_PORT']}/{app.config['DB_NAME']}",
                password=app.config['DB_PASSWORD'], sslmode='disable')
            g.db.execute('BEGIN')
        return g.db

    def query(sql, *args):
        statement = db().prepare(sql)
        rows = statement(*args)
        return [dict(zip(statement.column_names, row)) for row in rows] if statement.column_names else []

    def one(sql, *args):
        rows = query(sql, *args)
        return rows[0] if rows else None

    def uid():
        return g.user['user_id'] if g.user else None

    @app.before_request
    def load_user():
        if request.endpoint in ('static', 'catalog.stream', 'catalog.lyrics'):
            return
        session.setdefault('csrf', secrets.token_hex(24))
        g.user = one('SELECT user_id, username, nickname, bio, is_admin FROM music.app_user WHERE user_id=$1', session['uid']) if session.get('uid') else None
        if request.method == 'POST':
            if not hmac.compare_digest(str(session['csrf']), request.form.get('csrf', '')):
                abort(400, '页面已过期，请刷新后重试。')

    @app.after_request
    def finish(response):
        committed = response.status_code < 400
        if 'db' in g:
            try:
                g.db.execute('COMMIT' if committed else 'ROLLBACK')
            except DatabaseError:
                committed = False
                try:
                    g.db.execute('ROLLBACK')
                except DatabaseError:
                    pass
                response = make_response(render_template('error.html', message='保存未完成，所有改动已取消，请重试。'), 503)
            g.transaction_finished = True
        finish_files(committed)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.teardown_request
    def close(error):
        if 'db' in g:
            if not g.get('transaction_finished'):
                try:
                    g.db.execute('ROLLBACK')
                except DatabaseError:
                    pass
                finish_files(False)
            g.db.close()

    @app.errorhandler(DatabaseError)
    def database_error(error):
        app.logger.error('Database request failed: %s', type(error).__name__)
        return render_template('error.html', message='数据库操作未完成，请稍后重试。'), 503

    for code in (400, 403, 404, 409, 413, 503):
        app.register_error_handler(code, lambda error: (render_template('error.html', message=error.description), error.code))

    @app.context_processor
    def common():
        return {'me': getattr(g, 'user', None), 'csrf': session.get('csrf'), 'duration': lambda s: f'{int(s or 0)//60}:{int(s or 0)%60:02d}'}

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                flash('请先登录。')
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return wrapped

    def field(name, limit, required=True):
        value = request.form.get(name, '').strip()
        if (required and not value) or len(value) > limit:
            abort(400, f'请检查{name}，最长 {limit} 个字符。')
        return value

    def playlist(pid, owner=False, lock=False):
        p = one('SELECT p.*, u.nickname FROM music.playlist p JOIN music.app_user u ON u.user_id=p.creator_id WHERE p.playlist_id=$1' + (' FOR UPDATE OF p' if lock else ''), pid)
        if not p or (p['visibility'] == 'private' and p['creator_id'] != uid()):
            abort(404, '歌单不存在或未公开。')
        if owner and p['creator_id'] != uid():
            abort(403, '只有创建者可以修改这张歌单。')
        return p

    song_sql = '''SELECT s.*, (m.song_id IS NOT NULL) AS has_audio, m.original_name AS audio_name, EXISTS(SELECT 1 FROM music.song_lyrics ly WHERE ly.song_id=s.song_id) AS has_lyrics, COALESCE(a.album_title, '独立单曲') AS album_title,
        COALESCE((SELECT string_agg(ar.artist_name, ' / ' ORDER BY ar.artist_id)
        FROM music.song_artist sa JOIN music.artist ar ON ar.artist_id=sa.artist_id WHERE sa.song_id=s.song_id), '未知音乐人') AS artists,
        EXISTS(SELECT 1 FROM music.song_like l WHERE l.song_id=s.song_id AND l.user_id=$1) AS liked
        FROM music.song s LEFT JOIN music.album a ON a.album_id=s.album_id
        LEFT JOIN music.song_media m ON m.song_id=s.song_id'''

    def songs(search=''):
        return query(song_sql + ''' WHERE s.song_title ILIKE $2 OR a.album_title ILIKE $2 OR EXISTS
            (SELECT 1 FROM music.song_artist sa JOIN music.artist ar ON ar.artist_id=sa.artist_id
             WHERE sa.song_id=s.song_id AND ar.artist_name ILIKE $2) ORDER BY s.song_id''', uid(), '%'+search+'%')

    playlist_sql = '''SELECT p.*, u.nickname,
        (SELECT count(*) FROM music.playlist_song ps WHERE ps.playlist_id=p.playlist_id) AS song_count,
        COALESCE((SELECT sum(s.duration_seconds) FROM music.playlist_song ps JOIN music.song s ON s.song_id=ps.song_id WHERE ps.playlist_id=p.playlist_id),0) AS seconds,
        (SELECT count(*) FROM music.playlist_favorite f WHERE f.playlist_id=p.playlist_id) AS favorites
        FROM music.playlist p JOIN music.app_user u ON u.user_id=p.creator_id'''

    @app.get('/')
    @app.get('/songs')
    def library():
        search = request.args.get('q', '')[:150]
        own_playlists = query('SELECT playlist_id,playlist_name,visibility FROM music.playlist WHERE creator_id=$1 ORDER BY playlist_id DESC', uid()) if g.user else []
        memberships = query('''SELECT ps.playlist_id,ps.song_id FROM music.playlist_song ps
            JOIN music.playlist p ON p.playlist_id=ps.playlist_id WHERE p.creator_id=$1''', uid()) if g.user else []
        for item in own_playlists:
            item['song_ids'] = [r['song_id'] for r in memberships if r['playlist_id']==item['playlist_id']]
        return render_template('songs.html', songs=songs(search), search=search, own_playlists=own_playlists)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username, nickname = field('username', 50), field('nickname', 50)
            password = request.form.get('password', '')
            if not 8 <= len(password) <= 128:
                abort(400, '密码长度应为 8 至 128 个字符。')
            query('SAVEPOINT register_user')
            try:
                row = one('INSERT INTO music.app_user(username,nickname,password_hash) VALUES($1,$2,$3) RETURNING user_id', username, nickname, generate_password_hash(password))
            except UniqueError:
                query('ROLLBACK TO SAVEPOINT register_user')
                flash('这个用户名已经有人使用了。')
            else:
                session.clear(); session.update(uid=row['user_id'], csrf=secrets.token_hex(24))
                return redirect(url_for('library'))
            finally:
                query('RELEASE SAVEPOINT register_user')
        return render_template('auth.html', register=True)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = one('SELECT user_id,password_hash FROM music.app_user WHERE username=$1', field('username', 50))
            password = request.form.get('password', '')
            if user and user['password_hash'] and len(password) <= 128 and check_password_hash(user['password_hash'], password):
                session.clear(); session.update(uid=user['user_id'], csrf=secrets.token_hex(24))
                return redirect(url_for('library'))
            flash('用户名或密码不正确；历史账号需先初始化密码。')
        return render_template('auth.html', register=False)

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('library'))

    @app.route('/me', methods=['GET', 'POST'])
    @login_required
    def profile():
        if request.method == 'POST':
            query('UPDATE music.app_user SET nickname=$1,bio=$2 WHERE user_id=$3', field('nickname', 50), field('bio', 300, False), uid())
            flash('个人资料已保存。')
            return redirect(url_for('profile'))
        liked = [s for s in songs() if s['liked']]
        favorites = query(playlist_sql + " WHERE p.visibility='public' AND EXISTS(SELECT 1 FROM music.playlist_favorite f WHERE f.playlist_id=p.playlist_id AND f.user_id=$1) ORDER BY p.playlist_id", uid())
        return render_template('profile.html', songs=liked, playlists=favorites)

    def like_return_url():
        # Only existing song-list pages may be a return target, never an external URL.
        target = request.form.get('return_path', '')
        if (target.startswith('/') and not target.startswith('//')
                and len(target) <= 2048 and '\\' not in target
                and not any(ord(char) < 32 or ord(char) == 127 for char in target)):
            parts = urlsplit(target)
            if not parts.scheme and not parts.netloc and not parts.fragment:
                try:
                    endpoint, _ = app.url_map.bind('localhost').match(parts.path, method='GET')
                except HTTPException:
                    pass
                else:
                    if endpoint in {'library', 'profile', 'discover', 'detail'}:
                        return target
        # Keep compatibility with forms rendered before this update.
        return (url_for('profile') if request.form.get('return_to') == 'profile'
                else url_for('library', q=request.form.get('q', '')[:150]))

    @app.post('/songs/<int:sid>/<action>')
    @login_required
    def like(sid, action):
        if action not in ('like', 'unlike') or not one('SELECT song_id FROM music.song WHERE song_id=$1', sid):
            abort(404)
        query('SELECT user_id FROM music.app_user WHERE user_id=$1 FOR UPDATE', uid())
        if action == 'like':
            query('INSERT INTO music.song_like(user_id,song_id) SELECT $1,$2 WHERE NOT EXISTS(SELECT 1 FROM music.song_like WHERE user_id=$1 AND song_id=$2)', uid(), sid)
        else:
            query('DELETE FROM music.song_like WHERE user_id=$1 AND song_id=$2', uid(), sid)
        return redirect(like_return_url())

    @app.get('/playlists')
    def public_playlists():
        return render_template('playlists.html', mine=False, playlists=query(playlist_sql + " WHERE p.visibility='public' ORDER BY p.playlist_id DESC"))

    @app.get('/my/playlists')
    @login_required
    def my_playlists():
        return render_template('playlists.html', mine=True, playlists=query(playlist_sql+' WHERE p.creator_id=$1 ORDER BY p.playlist_id DESC', uid()))

    def playlist_fields():
        visibility = request.form.get('visibility')
        if visibility not in ('public', 'private'):
            abort(400, '请选择公开或私密。')
        return field('playlist_name', 100), field('description', 1000, False), visibility

    @app.post('/playlists')
    @login_required
    def create_playlist():
        name, description, visibility = playlist_fields()
        p = one('INSERT INTO music.playlist(creator_id,playlist_name,description,visibility) VALUES($1,$2,$3,$4) RETURNING playlist_id', uid(), name, description, visibility)
        return redirect(url_for('detail', pid=p['playlist_id']))

    @app.get('/playlists/<int:pid>')
    def detail(pid):
        p = playlist(pid)
        stats = one(playlist_sql+' WHERE p.playlist_id=$1', pid)
        selected = query('SELECT song_id,position_no FROM music.playlist_song WHERE playlist_id=$1 ORDER BY position_no', pid)
        all_songs = songs()
        lookup = {s['song_id']:s for s in all_songs}
        ordered = [{**lookup[x['song_id']], 'position_no':x['position_no']} for x in selected]
        return render_template('detail.html', p=p, stats=stats, songs=ordered,
            available=[s for s in all_songs if s['song_id'] not in {x['song_id'] for x in selected}],
            favorite=one('SELECT user_id FROM music.playlist_favorite WHERE user_id=$1 AND playlist_id=$2', uid(), pid))

    @app.post('/playlists/<int:pid>/edit')
    @login_required
    def edit_playlist(pid):
        playlist(pid, owner=True, lock=True)
        name, description, visibility = playlist_fields()
        query('UPDATE music.playlist SET playlist_name=$1,description=$2,visibility=$3 WHERE playlist_id=$4', name, description, visibility, pid)
        flash('歌单已保存。')
        return redirect(url_for('detail', pid=pid))

    @app.post('/playlists/<int:pid>/delete')
    @login_required
    def delete_playlist(pid):
        playlist(pid, owner=True, lock=True)
        query('DELETE FROM music.playlist_favorite WHERE playlist_id=$1', pid)
        query('DELETE FROM music.playlist_song WHERE playlist_id=$1', pid)
        query('DELETE FROM music.playlist WHERE playlist_id=$1', pid)
        flash('歌单已删除。')
        return redirect(url_for('my_playlists'))

    @app.post('/playlists/<int:pid>/<action>')
    @login_required
    def favorite(pid, action):
        if action not in ('favorite', 'unfavorite'):
            abort(404)
        playlist(pid, lock=True)
        if action == 'favorite':
            query('INSERT INTO music.playlist_favorite(user_id,playlist_id) SELECT $1,$2 WHERE NOT EXISTS(SELECT 1 FROM music.playlist_favorite WHERE user_id=$1 AND playlist_id=$2)', uid(), pid)
        else:
            query('DELETE FROM music.playlist_favorite WHERE user_id=$1 AND playlist_id=$2', uid(), pid)
        return redirect(url_for('detail', pid=pid))

    @app.post('/playlists/<int:pid>/songs')
    @login_required
    def add_song(pid):
        target_playlist = playlist(pid, owner=True, lock=True)
        try:
            sid = int(request.form.get('song_id', ''))
        except ValueError:
            abort(400, '请选择歌曲。')
        if not one('SELECT song_id FROM music.song WHERE song_id=$1', sid):
            abort(404, '歌曲不存在。')
        already_added = one('SELECT song_id FROM music.playlist_song WHERE playlist_id=$1 AND song_id=$2', pid, sid)
        if not already_added:
            query('CALL music.add_song_to_playlist($1,$2,$3)', uid(), pid, sid)
        if request.form.get('return_to') == 'library':
            flash(('这首歌已在「%s」中，无需重复添加。' if already_added else '已添加到「%s」。') % target_playlist['playlist_name'])
            return redirect(url_for('library', q=request.form.get('q','')[:150]))
        return redirect(url_for('detail', pid=pid))

    @app.post('/playlists/<int:pid>/songs/<int:sid>/<action>')
    @login_required
    def arrange(pid, sid, action):
        playlist(pid, owner=True, lock=True)
        if action not in ('remove', 'move'):
            abort(404)
        ids = [x['song_id'] for x in query('SELECT song_id FROM music.playlist_song WHERE playlist_id=$1 ORDER BY position_no', pid)]
        if sid not in ids:
            abort(404)
        i = ids.index(sid)
        if action == 'remove':
            query('DELETE FROM music.playlist_song WHERE playlist_id=$1 AND song_id=$2', pid, sid)
            ids.remove(sid)
        else:
            direction = request.form.get('direction')
            if direction not in ('up', 'down'):
                abort(400)
            j = i + (-1 if direction == 'up' else 1)
            if 0 <= j < len(ids):
                ids[i], ids[j] = ids[j], ids[i]
        max_pos = one('SELECT COALESCE(MAX(position_no),0) AS n FROM music.playlist_song WHERE playlist_id=$1', pid)['n']
        # Move each row above the previous maximum, then assign compact final positions.
        for k, song_id in enumerate(ids, 1):
            query('UPDATE music.playlist_song SET position_no=$1 WHERE playlist_id=$2 AND song_id=$3', max_pos+k, pid, song_id)
        for k, song_id in enumerate(ids, 1):
            query('UPDATE music.playlist_song SET position_no=$1 WHERE playlist_id=$2 AND song_id=$3', k, pid, song_id)
        return redirect(url_for('detail', pid=pid))

    @app.get('/discover')
    @login_required
    def discover():
        # SQL calculates intersections/unions; NULL distinguishes users with insufficient data.
        people = query('''WITH mine AS (SELECT song_id FROM music.song_like WHERE user_id=$1),
            counts AS (SELECT u.user_id,u.nickname,count(l.song_id) AS other_count,
                sum(CASE WHEN l.song_id IN (SELECT song_id FROM mine) THEN 1 ELSE 0 END) AS shared_count
                FROM music.app_user u LEFT JOIN music.song_like l ON l.user_id=u.user_id
                WHERE u.user_id<>$1 GROUP BY u.user_id,u.nickname)
            SELECT *, CASE WHEN (SELECT count(*) FROM mine)=0 OR other_count=0 THEN NULL
                ELSE shared_count*1.0/((SELECT count(*) FROM mine)+other_count-shared_count) END AS similarity
            FROM counts ORDER BY similarity DESC NULLS LAST,user_id''', uid())
        scores = {}
        liked = {s['song_id'] for s in songs() if s['liked']}
        for person in people:
            if person['similarity'] and person['similarity'] > 0:
                for item in query('SELECT song_id FROM music.song_like WHERE user_id=$1', person['user_id']):
                    if item['song_id'] not in liked:
                        scores[item['song_id']] = scores.get(item['song_id'], 0) + person['similarity']
        recommended = sorted([{**s, 'score':scores[s['song_id']]} for s in songs() if s['song_id'] in scores], key=lambda s: (-s['score'],s['song_id']))
        return render_template('discover.html', people=people, songs=recommended)

    register_catalog(app, query, one, songs, field)
    return app
