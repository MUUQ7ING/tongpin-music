-- 本次实际以omm连接music_platform；逐段执行，预期错误调用需单独执行。
INSERT INTO music.playlist (playlist_id, creator_id, playlist_name, visibility)
VALUES (2001, 1, '实验二测试歌单', 'public');
CREATE OR REPLACE PROCEDURE music.add_song_to_playlist(
    IN p_user_id INTEGER, IN p_playlist_id INTEGER, IN p_song_id INTEGER
)
AS
DECLARE
    v_owner INTEGER;
    v_position INTEGER;
BEGIN
    SELECT creator_id INTO v_owner FROM music.playlist
    WHERE playlist_id = p_playlist_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Playlist does not exist';
    END IF;
    IF p_user_id IS NULL OR v_owner <> p_user_id THEN
        RAISE EXCEPTION 'Only the playlist creator may add songs';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM music.song WHERE song_id = p_song_id) THEN
        RAISE EXCEPTION 'Song does not exist';
    END IF;
    IF EXISTS (SELECT 1 FROM music.playlist_song
               WHERE playlist_id = p_playlist_id AND song_id = p_song_id) THEN
        RAISE EXCEPTION 'Song already in playlist';
    END IF;
    SELECT COALESCE(MAX(position_no), 0) + 1 INTO v_position
    FROM music.playlist_song WHERE playlist_id = p_playlist_id;
    INSERT INTO music.playlist_song (playlist_id, song_id, position_no)
    VALUES (p_playlist_id, p_song_id, v_position);
END;
/
CALL music.add_song_to_playlist(1, 2001, 2);
SELECT playlist_id, song_id, position_no FROM music.playlist_song WHERE playlist_id = 2001;
-- 以下分别单独执行，预期报错：非创建者、重复歌曲、歌曲不存在。
CALL music.add_song_to_playlist(2, 2001, 1);
CALL music.add_song_to_playlist(1, 2001, 2);
CALL music.add_song_to_playlist(1, 2001, -1);
SELECT playlist_id, song_id, position_no FROM music.playlist_song WHERE playlist_id = 2001;
-- p_user_id由调用者提供，只演示业务校验；不是可信身份认证机制。
