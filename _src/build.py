#!/usr/bin/env python3
"""Build the static NY trip site.
usage: python3 build.py [OUT_DIR]   (default: /mnt/project-files/ny-trip/site)
Reads content.yaml + ../media/web/manifest.json, writes RU at OUT/ and EN at OUT/en/.
"""
import os, sys, json, shutil, datetime as dt, html
import yaml
from jinja2 import Environment, FileSystemLoader

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.normpath(os.path.join(HERE, '..', 'media'))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(os.path.join(HERE, '..', 'site'))

C = yaml.safe_load(open(os.path.join(HERE, 'content.yaml'), encoding='utf-8'))
manifest = json.load(open(os.path.join(MEDIA, 'web', 'manifest.json'), encoding='utf-8'))

# Privacy switches: flip to True once consent is confirmed.
CONSENT = {'masha': True, 'stranger': True}  # Masha's parents agreed 2026-11-12

FOLDER_TZ = {'day0-cyprus': 2, 'doha': 3}
DAY0_FOLDERS = {'day0-cyprus', 'doha'}
DAY_COLORS = ['#ffcc00', '#e3262b', '#1f4fd8', '#0a8a4f']  # yellow, red, blue, green (style.css tokens)

days = C['days']
day_by_id = {d['id']: d for d in days}
for i, d in enumerate(days):
    d['color'] = DAY_COLORS[i % len(DAY_COLORS)]
    d['moments'] = []
    d['media'] = []
topics = C['topics']
topic_by_id = {t['id']: t for t in topics}

# ---------- media -> days ----------
seen = set()
for m in sorted(manifest, key=lambda x: x['t']):
    key = m['src']
    if key in seen:
        continue
    seen.add(key)
    tz = FOLDER_TZ.get(m['day'], -5)
    t = dt.datetime.fromisoformat(m['t'].replace('Z', '+00:00')) + dt.timedelta(hours=tz)
    did = '2026-11-03' if m['day'] in DAY0_FOLDERS else t.strftime('%Y-%m-%d')
    if did not in day_by_id:
        continue
    m['local'] = t.strftime('%H:%M')
    m['used'] = False
    day_by_id[did]['media'].append(m)

# ---------- curation (media/curation.json from the curation thread) ----------
# On by default (Sergey approved 2026-11-12); CURATED=0 disables.
CURATED = os.environ.get('CURATED', '1') == '1'
details_media = []
topic_media = {}  # topic id -> media shown on that topic page (side observations)
for d in days:
    d['all_media'] = list(d['media'])  # before curation: explicit moment `photos` may pick any of these
if CURATED and os.path.exists(os.path.join(MEDIA, 'curation.json')):
    cur = json.load(open(os.path.join(MEDIA, 'curation.json'), encoding='utf-8'))['days']
    for d in days:
        cd = cur.get(d['id'], {})
        st = {p['src']: p for p in cd.get('photos', [])}
        st.update({v['src']: v for v in cd.get('videos', [])})
        keep = []
        for m in d['media']:
            c = st.get(m['src'], {})
            status = c.get('status', 'keep')
            if status == 'cut' or (status == 'masha' and not CONSENT['masha']):
                continue
            if c.get('loop') and status in ('loop', 'topic', 'details'):
                m['loop'], m['loop_poster'] = c['loop'], c.get('poster')
            tids = list(c.get('topics') or [])
            if status == 'details' and 'details' not in tids:
                tids.append('details')
            for tid in tids:
                topic_media.setdefault(tid, []).append(m)
            if status in ('details', 'topic'):
                details_media.append(m)  # kept for media refs
                continue
            m['order'] = c.get('order') if c.get('order') is not None else 10_000
            keep.append(m)
        d['media'] = keep
        if cd.get('reel'):
            d['reel'] = cd['reel']

# ---------- moments ----------
moments = C['moments']
for i, mo in enumerate(moments):
    d = day_by_id[mo['day']]
    mo['order'] = i
    d['moments'].append(mo)
    mo['media'] = []
    blocked = mo.get('privacy') and not CONSENT.get(mo['privacy'], False)
    mo['hidden_media'] = bool(blocked)
    if mo.get('photos'):
        # search this day first, then any day (e.g. the cap photo lives on Nov 10)
        for m in d['all_media'] + [x for dd in days if dd is not d for x in dd['all_media']]:
            if any(m['src'].startswith(p) for p in mo['photos']):
                if not blocked:
                    mo['media'].append(m)
                m['used'] = True
                m['blocked'] = bool(blocked)
