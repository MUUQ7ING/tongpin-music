"""Bind a reviewed local Music folder to existing catalog rows; never create new songs."""
import argparse,hashlib,io,json,os,re,subprocess,sys,unicodedata
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import py_opengauss
from app import create_app
from app.lyrics import parse_lrc,read_lrc_upload
from werkzeug.datastructures import FileStorage
ROOT=Path(__file__).resolve().parent.parent
ALIASES={'新宝島':'新宝岛','三日月サンセット':'新月余晖'}
ARTISTS={'サカナクション':'Sakanaction','ヨルシカ':'ヨルシカ（夜鹿）','Fred again':'Fred again..'}
def norm(text):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text).replace('’',"'").strip()).casefold()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('directory',nargs='?',default=str(ROOT.parent/'Music'));parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 source=Path(args.directory).resolve();app=create_app({'TESTING':True});cfg=app.config
 c=py_opengauss.open('pq://%s@127.0.0.1:%s/%s'%(cfg['DB_USER'],cfg['DB_PORT'],cfg['DB_NAME']),password=cfg['DB_PASSWORD'],sslmode='disable')
 def rows(sql,*values):
  st=c.prepare(sql);return [dict(zip(st.column_names,r)) for r in st(*values)]
 try:
  songs=rows('SELECT song_id,song_title,duration_seconds FROM music.song ORDER BY song_id')
  catalog={norm(s['song_title']):s for s in songs}
  people={s['song_id']:set() for s in songs}
  for row in rows('SELECT sa.song_id,a.artist_name FROM music.song_artist sa JOIN music.artist a ON a.artist_id=sa.artist_id'):people[row['song_id']].add(norm(row['artist_name']))
  report=json.loads((source/'_download_report.json').read_text())
  by_index={int(item['index']):item for item in report}
  groups={}
  for file in sorted(source.glob('*.mp3')):
   numbered=re.match(r'^(\d+) - ',file.stem)
   if numbered:
    item=by_index[int(numbered[1])];title=item['title'];artist=item['artist'].split(' / ')[0]
   else:
    artist,title=file.stem.split(' - ',1);artist=artist.split(',')[0].strip()
   title=ALIASES.get(unicodedata.normalize('NFKC',title),title)
   track=catalog.get(norm(title))
   if not track:raise ValueError('未匹配歌曲：'+file.name)
   main_artist=ARTISTS.get(unicodedata.normalize('NFKC',artist),artist)
   if norm(main_artist) not in people[track['song_id']]:raise ValueError('主要音乐人不匹配：'+file.name)
   probe=json.loads(subprocess.check_output([cfg['FFPROBE_BIN'],'-v','error','-show_entries','format=duration,bit_rate','-of','json',str(file)]))['format']
   groups.setdefault(track['song_id'],[]).append(dict(path=file,seconds=float(probe['duration']),bit_rate=int(probe.get('bit_rate',0))))
  if len(groups)!=35:raise ValueError('本批应完整匹配原有35首歌曲，实际为'+str(len(groups)))
  plans=[]
  for song in songs:
   if song['song_id'] not in groups:continue
   candidates=groups[song['song_id']];selected=max(candidates,key=lambda item:item['bit_rate'])
   # A higher-quality duplicate can reuse sidecar lyrics from the same-title lower-quality file.
   lyric_candidates=[item['path'].with_suffix('.lrc') for item in candidates if item['path'].with_suffix('.lrc').is_file()]
   original=lyric_candidates[0] if lyric_candidates else None
   translation=original.with_name(original.stem+'.zh.lrc') if original else None
   if translation and not translation.is_file():translation=None
   for lrc in [original,translation]:
    if lrc:
     with app.test_request_context(),lrc.open('rb') as file:read_lrc_upload(FileStorage(stream=file,filename=lrc.name))
   plans.append(dict(song_id=song['song_id'],title=song['song_title'],file=selected['path'].name,
    duration=selected['seconds'],previous_duration=song['duration_seconds'],sha256=hashlib.sha256(selected['path'].read_bytes()).hexdigest(),
    lyrics=original.name if original else None,translation=translation.name if translation else None,
    duplicates=[item['path'].name for item in candidates if item is not selected]))
  output=ROOT/'数据/本地音乐绑定清单.json';output.write_text(json.dumps(plans,ensure_ascii=False,indent=2)+'\n')
  print('匹配',len(plans),'首；原文歌词',sum(bool(p['lyrics']) for p in plans),'份；翻译',sum(bool(p['translation']) for p in plans),'份。',flush=True)
  if not args.apply:return
  stamp=datetime.now().strftime('%Y%m%d_%H%M%S');backup=ROOT/'备份'/('music_binding_'+stamp);backup.mkdir(parents=True)
  snapshot=dict(songs=songs,media=rows('SELECT * FROM music.song_media'),lyrics=rows('SELECT * FROM music.song_lyrics'))
  (backup/'before.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str))
  admin=rows('SELECT user_id FROM music.app_user WHERE username=$1 AND is_admin=true','music_admin')[0]['user_id']
  client=app.test_client()
  with client.session_transaction() as sess:sess.update(uid=admin,csrf='local-music-batch')
  outcomes=[]
  def save(): (backup/'results.json').write_text(json.dumps(outcomes,ensure_ascii=False,indent=2)+'\n')
  for plan in plans:
   sid=plan['song_id'];current=rows('SELECT sha256 FROM music.song_media WHERE song_id=$1',sid)
   result={'song_id':sid,'title':plan['title'],'audio':'unchanged','lyrics':'none'}
   if not current or current[0]['sha256']!=plan['sha256']:
    with (source/plan['file']).open('rb') as file:r=client.post(f'/admin/catalog/songs/{sid}/audio',data={'csrf':'local-music-batch','audio':(file,plan['file'])})
    if r.status_code!=302:save();raise RuntimeError('音频绑定失败：'+plan['title']+' HTTP '+str(r.status_code))
    result['audio']='bound'
   if plan['lyrics']:
    from contextlib import ExitStack
    with ExitStack() as stack:
     data={'csrf':'local-music-batch','lyrics':(stack.enter_context((source/plan['lyrics']).open('rb')),plan['lyrics'])}
     if plan['translation']:data['translation']=(stack.enter_context((source/plan['translation']).open('rb')),plan['translation'])
     original=(source/plan['lyrics']).read_bytes().decode('utf-8-sig');translated=(source/plan['translation']).read_bytes().decode('utf-8-sig') if plan['translation'] else None
     current_lyric=rows('SELECT original_lrc,translated_lrc FROM music.song_lyrics WHERE song_id=$1',sid)
     if not current_lyric or current_lyric[0]['original_lrc']!=original or current_lyric[0]['translated_lrc']!=translated:
      r=client.post(f'/admin/catalog/songs/{sid}/lyrics',data=data)
      if r.status_code!=302:save();raise RuntimeError('歌词绑定失败：'+plan['title'])
      result['lyrics']='bound'
     else:result['lyrics']='unchanged'
   outcomes.append(result);save();print(plan['title'],result['audio'],result['lyrics'],flush=True)
  print('每首歌按独立事务保存；原文件保留。备份：',backup,flush=True)
 finally:c.close()
if __name__=='__main__':main()
