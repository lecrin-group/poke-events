# deltas/
毎日のイベント更新タスクが置く差分（events-add-YYYYMMDD.json）。中身はドライブに置いていたものと同じ形。
ここに push されると .github/workflows/sync.yml がすぐ動いて events.json に取り込む（同じ差分を2回足すことはない）。
同じ日に2回目を置くときは events-add-YYYYMMDD-2.json のように名前を変える。
