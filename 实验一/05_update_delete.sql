-- 在 music_platform 的 jp 会话执行。每组含操作前后查询，分别截图。

-- A：修改歌单信息（截图25）。只影响歌单1，不改变歌曲与偏好数据。
SELECT playlist_id, playlist_name, description
FROM music.playlist WHERE playlist_id = 1;

UPDATE music.playlist
SET playlist_name = '通勤路上的音乐',
    description = '分享每天通勤时喜欢听的歌曲'
WHERE playlist_id = 1 AND creator_id = 1;

SELECT playlist_id, playlist_name, description
FROM music.playlist WHERE playlist_id = 1;

-- B：模拟用户6收藏公开歌单2（截图26）。
SELECT user_id, playlist_id FROM music.playlist_favorite
WHERE user_id = 6 AND playlist_id = 2;

INSERT INTO music.playlist_favorite (user_id, playlist_id)
VALUES (6, 2);

SELECT user_id, playlist_id FROM music.playlist_favorite
WHERE user_id = 6 AND playlist_id = 2;

-- C：用户6取消该收藏（截图27）。删除后恢复原有收藏数据量。
DELETE FROM music.playlist_favorite
WHERE user_id = 6 AND playlist_id = 2;

SELECT user_id, playlist_id FROM music.playlist_favorite
WHERE user_id = 6 AND playlist_id = 2;

SELECT COUNT(*) AS favorite_count FROM music.playlist_favorite;
