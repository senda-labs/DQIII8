---
name: drive-upload
description: Upload DOCX files from intl-reports to Google Drive Carpeta 3 using rclone. Zero reasoning — action only.
---

# SKILL: drive-upload

## INVARIANTS (NEVER BREAK)
- ZERO reasoning output. Respond ONLY: `OK: {slug}` or `FAIL: {slug} — {reason}`
- NEVER read file content. NEVER base64. Use rclone only.
- NEVER create duplicate Borradores folders. Check first with `rclone lsd`.
- If DOCX already exists in destination AND local is newer → overwrite (`--update` flag).
- If DOCX already exists AND local is NOT newer → skip (already up to date).
- rclone binary: `/usr/bin/rclone`
- DOCX base path: `/root/dqiii8/my-projects/intl-reports/companies/{slug}/drafts/`
- Files: `{slug}_diagnostico.docx` and `{slug}_plan_internacionalizacion.docx`

## UPLOAD PROTOCOL

DOCXs van SOLO en Borradores. La carpeta padre numerada es para entregas finales — NO tocar.

For each company (slug + numbered_folder_id):

```bash
SLUG="{slug}"
FOLDER_ID="{numbered_folder_id}"
DRAFTS="/root/dqiii8/my-projects/intl-reports/companies/$SLUG/drafts"

# 1. Create Borradores if not exists (rclone handles idempotently — no duplicate if already exists)
/usr/bin/rclone mkdir "gdrive:Borradores" --drive-root-folder-id "$FOLDER_ID" 2>/dev/null

# 2. Upload both DOCXs to Borradores ONLY (overwrite if local is newer)
/usr/bin/rclone copy "$DRAFTS/" "gdrive:Borradores" \
  --drive-root-folder-id "$FOLDER_ID" \
  --include "*.docx" --update --no-traverse 2>/dev/null
```

## RESPONSE FORMAT
```
OK: {slug}
```
or
```
FAIL: {slug} — {one-line reason}
```
