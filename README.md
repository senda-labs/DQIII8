# JARVIS

Sistema de orquestación sobre Claude Code. Comando: `j`.

---

## Instalación en Windows (Fase 0)

### 1. Prerrequisitos

```powershell
# Verificar que tienes todo:
python --version       # ≥ 3.10
node --version         # ≥ 18 (para MCPs via npx)
git --version
ollama list            # debe mostrar qwen2.5-coder
```

### 2. Copiar el repo

```powershell
# Opción A: git clone
git clone https://github.com/[tuusuario]/jarvis C:\jarvis

# Opción B: copiar manualmente desde este ZIP
# Descomprimir en C:\jarvis\
```

### 3. Inicializar la base de datos

```powershell
cd C:\jarvis\database
python -c "
import sqlite3
conn = sqlite3.connect('jarvis_metrics.db')
with open('schema.sql') as f:
    conn.executescript(f.read())
conn.close()
print('BD inicializada')
"
```

### 4. Instalar dependencias Python opcionales

```powershell
pip install black          # auto-format en PostToolUse hook
pip install win10toast     # notificaciones nativas Windows (opcional)
```

### 5. Registrar el comando `j`

Añadir a tu PowerShell profile (`notepad $PROFILE`):

```powershell
# Copiar contenido de bin\profile_snippet.ps1
```

Recargar: `. $PROFILE`

### 6. Configurar variables de entorno

En PowerShell o en Variables de entorno de Windows:

```powershell
$env:GITHUB_TOKEN = "ghp_tu_token_aqui"
# (ANTHROPIC_API_KEY se gestiona internamente por Claude Code)
```

### 7. Test de Fase 0

```powershell
j --status           # debe mostrar proyecto y modelo sin errores
j                    # debe abrir Claude Code con Ollama
# En Claude Code:
/mcp                 # debe mostrar los 4 MCPs conectados
```

---

## Estructura

```
C:\jarvis\
├── CLAUDE.md                    ← Constitución del sistema (98 líneas)
├── .claude\
│   ├── settings.json            ← Hooks declarados
│   ├── .mcp.json                ← 4 MCPs: filesystem, github, fetch, sqlite
│   ├── agents\                  ← 4 agentes activos (Fase 1)
│   └── hooks\                   ← 5 scripts Python
├── projects\                    ← Estado de cada proyecto
├── tasks\                       ← lessons.md, todo.md, results/
├── database\                    ← jarvis_metrics.db + schema.sql
├── skills-registry\             ← INDEX.md + cache/
└── bin\
    ├── j.ps1                    ← Comando principal
    ├── sqlite_mcp.py            ← MCP SQLite local
    └── profile_snippet.ps1      ← Añadir a $PROFILE
```

---

## Fases de implementación

| Fase | Dónde | Objetivo |
|------|-------|----------|
| **0** | Local | `j` funciona, Ollama, 4 MCPs, BD inicializada |
| **1** | Local | CLAUDE.md + 4 agentes + hooks completos |
| **2** | Local | BD recibiendo métricas, lessons.md auto-update |
| **3** | VPS | Provisionar VPS, Docker, j.sh, tmux, SSH keys |
| **4** | VPS | Worktrees, /mobilize, Agent Teams, Ollama 7b+ |
| **5** | VPS | Skills sync + revisión, auditor, primera auditoría |
| **6** | VPS | Más agentes (métricas guían cuándo), CI/CD headless |
