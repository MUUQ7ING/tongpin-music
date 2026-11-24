-- 本批曲库导入前，以 omm 在 music_platform 执行。
-- 四个序列由 omm 创建，曲库表的数据所有者 jp 需要使用其默认编号。
-- 不扩大 Web 角色 music_web 的曲库写权限。
GRANT USAGE, SELECT ON SEQUENCE
    music.artist_id_seq, music.album_id_seq,
    music.song_id_seq, music.playlist_id_seq TO jp;
