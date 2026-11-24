"""Validated audio storage. Files stay outside static and use opaque server-generated names."""
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from flask import abort, current_app, g

FORMATS = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.flac': 'audio/flac',
           '.ogg': 'audio/ogg', '.m4a': 'audio/mp4'}


def probe_audio(path, suffix):
    binary = current_app.config['FFPROBE_BIN']
    if not binary or not shutil.which(binary):
        abort(503, '音频校验工具尚未安装，请联系管理员。')
    try:
        run = subprocess.run([binary, '-v', 'error', '-show_entries',
            'format=duration:stream=codec_type,codec_name:stream_disposition=attached_pic',
            '-of', 'json', str(path)], capture_output=True, timeout=20, check=True)
        data = json.loads(run.stdout)
        streams = data.get('streams', [])
        audio = [s for s in streams if s.get('codec_type') == 'audio']
        if len(audio) != 1 or any(s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic') for s in streams):
            raise ValueError('not a single audio track')
        codec = audio[0].get('codec_name', '')
        valid = {'.mp3': codec == 'mp3', '.wav': codec.startswith('pcm_'), '.flac': codec == 'flac',
                 '.ogg': codec in ('vorbis', 'opus'), '.m4a': codec in ('aac', 'alac')}
        seconds = float(data['format']['duration'])
        if not valid[suffix] or not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise ValueError('unsupported audio')
        return round(seconds, 3)
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError):
        abort(400, '文件不是有效的音频，或内容与扩展名不符。请上传 MP3、WAV、FLAC、OGG 或 M4A。')


def store_upload(upload):
    original = re.sub(r'[\x00-\x1f\x7f]', '', (upload.filename or '').replace('\\', '/').rsplit('/', 1)[-1]).strip()
    suffix = Path(original).suffix.lower()
    if suffix not in FORMATS:
        abort(400, '支持 MP3、WAV、FLAC、OGG、M4A，不能上传其他类型的文件。')
    root = Path(current_app.config['MEDIA_ROOT'])
    root.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex + suffix
    path = root / key
    g.setdefault('new_media_files', []).append(path)
    size = 0
    digest = hashlib.sha256()
    with path.open('xb') as target:
        while block := upload.stream.read(1024 * 1024):
            size += len(block)
            if size > current_app.config['MAX_AUDIO_BYTES']:
                abort(413, '单个音频文件不能超过 100 MB。')
            target.write(block)
            digest.update(block)
    if size == 0:
        abort(400, '不能上传空文件。')
    path.chmod(0o600)
    seconds = probe_audio(path, suffix)
    return dict(storage_key=key, original_name=original[:255], mime_type=FORMATS[suffix],
                byte_size=size, duration_seconds=seconds, sha256=digest.hexdigest())


def media_path(key):
    if not re.fullmatch(r'[a-f0-9]{32}\.(mp3|wav|flac|ogg|m4a)', key or ''):
        abort(404, '音频文件不存在。')
    root = Path(current_app.config['MEDIA_ROOT']).resolve()
    path = root / key
    if path.is_symlink() or path.resolve().parent != root:
        abort(404, '音频文件不存在。')
    return path


def finish_files(committed):
    files = g.get('old_media_files', []) if committed else g.get('new_media_files', [])
    for path in files:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            current_app.logger.error('Could not clean up an audio file')
    g.pop('new_media_files', None)
    g.pop('old_media_files', None)
