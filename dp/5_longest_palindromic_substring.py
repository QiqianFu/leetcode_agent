# 5. Longest Palindromic Substring
# https://leetcode.com/problems/longest-palindromic-substring/

"""
Given a string `s`, return *the longest* *palindromic* *substring* in `s`.

**Example 1:**

```
Input: s = "babad"
Output: "bab"
Explanation: "aba" is also a valid answer.
```

**Example 2:**

```
Input: s = "cbbd"
Output: "bb"
```

**Constraints:**

- `1 <= s.length <= 1000`
- `s` consist of only digits and English letters.
"""


class Solution:
    def longestPalindrome(self, s: str) -> str:
        total_len = len(s)
        queue = []
        for i in range(total_len):
            queue.append(s[i])
        return queue

# ─── 参考解法 ───

class Solution:
    def longestPalindrome(self, s: str) -> str:
        if not s:
            return ""
        
        start = 0
        end = 0
        
        def expand_around_center(left: int, right: int) -> tuple:
            """从中心向两边扩展，返回回文串的起止索引"""
            while left >= 0 and right < len(s) and s[left] == s[right]:
                left -= 1
                right += 1
            # 注意：循环结束时 left 和 right 已经超出了回文范围
            return left + 1, right - 1
        
        for i in range(len(s)):
            # 奇数长度回文
            left1, right1 = expand_around_center(i, i)
            # 偶数长度回文
            left2, right2 = expand_around_center(i, i + 1)
            
            # 更新最长回文
            if right1 - left1 > end - start:
                start, end = left1, right1
            if right2 - left2 > end - start:
                start, end = left2, right2
        
        return s[start:end + 1]
