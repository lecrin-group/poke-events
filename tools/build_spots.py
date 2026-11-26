# build_spots.py — 全国の常設スポット（spots/）を OpenStreetMap から作る
# 使い方: python3 tools/build_spots.py [OSMのJSON]   （引数が無ければ Overpass から取る）
# 出力: spots/<県コード>.json（その県のスポット）と spots/index.json（県ごとの件数・ジャンル）
# データの出典: © OpenStreetMap contributors（ODbL 1.0）。spots/ は ODbL で公開する（spots/LICENSE.md）
# 月1回くらい回せば、閉店（OSM から消えたもの）と新規開店（OSM に増えたもの）が入れかわる
import sys, os, re, json, math, time, datetime, subprocess, urllib.request, urllib.parse
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "spots")
JST = datetime.timezone(datetime.timedelta(hours=9))
MIRRORS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter",
           "https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]
# ジャンルと取り方は spot_genres.py（2026-11-26 ナギサの ○△× に合わせて約100ジャンル・16大分類）
sys.path.insert(0, HERE)
from spot_genres import QUERIES, GROUPS, R as GENRE_RULES, classify

def fetch():
    els = []
    for q in QUERIES:
        for u in MIRRORS * 2:
            r = subprocess.run(["curl", "-sS", "-m", "420", u, "--data-urlencode", "data=" + q], capture_output=True)
            try:
                els += json.loads(r.stdout)["elements"]; break
            except Exception:
                print("取れなかった:", u, r.stderr.decode()[:120], flush=True)
        else:
            sys.exit("Overpass から取れなかった（今のデータはそのまま）")
    return els

def load_geo():
    g = json.load(open(os.path.join(HERE, "jp_geo.json"), encoding="utf-8"))
    pts = []
    for pref, s in g.items():
        for row in s.split(";"):
            n, la, lo = row.split(",")
            pts.append((float(la), float(lo), pref, n))
    return pts

def nearest(pts, la, lo):
    best, bd = None, 1e9
    c = math.cos(math.radians(la))
    for p in pts:
        d = (p[0] - la) ** 2 + ((p[1] - lo) * c) ** 2
        if d < bd:
            best, bd = p, d
    return best

UA = "esj-spots-builder/1.0 (+https://github.com/lecrin-group/poke-events)"

def get(url, t=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=t) as r:
        return r.read().decode("utf-8")

def muni_table():
    js = get("https://maps.gsi.go.jp/js/muni.js")
    m = {}
    for code, v in re.findall(r'MUNI_ARRAY\["(\d+)"\] = \'([^\']+)\'', js):
        f = v.split(",")
        m[int(code)] = ("%02d" % int(f[0]), f[3].replace("\u3000", ""))
    return m

