# ── Add this to your PowerShell profile ───────────────────────────
# To edit the profile: notepad $PROFILE
# Or run directly: . $PROFILE  (to reload without restarting)

# Global alias for JARVIS
function j {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$args)
    & "C:\jarvis\bin\j.ps1" @args
}

# Base environment variable
$env:JARVIS_ROOT = "C:\jarvis"

# Basic autocompletion (known projects)
Register-ArgumentCompleter -CommandName j -ScriptBlock {
    param($word)
    @("content-automation","hult-finance","leyendas-del-este",
      "--model","--status","--sync","--audit","--clear","--worktree","--new") |
    Where-Object { $_ -like "$word*" }
}
