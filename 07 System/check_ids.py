import os, json, urllib.request
TOK = os.environ["TELEGRAM_BOT_TOKEN"]
MAIN, SCALP = "-1003888563475", "-1004292274970"
KAND = [
    (435, "8328877156", "hansdampf_derechte@outlook.com"),
    (453, "6198462235", "tarik_guel@hotmail.com"),
    (452, "1571360522", "christoph.drda@gmail.com"),
]
def call(m, **p):
    u = f"https://api.telegram.org/bot{TOK}/{m}?" + urllib.parse.urlencode(p)
    try:
        return json.load(urllib.request.urlopen(u, timeout=15))
    except Exception as e:
        return {"ok": False, "error": str(e)}
for duid, uid, mail in KAND:
    out = []
    for name, chat in (("Main", MAIN), ("Scalp", SCALP)):
        r = call("getChatMember", chat_id=chat, user_id=uid)
        if r.get("ok"):
            res = r["result"]
            who = res.get("user", {})
            out.append(f"{name}={res.get('status')}")
            nm = (who.get("first_name","") + " " + (who.get("last_name") or "")).strip()
            handle = who.get("username")
        else:
            out.append(f"{name}=FEHLER({r.get('description') or r.get('error')})")
            nm, handle = "?", None
    print(f"id {duid:>4} {mail:<34} -> {nm!r} @{handle}  {' | '.join(out)}")
