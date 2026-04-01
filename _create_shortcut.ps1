$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\GrowthChart.lnk")
$Shortcut.TargetPath = "$env:USERPROFILE\Projects\GrowthChart\venv\Scripts\pythonw.exe"
$Shortcut.Arguments = "$env:USERPROFILE\Projects\GrowthChart\main.py"
$Shortcut.WorkingDirectory = "$env:USERPROFILE\Projects\GrowthChart"
$Shortcut.Description = "Pediatric Growth Chart App"
$Shortcut.IconLocation = "shell32.dll,21"
$Shortcut.Save()
Write-Host "Shortcut created on Desktop"
