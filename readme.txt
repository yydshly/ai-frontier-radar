虽然实现了能力，但是用python直接实现，打包总觉得不好。
现在目前得打包用得打包.venv  和PyInstaller  得区别是PyInstaller 启动慢。
但是现在得问题是启动图标得问题，不够直观，这是一个坎。
uvicorn app.main:app --reload --port 8892 

我们得项目实际上借助得windows定时器得能力，直接进行得执行。

① 换了目录会怎样？
会失败。

定时任务里写的是绝对路径：


操作: cmd.exe /c python D:\旧路径\scripts\run_daily_cycle.py --apply
移动文件夹后，路径不存在了，任务每次会报错。

正确做法：换了目录后重新安装：


# 1. 先卸载旧任务
.\scripts\uninstall_windows_daily_task.ps1

# 2. 重新安装（会自动用新路径）
.\scripts\install_windows_daily_task.ps1
或者：移动前卸载，移动后重新装。

② 08:05 电脑没开机怎么办？
取决于是否勾选了 StartWhenAvailable。

情况	行为
没开机，任务到点	❌ 跳过，不补跑
开机后	✅ 立即补跑一次（因为 StartWhenAvailable）
所以你新加的 install_windows_daily_task.ps1 里有这行：


$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `   # ← 这个是关键
意思：08:05 没开机，开机后马上触发一次。

总结
问题	答案
换目录	任务失效，要卸载重装
08:05 没开机	StartWhenAvailable 会开机后立即补跑
关机一整天	只漏跑一次，开机后补跑
多天没开机	只漏跑一次，开机后补跑一次
