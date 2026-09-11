#!/usr/bin/env bash
set -euo pipefail
setfacl -R -m u:plglobal-isabel:rwX,u:plglobal-mario:rwX,default:u:plglobal-isabel:rwX,default:u:plglobal-mario:rwX /root/dqiii8/my-projects /root/dqiii8/tasks /root/dqiii8/knowledge /root/dqiii8/skills-registry
setfacl -m u:plglobal-isabel:rw-,u:plglobal-mario:rw- /root/dqiii8/00_DASHBOARD.md
