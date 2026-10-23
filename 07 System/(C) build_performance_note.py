"""(C) build_performance_note.py - baut die Markdown-Auswertung aus master_performance.json."""
import json
from datetime import datetime, timezone
from collections import defaultdict

BALANCE_HEUTE = 104559.10
LAUNCH = datetime(2026, 6, 28, tzinfo=timezone.utc)

T = json.load(open("master_performance.json"))
for t in T:
    t["ot"] = datetime.fromisoformat(t["open_time"])
    t["ct"] = datetime.fromisoformat(t["close_time"])
T.sort(key=lambda t: t["ot"])


def de(x, nk=2):
    s = f"{x:,.{nk}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def block(rows, label):
    rows = sorted([r for r in rows], key=lambda r: r["ct"])
    if not rows:
        return f"**{label}** — keine Trades\n"
    net = [r["net"] for r in rows]
    w = [x for x in net if x > 0]
    l = [x for x in net if x <= 0]
    gw, gl = sum(w), -sum(l)
    eq = peak = dd = 0.0
    for r in rows:
        eq += r["net"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    rois = sorted(r["roi_margin"] for r in rows)
    return (
        f"| {label} | {len(rows)} | {len(w)}/{len(l)} | {len(w)/len(rows)*100:.1f} % | "
        f"**{de(sum(net),0)}** | {de(gw,0)} | −{de(gl,0)} | "
        f"{gw/gl if gl else 0:.2f} | {de(dd,0)} | {de(max(net),0)} | {de(min(net),0)} | "
        f"{rois[len(rois)//2]:+.1f} % |\n"
    )


out = []
A = out.append

A("# (C) Performance-Auswertung Copy Trading — Stand 30.09.2026\n")
A("> ↩ [[CLAUDE|Copy Trading Bot]] · Quelle: LeveX Trade-Historie des Master-Accounts (UID 1080129), Trade für Trade\n")

A("\n## Was hier drinsteht\n")
A("Jeder einzelne Fill des Master-Accounts aus der LeveX-Historie, zu **Positionen zusammengerechnet** — "
  "inklusive Nachkäufen (Scale-In), Teilverkäufen (Scale-Out), Hebel, Handelsgebühren und Funding-Kosten. "
  "Das ist das Ergebnis, das ein Nachtrader 1:1 erzielt hätte, der proportional zu seiner Kontogröße mitgegangen ist.\n")
A("\n**Nicht enthalten** (bewusst): Limit-Orders, die nie ausgelöst wurden — die haben nie Geld bewegt.\n")

A("\n### Methodik\n")
A("- **Netto-PnL** = realisierter PnL (`closedPnl`) − Handelsgebühren (`execFee`) − Funding\n")
A("- **Margin** = Summe der Einstiege ÷ Hebel = das tatsächlich gebundene Kapital\n")
A("- **ROI auf Margin** = Netto-PnL ÷ eingesetzte Margin. Das ist die Rendite **auf den Einsatz, also inklusive Hebel**\n")
A("- Teilverkäufe sind vollständig eingerechnet: jeder einzelne Ausstieg zählt mit seinem realisierten PnL\n")

A("\n### Vorbehalte (ehrlich)\n")
A("- **Eine Position ist noch offen** (BTC Short „The Big Short 2.0\", seit 24.08.). Deren unrealisierter Gewinn/Verlust "
  "ist nicht enthalten — nur die bereits angefallenen Funding- und Gebührenkosten.\n")
A(f"- Das Konto hat aktuell **{de(BALANCE_HEUTE)} USDT** Balance, davon 18.329 USDT als Margin gebunden. "
  "Die gebundene Margin ist höher als die der offenen Position — es wurde also Margin nachgeschossen "
  "(`AddMargin` taucht in der Trade-Historie nicht auf).\n")
A("- **Prozentuale Kontorenditen sind Näherungen**: Ein- und Auszahlungen auf dem Master-Account sind über die "
  "Trade-API nicht sichtbar. Belastbar sind die absoluten USDT-Zahlen und der ROI auf die eingesetzte Margin.\n")

A("\n---\n\n## Die drei Sichten\n")
A("Welche Zahl gilt, hängt davon ab, wann jemand eingestiegen ist. Deshalb getrennt:\n\n")
A("| Sicht | Trades | W/L | Winrate | Netto USDT | Gewinne | Verluste | Profitfaktor | Max DD | Bester | Schlechtester | Median ROI |\n")
A("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|\n")
A(block(T, "**A** Kompletter Track Record (08.12.25–30.09.26)"))
A(block([t for t in T if t["ct"] >= LAUNCH], "**B** Im Signal-Zeitraum geschlossen (ab 28.06.)"))
A(block([t for t in T if t["ot"] >= LAUNCH], "**C** Erst ab Launch eröffnet (echter Neukunde)"))

A("\n**Der Unterschied zwischen B und C ist der entscheidende Punkt:**\n")
A("Sicht B enthält „The Big Short\" — eröffnet am **29.04.2026**, geschlossen am 10.07.2026, **+32.877 USDT netto "
  "bei +203,5 % auf den Einsatz**. Dieser eine Trade macht **62 % des gesamten Gewinns** aus dem kompletten Track Record aus.\n")
A("Ein Kunde, der zum Launch am 28.06. eingestiegen ist, konnte diesen Trade **nicht mehr eröffnen** — er lief da schon zwei Monate. "
  "Für ihn gilt Sicht C: **+2.632 USDT in 3 Monaten bei 67 Trades**, Profitfaktor 1,28.\n")

A("\n---\n\n## Monatsverlauf (nach Schließungsdatum)\n\n")
m = defaultdict(lambda: [0, 0, 0, 0.0, 0.0, 0.0])
for t in T:
    k = t["ct"].strftime("%Y-%m")
    m[k][0] += 1
    if t["net"] > 0:
        m[k][1] += 1
    else:
        m[k][2] += 1
    m[k][3] += t["net"]
    m[k][4] += t["fees"]
    m[k][5] += t["funding"]
A("| Monat | Trades | Gewinner | Verlierer | Netto USDT | davon Gebühren | davon Funding | kumuliert |\n")
A("|---|--:|--:|--:|--:|--:|--:|--:|\n")
kum = 0.0
for k in sorted(m):
    n, w, l, s, fe, fu = m[k]
    kum += s
    A(f"| {k} | {n} | {w} | {l} | **{de(s,0)}** | {de(fe,0)} | {de(fu,0)} | {de(kum,0)} |\n")

A("\n---\n\n## Kostenblock\n\n")
A(f"- **Handelsgebühren gesamt:** {de(sum(t['fees'] for t in T),0)} USDT\n")
A(f"- **Funding gesamt:** {de(sum(t['funding'] for t in T),0)} USDT\n")
A(f"- **Zusammen:** {de(sum(t['fees']+t['funding'] for t in T),0)} USDT — das sind "
  f"{sum(t['fees']+t['funding'] for t in T)/sum(t['gross'] for t in T)*100:.1f} % des Bruttogewinns.\n")
A("\nSeit Launch (ab 28.06. eröffnet) fielen 2.913 USDT Gebühren + 1.496 USDT Funding an — bei 2.632 USDT Netto-Gewinn. "
  "**Die Kosten waren in diesem Zeitraum höher als der Gewinn.** Ohne sie wären es 7.041 USDT gewesen.\n")

A("\n---\n\n## Top 10 Trades\n\n")
A("| Eröffnet | Geschlossen | Markt | Richtung | Hebel | Margin | Ein/Aus | Netto USDT | ROI |\n|---|---|---|---|--:|--:|:-:|--:|--:|\n")
for t in sorted(T, key=lambda x: -x["net"])[:10]:
    A(f"| {t['ot']:%d.%m.%y %H:%M} | {t['ct']:%d.%m.%y %H:%M} | {t['symbol'].replace('USDT','')} | {t['side']} | "
      f"{t['leverage']:.1f}x | {de(t['margin'],0)} | {t['n_open']}/{t['n_close']} | **{de(t['net'],0)}** | {t['roi_margin']:+.1f} % |\n")

A("\n## Flop 10 Trades\n\n")
A("| Eröffnet | Geschlossen | Markt | Richtung | Hebel | Margin | Ein/Aus | Netto USDT | ROI | Liq. |\n|---|---|---|---|--:|--:|:-:|--:|--:|:-:|\n")
for t in sorted(T, key=lambda x: x["net"])[:10]:
    A(f"| {t['ot']:%d.%m.%y %H:%M} | {t['ct']:%d.%m.%y %H:%M} | {t['symbol'].replace('USDT','')} | {t['side']} | "
      f"{t['leverage']:.1f}x | {de(t['margin'],0)} | {t['n_open']}/{t['n_close']} | **{de(t['net'],0)}** | "
      f"{t['roi_margin']:+.1f} % | {'⚠️' if t['liquidated'] else ''} |\n")

liqs = [t for t in T if t["liquidated"]]
A(f"\n**{len(liqs)} Liquidationen** im gesamten Zeitraum, zusammen {de(sum(t['net'] for t in liqs),0)} USDT:\n\n")
for t in liqs:
    A(f"- {t['ct']:%d.%m.%Y} — {t['symbol'].replace('USDT','')} {t['side']}, {t['leverage']:.1f}x, "
      f"{de(t['net'],0)} USDT ({t['roi_margin']:+.0f} % auf den Einsatz) — „{t['name'].strip()}\"\n")

A("\n---\n\n## Hebel-Auswertung\n\n")
buckets = [(0, 15, "bis 15x"), (15, 25, "15–25x"), (25, 50, "25–50x"), (50, 80, "50–80x"), (80, 1e9, "ab 80x")]
A("| Hebelklasse | Trades | Winrate | Netto USDT | Ø ROI auf Margin |\n|---|--:|--:|--:|--:|\n")
for lo, hi, name in buckets:
    rows = [t for t in T if lo <= t["leverage"] < hi]
    if not rows:
        continue
    w = len([r for r in rows if r["net"] > 0])
    A(f"| {name} | {len(rows)} | {w/len(rows)*100:.0f} % | **{de(sum(r['net'] for r in rows),0)}** | "
      f"{sum(r['roi_margin'] for r in rows)/len(rows):+.1f} % |\n")

A("\n---\n\n## Märkte\n\n")
sym = defaultdict(lambda: [0, 0, 0.0])
for t in T:
    s = sym[t["symbol"].replace("USDT", "")]
    s[0] += 1
    if t["net"] > 0:
        s[1] += 1
    s[2] += t["net"]
A("| Markt | Trades | Winrate | Netto USDT |\n|---|--:|--:|--:|\n")
for k, v in sorted(sym.items(), key=lambda x: -x[1][2]):
    A(f"| {k} | {v[0]} | {v[1]/v[0]*100:.0f} % | **{de(v[2],0)}** |\n")

A("\n---\n\n## Vollständige Trade-Liste\n\n")
A("Alle 207 Positionen chronologisch nach Eröffnung. „Ein/Aus\" = Anzahl Einstiege (inkl. Nachkäufe) / Ausstiege (inkl. Teilverkäufe).\n\n")
A("| # | Eröffnet | Geschlossen | Markt | Ri. | Entry Ø | Exit Ø | Hebel | Margin | Ein/Aus | Brutto | Geb. | Fund. | **Netto** | ROI |\n")
A("|--:|---|---|---|---|--:|--:|--:|--:|:-:|--:|--:|--:|--:|--:|\n")
for i, t in enumerate(T, 1):
    nk = 2 if t["entry"] > 100 else 5
    mark = " 🔴" if t["liquidated"] else (" ⏳" if t["offen"] else "")
    A(f"| {i}{mark} | {t['ot']:%d.%m.%y %H:%M} | {t['ct']:%d.%m.%y %H:%M} | {t['symbol'].replace('USDT','')} | "
      f"{'L' if t['side']=='Long' else 'S'} | {de(t['entry'],nk)} | {de(t['exit'],nk) if t['exit'] else '—'} | "
      f"{t['leverage']:.1f}x | {de(t['margin'],0)} | {t['n_open']}/{t['n_close']} | {de(t['gross'],0)} | "
      f"{de(t['fees'],0)} | {de(t['funding'],0)} | **{de(t['net'],0)}** | {t['roi_margin']:+.0f} % |\n")

A("\n🔴 = liquidiert · ⏳ = noch offen (PnL nur teilweise realisiert)\n")

A("\n---\n\n## Einordnung\n\n")
A("1. **Der Track Record insgesamt ist stark** — 207 Trades, 74 % Winrate, Profitfaktor 3,05, +53.420 USDT netto "
  "über knapp 10 Monate, bei einem maximalen kumulierten Drawdown von nur −4.081 USDT.\n")
A("2. **Er hängt aber an einem einzigen Trade.** Ohne „The Big Short\" bleiben +20.543 USDT über 206 Trades. "
  "Das ist immer noch profitabel, aber ein völlig anderes Bild als das, was die 53.420 suggerieren.\n")
A("3. **Seit dem Launch ist die Performance dünn.** Wer am 28.06. eingestiegen ist, steht nach 3 Monaten und 67 Trades "
  "bei +2.632 USDT — Profitfaktor 1,28. Die Winrate ist mit 83,6 % sogar am höchsten, aber die Gewinne sind klein "
  "und die Verluste groß: 56 Gewinner bringen 12.152, 11 Verlierer kosten 9.520.\n")
A("4. **Das deckt sich mit den Kündigungsgründen.** Michael Grossmann und Gunnar Still haben am 24.09. unabhängig "
  "voneinander gesagt, das Copy Trading bringe ihnen nichts. Die Zahlen geben ihnen recht — nicht weil die Strategie "
  "schlecht ist, sondern weil die drei Monate seit Launch die schwächste Phase des gesamten Track Records waren.\n")
A("5. **September ist negativ** (−1.449 USDT), August praktisch flat (+502). Die letzten zwei Monate haben nichts verdient.\n")
A("6. **Extremhebel bringt nichts.** Die 19 Trades ab 80x stehen zusammen bei −185 USDT. "
  "Seit Launch sind es nur noch zwei Trades ab 80x — die kosten aber allein −1.733 USDT und damit mehr, "
  "als alle 67 Trades zusammen verdient haben. Der Bereich 50–80x läuft dagegen solide (+5.791 über den ganzen Zeitraum, "
  "+1.896 seit Launch). **Das Problem ist nicht Hebel generell, sondern die Spitze ab 80x.**\n")
A("7. **Für Marketing-Zahlen:** Sauber ist Sicht A mit dem Hinweis auf den Zeitraum. Wer mit 53.420 USDT wirbt und "
  "einen Kunden gewinnt, der dann Sicht C erlebt, produziert genau die Kündigungen, die gerade reinkommen.\n")

open("performance_note.md", "w", encoding="utf-8").write("".join(out))
print("ok,", len("".join(out)), "Zeichen")
