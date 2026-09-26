# poke-events: Googleドライブの公開フォルダから最新の events-YYYYMMDD.json を取り込み、
# チェックしてから events.json に保存する。終わったイベントもここで消す。
# 取り込みに失敗しても、今の events.json から終わったものを消すだけにして、壊れたデータは絶対に入れない。
import json, re, sys, urllib.request, datetime

FOLDER_ID = "1r-9U6KJ-wXfflYix1Y9wBmT6aCtIEx6O"
CATS = {"フェス・祭り", "展示会", "公園・庭園", "商業施設", "ライブ", "スポーツ"}
JST = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(JST).strftime("%Y-%m-%d")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 poke-events-sync"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def ok_event(e):
    if not isinstance(e, dict):
        return False
    for k in ("id", "title", "pref", "cat", "start", "end"):
        if not isinstance(e.get(k), str) or not e[k].strip():
            return False
    if not re.fullmatch(r"\d{2}", e["pref"]) or not (0 <= int(e["pref"]) <= 47):
        return False
    if e["cat"] not in CATS:
        return False
    if not DATE.match(e["start"]) or not DATE.match(e["end"]) or e["end"] < e["start"]:
        return False
    if e.get("url") and not str(e["url"]).startswith("https://"):
        return False
    return True

def clean(events):
    out, seen = [], set()
    for e in events:
        if not ok_event(e) or e["end"] < today or e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append({k: e.get(k, "") for k in ("id", "title", "pref", "area", "venue", "cat", "start", "end", "url", "src")})
    out.sort(key=lambda e: (e["start"], e["id"]))
    return out

with open("events.json", encoding="utf-8") as f:
    cur = json.load(f)

new = None
try:
    html = get("https://drive.google.com/embeddedfolderview?id=" + FOLDER_ID).decode("utf-8", "replace")
    files = []
    for chunk in html.split('id="entry-')[1:]:   # 1ファイル＝1かたまりに分けてから見る（別のファイルと取り違えないため）
        m_id = re.match(r"([A-Za-z0-9_-]+)", chunk)
        m_t = re.search(r"(events-(\d{8})\.json)", chunk)
        if m_id and m_t:
            files.append((m_id.group(1), m_t.group(1), m_t.group(2)))
    if files:
        fid = max(files, key=lambda t: t[2])[0]
        data = json.loads(get("https://drive.google.com/uc?export=download&id=" + fid).decode("utf-8"))
        if data.get("schema") == 1 and isinstance(data.get("events"), list):
            evs = clean(data["events"])
            if evs:
                new = {"schema": 1, "updated": str(data.get("updated", "")), "events": evs}
    print("drive files:", len(files), "adopted:", bool(new))
except Exception as ex:
    print("drive fetch failed:", ex)

if new is None:
    new = {"schema": 1, "updated": cur.get("updated", ""), "events": clean(cur.get("events", []))}

with open("events.json", "w", encoding="utf-8") as f:
    json.dump(new, f, ensure_ascii=False, indent=1)
    f.write("\n")
print("events:", len(new["events"]))
