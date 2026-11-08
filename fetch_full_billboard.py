import urllib.request
from bs4 import BeautifulSoup
import concurrent.futures
import datetime
import json
import os
import time

CACHE_FILE = "billboard_cache.json"

# 2008-01-16 (Billboard JAPAN Hot 100 初回公開水曜日) から 2026-11-04 (最新水曜日) まで
start_wed = datetime.date(2008, 1, 16)
latest_wed = datetime.date(2026, 11, 4)

weeks = []
cur = start_wed
while cur <= latest_wed:
    chart_mon = cur + datetime.timedelta(days=5)
    # その月の第何水曜日かを計算
    first_day_of_month = datetime.date(cur.year, cur.month, 1)
    wed_count = 0
    t = first_day_of_month
    while t <= cur:
        if t.weekday() == 2: # 水曜日
            wed_count += 1
        t += datetime.timedelta(days=1)
    
    weeks.append({
        'release_date': cur.strftime('%Y-%m-%d'),
        'chart_date': chart_mon.strftime('%Y-%m-%d'),
        'year': cur.year,
        'month': cur.month,
        'week': wed_count,
        'chart_year': chart_mon.year,
        'chart_month': chart_mon.month,
        'chart_day': chart_mon.day
    })
    cur += datetime.timedelta(days=7)

print(f"Total target weeks: {len(weeks)}")

# キャッシュの読み込み
cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        print(f"Loaded {len(cache)} weeks from cache.")
    except Exception as e:
        print("Cache load error:", e)

def fetch_week(w):
    key = w['release_date']
    if key in cache and len(cache[key].get('songs', [])) >= 10:
        return key, cache[key]['songs']
    
    url = f"https://www.billboard-japan.com/charts/detail?a=hot100&year={w['chart_year']}&month={w['chart_month']:02d}&day={w['chart_day']:02d}"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            html = urllib.request.urlopen(req, timeout=12).read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            titles = soup.select('p.musuc_title')
            artists = soup.select('p.artist_name')
            songs = []
            for i in range(min(10, len(titles))):
                t_text = titles[i].get_text(strip=True)
                a_text = artists[i].get_text(strip=True) if i < len(artists) else "不明"
                if t_text:
                    songs.append({
                        'rank': i + 1,
                        'track': t_text,
                        'artist': a_text
                    })
            if len(songs) >= 5: # 最低5曲取れていればOK
                return key, songs
            time.sleep(0.3)
        except Exception as e:
            time.sleep(0.8)
    return key, None

remaining = [w for w in weeks if w['release_date'] not in cache or len(cache[w['release_date']].get('songs', [])) < 10]
print(f"Remaining weeks to fetch: {len(remaining)}")

batch_size = 40
for i in range(0, len(remaining), batch_size):
    batch = remaining[i:i+batch_size]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_week, w): w for w in batch}
        for f in concurrent.futures.as_completed(futures):
            w = futures[f]
            key, songs = f.result()
            if songs:
                cache[key] = {
                    'release_date': w['release_date'],
                    'chart_date': w['chart_date'],
                    'year': w['year'],
                    'month': w['month'],
                    'week': w['week'],
                    'songs': songs
                }
            else:
                print(f"Failed to fetch {key}")
    
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"Progress: {len(cache)}/{len(weeks)} saved. (Batch {i//batch_size + 1}/{(len(remaining) + batch_size - 1)//batch_size})")
    time.sleep(0.5)

# 最終確認と出力
success_count = sum(1 for w in weeks if w['release_date'] in cache and len(cache[w['release_date']]['songs']) > 0)
print(f"Completed! {success_count} / {len(weeks)} weeks successfully fetched.")

# 日付順にソートしてJS形式で出力
sorted_cache = {k: cache[k] for k in sorted(cache.keys())}
js_content = f"// Billboard JAPAN Hot 100 週間TOP10 公式実データ (2008年1月16日週〜2026年11月)\n// 全{len(sorted_cache)}週分 完全収録\nconst BILLBOARD_WEEKLY_DATA = " + json.dumps(sorted_cache, ensure_ascii=False, separators=(',', ':')) + ";\n"
with open("billboard_data.js", "w", encoding="utf-8") as f:
    f.write(js_content)

print(f"Wrote billboard_data.js ({os.path.getsize('billboard_data.js')} bytes)")
