-- 先停 Web、备份数据库及媒体目录，还原歌词接入前代码后再使用。
BEGIN;
DROP TABLE music.song_lyrics;
COMMIT;
-- 不删除音频文件，不撤回已绑定的音频或真实时长。
