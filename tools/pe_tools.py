# pe_tools.py v2 — イベント毎日更新タスク用の道具箱（出力は短く。長い本文は会話に出さない）
# 使い方: python3 pe_tools.py <コマンド> [引数]
#   prep            今日の日付・窓・raw events.json・ドライブのカード/ログ/過去ログを work/ に取得し、要約だけ表示
#   ragnet          学園祭まとめ28ページを取得→14日窓で絞る→既存/判定済みを除いた候補だけ表示
#   zepp            Zepp6館の金土日祝（窓内）で未登録の公演を JSON 行で表示
#   check URL ...   公式ページを取得し、日付・一般公開キーワードの前後だけ表示（1URL最大5か所）
#   dup 語 ...      既存イベントのタイトル・URLに語を含むものを表示
#   build           work/add.jsonl（1行1イベント）＋ work/remove.txt を検査し、out/events-add-YYYYMMDD.json を作る
#   full            （非常用）raw＋add.jsonl を合体して out/events-YYYYMMDD.json を1イベント1行で作る
#   venues          大型会場・大きな公園の公式ページを取り、今日〜21日先の日付の前後だけ表示（未登録っぽいものだけ）
#   due             毎年恒例の大型台帳（GitHub の big-events.json）から、今月・来月で未登録のものを表示
#   verify FILEID   ドライブに置いたファイルをダウンロードして out/ のものと一致するか確認
import sys, os, re, json, datetime, glob, subprocess, concurrent.futures as cf

FOLDER = "1r-9U6KJ-wXfflYix1Y9wBmT6aCtIEx6O"
RAW = "https://raw.githubusercontent.com/lecrin-group/poke-events/main/events.json"
BIG = "https://raw.githubusercontent.com/lecrin-group/poke-events/main/big-events.json"
SYNC = "https://raw.githubusercontent.com/lecrin-group/poke-events/main/.github/sync.py"
CATS = {"フェス・祭り", "展示会", "公園・庭園", "商業施設", "ライブ", "スポーツ"}
KEYS = ["id", "title", "pref", "area", "venue", "cat", "start", "end", "url", "src"]
JST = datetime.timezone(datetime.timedelta(hours=9))
NOW = datetime.datetime.now(JST)
TODAY = NOW.date()
WEND = TODAY + datetime.timedelta(days=14)
YMD = TODAY.strftime("%Y%m%d")
W, O = "work", "out"
os.makedirs(W, exist_ok=True); os.makedirs(O, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

def curl(url, t=30, binary=False):
    r = subprocess.run(["curl", "-sSL", "-m", str(t), "-A", UA, url], capture_output=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "ignore")

def text(html):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))

def events():
    return json.load(open(f"{W}/events.json", encoding="utf-8"))["events"]

def drive_list():
    h = curl(f"https://drive.google.com/embeddedfolderview?id={FOLDER}")
    out = []
    for c in h.split('id="entry-')[1:]:
        i = re.match(r"([A-Za-z0-9_-]+)", c); t = re.search(r'flip-entry-title">([^<]+)', c)
        if i and t: out.append((t.group(1).strip(), i.group(1)))
    return out

def judged_text():
    s = ""
    for p in glob.glob(f"{W}/*.md"):
        s += open(p, encoding="utf-8", errors="ignore").read()
    return s

def cmd_prep():
    open(f"{W}/events.json", "w", encoding="utf-8").write(curl(RAW))
    ev = events()
    delta = "DELTA-SUPPORT-V1" in curl(SYNC)
    files = drive_list()
    got = []
    for kind in ("card-", "archive-sources-"):
        c = sorted([f for f in files if f[0].startswith(kind)])
        if c:
            open(f"{W}/{c[-1][0]}", "w", encoding="utf-8").write(curl(f"https://drive.google.com/uc?export=download&id={c[-1][1]}"))
            got.append(c[-1][0])
    for name, fid in sorted(f for f in files if f[0].startswith("log-")):
        open(f"{W}/{name}", "w", encoding="utf-8").write(curl(f"https://drive.google.com/uc?export=download&id={fid}"))
        got.append(name)
    ended = sum(1 for e in ev if e["end"] < str(TODAY))
    from collections import Counter
    print(f"today={TODAY} window={TODAY}..{WEND} weekday={'月火水木金土日'[TODAY.weekday()]}")
    print(f"events={len(ev)} ended={ended} pref={dict(Counter(e['pref'] for e in ev))}")
    print(f"mode={'delta' if delta else 'FULL（Actions未対応）'}")
    print("drive files:", ", ".join(f"{n}={i}" for n, i in files))
    print("downloaded:", ", ".join(got))

