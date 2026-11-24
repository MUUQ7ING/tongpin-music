-- 在 music_platform 数据库，以 jp 执行；每组执行后截图。
-- A：为分享歌单新增封面地址，并扩展简介长度。
ALTER TABLE music.playlist ADD COLUMN cover_url VARCHAR(300);
ALTER TABLE music.playlist ALTER COLUMN description TYPE VARCHAR(1000);

-- 单独执行 gsql 元命令（不要复制前面的 --，末尾不加分号）：
-- \d music.playlist

-- B：为按歌曲统计喜欢人数的查询建立普通索引。
-- 已有主键 (user_id, song_id)，这里以 song_id 为首列。
CREATE INDEX idx_song_like_song_id ON music.song_like (song_id);

SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'music' AND indexname = 'idx_song_like_song_id';

-- C：删除刚才手动建立的普通索引，保留主键索引。
DROP INDEX music.idx_song_like_song_id;

SELECT indexname
FROM pg_indexes
WHERE schemaname = 'music' AND tablename = 'song_like'
ORDER BY indexname;
