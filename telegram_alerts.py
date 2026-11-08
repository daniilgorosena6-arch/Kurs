#!/usr/bin/env python3
"""Уведомления о курсах НБ РБ в Telegram. Без внешних библиотек.

Переменные окружения:
  TG_TOKEN  токен бота от @BotFather (секрет, в код не вписывать)
  TG_CHAT   ваш chat id
  WATCH     валюты через запятую, по умолчанию USD,EUR,RUB
  ALERTS    пороги, например: USD>3.10,EUR<3.30  (необязательно)
  ALWAYS    1 = присылать актуальные курсы при каждом запуске, даже если не менялись
"""
import json, os, sys, urllib.parse, urllib.request

API = "https://api.nbrb.by/exrates/rates?periodicity=0"
STATE = os.environ.get("STATE_FILE", "state.json")
TOKEN, CHAT = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT")
WATCH = [c.strip().upper() for c in os.environ.get("WATCH", "USD,EUR,RUB").split(",") if c.strip()]
ALWAYS = os.environ.get("ALWAYS", "") == "1"
ALERTS = [a.strip() for a in os.environ.get("ALERTS", "").split(",") if a.strip()]


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data, timeout=20).read()


def main():
    if not TOKEN or not CHAT:
        sys.exit("Задайте TG_TOKEN и TG_CHAT")
    data = get(API)
    rates = {x["Cur_Abbreviation"]: x["Cur_OfficialRate"] / x["Cur_Scale"] for x in data}
    date = data[0]["Date"][:10] if data else ""
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        st = {}
    last, fired = st.get("last", {}), st.get("fired", {})
    msgs = []

    for c in WATCH:
        if c not in rates:
            continue
        new, old = rates[c], last.get(c)
        if ALWAYS:
            msgs.append(f"{c}: {new:.4f} BYN")
        elif old is None:
            msgs.append(f"{c}: {new:.4f} BYN (слежу за курсом)")
        elif abs(new - old) > 1e-9:
            pct = (new - old) / old * 100
            msgs.append(f"{c}: {old:.4f} → {new:.4f} BYN ({'▲' if pct > 0 else '▼'} {pct:+.2f}%)")
        last[c] = new

    for a in ALERTS:
        op = ">" if ">" in a else "<" if "<" in a else None
        if not op:
            continue
        c, v = a.split(op)
        c, v = c.strip().upper(), float(v.replace(",", "."))
        if c not in rates:
            continue
        hit = rates[c] > v if op == ">" else rates[c] < v
        if hit and not fired.get(a):
            msgs.append(f"Сработал порог: {c} {'выше' if op == '>' else 'ниже'} {v} BYN (сейчас {rates[c]:.4f})")
        fired[a] = hit

    if msgs:
        head = f"Курс НБ РБ на {date}" if ALWAYS else "Курс НБ РБ"
        send(head + "\n" + "\n".join(msgs))
    json.dump({"last": last, "fired": fired}, open(STATE, "w"))


if __name__ == "__main__":
    main()