RG = ["tokyo/7","tokyo/8","tokyo/9","tokyo/10","tokyo/11","tokyo/12","tokyo/13","tokyo/14","tokyo/15","tokyo/16",
      "kanagawa/5","kanagawa/6","kanagawa/7","kanagawa/8","kanagawa/9","chiba/3","chiba/4","chiba/5",
      "saitama/4","saitama/5","saitama/6","saitama/7","aichi/3","aichi/4","aichi/5","fukuoka/2","fukuoka/3","fukuoka/4"]

def cmd_ragnet():
    with cf.ThreadPoolExecutor(14) as ex:
        pages = list(ex.map(lambda p: curl(f"https://www.ragnet.co.jp/festival-{p}?disp=more", 40), RG))
    ev = events(); titles = " ".join(e["title"] for e in ev); urls = {e["url"].rstrip("/") for e in ev}
    jt = judged_text(); seen = set(); rows = []
    for h in pages:
        for b in re.split(r'(?=<h3 id="s\d+">)', h)[1:]:
            m = re.match(r'<h3 id="s\d+">(.*?)<span', b)
            d = re.search(r"<td>日程</td><td>(.*?)</td>", b)
            w = re.search(r'<td>ウェブサイト</td><td><a href="([^"]+)"', b)
            if not (m and d): continue
            name = re.sub("<.*?>", "", m.group(1)); dm = re.match(r"(\d{4})/(\d+)/(\d+)", d.group(1))
            if not dm or name in seen: continue
            st = datetime.date(int(dm[1]), int(dm[2]), int(dm[3]))
            if not (TODAY <= st <= WEND): continue
            seen.add(name); fes = name.split("｜")[0]; url = w.group(1) if w else ""
            if fes in titles or (url and url.rstrip("/") in urls): continue
            tag = "NEW"
            for line in jt.splitlines():
                if fes in line and re.search(r"保留|取得不可|不可|対象外|前年|採用|使える", line):
                    tag = "済"; break
            rows.append((tag, d.group(1), name, url))
    n = 0
    for r in sorted(rows):
        if r[0] == "NEW": print(*r, sep="\t"); n += 1
    print(f"NEW {n} / 判定済みスキップ {sum(1 for r in rows if r[0]=='済')}")

def cmd_zepp():
    halls = {"divercity": ("13", "江東区", "Zepp DiverCity(TOKYO)"), "haneda": ("13", "大田区", "Zepp Haneda(TOKYO)"),
             "yokohama": ("14", "横浜市西区", "KT Zepp Yokohama"), "nagoya": ("23", "名古屋市中村区", "Zepp Nagoya"),
             "osakabayside": ("27", "大阪市此花区", "Zepp Osaka Bayside"), "fukuoka": ("40", "福岡市中央区", "Zepp Fukuoka")}
    ev = events(); have = {e["url"] for e in ev}
    for h, (pref, area, venue) in halls.items():
        base = f"https://www.zepp.co.jp/hall/{h}/schedule/"
        page = curl(base)
        for blk in page.split("schedule/single/?rid=")[1:]:
            rid = re.match(r"(\d+)", blk)
            t = text(blk[:3000])
            dm = re.search(r"(20\d\d)[ ./]+(\d{1,2})\.(\d{1,2})", t)
            if not (rid and dm): continue
            d = datetime.date(int(dm[1]), int(dm[2]), int(dm[3]))
            if not (TODAY <= d <= WEND) or d.weekday() < 4: continue
            if re.search(r"中止|延期|FAN ?CLUB|ファンクラブ", t): continue
            url = f"{base}single/?rid={rid.group(1)}"
            if url in have: continue
            print(json.dumps({"date": str(d), "pref": pref, "area": area, "venue": venue, "url": url, "text": t[:160]}, ensure_ascii=False))

KW = r"どなたでも|一般の方|一般公開|予約不要|入場無料|事前登録不要|申し込み不要|地域の|来場者|ご来場|入場制限|20\d\d年|令和\d+年|\d{1,2}月\d{1,2}日|\d{1,2}/\d{1,2}"

def cmd_check(urls):
    def one(u):
        b = curl(u, 20, binary=True)
        try: t = b.decode("utf-8")
        except UnicodeDecodeError: t = b.decode("cp932", "ignore")
        t = text(t); hits = []
        for m in re.finditer(KW, t):
            s = t[max(0, m.start()-35): m.end()+45]
            if not any(s[:20] in h for h in hits): hits.append(s)
            if len(hits) >= 5: break
        return f"== {u} (len {len(t)})\n  " + "\n  ".join(hits)
    with cf.ThreadPoolExecutor(10) as ex:
        for r in ex.map(one, urls): print(r)

def cmd_dup(words):
    for e in events():
        if any(w in e["title"] or w in e["url"] for w in words):
            print(e["id"], e["start"], e["title"][:40], e["venue"][:20], sep=" | ")

