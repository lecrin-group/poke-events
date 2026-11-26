# spot_genres.py — スポットのジャンル（ナギサが ○ を付けたもの。シート「ESJ スポットのジャンル案（202）」2026-11-26）
# build_spots.py が読む。QUERIES で OpenStreetMap から取り、classify() でジャンルを決める
# 大分類（grp）→ ジャンル（cat）の2段。サイトの絞り込みも2段
# ×（図書館・銭湯・ゴルフ練習場・家電量販店・ドンキ・マッサージ・フィットネス・写真館・音楽スタジオ・
#     ビジターセンター・レンタサイクル・カプセルホテル・旅館）は入れない
# △ テニスコート・市民プールは保留（入れない）。ブックカフェはカフェ併設の大型書店だけ、ネカフェは大型の複合店だけ
# 数がとても多いもの（神社・お寺・カフェ・バー・公園など）は「公式サイトか Wikidata があるもの」だけ
import re

HEAD = '[out:json][timeout:300];area["ISO3166-1"="JP"]->.jp;('
NOTE = '[~"^(website|contact:website|wikidata)$"~"."]'   # 公式サイトか Wikidata がある
Q = lambda body: HEAD + body + ');out center tags;'
QUERIES = [
    Q('nwr[tourism~"^(aquarium|theme_park|zoo|museum|gallery)$"](area.jp);'
      'nwr[amenity~"^(cinema|theatre|planetarium|music_venue|nightclub|exhibition_centre|karaoke_box|hookah_lounge|biergarten|food_court|marketplace)$"][name](area.jp);'),
    Q('nwr[leisure~"^(water_park|stadium|bowling_alley|amusement_arcade|escape_game|indoor_play|trampoline_park|ice_rink|miniature_golf|dog_park|horse_riding|fishing|spa|sauna|beach_resort)$"][name](area.jp);'
      'nwr[leisure=garden][name](area.jp);nwr[man_made~"^(tower|lighthouse|observatory)$"][name](area.jp);'),
    Q('nwr[tourism~"^(viewpoint|camp_site|attraction)$"][name](area.jp);'
      'nwr[historic~"^(castle|archaeological_site|manor|monument|district)$"][name](area.jp);'
      'nwr[waterway=waterfall][name](area.jp);nwr[natural~"^(beach|hot_spring|valley)$"][name](area.jp);'),
    Q('nwr[amenity=place_of_worship][religion~"^(shinto|buddhist|christian)$"][name]' + NOTE + '(area.jp);'
      'nwr[leisure=park][name]' + NOTE + '(area.jp);nwr[natural=peak][name][wikidata](area.jp);'),
    Q('nwr[amenity=cafe][name][!brand]' + NOTE + '(area.jp);nwr[amenity=cafe][name~"猫|ねこ|ネコ|フクロウ|ふくろう|うさぎ|ハリネズミ|アニマル|メイド|コンセプト|ボードゲーム|蔦屋"](area.jp);'
      'nwr[amenity=bar][name][!brand]' + NOTE + '(area.jp);nwr[amenity=bar][name~"ダーツ|ビリヤード|シーシャ|ポーカー|ジャズ|スポーツバー"](area.jp);'),
    Q('nwr[shop~"^(mall|department_store)$"][name](area.jp);nwr[shop~"^(confectionery|pastry)$"][name][!brand]' + NOTE + '(area.jp);'
      'nwr[shop~"^(anime|games|model)$"][name](area.jp);nwr[shop=gift][name~"物産|土産|みやげ"](area.jp);'
      'nwr[craft~"^(winery|brewery|distillery|sake_brewery|pottery|glassblower)$"][name](area.jp);'),
    Q('nwr[sport~"^(darts|billiards|climbing|surfing|scuba_diving|canoe|karting|motor|free_flying|airsoft|paintball|table_tennis)$"][name](area.jp);'
      'nwr[leisure=sports_centre][name]' + NOTE + '(area.jp);nwr[leisure=golf_course][name](area.jp);nwr[landuse=winter_sports][name](area.jp);'
      'nwr[leisure=pitch][sport~"^(baseball|soccer)$"][name][wikidata](area.jp);nwr[amenity=bbq][name](area.jp);nwr[highway=services][name](area.jp);'
      'nwr[aerialway~"^(cable_car|gondola)$"][name](area.jp);nwr[railway=funicular][name](area.jp);nwr[amenity=internet_cafe][name~"ダーツ|カラオケ|ビリヤード|快活|自遊空間"](area.jp);'),
    Q('nwr[name~"商店街|横丁|道の駅|中華街|屋形船|水上バス|遊覧船|足湯|いちご狩り|ぶどう狩り|果物狩り|観光農園|着物レンタル|レンタル着物|寄席|演芸場|能楽堂|コスプレ|バッティングセンター|ラウンドワン|脱出ゲーム|謎解き|牧場|工場見学|大仏|観音"](area.jp);'),
]

