// ---- Clock ----
function updateClock() {
  var now = new Date();
  var hh = String(now.getHours()).padStart(2, '0');
  var mm = String(now.getMinutes()).padStart(2, '0');
  document.getElementById('clock-time').textContent = hh + ':' + mm;
  document.getElementById('clock-date').textContent = now.toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });
}
updateClock();
setInterval(updateClock, 1000 * 15);

// ---- Search ----
document.getElementById('search-form').addEventListener('submit', function (e) {
  e.preventDefault();
  var q = document.getElementById('search-input').value.trim();
  if (q) location.href = 'https://search.brave.com/search?q=' + encodeURIComponent(q);
});

// ---- Weather (Open-Meteo, fixed to Ho Chi Minh City) ----
var WEATHER_CODES = {
  0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
  45: 'Fog', 48: 'Fog', 51: 'Light drizzle', 53: 'Drizzle', 55: 'Dense drizzle',
  61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 71: 'Light snow', 73: 'Snow',
  75: 'Heavy snow', 80: 'Rain showers', 81: 'Rain showers', 82: 'Violent showers',
  95: 'Thunderstorm', 96: 'Thunderstorm', 99: 'Thunderstorm'
};
fetch('https://api.open-meteo.com/v1/forecast?latitude=10.78&longitude=106.70&current_weather=true')
  .then(function (r) { return r.json(); })
  .then(function (data) {
    var w = data.current_weather;
    var desc = WEATHER_CODES[w.weathercode] || 'Weather';
    document.getElementById('weather').innerHTML =
      '<div><div id="weather-temp">' + Math.round(w.temperature) + '°C</div>' +
      '<div id="weather-place">Ho Chi Minh City</div></div>' +
      '<div id="weather-desc">' + desc + '</div>';
  })
  .catch(function () {
    document.getElementById('weather').innerHTML = '<span class="error">Weather unavailable</span>';
  });

// ---- Watched repos (GitHub public API) ----
var REPOS = ['glanceapp/glance', 'brave/brave-browser', 'anthropics/claude-code'];
Promise.all(REPOS.map(function (r) {
  return fetch('https://api.github.com/repos/' + r).then(function (res) { return res.json(); });
})).then(function (results) {
  var html = results.map(function (repo) {
    if (!repo || repo.message) return '';
    return '<div class="repo-row">' +
      '<div><a class="repo-name" href="' + repo.html_url + '" target="_blank" rel="noopener">' + repo.full_name + '</a>' +
      '<div class="repo-desc">' + (repo.description || '') + '</div></div>' +
      '<div class="repo-stats"><span>★ ' + repo.stargazers_count.toLocaleString() + '</span>' +
      '<span>⚑ ' + repo.open_issues_count.toLocaleString() + '</span></div>' +
      '</div>';
  }).join('');
  document.getElementById('repos').innerHTML = html || '<span class="error">No data</span>';
}).catch(function () {
  document.getElementById('repos').innerHTML = '<span class="error">GitHub data unavailable</span>';
});

// ---- Hacker News front page (Algolia API) ----
fetch('https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=10')
  .then(function (r) { return r.json(); })
  .then(function (data) {
    var html = data.hits.map(function (hit, i) {
      var url = hit.url || ('https://news.ycombinator.com/item?id=' + hit.objectID);
      return '<li><span class="hn-rank">' + (i + 1) + '.</span>' +
        '<a href="' + url + '" target="_blank" rel="noopener">' + hit.title + '</a>' +
        '<span class="hn-points">' + (hit.points || 0) + 'pt</span></li>';
    }).join('');
    document.getElementById('hn').innerHTML = html;
  })
  .catch(function () {
    document.getElementById('hn').innerHTML = '<li class="error">Hacker News unavailable</li>';
  });

// ---- VOZ (RSS, per-tab cache + manual reload) ----
var VOZ_FEEDS = [
  { title: 'All', url: 'https://voz.vn/f/-/index.rss' },
  { title: 'Linh tinh', url: 'https://voz.vn/f/chuyen-tro-linh-tinh%E2%84%A2.17/index.rss' },
  { title: 'Điểm báo', url: 'https://voz.vn/f/diem-bao.33/index.rss' },
  { title: 'Lập trình', url: 'https://voz.vn/f/lap-trinh-cntt.91/index.rss' }
];
var VOZ_CACHE_MS = 5 * 60 * 1000;
var vozCache = {}; // index -> { items, fetchedAt }
var vozCurrent = 0;