def geocode(rows):
    # 国土地理院の住所検索（逆ジオコーダ）で市区町村を決める。結果は tools/spots_geocache.json にためて次から聞かない
    path = os.path.join(HERE, "spots_geocache.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    try:
        muni = muni_table()
    except Exception as e:
        print("市区町村表が取れなかった（近い役所で代用）:", e); return
    def ask(key):
        la, lo = key.split(",")
        for _ in range(3):
            try:
                return key, json.loads(get(f"https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress?lat={la}&lon={lo}"))["results"]["muniCd"]
            except Exception:
                pass
        return key, None
    keys = {f"{s['lat']:.4f},{s['lon']:.4f}" for s in rows} - set(cache)
    with cf.ThreadPoolExecutor(4) as ex:
        for k, v in ex.map(ask, sorted(keys)):
            if v:
                cache[k] = v
    json.dump(cache, open(path, "w"), separators=(",", ":"))
    hit = 0
    for s in rows:
        c = cache.get(f"{s['lat']:.4f},{s['lon']:.4f}")
        if c and int(c) in muni:
            s["pref"], s["area"] = muni[int(c)]; hit += 1
    print(f"市区町村：地理院で {hit}/{len(rows)} 件")

def wikidata_urls(rows):
    # OSM に公式サイトが無くても、Wikidata（CC0）に公式サイト（P856）があれば使う
    need = [s for s in rows if "url" not in s and s.get("wd")]
    got = {}
    for i in range(0, len(need), 200):
        ids = " ".join("wd:" + s["wd"] for s in need[i:i + 200] if re.match(r"^Q\d+$", s["wd"]))
        q = "SELECT ?i ?w WHERE { VALUES ?i {%s} ?i wdt:P856 ?w }" % ids
        for t in range(3):   # 混んでいると 1分に1回まで（429）になるので、待ってやり直す
            try:
                r = json.loads(get("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q}), 60))
                for b in r["results"]["bindings"]:
                    got.setdefault(b["i"]["value"].rsplit("/", 1)[1], b["w"]["value"])
                break
            except Exception as e:
                print("Wikidata 失敗（待ってやり直す）:", e, flush=True)
                time.sleep(65)
    n = 0
    for s in need:
        u = got.get(s["wd"])
        if u and official({"website": u}):
            s["url"] = official({"website": u}); n += 1
    print(f"公式サイト：Wikidata から {n} 件足した")

def official(t):
    u = t.get("website") or t.get("contact:website") or t.get("url") or ""
    u = u.split(";")[0].strip()
    if u and not re.match(r"^https?://", u):
        u = "https://" + u
    # SNS やまとめは公式サイト扱いしない
    if re.search(r"facebook\.com|twitter\.com|x\.com/|instagram\.com|tabelog|jalan\.net|walkerplus|wikipedia", u):
        return ""
    return u

def keep(t, gid):
    if not t.get("name"):
        return False
    if t.get("disused") or t.get("abandoned") or t.get("access") == "private":
        return False
    notable = bool(official(t) or t.get("wikidata") or t.get("wikipedia"))
    # 庭園・展望台・ボウリングは数が多くて個人の庭や小さいものも入るので、有名なものだけ
    if gid in ("garden", "tower") and not (notable or t.get("tourism") == "attraction"):
        return False
    if t.get("leisure") == "bowling_alley" and not notable:
        return False
    return True

def norm(s):
    return re.sub(r"[\s・･()（）「」『』]", "", s).lower()

def main():
    els = json.load(open(sys.argv[1]))["elements"] if len(sys.argv) > 1 else fetch()
    print("OSM", len(els), "件", flush=True)
    pts = load_geo()
    rows = []
    for e in els:
        t = e.get("tags", {})
        g = classify(t)
        if not g:
            continue
        la = e.get("lat") or (e.get("center") or {}).get("lat")
        lo = e.get("lon") or (e.get("center") or {}).get("lon")
        if la is None:
            continue
        p = nearest(pts, la, lo)
        s = {"id": f"{e['type'][0]}{e['id']}", "name": t["name"], "grp": g[0], "cat": g[1],
             "pref": p[2], "area": p[3], "lat": round(la, 5), "lon": round(lo, 5)}
        en = t.get("name:en")
        if en and en != t["name"]:
            s["en"] = en
        u = official(t)
        if u:
            s["url"] = u
        if t.get("opening_hours"):
            s["hours"] = t["opening_hours"]
        if t.get("wikidata"):
            s["wd"] = t["wikidata"]
        rows.append(s)
    geocode(rows)
    wikidata_urls(rows)
    # 同じ名前で 400m 以内は1つにまとめる（点と建物の両方が登録されていることがある）
    rows.sort(key=lambda s: (0 if "url" in s else 1, s["id"]))
    seen, out = {}, []
    for s in rows:
        k = norm(s["name"])
        dup = any(abs(a - s["lat"]) < 0.004 and abs(b - s["lon"]) < 0.005 for a, b in seen.get(k, []))
        if dup:
            continue
        seen.setdefault(k, []).append((s["lat"], s["lon"]))
        out.append(s)
    os.makedirs(OUT, exist_ok=True)
    now = datetime.datetime.now(JST).isoformat(timespec="minutes")
    by = {}
    for s in out:
        by.setdefault(s["pref"], []).append(s)
    index = {"schema": 1, "updated": now, "source": "© OpenStreetMap contributors (ODbL 1.0)",
             "groups": {gr: [c for g2, c, _ in GENRE_RULES if g2 == gr and c not in []] for gr in GROUPS}, "prefs": {}}
    for gr in index["groups"]:
        index["groups"][gr] = list(dict.fromkeys(index["groups"][gr]))
    index["genres"] = [c for gr in GROUPS for c in index["groups"][gr]]
    for pref in sorted(by):
        lst = sorted(by[pref], key=lambda s: (s["area"], s["cat"], s["name"]))
        with open(os.path.join(OUT, f"{pref}.json"), "w", encoding="utf-8") as f:
            f.write('{"schema":1,"updated":"%s","source":"© OpenStreetMap contributors (ODbL 1.0)","spots":[\n' % now)
            f.write(",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in lst))
            f.write("\n]}\n")
        cats = {}
        for s in lst:
            cats[s["cat"]] = cats.get(s["cat"], 0) + 1
        index["prefs"][pref] = {"n": len(lst), "url": sum(1 for s in lst if "url" in s), "cats": cats}
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    tot = len(out)
    print(f"スポット {tot} 件（公式URLあり {sum(1 for s in out if 'url' in s)} 件）・{len(by)} 都道府県")
    c = {}
    for s in out:
        c[s["cat"]] = c.get(s["cat"], 0) + 1
    print(" / ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda x: -x[1])))

if __name__ == "__main__":
    main()
