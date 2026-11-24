"""Read-only public deployment smoke checks; never prints passwords or lyrics."""
import http.cookiejar,json,re,urllib.request,urllib.parse
from pathlib import Path
base='http://121.36.78.59'
cookies=http.cookiejar.CookieJar()
client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(cookies))
def get(path,headers=None):
 return client.open(urllib.request.Request(base+path,headers=headers or {}),timeout=20)
checks=[]
for path in ('/songs','/playlists','/login'):
 with get(path) as r:
  assert r.status==200
  body=r.read().decode();assert '同频' in body
 checks.append('PASS GET '+path+' -> 200')
with get('/api/songs/2/lyrics') as r:
 data=json.load(r);assert data['lines'] and data['has_translation']
checks.append('PASS Shelter 同步歌词与翻译 JSON')
credentials=dict(l.split('=',1) for l in Path(__file__).resolve().parents[1].joinpath('.demo.env').read_text().splitlines() if '=' in l and not l.startswith('#'))
with get('/login') as r:html=r.read().decode()
csrf=re.search(r'name="csrf" value="([^"]+)"',html).group(1)
post=urllib.parse.urlencode({'csrf':csrf,'username':credentials['DEMO_USERNAME'],'password':credentials['DEMO_PASSWORD']}).encode()
with client.open(urllib.request.Request(base+'/login',data=post),timeout=20) as r:
 html=r.read().decode();assert '/logout' in html
checks.append('PASS 原体验账号公网登录')
for sid in (2,3):
 with get('/media/songs/'+str(sid),{'Range':'bytes=0-63'}) as r:
  assert r.status==206 and len(r.read())==64
 checks.append('PASS 音频 '+str(sid)+' Range -> 206')
print('\n'.join(checks))