for d in days:
    for m in d['media']:
        if m['used']:
            continue
        for mo in d['moments']:
            if mo.get('layout') == 'field' and mo.get('photos'):
                continue  # notes show only their explicit picks
            if 'from' in mo and mo['from'] <= m['local'] < mo['to']:
                m['used'] = True
                m['blocked'] = mo['hidden_media']
                if not mo['hidden_media']:
                    mo['media'].append(m)
                break
    if CURATED:
        for mo in d['moments']:
            mo['media'].sort(key=lambda m: (m.get('order', 10_000), m['t']))
    d['extra'] = [m for m in d['media'] if not m['used']]
    photos = [m for m in d['media'] if m['type'] == 'photo' and m['w'] >= m['h'] and not m.get('blocked')]
    cov = d.get('cover')
    d['cover_media'] = next((m for m in photos if cov and m['src'].startswith(cov)), None) or \
        (photos[len(photos) // 3] if photos else (d['media'][0] if d['media'] else None))

MULT = {'family': 1, 'person': 3, 'adult': 2, 'child': 1, 'night': 1}

def day_cost(d):
    total, unknown = 0, False
    for mo in d['moments']:
        p = mo.get('price')
        if not p:
            continue
        if p.get('usd') is None:
            unknown = True
            continue
        if p['usd'] > 0:
            total += p['usd'] * MULT.get(p.get('per', 'family'), 1)
            if p.get('per') == 'adult':
                unknown = True  # child ticket price not known
    return total, unknown

for d in days:
    d['cost'], d['cost_unknown'] = day_cost(d)

# ---------- i18n ----------
T = {
    'ru': dict(days='Дни', topics='Темы', map='Карта', repeat='Повторить поездку', other='EN', other_lang='en',
               day='День', more_photos='Ещё фото дня', spent='Потратили', steps='Шаги', steps_soon='скрин с часов скоро',
               to_check='уточняем', per={'family': 'на троих', 'person': 'с человека', 'adult': 'за взрослого', 'child': '', 'night': 'за ночь'},
               free='бесплатно', link='Сайт', tip='Совет', prev='Назад', next='Дальше', by_day='По дням',
               by_topic='По темам', all_route='Весь маршрут', open_map='Открыть карту', moments_n='моментов',
               hidden='Фото с Машей появятся, когда её родители скажут «да».', video='видео', draft='Черновик',
               hotel='Где жили', cheat_title='Повторить поездку', cheat_lede='Всё на одной странице: где жили, куда ходили, сколько стоило и где покупать билеты.',
               total='Известные траты', what='Что', price='Цена', notes='Заметки', tips='Лайфхаки', home='Главная',
               months={11: 'ноября'}, weekday=['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'],
               photos_word='фото', footer='Сделано для своих. Ноябрь 2026.', show_all='Показать все', day0='В пути',
               map_lede='Все места поездки. Цвет точки — день, фильтры сверху.', nyc='Нью-Йорк', dc='Вашингтон', niagara='Ниагара', doha='Доха'),
    'en': dict(days='Days', topics='Topics', map='Map', repeat='Repeat the trip', other='RU', other_lang='ru',
               day='Day', more_photos='More photos from the day', spent='Spent', steps='Steps', steps_soon='watch screenshot coming',
               to_check='TBC', per={'family': 'for three', 'person': 'per person', 'adult': 'per adult', 'child': '', 'night': 'per night'},
               free='free', link='Website', tip='Tip', prev='Previous', next='Next', by_day='By day',
               by_topic='By topic', all_route='Whole route', open_map='Open the map', moments_n='moments',
               hidden="Photos with Masha will appear once her parents say yes.", video='video', draft='Draft',
               hotel='Where we stayed', cheat_title='Repeat the trip', cheat_lede='Everything on one page: where we stayed, where we went, what it cost and where to book.',
               total='Known spending', what='What', price='Price', notes='Notes', tips='Hacks', home='Home',
               months={11: 'November'}, weekday=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
               photos_word='photos', footer='Made for family. November 2026.', show_all='Show all', day0='On the way',
               map_lede='Every place from the trip. Dot colour is the day; filters on top.', nyc='New York', dc='Washington', niagara='Niagara', doha='Doha'),
}

def fmt_date(did, lang):
    d = dt.date.fromisoformat(did)
    if lang == 'ru':
        return f"{d.day} {T['ru']['months'][d.month]}, {T['ru']['weekday'][d.weekday()]}"
    return f"{T['en']['weekday'][d.weekday()]}, {d.day} {T['en']['months'][d.month]}"

def short_date(did, lang):
    d = dt.date.fromisoformat(did)
    return f"{d.day} {T[lang]['months'][d.month]}" if lang == 'ru' else f"{d.day} Nov"

def price_text(p, lang):
    if not p:
        return ''
    t = T[lang]
    note = (p.get('note') or {}).get(lang, '')
    if p.get('usd') is None:
        s = f"<span class=tbc>{t['to_check']}</span>"
    elif p['usd'] == 0:
        s = t['free']
        note = '' if note == t['free'] else note
    elif p['usd'] < 0:
        s = f"+${-p['usd']}"
    else:
        s = f"${p['usd']}"
        per = t['per'].get(p.get('per', ''), '')
        if per:
            s += ' ' + per
    return s + (f" <span class=note>· {html.escape(note)}</span>" if note else '')

env = Environment(loader=FileSystemLoader(os.path.join(HERE, 'templates')), autoescape=True,
                  trim_blocks=True, lstrip_blocks=True)
import hashlib
ASSET_V = hashlib.sha1(b''.join(open(os.path.join(HERE, 'static', f), 'rb').read() for f in sorted(os.listdir(os.path.join(HERE, 'static'))))).hexdigest()[:10]
env.globals.update(asset_v=ASSET_V, fmt_date=fmt_date, short_date=short_date, price_text=price_text,
                   topic_by_id=topic_by_id, day_by_id=day_by_id)

def paras(s):
    from markupsafe import Markup
    return Markup(''.join(f'<p>{html.escape(x.strip())}</p>' for x in (s or '').split('\n') if x.strip()))
env.filters['paras'] = paras

def write(rel, tpl, lang, **ctx):
    prefix = '' if lang == 'ru' else 'en/'
    path = os.path.join(OUT, prefix + rel)
    depth = (prefix + rel).count('/')
    root = '../' * depth
    other_root = root + ('en/' if lang == 'ru' else '')
    if lang == 'en':
        other_root = '../' * depth
    other_path = (other_root + rel).replace('index.html', '') or './'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    html_out = env.get_template(tpl).render(lang=lang, t=T[lang], root=root, home=root + ('' if lang == 'ru' else 'en/'),
                                            other_href=other_path, site=C['site'], days=days, topics=topics, **ctx)
    open(path, 'w', encoding='utf-8').write(html_out)

def moment_json(lang, base):
    out = []
    for d in days:
        for mo in d['moments']:
            pl = mo.get('place') or {}
            if not pl.get('lat'):
                continue
            th = next((m['thumb'] for m in mo['media'] if m['type'] == 'photo'), None)
            out.append(dict(id=mo['id'], day=d['id'], n=d['n'], color=d['color'], lat=pl['lat'], lon=pl['lon'],
                            title=mo['title'][lang], place=pl.get('name', ''), topics=mo.get('topics', []),
                            thumb=(base + 'media/' + th) if th else None,
                            href=f"{base}{'' if lang == 'ru' else 'en/'}day/{d['id']}/#{mo['id']}"))
    return out

# ---------- build ----------
if os.path.exists(os.path.join(OUT, 'assets')):
    shutil.rmtree(os.path.join(OUT, 'assets'))
shutil.copytree(os.path.join(HERE, 'static'), os.path.join(OUT, 'assets'))

# media: copy only what is referenced
os.makedirs(os.path.join(OUT, 'media'), exist_ok=True)
refs = set()
for d in days:
    for m in d['media']:
        for k in ('full', 'thumb', 'video', 'loop', 'loop_poster'):
            if m.get(k):
                refs.add(m[k])
    if d.get('reel'):
        refs.update(x for x in (d['reel'].get('file'), d['reel'].get('poster')) if x)
for m in details_media + [x for v in topic_media.values() for x in v] + [x for mo in moments for x in mo['media']]:
    for k in ('full', 'thumb', 'video', 'loop', 'loop_poster'):
        if m.get(k):
            refs.add(m[k])
for mo in moments:
    if mo.get('image'):
        refs.add(mo['image'])
notes = C.get('notes') or []
for nt in notes:
    if nt.get('photo'):
        refs.add(nt['photo'])
for r in refs:
    src = os.path.join(MEDIA, r) if r.startswith('edited/') else os.path.join(MEDIA, 'web', r)
    dst = os.path.join(OUT, 'media', r)
    if os.path.exists(src) and (not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src)):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

# prune media no longer referenced (cut / hidden files must not stay public)
for dp, _, fs in os.walk(os.path.join(OUT, 'media')):
    for f in fs:
        rel = os.path.relpath(os.path.join(dp, f), os.path.join(OUT, 'media'))
        if rel not in refs:
            os.remove(os.path.join(dp, f))

for lang in ('ru', 'en'):
    write('index.html', 'home.html', lang)
    for i, d in enumerate(days):
        write(f"day/{d['id']}/index.html", 'day.html', lang, d=d,
              prev=days[i - 1] if i else None, next=days[i + 1] if i + 1 < len(days) else None)
    for tp in topics:
        items = [(d, mo) for d in days for mo in d['moments'] if tp['id'] in mo.get('topics', [])]
        tp['count'] = len(items)
        write(f"topic/{tp['id']}/index.html", 'topic.html', lang, tp=tp, items=items,
              notes=[nt for nt in notes if tp['id'] in (nt.get('topics') or [])],
              extra_media=sorted([m for m in topic_media.get(tp['id'], [])
                                  if not ({m.get('full'), m.get('thumb'), m.get('loop')} & {nt.get('photo') for nt in notes if tp['id'] in (nt.get('topics') or [])})],
                                 key=lambda m: m['t']))
    write('map/index.html', 'map.html', lang, hotel=C['hotel'], points=moment_json(lang, '../' * (1 if lang == 'ru' else 2)))
    write('repeat/index.html', 'repeat.html', lang, hotel=C['hotel'],
          tips=[(d, mo) for d in days for mo in d['moments'] if mo.get('tip')],
          total=sum(d['cost'] for d in days))
open(os.path.join(OUT, '.nojekyll'), 'w').close()
n_media = sum(len(d['media']) for d in days)
print(f"built {OUT}: {len(days)} days, {len(moments)} moments, {n_media} media, {len(refs)} files")
