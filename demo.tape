# VHS demo tape — generates demo.gif
# Install VHS: brew install vhs
# Run: vhs demo.tape

Output assets/demo.gif

Set Shell "zsh"
Set FontSize 14
Set Width 900
Set Height 550
Set Theme "Dracula"
Set PlaybackSpeed 1.0

# Start the agent
Type "leetcode"
Enter
Sleep 2s

# Ask for a problem
Type "来一道 medium 的 DP 题"
Enter
Sleep 3s

# Select first option (simulated)
Down
Sleep 500ms
Enter
Sleep 4s

# Ask for a hint
Type "给个提示"
Enter
Sleep 3s

# Ask to see the answer
Type "讲一下最优解"
Enter
Sleep 3s

# Find similar problems
Type "我做过类似的题吗"
Enter
Sleep 3s

Sleep 2s
