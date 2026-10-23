import os, json, urllib.request, urllib.parse
T = os.environ["TELEGRAM_BOT_TOKEN"]
BASE = "https://api.telegram.org/bot" + T + "/"
CH = (("Main", "-1003888563475"), ("Scalp", "-1004292274970"))
for duid, uid, m in [(453,"6198462235","tarik_guel"),
                     (452,"1571360522","christoph.drda"),
                     (435,"8328877156","hansdampf")]:
    out = []
    for n, c in CH:
        u = BASE + "getChatMember?" + urllib.parse.urlencode({"chat_id": c, "user_id": uid})
        try:
            r = json.load(urllib.request.urlopen(u, timeout=15))
            out.append(f"{n}={r['result']['status']}" if r.get("ok") else f"{n}=ERR")
        except Exception:
            out.append(f"{n}=ID_UNGUELTIG")
    print(f"  id {duid} {m:<16} {' | '.join(out)}")
