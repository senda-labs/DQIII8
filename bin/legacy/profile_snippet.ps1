# ── Añadir esto a tu PowerShell profile ──────────────────────────
# Para editar el profile: notepad $PROFILE
# O ejecutar directamente: . $PROFILE  (para recargar sin reiniciar)

# Alias global para JARVIS
function j {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$args)
    & "C:\jarvis\bin\j.ps1" @args
}

# Variable de entorno base
$env:JARVIS_ROOT = "C:\jarvis"

# Autocompletion básico (proyectos conocidos)
Register-ArgumentCompleter -CommandName j -ScriptBlock {
    param($word)
    @("content-automation","hult-finance","leyendas-del-este",
      "--model","--status","--sync","--audit","--clear","--worktree","--new") |
    Where-Object { $_ -like "$word*" }
}
