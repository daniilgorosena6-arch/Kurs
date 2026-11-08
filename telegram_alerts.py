#!/usr/bin/env python3
"""Бот курсов НБ РБ для Telegram. Без внешних библиотек.

Что делает:
  1) раз в запуск присылает курсы по правилу PUSH;
  2) около 4,5 минут отвечает на кнопки в чате («Все курсы», USD, EUR, RUB...).

Переменные окружения:
  TG_TOKEN   токен бота (секрет)
  TG_CHAT    ваш chat id (бот отвечает только вам)
  WATCH      валюты-кнопки, по умолчанию USD,EUR,RUB
  PUSH       change = писать, только когда курс изменился (по умолчанию)
             always = писать при каждом запуске
             off    = сам не писать, только отвечать на кнопки
  ALERTS     пороги, например: USD>3.10,EUR<3.30 (необязательно)
  DURATION   сколько секунд слушать кнопки за запуск (по умолчанию 270)
"""
import json, os, sys, time, urllib.parse, urllib.request

API = "https://api.nbrb.by/exrates/rates?periodicity=0"
STATE = os.environ.get("STATE_FILE", "state.json")
TOKEN, CHAT = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT")
WATCH = [c.strip().upper() for c in os.environ.get("WATCH", "USD,EUR,RUB").split(",") if c.strip()]
PUSH = os.environ.get("PUSH", "change").strip().lower()
ALERTS = [a.strip() for a in os.environ.get("ALERTS", "").split(",") if a.strip()]
DURATION = int(os.environ.get("DURATION", "270"))
KB = {"keyboard": [[{"text": "Все курсы"}], [{"text": c} for c in WATCH]], "resize_keyboard": True}


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def tg(method, **params):
    data = urllib.parse.urlencode(params).encode()
    wait = int(params.get("timeout", 0)) + 15
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/{method}", data, timeout=wait) as r:
        return json.load(r)


def send(text):
    tg("sendMessage", chat_id=CHAT, text=text, reply_markup=json.dumps(KB))


def fetch():
    data = get(API)
    rates = {x["Cur_Abbreviation"]: x["Cur_OfficialRate"] / x["Cur_Scale"] for x in data}
    return rates, (data[0]["Date"][:10] if data else "")


def reply(text):
    rates, date = fetch()
    t = text.strip().upper()
    if t in rates:
        send(f"{t}: {rates[t]:.4f} BYN\n(курс НБ РБ на {date})")
    elif t in ("/START", "/RATE", "ВСЕ КУРСЫ", "КУРС"):
        body = "\n".join(f"{c}: {rates[c]:.4f} BYN" for c in WATCH if c in rates)
        send(f"Курс НБ РБ на {date}\n{body}")
    else:
        send("Нажмите кнопку или напишите код валюты, например PLN.")


def push(st):
    rates, date = fetch()
    last, fired, msgs = st.get("last", {}), st.get("fired", {}), []
    for c in WATCH:
        if c not in rates:
            continue
        new, old = rates[c], last.get(c)
        if PUSH == "always":
            msgs.append(f"{c}: {new:.4f} BYN")
        elif PUSH == "change":
            if old is None:
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
    st["last"], st["fired"] = last, fired
    if msgs:
        send(("Курс НБ РБ на " + date if PUSH == "always" else "Курс НБ РБ") + "\n" + "\n".join(msgs))


def listen(st):
    end, off = time.time() + DURATION, st.get("offset")
    while end - time.time() > 3:
        try:
            p = {"timeout": min(25, int(end - time.time()))}
            if off is not None:
                p["offset"] = off
            for u in tg("getUpdates", **p).get("result", []):
                off = u["update_id"] + 1
                m = u.get("message") or {}
                if str(m.get("chat", {}).get("id")) == str(CHAT) and m.get("text"):
                    reply(m["text"])
            st["offset"] = off
        except Exception as e:
            print("ошибка:", e)
            time.sleep(3)


def main():
    if not TOKEN or not CHAT:
        sys.exit("Задайте TG_TOKEN и TG_CHAT")
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        st = {}
    try:
        push(st)
    except Exception as e:
        print("ошибка отправки:", e)
    json.dump(st, open(STATE, "w"))
    listen(st)
    json.dump(st, open(STATE, "w"))


if __name__ == "__main__":
    main()
