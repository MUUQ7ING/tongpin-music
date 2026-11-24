#!/bin/bash
# 设计稿，用户确认后才执行。以操作系统omm运行；不含密码。
set -euo pipefail
lab2_dir="$HOME/lab2_backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$lab2_dir"
# 恢复目标必须事先确认不存在；存在时停止，不覆盖或删除。
# 下列创建语句若目标已存在会失败，set -e会终止脚本。
gsql -d postgres -p 26000 -v ON_ERROR_STOP=1 -c 'CREATE DATABASE music_platform_restore OWNER jp TEMPLATE template0;'
gs_dump -p 26000 music_platform -F p -f "$lab2_dir/music_platform.sql"
test -s "$lab2_dir/music_platform.sql"
ls -lh "$lab2_dir/music_platform.sql"
gsql -d music_platform_restore -p 26000 -v ON_ERROR_STOP=1 -f "$lab2_dir/music_platform.sql" > "$lab2_dir/restore.log" 2>&1
# 05_verify.sql须上传到本脚本同目录。
lab2_script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
gsql -d music_platform -p 26000 -A -t -v ON_ERROR_STOP=1 -f "$lab2_script_dir/05_verify.sql" > "$lab2_dir/source.txt"
gsql -d music_platform_restore -p 26000 -A -t -v ON_ERROR_STOP=1 -f "$lab2_script_dir/05_verify.sql" > "$lab2_dir/restored.txt"
sed "/^total time:/d" "$lab2_dir/source.txt" > "$lab2_dir/source.normalized.txt"
sed "/^total time:/d" "$lab2_dir/restored.txt" > "$lab2_dir/restored.normalized.txt"
diff -u "$lab2_dir/source.normalized.txt" "$lab2_dir/restored.normalized.txt"
echo "Backup and restore verification passed: $lab2_dir"
# 验证期间暂停业务写入。备份是数据库级逻辑备份，不含全局账号定义。
