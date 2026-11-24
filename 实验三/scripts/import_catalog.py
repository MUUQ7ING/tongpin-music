"""导入审核后的歌曲资料；全程事务，先保存受影响表快照，支持重复执行。"""
import json,os,sys,unicodedata,argparse
from datetime import datetime
from pathlib import Path
from getpass import getpass
import py_opengauss
ROOT=Path(__file__).resolve().parent.parent
BANDS={'Daft Punk','Magdalena Bay','ヨルシカ（夜鹿）','Mrs. GREEN APPLE','結束バンド','Radiohead','New Order','Bôa','Chinese Football'}
ALIASES={'サカナクション（鱼韵）':'Sakanaction','新宝島':'新宝岛'}
def norm(value):
    return unicodedata.normalize('NFKC',ALIASES.get(value,value)).casefold().strip()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    tracks=json.loads((ROOT/'数据/扩充导入资料.json').read_text())
    descriptions=json.loads((ROOT/'数据/分类歌单简介.json').read_text())
    settings=dict(line.split('=',1) for line in (ROOT/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    port=os.getenv('DB_PORT',settings.get('DB_PORT','12600'))
    c=py_opengauss.open(f'pq://jp@127.0.0.1:{port}/music_platform',password=os.getenv('DB_OWNER_PASSWORD') or getpass('jp 数据库密码: '),sslmode='disable')
    def rows(sql,*args):
        st=c.prepare(sql);data=st(*args)
        return [dict(zip(st.column_names,row)) for row in data] if st.column_names else []
    manifest=dict(created={k:[] for k in ['artist','album','song','playlist']},reused_songs=[],playlists=[],source='扩充歌单.md',state='dry_run')
    run=ROOT/'备份'/('catalog_'+datetime.now().strftime('%Y%m%d_%H%M%S'));run.mkdir(parents=True)
    try:
        c.execute('BEGIN')
        c.execute('LOCK TABLE music.artist, music.album, music.song, music.song_artist, music.playlist, music.playlist_song IN SHARE ROW EXCLUSIVE MODE')
        snapshot={table:rows(f'SELECT * FROM music.{table} ORDER BY 1,2') for table in ['artist','album','song','song_artist','playlist','playlist_song']}
        (run/'before.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str))
        artists={norm(x['artist_name']):x['artist_id'] for x in snapshot['artist']}
        albums={norm(x['album_title']):x['album_id'] for x in snapshot['album']}
        relations={x['song_id']:set() for x in snapshot['song']}
        for x in snapshot['song_artist']:relations[x['song_id']].add(x['artist_id'])
        existing=list(snapshot['song']);selected={}
        for track in tracks:
            artist_ids=[]
            for name in track['artists']:
                key=norm(name)
                if key not in artists:
                    aid=rows('INSERT INTO music.artist(artist_name,artist_type) VALUES($1,$2) RETURNING artist_id',name,'band' if name in BANDS else 'solo')[0]['artist_id']
                    artists[key]=aid;manifest['created']['artist'].append(aid)
                artist_ids.append(artists[key])
            matched=[s for s in existing if norm(s['song_title'])==norm(track['title']) and relations[s['song_id']]==set(artist_ids)]
            if matched:
                sid=matched[0]['song_id'];manifest['reused_songs'].append({'title':track['title'],'song_id':sid})
            else:
                key=norm(track['album'])
                if key not in albums:
                    albums[key]=rows('INSERT INTO music.album(album_title) VALUES($1) RETURNING album_id',track['album'])[0]['album_id'];manifest['created']['album'].append(albums[key])
                sid=rows('INSERT INTO music.song(song_title,album_id,duration_seconds,genre) VALUES($1,$2,$3,$4) RETURNING song_id',track['title'],albums[key],track['duration_seconds'],track['genre'])[0]['song_id']
                manifest['created']['song'].append(sid)
                for aid in artist_ids:rows('INSERT INTO music.song_artist(song_id,artist_id) VALUES($1,$2)',sid,aid)
                existing.append({'song_id':sid,'song_title':track['title']});relations[sid]=set(artist_ids)
            selected.setdefault(track['category'],[]).append(sid)
        creator=rows('SELECT user_id FROM music.app_user WHERE username=$1','tongpin_demo')[0]['user_id']
        for name,ids in selected.items():
            desc=descriptions.get(name, '收录想反复听的音乐。')
            found=rows('SELECT playlist_id FROM music.playlist WHERE creator_id=$1 AND playlist_name=$2',creator,name)
            if len(found)>1:raise ValueError('同名歌单不唯一，请先明确要复用的歌单：'+name)
            if found:pid=found[0]['playlist_id']
            else:
                pid=rows("INSERT INTO music.playlist(creator_id,playlist_name,description,visibility) VALUES($1,$2,$3,'public') RETURNING playlist_id",creator,name,desc)[0]['playlist_id'];manifest['created']['playlist'].append(pid)
                for position,sid in enumerate(dict.fromkeys(ids),1):rows('INSERT INTO music.playlist_song(playlist_id,song_id,position_no) VALUES($1,$2,$3)',pid,sid,position)
            manifest['playlists'].append({'name':name,'playlist_id':pid,'song_ids':ids})
        manifest['counts_after']={t:rows(f'SELECT count(*) AS n FROM music.{t}')[0]['n'] for t in ['artist','album','song','playlist','playlist_song']}
        manifest['state']='prepared'
        # Save the ID manifest before commit so it is available even if the process exits immediately afterward.
        (run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        c.execute('COMMIT' if args.apply else 'ROLLBACK')
        manifest['state']='committed' if args.apply else 'rolled_back_dry_run'
        (run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        rollback=['-- 仅撤回本批新增数据；后续其他对象若已引用新增歌曲，外键将阻止删除。','BEGIN;']
        def delete(table,column,ids):
            if ids:rollback.append(f"DELETE FROM music.{table} WHERE {column} IN ({','.join(map(str,ids))});")
        pids=manifest['created']['playlist'];sids=manifest['created']['song']
        delete('playlist_favorite','playlist_id',pids);delete('playlist_song','playlist_id',pids);delete('playlist','playlist_id',pids)
        delete('song_artist','song_id',sids);delete('song','song_id',sids);delete('album','album_id',manifest['created']['album']);delete('artist','artist_id',manifest['created']['artist'])
        rollback.append('COMMIT;');(run/'rollback.sql').write_text('\n'.join(rollback)+'\n')
        print(json.dumps(manifest,ensure_ascii=False,indent=2));print('快照与撤回脚本:',run)
    except BaseException as error:
        c.execute('ROLLBACK')
        manifest['state']='rolled_back_error'
        manifest['error']=type(error).__name__
        (run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        raise
    finally:c.close()
if __name__=='__main__':main()