function parseRSS(xmlText) {
  var doc = new DOMParser().parseFromString(xmlText, 'text/xml');
  return Array.from(doc.querySelectorAll('item')).slice(0, 20).map(function (item) {
    return {
      title: (item.querySelector('title') || {}).textContent || '(untitled)',
      link: (item.querySelector('link') || {}).textContent || '#'
    };
  });
}

function renderVozContent(items) {
  if (!items || items.length === 0) {
    document.getElementById('voz-content').innerHTML = '<li class="error">No items</li>';
    return;
  }
  document.getElementById('voz-content').innerHTML = items.map(function (item) {
    return '<li><a href="' + item.link + '" target="_blank" rel="noopener">' + item.title + '</a></li>';
  }).join('');
}

function setVozUpdatedLabel(timestamp) {
  document.getElementById('voz-updated').textContent =
    'Loaded ' + new Date(timestamp).toLocaleTimeString();
}

function loadVozTab(index, force) {
  vozCurrent = index;
  var cached = vozCache[index];
  var fresh = cached && !force && (Date.now() - cached.fetchedAt < VOZ_CACHE_MS);
  if (fresh) {
    renderVozContent(cached.items);
    setVozUpdatedLabel(cached.fetchedAt);
    return;
  }
  document.getElementById('voz-content').innerHTML = '<li><span class="loading">Loading...</span></li>';
  fetch(VOZ_FEEDS[index].url)
    .then(function (r) { return r.text(); })
    .then(function (xml) {
      var items = parseRSS(xml);
      var fetchedAt = Date.now();
      vozCache[index] = { items: items, fetchedAt: fetchedAt };
      if (vozCurrent === index) {
        renderVozContent(items);
        setVozUpdatedLabel(fetchedAt);
      }
    })
    .catch(function () {
      if (vozCurrent === index) {
        document.getElementById('voz-content').innerHTML = '<li class="error">VOZ feed unavailable</li>';
        document.getElementById('voz-updated').textContent = '';
      }
    });
}

function renderVozTabs() {
  var tabsEl = document.getElementById('voz-tabs');
  tabsEl.innerHTML = VOZ_FEEDS.map(function (feed, i) {
    return '<button class="tab-btn' + (i === 0 ? ' active' : '') + '" data-index="' + i + '">' + feed.title + '</button>';
  }).join('');
  Array.from(tabsEl.children).forEach(function (btn) {
    btn.addEventListener('click', function () {
      var index = Number(btn.dataset.index);
      if (index === vozCurrent) return;
      Array.from(tabsEl.children).forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      loadVozTab(index, false);
    });
  });
}

document.getElementById('voz-reload').addEventListener('click', function () {
  var btn = document.getElementById('voz-reload');
  btn.disabled = true;
  btn.classList.add('spinning');
  Promise.resolve(loadVozTab(vozCurrent, true)).finally(function () {
    // loadVozTab's fetch isn't awaited above (fire-and-forget), so just
    // give the spin a moment then release the button.
    setTimeout(function () {
      btn.disabled = false;
      btn.classList.remove('spinning');
    }, 500);
  });
});

renderVozTabs();
loadVozTab(0, false);

// ---- Auto-refresh ----
// None of these sources expose a push/SSE endpoint (VOZ's RSS, GitHub's
// REST API, and HN's Algolia API are all pull-only), so there's no true
// streaming option here. Closest equivalent: poll quietly in the
// background on an interval, and immediately refresh anything stale
// when the new tab regains focus (covers "I left this tab open for an
// hour" without polling while nobody's looking).
var AUTO_REFRESH_MS = 5 * 60 * 1000;

function refreshAll(force) {
  loadVozTab(vozCurrent, force);
  fetch('https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=10')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var html = data.hits.map(function (hit, i) {
        var url = hit.url || ('https://news.ycombinator.com/item?id=' + hit.objectID);
        return '<li><span class="hn-rank">' + (i + 1) + '.</span>' +
          '<a href="' + url + '" target="_blank" rel="noopener">' + hit.title + '</a>' +
          '<span class="hn-points">' + (hit.points || 0) + 'pt</span></li>';
      }).join('');
      document.getElementById('hn').innerHTML = html;
    })
    .catch(function () {});
}

setInterval(function () { refreshAll(false); }, AUTO_REFRESH_MS);

var lastVisibleRefresh = Date.now();
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState !== 'visible') return;
  if (Date.now() - lastVisibleRefresh < AUTO_REFRESH_MS) return;
  lastVisibleRefresh = Date.now();
  refreshAll(false);
});
