// Lightbox, "show all" buttons, maps.
(function () {
  document.querySelectorAll('.showall').forEach(function (b) {
    b.addEventListener('click', function () { b.previousElementSibling.classList.add('open'); b.remove(); });
  });
  var lb = document.getElementById('lb'); if (!lb) return;
  var box = lb.querySelector('.lb-media'), cap = lb.querySelector('figcaption'), list = [], i = 0;
  function show() {
    var a = list[i]; box.innerHTML = '';
    var v = a.getAttribute('data-video'), el;
    if (v) { el = document.createElement('video'); el.src = v; el.controls = true; el.autoplay = true; el.playsInline = true; el.poster = a.getAttribute('data-full'); }
    else { el = document.createElement('img'); el.src = a.getAttribute('data-full'); el.alt = ''; }
    box.appendChild(el); cap.textContent = (a.getAttribute('data-cap') || '') + '  ·  ' + (i + 1) + ' / ' + list.length;
  }
  function open(a) {
    var g = a.closest('.grid'); list = g ? Array.prototype.slice.call(g.querySelectorAll('a.tile')) : [a];
    i = list.indexOf(a); lb.hidden = false; document.body.style.overflow = 'hidden'; show();
  }
  function close() { lb.hidden = true; box.innerHTML = ''; document.body.style.overflow = ''; }
  function step(d) { i = (i + d + list.length) % list.length; show(); }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a.tile, a.card-img'); if (!a) return;
    if (a.classList.contains('vid') && !a.getAttribute('data-video')) { e.preventDefault(); open(a); return; }
    e.preventDefault(); open(a);
  });
  lb.querySelector('.lb-x').onclick = close;
  lb.querySelector('.lb-prev').onclick = function () { step(-1); };
  lb.querySelector('.lb-next').onclick = function () { step(1); };
  lb.addEventListener('click', function (e) { if (e.target === lb) close(); });
  document.addEventListener('keydown', function (e) {
    if (lb.hidden) return;
    if (e.key === 'Escape') close(); if (e.key === 'ArrowLeft') step(-1); if (e.key === 'ArrowRight') step(1);
  });
  var x0 = null;
  lb.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  lb.addEventListener('touchend', function (e) { if (x0 === null) return; var dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 50) step(dx < 0 ? 1 : -1); x0 = null; });
})();

var TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
var ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

function pinIcon(color, label, cls) {
  return L.divIcon({ className: '', iconSize: [26, 26], iconAnchor: [13, 13],
    html: '<div class="pin ' + (cls || '') + '" style="--c:' + color + '">' + label + '</div>' });
}

function miniMap(places, ids, color) {
  var el = document.getElementById('minimap'); if (!el || !window.L || !places.length) { if (el) el.style.display = 'none'; return; }
  var map = L.map(el, { scrollWheelZoom: false, zoomControl: false });
  L.tileLayer(TILES, { maxZoom: 19 }).addTo(map);
  var pts = [];
  places.forEach(function (p, k) {
    if (!p.lat) return; pts.push([p.lat, p.lon]);
    L.marker([p.lat, p.lon], { icon: pinIcon(color, k + 1) }).addTo(map).bindTooltip(p.name)
      .on('click', function () { location.hash = ids[k]; });
  });
  if (pts.length > 1) L.polyline(pts, { color: color, weight: 2, opacity: .6, dashArray: '4 6' }).addTo(map);
  map.fitBounds(pts, { padding: [24, 24], maxZoom: 14 });
}

function bigMap(points, hotel) {
  var map = L.map('bigmap', { zoomControl: true });
  L.tileLayer(TILES, { maxZoom: 19, attribution: ATTR }).addTo(map);
  var layer = L.layerGroup().addTo(map);
  if (hotel) L.marker([hotel.lat, hotel.lon], { icon: pinIcon('#1d1b18', '★', 'hotelpin'), zIndexOffset: 1000 })
    .addTo(map).bindPopup('<div class="pop"><b>' + hotel.name + '</b><small>' + hotel.address + '</small></div>');
  var days = {}, topic = null;
  document.querySelectorAll('#fdays .chip').forEach(function (c) { days[c.dataset.day] = true; });
  function draw() {
    layer.clearLayers();
    points.forEach(function (p) {
      if (!days[p.day]) return; if (topic && p.topics.indexOf(topic) < 0) return;
      var html = '<a class="poplink" href="' + p.href + '"><div class="pop">' + (p.thumb ? '<img src="' + p.thumb + '" alt="">' : '') +
        '<b>' + p.title + '</b><small>' + p.place + '</small></div></a>';
      L.marker([p.lat, p.lon], { icon: pinIcon(p.color, p.n) }).addTo(layer).bindPopup(html);
    });
  }
  var R = { nyc: [[40.64, -74.06], [40.80, -73.94]], dc: [[38.87, -77.08], [38.905, -77.0]], niagara: [[43.07, -79.09], [43.095, -79.05]], all: [[24, 33], [44, -80]] };
  function region(r) {
    document.querySelectorAll('.regions button').forEach(function (b) { b.classList.toggle('on', b.dataset.r === r); });
    if (r === 'all') { var b = L.latLngBounds(points.map(function (p) { return [p.lat, p.lon]; })); map.fitBounds(b, { padding: [30, 30] }); }
    else map.fitBounds(R[r]);
  }
  document.querySelectorAll('.regions button').forEach(function (b) { b.onclick = function () { region(b.dataset.r); }; });
  document.querySelectorAll('#fdays .chip').forEach(function (c) {
    c.onclick = function () { days[c.dataset.day] = !days[c.dataset.day]; c.classList.toggle('on', days[c.dataset.day]); draw(); };
  });
  document.querySelectorAll('#ftopics .chip').forEach(function (c) {
    c.onclick = function () {
      topic = topic === c.dataset.topic ? null : c.dataset.topic;
      document.querySelectorAll('#ftopics .chip').forEach(function (o) { o.classList.toggle('on', o.dataset.topic === topic); });
      draw();
    };
  });
  draw(); region('nyc');
}
