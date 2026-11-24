-- 在备份成功后，以 omm 在 music_platform 执行。
BEGIN;
ALTER TABLE music.app_user ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false;
CREATE TABLE music.song_media (
    song_id INTEGER PRIMARY KEY REFERENCES music.song(song_id),
    storage_key VARCHAR(64) NOT NULL UNIQUE,
    original_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(80) NOT NULL,
    byte_size BIGINT NOT NULL CHECK (byte_size > 0),
    duration_seconds NUMERIC(12,3) NOT NULL CHECK (duration_seconds > 0),
    sha256 CHAR(64) NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES music.app_user(user_id),
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE music.song_media OWNER TO jp;
GRANT SELECT, INSERT, UPDATE, DELETE ON music.song_media TO music_web;
GRANT USAGE, SELECT ON SEQUENCE music.app_user_id_seq TO jp;
GRANT INSERT, UPDATE ON music.song, music.album, music.artist TO music_web;
GRANT INSERT, DELETE ON music.song_artist TO music_web;
GRANT USAGE, SELECT ON SEQUENCE music.song_id_seq, music.album_id_seq, music.artist_id_seq TO music_web;
-- 管理员标志由数据库所有者维护；注册接口无法写入，应用角色也没有该列的更新权限。
REVOKE INSERT, UPDATE ON music.app_user FROM music_web;
GRANT INSERT (username,nickname,bio,password_hash) ON music.app_user TO music_web;
GRANT UPDATE (nickname,bio,password_hash) ON music.app_user TO music_web;
COMMIT;
