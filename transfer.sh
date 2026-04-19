#!/bin/bash
# 1) 打包 memories + 题目文件夹 + DB
cd /Users/austin/leetcode_agent

tar czf lc_backup.tar.gz \
  .memories/ \
  binary_search/ \
  design/ \
  dfs_bfs/ \
  dp/ \
  sorting/ \
  tree/ \
  two_pointers/ \
  -C /Users/austin .leetcode_agent/leetcode.db

echo "✓ 已创建 lc_backup.tar.gz ($(du -h lc_backup.tar.gz | cut -f1))"

# 2) 传到服务器
scp lc_backup.tar.gz qiqianf2@vision-submit.cs.illinois.edu:/home/qiqianf2/LC-Agent/leetcode_agent/

echo "✓ 传输完成"
