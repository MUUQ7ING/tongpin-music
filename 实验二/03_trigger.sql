-- 本次实际以omm连接music_platform。
CREATE TABLE music.playlist_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    playlist_id INTEGER NOT NULL,
    old_name VARCHAR(100), new_name VARCHAR(100),
    old_description VARCHAR(1000), new_description VARCHAR(1000),
    old_visibility VARCHAR(10), new_visibility VARCHAR(10),
    db_user VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- 审计表不设歌单外键，使删除歌单后仍能保留历史记录。
CREATE OR REPLACE FUNCTION music.audit_playlist_update()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.playlist_name IS DISTINCT FROM NEW.playlist_name
       OR OLD.description IS DISTINCT FROM NEW.description
       OR OLD.visibility IS DISTINCT FROM NEW.visibility THEN
        INSERT INTO music.playlist_audit
        (playlist_id, old_name, new_name, old_description, new_description,
         old_visibility, new_visibility, db_user)
        VALUES (OLD.playlist_id, OLD.playlist_name, NEW.playlist_name,
                OLD.description, NEW.description, OLD.visibility, NEW.visibility,
                CURRENT_USER);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_playlist_update_audit
AFTER UPDATE ON music.playlist
FOR EACH ROW EXECUTE PROCEDURE music.audit_playlist_update();
UPDATE music.playlist
SET playlist_name = '实验二分享歌单', description = '用于存储过程与触发器验证', visibility = 'private'
WHERE playlist_id = 2001;
SELECT audit_id, playlist_id, old_name, new_name, old_visibility, new_visibility, db_user
FROM music.playlist_audit WHERE playlist_id = 2001 ORDER BY audit_id;
SELECT COUNT(*) FROM music.playlist_audit WHERE playlist_id = 2001;
UPDATE music.playlist SET playlist_name = playlist_name WHERE playlist_id = 2001;
SELECT COUNT(*) FROM music.playlist_audit WHERE playlist_id = 2001;
-- 两次COUNT预期均为1，未改变内容的UPDATE不新增审计记录。
