-- 仅在停 Web、备份当前数据库及 media 文件后，由 omm 执行；同时还原原版代码。
BEGIN;
DROP TABLE music.song_media;
ALTER TABLE music.app_user DROP COLUMN is_admin;
REVOKE INSERT, UPDATE ON music.song, music.album, music.artist FROM music_web;
REVOKE INSERT, DELETE ON music.song_artist FROM music_web;
REVOKE USAGE, SELECT ON SEQUENCE music.song_id_seq, music.album_id_seq, music.artist_id_seq FROM music_web;
GRANT INSERT, UPDATE ON music.app_user TO music_web;
COMMIT;
-- 新管理员账号在去掉标志后仅为普通账号；不自动删除账号或媒体文件。
