"""LRC parsing without evaluating markup or fetching external content."""
from bisect import bisect_left
import re
from flask import abort
MAX_LRC_BYTES=1024*1024
STAMP=re.compile(r'\[(\d{1,4}):([0-5]\d)(?:[.:](\d{1,3}))?\]')

def parse_lrc(text):
    if not isinstance(text,str):return []
    offsets=re.findall(r'\[offset:([+-]?\d{1,9})\]',text,re.I)
    offset=int(offsets[-1])/1000 if offsets else 0
    cues={}
    for raw in text.splitlines():
        matches=list(STAMP.finditer(raw))
        if not matches:continue
        content=STAMP.sub('',raw).strip()
        for match in matches:
            seconds=int(match[1])*60+int(match[2])+(int(match[3])/(10**len(match[3])) if match[3] else 0)-offset
            seconds=round(max(0,seconds),3)
            if seconds>86400:continue
            # Keep empty timed cues to represent instrumental gaps, but prefer text for duplicate times.
            if seconds not in cues or (not cues[seconds] and content):cues[seconds]=content
            if len(cues)>10000:return []
    return [{'time':at,'text':value} for at,value in sorted(cues.items())]

def merge_lyrics(original,translation=None):
    lines=parse_lrc(original);translated=parse_lrc(translation or '')
    times=[item['time'] for item in translated]
    for line in lines:
        index=bisect_left(times,line['time'])
        candidates=translated[max(0,index-1):index+1]
        nearest=min(candidates,key=lambda item:abs(item['time']-line['time']),default=None)
        line['translation']=nearest['text'] if nearest and abs(nearest['time']-line['time'])<=0.6 else ''
    return lines

def read_lrc_upload(upload):
    if not (upload.filename or '').lower().endswith('.lrc'):abort(400,'歌词文件必须为 .lrc 格式。')
    data=upload.stream.read(MAX_LRC_BYTES+1)
    if not data or len(data)>MAX_LRC_BYTES:abort(400,'歌词文件不能为空，且不能超过 1 MB。')
    encodings=['utf-16'] if data.startswith((b'\xff\xfe',b'\xfe\xff')) else ['utf-8-sig','gb18030']
    text=None
    for encoding in encodings:
        try:text=data.decode(encoding);break
        except UnicodeError:continue
    if text is None or '\x00' in text:abort(400,'无法读取歌词编码，请保存为 UTF-8 格式。')
    cues=parse_lrc(text)
    if not any(line['text'] for line in cues):abort(400,'歌词中没有有效的时间戳和正文，请上传逐行 LRC 歌词。')
    return text
