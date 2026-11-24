-- 部分采用真实音乐资料；用户资料、行为、歌曲时长和曲风为实验模拟数据。
-- 同名歌曲可能有不同发行版本；回避依恋按实验要求仅关联张方钊，省略合作音乐人。
-- 在 music_platform 的 jp 会话，按 A/B/C 分组执行一次并截图。
-- 遇到报错停止，保留输出，不要整段重复插入。

-- A：用户与曲库（截图21，可拆分）
INSERT INTO music.app_user (user_id, username, nickname) VALUES
(1, 'lin', 'Oin76'), (2, 'sha', '鲨鲨'), (3, 'jp', 'Jpppp_'),
(4, 'gulu', '咕噜灵波'), (5, 'muqi', 'Muuq7_7'), (6, 'newcomer', '新听众');

INSERT INTO music.artist (artist_id, artist_name, artist_type) VALUES
(1, 'Porter Robinson', 'solo'), (2, 'Sakanaction', 'band'),
(3, '张方钊', 'solo'), (4, '透明杂志', 'band'),
(5, 'Madeon', 'solo');

INSERT INTO music.album (album_id, album_title, release_date) VALUES
(1, 'Nurture', '2021-04-23'),
(2, '834.194', '2019-06-19'),
(3, '我们的灵魂乐', '2010-10-15'),
(5, '钱专', '2025-08-29');

INSERT INTO music.song (song_id, song_title, album_id, duration_seconds, genre) VALUES
(1, 'Look at the Sky', 1, 210, 'Electronic'),
(2, 'Shelter', NULL, 240, 'Electronic'),
(3, '新月余晖', 2, 260, 'Rock'),
(4, '新宝岛', 2, 230, 'Rock'),
(5, '回避依恋', 5, 200, 'Pop'),
(6, '工厂', 5, 220, 'Pop'),
(7, '凌晨晚餐', 3, 180, 'Folk'),
(8, '少女', 3, 250, 'Pop');

INSERT INTO music.song_artist (song_id, artist_id) VALUES
(1,1), (2,1), (2,5), (3,2), (4,2),
(5,3), (6,3), (7,4), (8,4);

-- B：歌单与收录（截图22，可拆分）
-- 歌单5为私密，歌单6为空；歌单1省略visibility以使用默认公开值。
INSERT INTO music.playlist (playlist_id, creator_id, playlist_name, description) VALUES
(1,1,'通勤路上','每天出发时听的歌');

INSERT INTO music.playlist (playlist_id, creator_id, playlist_name, description, visibility) VALUES
(2,2,'海边公路','适合旅行的音乐','public'),
(3,3,'深夜电台','夜晚的音乐','public'),
(4,4,'安静午后','放松时刻','public'),
(5,1,'私人收藏','仅自己可见','private'),
(6,5,'等待发现','还没有添加歌曲','public');

INSERT INTO music.playlist_song (playlist_id, song_id, position_no) VALUES
(1,1,1), (1,2,2), (1,3,3),
(2,3,1), (2,4,2), (2,8,3),
(3,5,1), (3,6,2),
(4,7,1), (4,1,2), (5,8,1);

-- C：用户偏好与歌单收藏（截图23）
-- 用户1与2相似度3/5=60%；1与4为0；用户6没有喜欢记录。
INSERT INTO music.song_like (user_id, song_id) VALUES
(1,1), (1,2), (1,3), (1,8),
(2,1), (2,3), (2,4), (2,8),
(3,5), (3,6),
(4,7),
(5,1), (5,2), (5,7);

INSERT INTO music.playlist_favorite (user_id, playlist_id) VALUES
(2,1), (3,1), (5,1), (1,2), (5,2), (1,3), (2,4);

-- D：各表记录数（截图24）
SELECT 'app_user' AS table_name, COUNT(*) AS row_count FROM music.app_user
UNION ALL SELECT 'artist', COUNT(*) FROM music.artist
UNION ALL SELECT 'album', COUNT(*) FROM music.album
UNION ALL SELECT 'song', COUNT(*) FROM music.song
UNION ALL SELECT 'song_artist', COUNT(*) FROM music.song_artist
UNION ALL SELECT 'playlist', COUNT(*) FROM music.playlist
UNION ALL SELECT 'playlist_song', COUNT(*) FROM music.playlist_song
UNION ALL SELECT 'song_like', COUNT(*) FROM music.song_like
UNION ALL SELECT 'playlist_favorite', COUNT(*) FROM music.playlist_favorite
ORDER BY table_name;
