# add_images.py — イベントとスポットの「公式ページの画像（og:image）」の URL を集める
# 使い方: python3 tools/add_images.py [events|spots|all]（標準は all）
# 出力: images.json（{"events": {id: 画像URL}, "spots": {id: 画像URL}}）
# ⚠️ 画像そのものはコピーしない。公式サイトの画像の URL を記録して、サイトはそれを直接表示するだけ（2026-11-26 ナギサ決定）
# ⚠️ 権利者から「外して」と言われたら noimage.txt に id かドメインを1行足して push する（images.yml がすぐ動いて消える）
import sys, os, re, json, datetime, urllib.request, urllib.parse
import concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "images.json")
CACHE = os.path.join(ROOT, "tools", "images_cache.json")   # ページURL → [画像URL, 調べた日]
NOIMG = os.path.join(ROOT, "noimage.txt")
JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).date()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
REFRESH_DAYS = 30

def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

def blocked():
    out = set()
    if os.path.exists(NOIMG):
        for line in open(NOIMG, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if line:
                out.add(line.lower())
    return out

def is_blocked(bl, key, page, img):
    if key.lower() in bl:
        return True
    for u in (page, img):
        host = urllib.parse.urlparse(u or "").hostname or ""
        if any(host == b or host.endswith("." + b) for b in bl):
            return True
    return False

def og_image(page):
    try:
        req = urllib.request.Request(page, headers={"User-Agent": UA, "Accept-Language": "ja"})
        with urllib.request.urlopen(req, timeout=15) as r:
            if "html" not in (r.headers.get("Content-Type") or "html"):
                return ""
            html = r.read(400000).decode("utf-8", "ignore")
            base = r.geturl()
    except Exception:
        return None   # 取れなかった（次の回にもう一度）
    head = html.split("</head>")[0]
    for prop in ("og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"):
        for m in re.finditer(r"<meta\b[^>]*>", head, re.I):
            tag = m.group(0)
            if re.search(r'(?:property|name)\s*=\s*["\']%s["\']' % re.escape(prop), tag, re.I):
                c = re.search(r'content\s*=\s*["\']([^"\']+)["\']', tag, re.I)
                if c:
                    u = urllib.parse.urljoin(base, c.group(1).strip().replace("&amp;", "&"))
                    # ロゴやアイコンっぽいもの・http のものは使わない
                    if u.startswith("https://") and not re.search(r"logo|favicon|icon|noimage|no_image|default", u, re.I):
                        return u
                    return ""
    return ""

def collect(items, cache, bl):
    """items: [(id, ページURL)] → {id: 画像URL}"""
    todo = []
    for key, page in items:
        c = cache.get(page)
        if not c or (TODAY - datetime.date.fromisoformat(c[1])).days > REFRESH_DAYS:
            todo.append(page)
    todo = sorted(set(todo))
    print(f"調べるページ {len(todo)} / 全体 {len(items)}", flush=True)
    with cf.ThreadPoolExecutor(10) as ex:
        for page, img in zip(todo, ex.map(og_image, todo)):
            if img is not None:
                cache[page] = [img, str(TODAY)]
    out = {}
    for key, page in items:
        img = (cache.get(page) or [""])[0]
        if img and not is_blocked(bl, key, page, img):
            out[key] = img
    return out

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    cache, bl = load(CACHE, {}), blocked()
    res = load(OUT, {"events": {}, "spots": {}})
    if what in ("events", "all"):
        ev = load(os.path.join(ROOT, "events.json"), {"events": []})["events"]
        res["events"] = collect([(e["id"], e["url"]) for e in ev if e.get("url", "").startswith("http")], cache, bl)
        print("イベントの画像", len(res["events"]), "/", len(ev))
    if what in ("spots", "all"):
        items = []
        sd = os.path.join(ROOT, "spots")
        for f in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
            if re.fullmatch(r"\d{2}\.json", f):
                for s in load(os.path.join(sd, f), {"spots": []})["spots"]:
                    if s.get("url"):
                        items.append((s["id"], s["url"]))
        res["spots"] = collect(items, cache, bl)
        print("スポットの画像", len(res["spots"]), "/", len(items))
    else:
        # events だけのときも、ブロックは spots にも当てる
        res["spots"] = {k: v for k, v in res.get("spots", {}).items() if not is_blocked(bl, k, "", v)}
    res["schema"] = 1
    res["updated"] = datetime.datetime.now(JST).isoformat(timespec="minutes")
    res["note"] = "画像は各公式サイトのもの（URL だけを記録して直接表示）。権利者の方からのご連絡で迅速に外します。"
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
