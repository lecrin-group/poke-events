# poke-events: Googleドライブの公開フォルダから、差分 events-add-YYYYMMDD.json（ふだん）か全件 events-YYYYMMDD.json（非常用）を取り込み、
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

def norm(e):
    return {k: e.get(k, "") for k in ("id", "title", "pref", "area", "venue", "cat", "start", "end", "url", "src")}

with open("events.json", encoding="utf-8") as f:
    cur = json.load(f)

# DELTA-SUPPORT-V1（この印があると、毎日のタスクは差分の events-add-YYYYMMDD.json だけを置く）
# - 土台は今の events.json
# - 全件版 events-YYYYMMDD.json が今より新しければ、それを土台にする（非常用・前の方式）
# - そのあと、土台より新しい差分版 events-add-YYYYMMDD.json を日付の順に足す（add は同じ id なら上書き、remove は消す）
# - 「新しいか」は中の updated（例 2026-11-01T16:55:00+09:00）でくらべる。同じ差分を2回足すことはない
base_updated = str(cur.get("updated", ""))
base_events = cur.get("events", [])
changed = False
try:
    html = get("https://drive.google.com/embeddedfolderview?id=" + FOLDER_ID).decode("utf-8", "replace")
    fulls, adds = [], []
    for chunk in html.split('id="entry-')[1:]:   # 1ファイル＝1かたまりに分けてから見る（別のファイルと取り違えないため）
        m_id = re.match(r"([A-Za-z0-9_-]+)", chunk)
        m_t = re.search(r'flip-entry-title">\s*(events-(add-)?(\d{8})\.json)\s*<', chunk) or re.search(r"(events-(add-)?(\d{8})\.json)", chunk)
        if m_id and m_t:
            (adds if m_t.group(2) else fulls).append((m_t.group(3), m_id.group(1)))
    print("drive files: full", len(fulls), "add", len(adds))

    if fulls:
        d, fid = max(fulls)
        try:
            data = json.loads(get("https://drive.google.com/uc?export=download&id=" + fid).decode("utf-8"))
            up = str(data.get("updated", ""))
            if data.get("schema") == 1 and isinstance(data.get("events"), list) and up > base_updated:
                evs = clean(data["events"])
                if evs:
                    base_events, base_updated, changed = evs, up, True
                    print("full adopted:", d, up)
        except Exception as ex:
            print("full skipped:", d, ex)

    by_id = {e["id"]: norm(e) for e in base_events if isinstance(e, dict) and isinstance(e.get("id"), str)}
    for d, fid in sorted(adds):
        try:
            data = json.loads(get("https://drive.google.com/uc?export=download&id=" + fid).decode("utf-8"))
            up = str(data.get("updated", ""))
            if data.get("schema") != 1 or not isinstance(data.get("add"), list) or up <= base_updated:
                print("add skipped:", d, up or "(no updated)")
                continue
            n_add = n_rm = 0
            for rid in data.get("remove") or []:
                if isinstance(rid, str) and by_id.pop(rid.strip(), None) is not None:
                    n_rm += 1
            for e in data["add"]:
                if ok_event(e):
                    by_id[e["id"]] = norm(e); n_add += 1
            base_updated, changed = up, True
            print("add applied:", d, up, "add", n_add, "remove", n_rm)
        except Exception as ex:
            print("add failed:", d, ex)   # こわれた差分は飛ばす（次の差分は updated がもっと新しいので、そのまま足せる）
    base_events = list(by_id.values())
except Exception as ex:
    print("drive fetch failed:", ex)

evs = clean(base_events)
if not evs:   # 万一ぜんぶ消えるような結果なら、今のデータから終わったものを消すだけにする
    evs, base_updated = clean(cur.get("events", [])), str(cur.get("updated", ""))
new = {"schema": 1, "updated": base_updated, "events": evs}
print("changed:", changed)

with open("events.json", "w", encoding="utf-8") as f:
    json.dump(new, f, ensure_ascii=False, indent=1)
    f.write("\n")
print("events:", len(new["events"]))
