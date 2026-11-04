"""Hourly follower count for the Breaking Clouds dashboard. Uses no AI.

Reads the public pages, updates data.json, then pushes it to the website.
A platform that can't be read keeps its last number and is marked out of date.
"""
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data.json"
LOG = HERE / "update.log"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PATTERNS = {
    "instagram": r'([\d,]+) [Ff]ollowers',
    "tiktok": r'"followerCount":(\d+)',
    "youtube": r'"content":"([\d,]+) subscribers?"',
    "linkedin": r'([\d,]+) followers',
    "substack": r'freeSubscriberCountOrderOfMagnitude\\?":\\?"([\d,]+)',
}


def log(msg):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}\n")


def read_count(platform):
    req = urllib.request.Request(platform["read"], headers={
        "User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-GB,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "ignore")
    m = re.search(PATTERNS[platform["id"]], html)
    return int(m.group(1).replace(",", "")) if m else None


def looks_wrong(new, old):
    # small accounts can legitimately double, so only judge once there is a real base
    return old is not None and old >= 20 and (new > old * 2 or new < old / 2)


def update(data):
    today = dt.date.today().isoformat()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for p in data["platforms"]:
        old = p["counts"][-1]["n"] if p["counts"] else None
        try:
            n = read_count(p)
        except Exception as e:
            log(f"{p['id']}: could not read ({e})")
            continue
        if n is None:
            log(f"{p['id']}: number not on the page")
            continue
        if looks_wrong(n, old):
            log(f"{p['id']}: ignored {n}, last was {old}")
            continue
        p["counts"] = [c for c in p["counts"] if c["date"] != today] + [{"date": today, "n": n}]
        p["lastRead"] = now
        log(f"{p['id']}: {n}")
    data["checked"] = now


def set_count(data, pid, n):
    # for a platform the script can't read itself: the number is supplied by the daily Claude sync
    p = next(x for x in data["platforms"] if x["id"] == pid)
    today = dt.date.today().isoformat()
    p["counts"] = [c for c in p["counts"] if c["date"] != today] + [{"date": today, "n": n}]
    p["lastRead"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    log(f"{pid}: {n} (supplied)")


def publish():
    def git(*args):
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    git("add", "data.json")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("commit", "-m", "Update follower counts")
    r = git("push")
    if r.returncode:
        log(f"push failed: {r.stderr.strip()[:300]}")


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    update(data)
    if "--instagram" in sys.argv:
        set_count(data, "instagram", int(sys.argv[sys.argv.index("--instagram") + 1]))
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    if "--no-publish" not in sys.argv:
        publish()


if __name__ == "__main__":
    main()
