-- 在 music_platform 的 jp 会话逐组执行，每组截图。

-- A 单表查询（截图28）：搜索名称中含“音乐”的公开歌单。
SELECT playlist_id, playlist_name, creator_id
FROM music.playlist
WHERE visibility = 'public' AND playlist_name LIKE '%音乐%'
ORDER BY playlist_id;

-- B 多表连接并排序（截图29）：歌单1的歌曲、专辑及音乐人。
-- LEFT JOIN 保留无专辑的 Shelter；合作音乐人按多行显示。
SELECT ps.position_no, s.song_title,
       COALESCE(al.album_title, '未关联专辑') AS album_title,
       ar.artist_name
FROM music.playlist p
JOIN music.playlist_song ps ON ps.playlist_id = p.playlist_id
JOIN music.song s ON s.song_id = ps.song_id
LEFT JOIN music.album al ON al.album_id = s.album_id
JOIN music.song_artist sa ON sa.song_id = s.song_id
JOIN music.artist ar ON ar.artist_id = sa.artist_id
WHERE p.playlist_id = 1 AND p.visibility = 'public'
ORDER BY ps.position_no, ar.artist_id;

-- C 聚集函数（截图30）：歌单1的歌曲数量、总时长和平均时长。
-- 不连接演唱关系，避免合作演唱造成时长重复累计。
SELECT COUNT(*) AS song_count,
       SUM(s.duration_seconds) AS total_seconds,
       ROUND(AVG(s.duration_seconds), 2) AS avg_seconds
FROM music.playlist_song ps
JOIN music.song s ON s.song_id = ps.song_id
WHERE ps.playlist_id = 1;

-- D 分组查询（截图31）：收藏人数至少为2的公开歌单。
SELECT p.playlist_id, p.playlist_name, COUNT(f.user_id) AS favorite_count
FROM music.playlist p
LEFT JOIN music.playlist_favorite f ON f.playlist_id = p.playlist_id
WHERE p.visibility = 'public'
GROUP BY p.playlist_id, p.playlist_name
HAVING COUNT(f.user_id) >= 2
ORDER BY favorite_count DESC, p.playlist_id;

-- E 嵌套查询（截图32）：用户2喜欢而用户1尚未喜欢的歌曲。
SELECT s.song_id, s.song_title
FROM music.song s
WHERE s.song_id IN (
    SELECT song_id FROM music.song_like WHERE user_id = 2
)
AND NOT EXISTS (
    SELECT 1 FROM music.song_like mine
    WHERE mine.user_id = 1 AND mine.song_id = s.song_id
)
ORDER BY s.song_id;

-- F 创建并使用视图（截图33，可拆分）：公开歌单、创建者和歌曲数。
-- COUNT(ps.song_id) 使空歌单显示0；视图仅作为公开展示查询，不构成访问控制。
CREATE VIEW music.v_public_playlist AS
SELECT p.playlist_id, p.playlist_name, u.nickname AS creator,
       COUNT(ps.song_id) AS song_count
FROM music.playlist p
JOIN music.app_user u ON u.user_id = p.creator_id
LEFT JOIN music.playlist_song ps ON ps.playlist_id = p.playlist_id
WHERE p.visibility = 'public'
GROUP BY p.playlist_id, p.playlist_name, u.nickname;

SELECT playlist_id, playlist_name, creator, song_count
FROM music.v_public_playlist
ORDER BY playlist_id;

-- G 特色扩展（截图34）：用户1与其余用户的喜欢歌曲 Jaccard 相似度。
-- 无偏好用户显示NULL；相似度为0表示双方有数据但无共同喜欢。
WITH like_counts AS (
    SELECT user_id, COUNT(*) AS liked_count
    FROM music.song_like GROUP BY user_id
), common_counts AS (
    SELECT other.user_id, COUNT(*) AS common_count
    FROM music.song_like mine
    JOIN music.song_like other ON other.song_id = mine.song_id
    WHERE mine.user_id = 1 AND other.user_id <> 1
    GROUP BY other.user_id
)
SELECT u.user_id, u.nickname,
       COALESCE(lc.liked_count, 0) AS liked_count,
       COALESCE(cc.common_count, 0) AS common_count,
       CASE WHEN COALESCE(lc.liked_count, 0) = 0
                  OR COALESCE(me.liked_count, 0) = 0 THEN NULL
            ELSE ROUND(100.0 * COALESCE(cc.common_count, 0) /
                 NULLIF(me.liked_count + lc.liked_count -
                        COALESCE(cc.common_count, 0), 0), 2)
       END AS similarity_pct
FROM music.app_user u
LEFT JOIN like_counts lc ON lc.user_id = u.user_id
LEFT JOIN like_counts me ON me.user_id = 1
LEFT JOIN common_counts cc ON cc.user_id = u.user_id
WHERE u.user_id <> 1
ORDER BY similarity_pct DESC NULLS LAST, u.user_id;
