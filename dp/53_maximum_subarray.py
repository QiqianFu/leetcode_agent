# 53. Maximum Subarray
# https://leetcode.com/problems/maximum-subarray/

"""
Given an integer array `nums`, find the subarray with the largest sum, and return *its sum*.

**Example 1:**

```
Input: nums = [-2,1,-3,4,-1,2,1,-5,4]
Output: 6
Explanation: The subarray [4,-1,2,1] has the largest sum 6.
```

**Example 2:**

```
Input: nums = [1]
Output: 1
Explanation: The subarray [1] has the largest sum 1.
```

**Example 3:**

```
Input: nums = [5,4,-1,7,8]
Output: 23
Explanation: The subarray [5,4,-1,7,8] has the largest sum 23.
```

**Constraints:**

- `1 <= nums.length <= 105`
- `-104 <= nums[i] <= 104`

**Follow up:** If you have figured out the `O(n)` solution, try coding another solution using the **divide and conquer** approach, which is more subtle.
"""

from typing import List

import numpy as np

class Solution:
    def maxSubArray(self, nums: List[int]) -> int:
        total_len = len(nums)
        sub_len = 0
        dp = np.zeros(total_len)
        for i in range(1, total_len):
            for j in range(i, total_len):
                dp[i] = max(dp[i], dp[i-1] + nums[j])
        return max(dp)


# ─── 参考解法 ───

class Solution:
    def maxSubArray(self, nums: List[int]) -> int:
        """
        动态规划解法（Kadane算法）
        时间复杂度：O(n)
        空间复杂度：O(1)
        """
        if not nums:
            return 0
            
        # 初始化：第一个元素就是当前最大和
        current_sum = nums[0]
        max_sum = nums[0]
        
        # 从第二个元素开始遍历
        for i in range(1, len(nums)):
            # 关键：要么从当前元素重新开始，要么加入前面的子数组
            current_sum = max(nums[i], current_sum + nums[i])
            # 更新全局最大值
            max_sum = max(max_sum, current_sum)
            
        return max_sum

    def maxSubArray_dp_array(self, nums: List[int]) -> int:
        """
        使用dp数组的版本，更容易理解动态规划思想
        时间复杂度：O(n)
        空间复杂度：O(n)
        """
        if not nums:
            return 0
            
        n = len(nums)
        # dp[i] 表示以 nums[i] 结尾的最大子数组和
        dp = [0] * n
        dp[0] = nums[0]
        max_sum = nums[0]
        
        for i in range(1, n):
            # 状态转移方程
            dp[i] = max(nums[i], dp[i-1] + nums[i])
            max_sum = max(max_sum, dp[i])
            
        return max_sum

    def maxSubArray_divide_conquer(self, nums: List[int]) -> int:
        """
        分治法解法（题目要求尝试的follow up）
        时间复杂度：O(n log n)
        空间复杂度：O(log n) 递归栈空间
        """
        def divide_conquer(left, right):
            if left == right:
                return nums[left]
            
            mid = (left + right) // 2
            
            # 分别计算左半部分、右半部分的最大子数组和
            left_max = divide_conquer(left, mid)
            right_max = divide_conquer(mid + 1, right)
            
            # 计算跨越中点的最大子数组和
            # 从中点向左扩展
            left_cross = nums[mid]
            current = nums[mid]
            for i in range(mid - 1, left - 1, -1):
                current += nums[i]
                left_cross = max(left_cross, current)
            
            # 从中点向右扩展
            right_cross = nums[mid + 1]
            current = nums[mid + 1]
            for i in range(mid + 2, right + 1):
                current += nums[i]
                right_cross = max(right_cross, current)
            
            # 跨越中点的最大和
            cross_max = left_cross + right_cross
            
            # 返回三者中的最大值
            return max(left_max, right_max, cross_max)
        
        return divide_conquer(0, len(nums) - 1)
