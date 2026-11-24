SELECT table_name FROM information_schema.tables
WHERE table_schema = 'music' AND table_type = 'BASE TABLE' ORDER BY table_name;
SELECT 'users' AS object_name, COUNT(*) FROM music.app_user
UNION ALL SELECT 'artist', COUNT(*) FROM music.artist
UNION ALL SELECT 'album', COUNT(*) FROM music.album
UNION ALL SELECT 'song', COUNT(*) FROM music.song
UNION ALL SELECT 'song_artist', COUNT(*) FROM music.song_artist
UNION ALL SELECT 'playlist', COUNT(*) FROM music.playlist
UNION ALL SELECT 'playlist_song', COUNT(*) FROM music.playlist_song
UNION ALL SELECT 'song_like', COUNT(*) FROM music.song_like
UNION ALL SELECT 'playlist_favorite', COUNT(*) FROM music.playlist_favorite
UNION ALL SELECT 'playlist_audit', COUNT(*) FROM music.playlist_audit
ORDER BY object_name;
SELECT * FROM music.v_public_playlist ORDER BY playlist_id;
SELECT playlist_id, song_id, position_no FROM music.playlist_song ORDER BY playlist_id, position_no;
SELECT audit_id, playlist_id, old_name, new_name, old_visibility, new_visibility, db_user, changed_at
FROM music.playlist_audit ORDER BY audit_id;
SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'music' AND p.proname IN ('add_song_to_playlist','audit_playlist_update') ORDER BY p.proname;
SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = 'trg_playlist_update_audit';
-- 恢复后额外验证：在事务中实际调用过程和触发更新，查询结果后ROLLBACK，避免留数据。
BEGIN;
CALL music.add_song_to_playlist(1, 2001, 1);
UPDATE music.playlist SET playlist_name = '恢复后功能验证' WHERE playlist_id = 2001;
SELECT song_id, position_no FROM music.playlist_song WHERE playlist_id = 2001 ORDER BY position_no;
SELECT COUNT(*) FROM music.playlist_audit WHERE playlist_id = 2001;
ROLLBACK;