def nm(t):
    return t.get("name", "")

def has(rx, s):
    return re.search(rx, s) is not None

# (大分類, ジャンル, 当てはまるか)。上から順に最初に当たったものを使う
R = [
    # ---- 名前で決まるもの（先に見る）
    ("買う・街歩き", "商店街", lambda t: has(r"商店街", nm(t)) and not t.get("amenity") and not t.get("shop") or has(r"商店街$", nm(t))),
    ("カフェ・食べる", "道の駅", lambda t: has(r"^道の駅", nm(t))),
    ("カフェ・食べる", "横丁・飲み屋街", lambda t: has(r"横丁$|横町$", nm(t)) and not t.get("shop")),
    ("買う・街歩き", "中華街", lambda t: has(r"中華街$", nm(t)) and not t.get("amenity")),
    ("夜・大人の遊び", "屋形船", lambda t: has(r"屋形船", nm(t))),
    ("乗る・移動を楽しむ", "遊覧船・水上バス", lambda t: has(r"水上バス|遊覧船", nm(t))),
    ("温泉・リラックス", "足湯", lambda t: has(r"足湯", nm(t)) or t.get("bath:type") == "foot"),
    ("体験・つくる", "果物狩り・観光農園", lambda t: has(r"いちご狩り|ぶどう狩り|果物狩り|観光農園", nm(t))),
    ("体験・つくる", "着物レンタル", lambda t: has(r"着物レンタル|レンタル着物", nm(t))),
    ("観る・聴く", "寄席・演芸場", lambda t: has(r"寄席|演芸場", nm(t))),
    ("観る・聴く", "能楽堂", lambda t: has(r"能楽堂", nm(t))),
    ("ポップカルチャー", "コスプレスタジオ", lambda t: has(r"コスプレ", nm(t))),
    ("ゲーム・アミューズメント", "バッティングセンター", lambda t: has(r"バッティングセンター", nm(t))),
    ("ゲーム・アミューズメント", "複合アミューズメント", lambda t: has(r"ラウンドワン|ROUND1|Round1", nm(t))),
    ("遊園地・テーマパーク", "謎解き・脱出ゲーム", lambda t: t.get("leisure") == "escape_game" or has(r"脱出ゲーム|謎解き", nm(t))),
    ("生きもの", "観光牧場", lambda t: has(r"牧場$|ファーム$", nm(t)) and (t.get("tourism") or t.get("website") or t.get("wikidata"))),
    ("見る・学ぶ", "工場見学", lambda t: has(r"工場見学|見学センター|ファクトリー", nm(t)) and (t.get("tourism") or t.get("website"))),
    ("神社・お寺", "大仏・観音像", lambda t: has(r"大仏$|観音$|観音像", nm(t)) and not t.get("amenity")),
    # ---- 遊園地・テーマパーク
    ("遊園地・テーマパーク", "テーマパーク・遊園地", lambda t: t.get("tourism") == "theme_park"),
    ("遊園地・テーマパーク", "ウォーターパーク", lambda t: t.get("leisure") == "water_park"),
    ("遊園地・テーマパーク", "キッズパーク・屋内遊び場", lambda t: t.get("leisure") == "indoor_play"),
    ("遊園地・テーマパーク", "トランポリンパーク", lambda t: t.get("leisure") == "trampoline_park"),
    # ---- 生きもの
    ("生きもの", "サファリパーク", lambda t: t.get("tourism") == "zoo" and t.get("zoo") == "safari_park"),
    ("生きもの", "ふれあい動物園", lambda t: t.get("tourism") == "zoo" and t.get("zoo") == "petting_zoo"),
    ("生きもの", "動物園", lambda t: t.get("tourism") == "zoo"),
    ("生きもの", "水族館", lambda t: t.get("tourism") == "aquarium"),
    ("生きもの", "動物カフェ", lambda t: t.get("amenity") == "cafe" and has(r"猫|ねこ|ネコ|フクロウ|ふくろう|うさぎ|ハリネズミ|アニマル|ドッグ|わんこ", nm(t))),
    ("生きもの", "釣り・釣り堀", lambda t: t.get("leisure") == "fishing"),
    ("公園・自然", "ドッグラン", lambda t: t.get("leisure") == "dog_park"),
    # ---- 見る・学ぶ
    ("見る・学ぶ", "プラネタリウム", lambda t: t.get("amenity") == "planetarium"),
    ("見る・学ぶ", "科学館", lambda t: t.get("tourism") == "museum" and (t.get("museum") == "science" or has(r"科学館|サイエンス", nm(t)))),
    ("見る・学ぶ", "美術館・ギャラリー", lambda t: t.get("tourism") == "gallery" or (t.get("tourism") == "museum" and (t.get("museum") == "art" or has(r"美術館|アート|ミュージアム", nm(t))))),
    ("見る・学ぶ", "博物館・記念館", lambda t: t.get("tourism") == "museum"),
    ("見る・学ぶ", "天文台", lambda t: t.get("man_made") == "observatory" and (t.get("website") or t.get("wikidata") or t.get("tourism"))),
    ("見る・学ぶ", "城・城跡", lambda t: t.get("historic") == "castle"),
    ("見る・学ぶ", "史跡・遺跡", lambda t: t.get("historic") == "archaeological_site" and (t.get("wikidata") or t.get("website") or t.get("tourism"))),
    ("見る・学ぶ", "歴史的建造物", lambda t: t.get("historic") in ("manor", "monument") and (t.get("wikidata") or t.get("tourism"))),
    ("買う・街歩き", "古い町並み", lambda t: t.get("historic") == "district"),
    ("体験・つくる", "体験工房", lambda t: t.get("craft") in ("pottery", "glassblower")),
    # ---- 展望・景色
    ("展望・景色", "展望台・タワー", lambda t: t.get("man_made") == "tower" and (t.get("tourism") or t.get("wikidata") or t.get("website") or has(r"タワー|展望", nm(t)))),
    ("展望・景色", "展望スポット・夜景", lambda t: t.get("tourism") == "viewpoint"),
    ("展望・景色", "滝", lambda t: t.get("waterway") == "waterfall"),
    ("展望・景色", "渓谷", lambda t: t.get("natural") == "valley" and (t.get("wikidata") or t.get("tourism"))),
    ("展望・景色", "海水浴場", lambda t: t.get("leisure") == "beach_resort" or (t.get("natural") == "beach" and has(r"海水浴場", nm(t)))),
    ("展望・景色", "海岸・ビーチ", lambda t: t.get("natural") == "beach"),
    ("展望・景色", "灯台", lambda t: t.get("man_made") == "lighthouse" and (t.get("wikidata") or t.get("tourism") or t.get("website"))),
    ("展望・景色", "ロープウェイ・ケーブルカー", lambda t: t.get("aerialway") in ("cable_car", "gondola") or t.get("railway") == "funicular"),
    # ---- 公園・自然
    ("公園・自然", "植物園・フラワーパーク", lambda t: t.get("leisure") == "garden" and (t.get("garden:type") == "botanical" or has(r"植物園|フラワー|花の", nm(t)))),
    ("公園・自然", "日本庭園", lambda t: t.get("leisure") == "garden" and (t.get("wikidata") or t.get("website") or t.get("tourism") or t.get("garden:style") == "japanese" or has(r"庭園", nm(t)))),
    ("公園・自然", "大きな公園", lambda t: t.get("leisure") == "park"),
    ("公園・自然", "キャンプ・グランピング", lambda t: t.get("tourism") == "camp_site"),
    ("公園・自然", "バーベキュー場", lambda t: t.get("amenity") == "bbq"),
    ("公園・自然", "山", lambda t: t.get("natural") == "peak"),
    ("公園・自然", "川遊び・カヌー", lambda t: t.get("sport") == "canoe"),
    # ---- 神社・お寺
    ("神社・お寺", "神社", lambda t: t.get("amenity") == "place_of_worship" and t.get("religion") == "shinto"),
    ("神社・お寺", "お寺", lambda t: t.get("amenity") == "place_of_worship" and t.get("religion") == "buddhist"),
    ("神社・お寺", "教会・聖堂", lambda t: t.get("amenity") == "place_of_worship" and t.get("religion") == "christian" and (t.get("wikidata") or t.get("tourism"))),
    # ---- 温泉・リラックス
    ("温泉・リラックス", "温泉・スーパー銭湯", lambda t: t.get("natural") == "hot_spring" or (t.get("amenity") == "public_bath" and (t.get("bath:type") == "onsen" or t.get("website") or has(r"温泉|スパ|の湯|天然", nm(t))))),
    ("温泉・リラックス", "スパ・サウナ", lambda t: t.get("leisure") in ("spa", "sauna")),
    # ---- カフェ・食べる
    ("カフェ・食べる", "コンセプトカフェ・メイドカフェ", lambda t: t.get("amenity") == "cafe" and has(r"メイド|コンセプト", nm(t))),
    ("ゲーム・アミューズメント", "ボードゲームカフェ", lambda t: has(r"ボードゲーム", nm(t))),
    ("カフェ・食べる", "ブックカフェ（大型書店）", lambda t: t.get("amenity") == "cafe" and has(r"蔦屋|ブックカフェ|BOOK", nm(t))),
    ("カフェ・食べる", "カフェ・喫茶店", lambda t: t.get("amenity") == "cafe" and not t.get("brand")),
    ("カフェ・食べる", "スイーツ", lambda t: t.get("shop") in ("confectionery", "pastry")),
    ("カフェ・食べる", "フードコート・屋台村", lambda t: t.get("amenity") == "food_court"),
    ("カフェ・食べる", "ビアガーデン", lambda t: t.get("amenity") == "biergarten"),
    ("カフェ・食べる", "酒蔵・ワイナリー・ブルワリー", lambda t: t.get("craft") in ("winery", "brewery", "distillery", "sake_brewery")),
    ("カフェ・食べる", "市場・朝市", lambda t: t.get("amenity") == "marketplace"),
    ("カフェ・食べる", "サービスエリア", lambda t: t.get("highway") == "services"),
    # ---- 夜・大人の遊び
    ("夜・大人の遊び", "シーシャ", lambda t: t.get("amenity") == "hookah_lounge" or has(r"シーシャ|SHISHA|Shisha|hookah", nm(t))),
    ("夜・大人の遊び", "ダーツ", lambda t: t.get("sport") == "darts" or has(r"ダーツ", nm(t))),
    ("夜・大人の遊び", "ビリヤード", lambda t: t.get("sport") == "billiards" or has(r"ビリヤード|プールバー", nm(t))),
    ("夜・大人の遊び", "ポーカー・アミューズメントカジノ", lambda t: has(r"ポーカー|カジノ", nm(t)) and t.get("leisure") != "adult_gaming_centre"),
    ("夜・大人の遊び", "クラブ", lambda t: t.get("amenity") == "nightclub"),
    ("夜・大人の遊び", "ライブバー・ジャズバー", lambda t: t.get("amenity") == "bar" and (t.get("live_music") == "yes" or has(r"ジャズ|JAZZ|Jazz|ライブ", nm(t)))),
    ("夜・大人の遊び", "スポーツバー", lambda t: t.get("amenity") == "bar" and has(r"スポーツバー|SPORTS", nm(t))),
    ("夜・大人の遊び", "バー", lambda t: t.get("amenity") == "bar"),
    # ---- ゲーム・アミューズメント
    ("ゲーム・アミューズメント", "複合アミューズメント", lambda t: t.get("amenity") == "internet_cafe"),
    ("ゲーム・アミューズメント", "ゲームセンター", lambda t: t.get("leisure") == "amusement_arcade"),
    ("ゲーム・アミューズメント", "カラオケ", lambda t: t.get("amenity") == "karaoke_box"),
    ("ゲーム・アミューズメント", "ボウリング", lambda t: t.get("leisure") == "bowling_alley"),
    ("ゲーム・アミューズメント", "卓球", lambda t: t.get("sport") == "table_tennis"),
    ("ゲーム・アミューズメント", "ミニゴルフ", lambda t: t.get("leisure") == "miniature_golf"),
    ("ゲーム・アミューズメント", "サバゲー", lambda t: t.get("sport") in ("airsoft", "paintball")),
    # ---- スポーツ
    ("スポーツ・体を動かす", "競馬・競輪・競艇", lambda t: has(r"競馬場|競輪場|競艇|ボートレース|オートレース", nm(t))),
    ("スポーツ・体を動かす", "スタジアム", lambda t: t.get("leisure") == "stadium"),
    ("スポーツ・体を動かす", "野球場・サッカー場", lambda t: t.get("leisure") == "pitch"),
    ("スポーツ・体を動かす", "ボルダリング・クライミング", lambda t: t.get("sport") == "climbing"),
    ("スポーツ・体を動かす", "スケートリンク", lambda t: t.get("leisure") == "ice_rink"),
    ("スポーツ・体を動かす", "スキー場", lambda t: t.get("landuse") == "winter_sports"),
    ("スポーツ・体を動かす", "ゴルフ場", lambda t: t.get("leisure") == "golf_course" and not has(r"練習|打ちっぱなし", nm(t))),
    ("スポーツ・体を動かす", "サーフィン", lambda t: t.get("sport") == "surfing"),
    ("スポーツ・体を動かす", "ダイビング", lambda t: t.get("sport") == "scuba_diving"),
    ("スポーツ・体を動かす", "乗馬", lambda t: t.get("leisure") == "horse_riding"),
    ("スポーツ・体を動かす", "カート・サーキット", lambda t: t.get("sport") in ("karting", "motor")),
    ("スポーツ・体を動かす", "パラグライダー", lambda t: t.get("sport") == "free_flying"),
    ("スポーツ・体を動かす", "アリーナ・体育館", lambda t: t.get("leisure") == "sports_centre"),
    # ---- 観る・聴く
    ("観る・聴く", "映画館", lambda t: t.get("amenity") == "cinema"),
    ("観る・聴く", "ライブハウス", lambda t: t.get("amenity") == "music_venue"),
    ("観る・聴く", "劇場・ホール", lambda t: t.get("amenity") == "theatre"),
    ("観る・聴く", "イベントホール・展示場", lambda t: t.get("amenity") == "exhibition_centre"),
    # ---- 買う・街歩き
    ("買う・街歩き", "アウトレット", lambda t: t.get("shop") == "mall" and has(r"アウトレット|OUTLET|Outlet", nm(t))),
    ("買う・街歩き", "ショッピングモール", lambda t: t.get("shop") == "mall"),
    ("買う・街歩き", "百貨店", lambda t: t.get("shop") == "department_store"),
    ("ポップカルチャー", "アニメ・ホビーショップ", lambda t: t.get("shop") in ("anime", "games", "model")),
    ("買う・街歩き", "お土産・物産館", lambda t: t.get("shop") == "gift"),
    # ---- 観光名所（どれにも当たらない tourism=attraction）
    ("展望・景色", "観光名所", lambda t: t.get("tourism") == "attraction" and (t.get("wikidata") or t.get("website"))),
]
GROUPS = []
for g, c, _ in R:
    if g not in GROUPS:
        GROUPS.append(g)

def classify(t):
    if not t.get("name"):
        return None
    if t.get("disused") or t.get("abandoned") or t.get("access") == "private":
        return None
    for g, c, f in R:
        try:
            if f(t):
                return g, c
        except Exception:
            pass
    return None