def load_add():
    adds = []
    p = f"{W}/add.jsonl"
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line: adds.append(json.loads(line))
    rm = []
    if os.path.exists(f"{W}/remove.txt"):
        rm = [l.strip() for l in open(f"{W}/remove.txt", encoding="utf-8") if l.strip()]
    return adds, rm

def check_event(e):
    err = []
    if set(e) != set(KEYS): err.append("keys")
    if not re.fullmatch(r"[A-Za-z0-9-]+", e.get("id", "")): err.append("id")
    if not re.fullmatch(r"\d\d", e.get("pref", "")): err.append("pref")
    if e.get("cat") not in CATS: err.append("cat")
    for k in ("start", "end"):
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", e.get(k, "")): err.append(k)
    if e.get("end", "") < e.get("start", ""): err.append("end<start")
    if e.get("end", "9") < str(TODAY): err.append("ended")
    if not str(e.get("url", "")).startswith("https://"): err.append("url")
    if re.search("[\U0001F1E6-\U0001F1FF]", json.dumps(e, ensure_ascii=False)): err.append("flag")
    return err

def validated():
    ev = events(); adds, rm = load_add()
    ids = {e["id"] for e in ev}; k3 = {(e["title"], e["venue"], e["start"]) for e in ev}; urls = {e["url"] for e in ev}
    ok, seen = [], set()
    for e in adds:
        err = check_event(e)
        if e.get("id") in ids or e.get("id") in seen: err.append("dup-id")
        if (e.get("title"), e.get("venue"), e.get("start")) in k3: err.append("dup-title")
        if e.get("url") in urls and "?rid=" not in e.get("url", ""): err.append("same-url?")
        if err and err != ["same-url?"]:
            print("NG", e.get("id"), err); continue
        if err: print("注意(同URLあり・中身を確認)", e.get("id"))
        seen.add(e["id"]); ok.append({k: e[k] for k in KEYS})
    return ev, ok, rm

def summary(evs):
    from collections import Counter
    print("pref:", dict(sorted(Counter(e["pref"] for e in evs).items())))
    print("cat:", dict(Counter(e["cat"] for e in evs)))

def cmd_build():
    ev, ok, rm = validated()
    out = {"schema": 1, "updated": NOW.strftime("%Y-%m-%dT%H:%M:00+09:00"), "add": ok, "remove": rm}
    s = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    p = f"{O}/events-add-{YMD}.json"; open(p, "w", encoding="utf-8").write(s)
    alive = [e for e in ev if e["end"] >= str(TODAY) and e["id"] not in set(rm)] + ok
    print(f"OK {len(ok)}件 remove {len(rm)}件 → {p} ({len(s.encode())} bytes)  合体後の見込み {len(alive)}件")
    summary(alive)

def cmd_full():
    ev, ok, rm = validated()
    alive = [e for e in ev if e["end"] >= str(TODAY) and e["id"] not in set(rm)] + ok
    lines = ",\n".join(json.dumps({k: e.get(k, "") for k in KEYS}, ensure_ascii=False, separators=(",", ":")) for e in alive)
    s = '{"schema":1,"updated":"%s","events":[\n%s\n]}' % (NOW.strftime("%Y-%m-%dT%H:%M:00+09:00"), lines)
    json.loads(s)
    p = f"{O}/events-{YMD}.json"; open(p, "w", encoding="utf-8").write(s)
    print(f"FULL {len(alive)}件 → {p} ({len(s.encode())} bytes)"); summary(alive)

VENUES = [
 ("東京ビッグサイト", "https://www.bigsight.jp/visitor/event/"),
 ("東京ドーム", "https://www.tokyo-dome.co.jp/dome/event/schedule.html"),
 ("有明アリーナ", "https://ariake-arena.tokyo/event/"),
 ("代々木公園", "https://www.tokyo-park.or.jp/park/yoyogi/"),
 ("日比谷公園", "https://www.tokyo-park.or.jp/park/hibiya/"),
 ("葛西臨海公園", "https://www.tokyo-park.or.jp/park/kasairinkai/"),
 ("木場公園", "https://www.tokyo-park.or.jp/park/kiba/"),
 ("サンシャインシティ", "https://www.sunshinecity.jp/event/"),
 ("東京ドームシティ", "https://www.tokyo-dome.co.jp/event/"),
 ("幕張メッセ", "https://www.m-messe.co.jp/event/"),
 ("東京スカイツリー", "https://www.tokyo-skytree.jp/event/"),
 ("東京ソラマチ", "https://www.tokyo-solamachi.jp/event/"),
 ("六本木ヒルズ", "https://www.roppongihills.com/events/"),
 ("東京ミッドタウン", "https://www.tokyo-midtown.com/jp/event/"),
 ("恵比寿ガーデンプレイス", "https://gardenplace.jp/event/"),
 ("渋谷ストリーム", "https://shibuyastream.jp/event/"),
 ("よみうりランド", "https://www.yomiuriland.com/event/"),
 ("国営昭和記念公園", "https://www.showakinen-koen.jp/event/"),
 ("横浜赤レンガ倉庫", "https://www.yokohama-akarenga.jp/event/"),
 ("みなとみらい21", "https://www.minatomirai21.com/event/"),
 ("横浜アリーナ", "https://www.yokohama-arena.co.jp/event/"),
 ("さいたまスーパーアリーナ", "https://www.saitama-arena.co.jp/event/"),
 ("京セラドーム大阪", "https://www.kyoceradome-osaka.jp/events/"),
]

