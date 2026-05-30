import socket
import random
import time
import re
import threading
import json
import os

try:
    from config import NICK, TOKEN, CHANNEL, OWNER, COOLDOWN_OWNER, COOLDOWN_OTHER
except ImportError:
    print("Создай config.py из config.example.py и заполни свои данные")
    exit(1)

SCORE_FILE = "slots_scores.json"

REELS = ["🍒", "🍇", "🍊", "🍋", "🍉", "💎", "⭐", "7️⃣", "BAR"]
JACKPOT = ["💎", "💎", "💎"]
BIG_WIN = ["7️⃣", "7️⃣", "7️⃣"]

PRIZES = {
    "JACKPOT": 10000,
    "BIG_WIN": 5000,
    "THREE": 1000,
    "PAIR": 100,
}

last_used = {}
scores = {}

def load_scores():
    global scores
    if os.path.exists(SCORE_FILE):
        with open(SCORE_FILE, "r") as f:
            scores = json.load(f)

def save_scores():
    with open(SCORE_FILE, "w") as f:
        json.dump(scores, f, indent=2)

def spin():
    return [random.choice(REELS) for _ in range(3)]

def result_text(r):
    return f"{r[0]} | {r[1]} | {r[2]}"

def check_win(r):
    if r == JACKPOT:
        return "JACKPOT", PRIZES["JACKPOT"]
    if r == BIG_WIN:
        return "BIG_WIN", PRIZES["BIG_WIN"]
    if r[0] == r[1] == r[2]:
        return "THREE", PRIZES["THREE"]
    if r[0] == r[1] or r[1] == r[2] or r[0] == r[2]:
        return "PAIR", PRIZES["PAIR"]
    return None, 0

def check_cooldown(sock, user, cmd_name):
    now = time.time()
    cd = COOLDOWN_OWNER if user == OWNER else COOLDOWN_OTHER
    if user in last_used and now - last_used[user] < cd:
        remaining = int(cd - (now - last_used[user]))
        sock.sendall(f"PRIVMSG {CHANNEL} :@{user} Подожди {remaining} сек перед {cmd_name}\r\n".encode("utf-8"))
        return False
    last_used[user] = now
    if user == OWNER:
        time.sleep(2.0)
    return True

def cmd_slots(sock, user):
    if not check_cooldown(sock, user, "!slots"):
        return
    r = spin()
    win_type, prize = check_win(r)
    if user not in scores:
        scores[user] = 0
    scores[user] += prize
    save_scores()
    if win_type:
        resp = f"🎰 {user} [{result_text(r)}] {prize} очков! Баланс: {scores[user]}"
    else:
        resp = f"🎰 {user} [{result_text(r)}] Повезёт в следующий раз! Баланс: {scores[user]}"
    sock.sendall(f"PRIVMSG {CHANNEL} :{resp}\r\n".encode("utf-8"))

def cmd_lucky(sock, user):
    if not check_cooldown(sock, user, "!lucky"):
        return
    luck = random.randint(0, 100)
    if user == "opilkj7":
        luck //= 10
    elif user == "desertcat":
        luck = -random.randint(0, 100)
    resp = f"🍀 @{user} твоя удача {luck}%"
    sock.sendall(f"PRIVMSG {CHANNEL} :{resp}\r\n".encode("utf-8"))

def cmd_d20(sock, user):
    if not check_cooldown(sock, user, "!d20"):
        return
    roll = random.randint(1, 20)
    resp = f"🎲 @{user} бросает d20... {roll}"
    sock.sendall(f"PRIVMSG {CHANNEL} :{resp}\r\n".encode("utf-8"))

def cmd_help(sock, user):
    if not check_cooldown(sock, user, "!help"):
        return
    resp = f"@{user} Доступные команды: !slots (слоты), !lucky (удача 0-100), !d20 (кость 1-20)"
    sock.sendall(f"PRIVMSG {CHANNEL} :{resp}\r\n".encode("utf-8"))

def handle_message(sock, user, msg):
    try:
        text = msg.strip().lower()
        if text.startswith("!slots"):
            cmd_slots(sock, user)
        elif text.startswith("!lucky"):
            cmd_lucky(sock, user)
        elif text.startswith("!d20"):
            cmd_d20(sock, user)
        elif text.startswith("!help"):
            cmd_help(sock, user)
    except Exception as e:
        print(f"Error: {e}")

def keepalive(sock):
    while True:
        time.sleep(120)
        try:
            sock.sendall(b"PING :tmi.twitch.tv\r\n")
        except:
            break

def main():
    load_scores()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("irc.chat.twitch.tv", 6667))
    sock.sendall(b"CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n")
    sock.sendall(f"PASS {TOKEN}\r\n".encode("utf-8"))
    sock.sendall(f"NICK {NICK}\r\n".encode("utf-8"))
    sock.sendall(f"JOIN {CHANNEL}\r\n".encode("utf-8"))
    sock.settimeout(60)
    threading.Thread(target=keepalive, args=(sock,), daemon=True).start()
    print(f"Bot {NICK} running in {CHANNEL}")

    buffer = ""
    last_msg = time.time()
    while True:
        try:
            raw = sock.recv(2048)
            if not raw:
                print("Connection closed by server, reconnecting in 5s...")
                time.sleep(5)
                main()
                return
            data = raw.decode("utf-8", errors="replace")
        except socket.timeout:
            if time.time() - last_msg > 300:
                print("No messages for 5 min, reconnecting...")
                sock.close()
                time.sleep(3)
                main()
                return
            continue
        except (ConnectionResetError, BrokenPipeError):
            print("Connection lost, reconnecting in 5s...")
            time.sleep(5)
            main()
            return
        except OSError:
            print("Socket error, reconnecting in 5s...")
            time.sleep(5)
            main()
            return
        buffer += data
        lines = buffer.split("\r\n")
        buffer = lines.pop()
        for line in lines:
            if line:
                print(f"< {line}")
            if line.startswith("PING"):
                sock.sendall(f"PONG {line.split()[1]}\r\n".encode("utf-8"))
                continue
            if "PRIVMSG" in line:
                last_msg = time.time()
            match = re.search(r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG {} :(.+)".format(re.escape(CHANNEL)), line)
            if match:
                threading.Thread(target=handle_message, args=(sock, match.group(1), match.group(2)), daemon=True).start()

if __name__ == "__main__":
    main()
