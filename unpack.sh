#!/bin/bash
# 在服务器上运行：解压备份
cd /home/qiqianf2/LC-Agent/leetcode_agent

tar xzf lc_backup.tar.gz
echo "✓ 解压完成"

# 把 DB 放到正确位置
mkdir -p ~/.leetcode_agent
mv .leetcode_agent/leetcode.db ~/.leetcode_agent/ 2>/dev/null
rmdir .leetcode_agent 2>/dev/null

echo "✓ DB 已移至 ~/.leetcode_agent/leetcode.db"
ls -la .memories/ binary_search/ design/ dfs_bfs/ dp/ sorting/ tree/ two_pointers/ 2>/dev/null