def win_dates():
    out = set()
    for i in range(22):
        d = TODAY + datetime.timedelta(days=i)
        out.add((d.month, d.day))
    return out

def cmd_venues():
    wd = win_dates(); ev = events()
    known = [e["title"][:8] for e in ev if len(e["title"]) >= 4]
    pat = re.compile(r"(?:20\d\d\s*[./年]\s*)?(\d{1,2})\s*[./月]\s*(\d{1,2})")
    def one(v):
        name, u = v
        raw = curl(u, 25, True)
        try: h = raw.decode("utf-8")
        except UnicodeDecodeError: h = raw.decode("cp932", "ignore")
        t = text(h); got = []; seen = set(); last = -999
        for m in pat.finditer(t):
            try: md = (int(m.group(1)), int(m.group(2)))
            except ValueError: continue
            if md not in wd or m.start() - last < 90: continue
            sn = t[max(0, m.start() - 40): m.start() + 50].strip()
            if any(k in sn for k in known): continue
            key = sn[:30]
            if key in seen: continue
            seen.add(key); got.append(sn); last = m.start()
            if len(got) >= 3: break
        return name, u, len(t), got
    vs = list(VENUES)
    sp = f"{W}/spaces.csv"   # ドライブの「イベントスペース台帳（1都3県）」を CSV で落としたもの（状態=チェック中・読める だけ使う）
    if os.path.exists(sp):
        import csv
        have = {u for _, u in vs}
        for row in csv.DictReader(open(sp, encoding="utf-8-sig")):
            u = (row.get("イベント一覧の公式URL") or "").strip()
            if row.get("状態") == "チェック中" and row.get("機械で読めるか") == "読める" and u.startswith("https://") and u not in have:
                vs.append((row.get("スペース名", "?"), u)); have.add(u)
    print(f"会場 {len(vs)} か所（台帳から {len(vs) - len(VENUES)}）")
    with cf.ThreadPoolExecutor(8) as ex:
        for name, u, n, got in ex.map(one, vs):
            print(f"## {name} {u} ({'取得不可' if n < 200 else str(len(got)) + '件'})")
            for g in got: print("  -", g)

def cmd_due():
    try: big = json.loads(curl(BIG))["items"]
    except Exception as ex: print("big-events.json 取得失敗:", ex); return
    ev = events(); ms = {TODAY.month, (TODAY.replace(day=1) + datetime.timedelta(days=32)).month}
    titles = " ".join(e["title"] + " " + e["url"] for e in ev)
    done = judged_text()   # ログに「大型済：名前」と書いたものは1週間飛ばす（ログは8日で消える）
    n = 0
    for b in big:
        if not ms & set(b.get("m", [])): continue
        if b.get("k") and b["k"] in titles: continue
        if f"大型済：{b['n']}" in done: continue
        n += 1
        hint = " | → pref 00・area「オンライン」・cat 商業施設・venue はサイト名" if "オンライン" in b["n"] else ""
        print(f"{b['n']} | pref {b['p']} | 例年{','.join(map(str, b['m']))}月 | {b.get('url') or '公式を検索'}{hint}")
    print(f"due {n}件（今月・来月で未登録）")

def cmd_verify(fid):
    got = curl(f"https://drive.google.com/uc?export=download&id={fid}")
    for p in sorted(glob.glob(f"{O}/*.json")):
        mine = open(p, encoding="utf-8").read()
        try:
            if json.loads(got) == json.loads(mine): print("一致:", p); return
        except Exception as ex:
            print("JSONエラー:", ex); return
    print("不一致（out/ のどれとも違う）")

if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    a = sys.argv[2:]
    {"prep": cmd_prep, "ragnet": cmd_ragnet, "zepp": cmd_zepp, "build": cmd_build, "full": cmd_full, "venues": cmd_venues, "due": cmd_due}.get(c, lambda: None)() if c in ("prep", "ragnet", "zepp", "build", "full", "venues", "due") else \
        {"check": cmd_check, "dup": cmd_dup}.get(c, lambda x: None)(a) if c in ("check", "dup") else \
        cmd_verify(a[0]) if c == "verify" else print(open(__file__, encoding="utf-8").read().split("import sys")[0])
