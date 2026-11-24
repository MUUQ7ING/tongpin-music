-- 迁移前先备份，以 omm 在 music_platform 中执行；本迁移只执行一次。
BEGIN;
ALTER TABLE music.app_user ADD COLUMN password_hash VARCHAR(256);
CREATE SEQUENCE music.app_user_id_seq;
SELECT setval('music.app_user_id_seq', COALESCE((SELECT MAX(user_id) FROM music.app_user),0)+1, false);
ALTER TABLE music.app_user ALTER COLUMN user_id SET DEFAULT nextval('music.app_user_id_seq');
CREATE SEQUENCE music.artist_id_seq;
SELECT setval('music.artist_id_seq', COALESCE((SELECT MAX(artist_id) FROM music.artist),0)+1, false);
ALTER TABLE music.artist ALTER COLUMN artist_id SET DEFAULT nextval('music.artist_id_seq');
CREATE SEQUENCE music.album_id_seq;
SELECT setval('music.album_id_seq', COALESCE((SELECT MAX(album_id) FROM music.album),0)+1, false);
ALTER TABLE music.album ALTER COLUMN album_id SET DEFAULT nextval('music.album_id_seq');
CREATE SEQUENCE music.song_id_seq;
SELECT setval('music.song_id_seq', COALESCE((SELECT MAX(song_id) FROM music.song),0)+1, false);
ALTER TABLE music.song ALTER COLUMN song_id SET DEFAULT nextval('music.song_id_seq');
CREATE SEQUENCE music.playlist_id_seq;
SELECT setval('music.playlist_id_seq', COALESCE((SELECT MAX(playlist_id) FROM music.playlist),0)+1, false);
ALTER TABLE music.playlist ALTER COLUMN playlist_id SET DEFAULT nextval('music.playlist_id_seq');
COMMIT;
-- 应用角色由管理员用随机密码单独创建，不在脚本中记录密码。
GRANT CONNECT ON DATABASE music_platform TO music_web;
GRANT USAGE ON SCHEMA music TO music_web;
GRANT SELECT ON music.artist, music.album, music.song, music.song_artist TO music_web;
GRANT SELECT, INSERT, UPDATE ON music.app_user TO music_web;
GRANT SELECT, INSERT, UPDATE, DELETE ON music.playlist, music.playlist_song, music.song_like, music.playlist_favorite TO music_web;
GRANT INSERT ON music.playlist_audit TO music_web;
GRANT USAGE, SELECT ON SEQUENCE music.app_user_id_seq, music.playlist_id_seq, music.playlist_audit_audit_id_seq TO music_web;
GRANT EXECUTE ON PROCEDURE music.add_song_to_playlist(INTEGER, INTEGER, INTEGER) TO music_web;
