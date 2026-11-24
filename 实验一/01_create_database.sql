-- 在 omm 连接 postgres 的管理员 gsql 会话执行一次。
-- 不要在 BEGIN/COMMIT 事务块内执行 CREATE DATABASE。
CREATE DATABASE music_platform OWNER jp;

-- 随后退出管理员会话，在 Linux 终端执行：
-- gsql -d music_platform -p 26000 -U jp -r
-- 以下查询在重新连接的 jp 会话中执行。
-- SELECT current_database(), current_user;
