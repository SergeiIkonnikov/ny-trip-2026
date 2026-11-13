#!/usr/bin/env python3
"""Build the static NY trip site.
usage: python3 build.py [OUT_DIR]   (default: /mnt/project-files/ny-trip/site)
Reads content.yaml + ../media/web/manifest.json, writes RU at OUT/ and EN at OUT/en/.
"""
import os, sys, json, shutil, datetime as dt, html, re
import yaml
from jinja2 import Environment, FileSystemLoader

SITE_URL = 'https://sergeiikonnikov.github.io/ny-trip-2026/'
HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.normpath(os.path.join(HERE, '..', 'media'))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(os.path.join(HERE, '..', 'site'))

C = yaml.safe_load(open(os.path.join(HERE, 'content.yaml'), encoding='utf-8'))
manifest = json.load(open(os.path.join(MEDIA, 'web', 'manifest.json'), encoding='utf-8'))
# hi-res copies (tools/make_hi.py, tools/make_vhd.py): 2400px photos for srcset, 1080p videos
def _load(name):
    p = os.path.join(MEDIA, 'web', name)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
HI, VHD = _load('hi.json'), _load('vhd.json')
for _m in manifest:
    if _m.get('full') in HI:
        _m['hi'], _m['hw'], _m['hh'] = HI[_m['full']]
    if _m.get('video') in VHD:
        _m['video'] = VHD[_m['video']]
    if _m.get('w') and _m.get('h') and _m.get('thumb') and _m.get('full'):
        _m['tw'] = round(_m['w'] * 520 / max(_m['w'], _m['h']))  # make_web thumbs: 520px long side

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
                if c.get('full') is False:  # don't publish the full clip (e.g. Natasha's fall): lightbox plays the loop
                    m['video'] = c['loop']
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
        # a cropped variant (…-vN) replaces its original: hide the original from this day
        bases = {re.sub(r'-v\d+(\.\w+)$', r'\1', m['src']) for m in mo['media'] if re.search(r'-v\d+\.\w+$', m['src'])}
        for m in d['all_media']:
            if m['src'] in bases:
                m['used'] = True
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
    for m in d['all_media']:
        if m.get('nocap'):
            m['local'] = ''  # e.g. Health step mockups: no time caption
    d['extra'] = [m for m in d['media'] if not m['used']]
    photos = [m for m in d['media'] if m['type'] == 'photo' and m['w'] >= m['h'] and not m.get('blocked')]
    cov = d.get('cover')
    d['cover_media'] = next((m for m in d['all_media'] if cov and m['type'] == 'photo' and m['src'].startswith(cov)), None) or \
        (photos[len(photos) // 3] if photos else (d['media'][0] if d['media'] else None))
    hero = d.get('hero')  # day-page hero can differ from the home-card cover (Sergey, Nov 9)
    d['hero_media'] = next((m for m in d['all_media'] if hero and m['type'] == 'photo' and m['src'].startswith(hero)), None) or d['cover_media']

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
    if d.get('spent') is not None:  # real card spending for the day (Sergey, 2026-11-12) wins over moment prices
        d['cost'], d['cost_unknown'] = d['spent'], False

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
ASSET_V = hashlib.sha1(b''.join(open(os.path.join(HERE, 'static', f), 'rb').read() for f in ['style.css', 'app.js'] + sorted(x for x in os.listdir(os.path.join(HERE, 'static')) if x.startswith('cover-')) if os.path.isfile(os.path.join(HERE, 'static', f)))).hexdigest()[:10]
# Prices are hidden on the English site for now (Sergey, 2026-11-13). Add 'en' to show them again.
PRICE_LANGS = {'ru'}
env.globals.update(prices_on=lambda lang: lang in PRICE_LANGS)
env.globals.update(asset_v=ASSET_V, fmt_date=fmt_date, short_date=short_date, price_text=price_text,
                   topic_by_id=topic_by_id, day_by_id=day_by_id)

def thx_html(text):
    from markupsafe import Markup
    return Markup(f'<span class="thx">{html.escape(text)} <i>\u2764</i></span>') if text else ''

def paras(s, thx=None):
    # thx: {paragraph number (1-based): footnote text} -> span.thx right before that <p>
    from markupsafe import Markup
    ps = [x.strip() for x in (s or '').split('\n') if x.strip()]
    return Markup(''.join(str(thx_html((thx or {}).get(i)) or '') + f'<p>{html.escape(x)}</p>' for i, x in enumerate(ps, 1)))
env.globals['thx_html'] = thx_html
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
    page_url = SITE_URL + (prefix + rel).replace('index.html', '')
    html_out = env.get_template(tpl).render(lang=lang, t=T[lang], root=root, page_url=page_url, site_url=SITE_URL, home=root + ('' if lang == 'ru' else 'en/'),
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
_hist_p = os.path.join(MEDIA, 'web', 'hist', 'hist.json')
HIST = json.load(open(_hist_p, encoding='utf-8')) if os.path.exists(_hist_p) else {}
for nt in notes:  # historical photos (Wikimedia Commons) keyed by note id
    h = HIST.get(nt['id']) or HIST.get('note-' + nt['id'])
    if h:
        nt['hist'] = h
        refs.add(h['file'])
for nt in notes:
    if nt.get('photo'):
        refs.add(nt['photo'])
    for ph in nt.get('photos_more') or []:  # extra small photos under the main one
        refs.add(ph)
# ---------- topic covers (home page cards) ----------
by_path = {}
for d in days:
    for m in d['all_media']:
        for k in ('full', 'thumb'):
            if m.get(k):
                by_path[m[k]] = m
THANKS = C.get('thanks') or []
for th in THANKS:
    if th.get('media'):
        for d in days:
            for m in d['all_media']:
                if m['src'].startswith(th['media']):
                    m['thanks'] = th['text']
    elif th.get('note'):
        for nt in notes:
            if nt['id'] == th['note']:
                if th.get('photo'):
                    nt['thanks_photo'] = th['text']
                if th.get('para'):
                    nt.setdefault('thanks_para', {}).update({l: {th['para']: v} for l, v in th['text'].items()})
for nt in notes:  # a note whose photo is a loop item's thumb/full plays the loop
    lm = by_path.get(nt.get('photo'))
    if lm and lm.get('loop'):
        nt['loop'], nt['loop_poster'] = lm['loop'], lm.get('loop_poster') or lm.get('thumb')
        refs.update(x for x in (nt['loop'], nt['loop_poster']) if x)
taken = set()
for tp in topics:
    cands = []
    if tp.get('cover'):  # optional override in content.yaml: src prefix or media path
        cands += [m for m in by_path.values() if m['src'].startswith(str(tp['cover'])) or m.get('full') == tp['cover']]
    cands += [by_path[nt['photo']] for nt in notes if tp['id'] in (nt.get('topics') or []) and nt.get('photo') in by_path]
    cands += sorted(topic_media.get(tp['id'], []), key=lambda m: m['t'])
    cands += [m for d in days for mo in d['moments'] if tp['id'] in (mo.get('topics') or []) for m in mo['media']]
    cands = [m for m in cands if m.get('type') == 'photo' and m.get('thumb')]
    pick = next((m for m in cands if m['src'] not in taken), cands[0] if cands else None)
    if isinstance(tp.get('cover'), dict):
        pick = tp['cover']
    tp['cover_media'] = pick
    if pick:
        taken.add(pick['src'])
        refs.update(x for x in (pick.get('thumb'), pick.get('full')) if x)
for tp in topics:
    if tp.get('cover_media'):
        tp['cover'] = tp['cover_media']

for d in days:  # day covers / heroes may be photos that are cut from the day grid
    for cm in (d.get('cover_media'), d.get('hero_media')):
        if cm:
            refs.update(x for x in (cm.get('thumb'), cm.get('full')) if x)
refs |= {HI[r][0] for r in list(refs) if r in HI}  # hi-res copy next to every published full
for r in refs:
    src = os.path.join(MEDIA, r) if r.startswith('edited/') else os.path.join(MEDIA, 'web', r)
    dst = os.path.join(OUT, 'media', r)
    if os.path.exists(src) and (not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src)
                                     or int(os.path.getmtime(dst)) != int(os.path.getmtime(src))):
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
        # step mockups (manifest day 'steps') belong to the day page only, not to topic pages
        items = [(d, dict(mo, media=[m for m in mo['media'] if m.get('day') != 'steps'])) for d in days for mo in d['moments'] if tp['id'] in mo.get('topics', [])]
        tp['count'] = len(items)
        write(f"topic/{tp['id']}/index.html", 'topic.html', lang, tp=tp, items=items,
              notes=[nt for nt in notes if tp['id'] in (nt.get('topics') or [])],
              extra_media=sorted([m for m in topic_media.get(tp['id'], [])
                                  if not (({m.get('full'), m.get('thumb'), m.get('loop')} - {None}) & {nt.get('photo') for nt in notes if tp['id'] in (nt.get('topics') or [])})],
                                 key=lambda m: m['t']))
    write('map/index.html', 'map.html', lang, hotel=C['hotel'], points=moment_json(lang, '../' * (1 if lang == 'ru' else 2)))
    write('repeat/index.html', 'repeat.html', lang, hotel=C['hotel'], flight=C.get('flight'),
          tips=[(d, mo) for d in days for mo in d['moments'] if mo.get('tip')],
          total=sum(d['cost'] for d in days))
open(os.path.join(OUT, '.nojekyll'), 'w').close()
n_media = sum(len(d['media']) for d in days)
print(f"built {OUT}: {len(days)} days, {len(moments)} moments, {n_media} media, {len(refs)} files")
