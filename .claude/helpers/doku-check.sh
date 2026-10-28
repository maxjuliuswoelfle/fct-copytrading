#!/bin/sh
# Stop-Hook: Claude darf eine Session nicht beenden, wenn Dateien geändert wurden,
# aber kein Logbuch-Eintrag dazu existiert. Greift nur in Projekten mit "(C) Logbuch *.md".
IN=$(cat 2>/dev/null)
echo "$IN" | grep -q '"stop_hook_active": *true' && exit 0   # Schleifenschutz
D="${CLAUDE_PROJECT_DIR:-.}"; cd "$D" 2>/dev/null || exit 0
LB=$(ls "(C) Logbuch"*.md 2>/dev/null | head -1); [ -n "$LB" ] || exit 0
command -v git >/dev/null || exit 0
# Änderungen dieser Session: alles, was seit dem letzten Commit geändert wurde (Obsidian-Git committet alle 10 Min)
CH=$(git status --porcelain 2>/dev/null | grep -v -E '\.claudian|\.obsidian|\.DS_Store' | sed 's/^...//')
[ -n "$CH" ] || exit 0
echo "$CH" | grep -q "Logbuch" && exit 0
echo "$CH" | grep -qvE '^\(C\) Logbuch|^CLAUDE\.md$' || exit 0   # nur CLAUDE.md geändert → kein Logbuch nötig
cat >&2 <<MSG
DOKU-REGEL (Stop-Hook): Es wurden Dateien geändert, aber "$LB" hat keinen neuen Eintrag.
Geändert:
$CH
Bitte vor dem Beenden: (1) Eintrag OBEN ins Logbuch (Datum, was, warum, was offen), (2) Zeile "Zuletzt aktualisiert" in CLAUDE.md, (3) falls dauerhaft gültig: Wissensbasis; falls Dienst/Domain/Tool betroffen: (C) Systemlandkarte FCT.
MSG
exit 2
