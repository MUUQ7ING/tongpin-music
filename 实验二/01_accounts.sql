-- omm 管理员连接 music_platform 后逐段执行。
-- gsql先通过交互提示获取临时密码，设置ECHO为none避免回显。
\set ECHO none
\prompt -s "Temporary reader password: " reader_password
CREATE USER music_reader PASSWORD :'reader_password';
\unset reader_password
\set ECHO all
-- 实际执行使用非空随机密码；不要在截图中记录密码。
GRANT CONNECT ON DATABASE music_platform TO music_reader;
GRANT USAGE ON SCHEMA music TO music_reader;
GRANT SELECT ON music.v_public_playlist TO music_reader;
-- 单独以 music_reader 连接后执行以下两句，第二句预期拒绝：
-- SELECT * FROM music.v_public_playlist ORDER BY playlist_id;
-- UPDATE music.playlist SET playlist_name = playlist_name WHERE playlist_id = 1;
-- 退出 reader 会话，回到管理员会话：
REVOKE SELECT ON music.v_public_playlist FROM music_reader;
-- 再次以 reader 登录，查询视图预期拒绝，随后退出该会话。
-- 管理员清理：
REVOKE USAGE ON SCHEMA music FROM music_reader;
REVOKE CONNECT ON DATABASE music_platform FROM music_reader;
DROP USER music_reader;
SELECT rolname FROM pg_roles WHERE rolname = 'music_reader';
