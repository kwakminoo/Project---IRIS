// MV3 — 허용 URL 규칙에 맞는 모든 Chrome 탭을 Iris 로컬 API로 전송
importScripts("url_rules.js");

async function loadConfig() {
  const data = await chrome.storage.local.get([
    IRIS_STORAGE.allowedUrlRules,
    IRIS_STORAGE.port,
    IRIS_STORAGE.token,
    IRIS_STORAGE.allowedTabIds,
  ]);
  let rules = migrateLegacyTabIdsToRules(
    data[IRIS_STORAGE.allowedUrlRules],
    data[IRIS_STORAGE.allowedTabIds]
  );
  if (
    Array.isArray(data[IRIS_STORAGE.allowedTabIds]) &&
    data[IRIS_STORAGE.allowedTabIds].length > 0 &&
    rules.length > 0
  ) {
    await chrome.storage.local.set({
      [IRIS_STORAGE.allowedUrlRules]: rules,
      [IRIS_STORAGE.allowedTabIds]: [],
    });
  }
  const port = data[IRIS_STORAGE.port] || 17777;
  const token = data[IRIS_STORAGE.token] || "";
  return { rules, port, token };
}

/** YouTube 검색 결과에서 watch 링크·제목만 수집 (최대 8). */
function extractYoutubeSearchResults() {
  const out = [];
  const seen = new Set();
  const selectors = [
    'a#video-title[href*="watch?v="]',
    'ytd-video-renderer a[href*="watch?v="]',
    'a.ytd-video-renderer[href*="watch?v="]',
  ];
  const blocked = /\/shorts\/|googleads|doubleclick|\/pagead/i;

  function pushCandidate(title, href) {
    const t = (title || "").trim().slice(0, 240);
    let url = (href || "").trim();
    if (!t || !url || blocked.test(url)) return;
    if (url.startsWith("/")) url = "https://www.youtube.com" + url;
    if (!url.includes("watch?v=")) return;
    if (seen.has(url)) return;
    seen.add(url);
    out.push({ title: t, url });
  }

  for (const sel of selectors) {
    document.querySelectorAll(sel).forEach((a) => {
      pushCandidate(
        a.textContent || a.innerText || a.getAttribute("title"),
        a.href || a.getAttribute("href")
      );
    });
    if (out.length >= 8) break;
  }
  return out.slice(0, 8);
}

function sleepMs(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** SPA 로딩 지연 흡수 — 빈 결과면 짧은 간격으로 재시도. */
async function fetchYoutubeSearchResultsWithRetry(tabId, tabUrl) {
  if (!isYoutubeUrl(tabUrl) || !/youtube\.com\/results/i.test(tabUrl)) {
    return [];
  }
  const delays = [0, 400, 1200];
  let last = [];
  for (const d of delays) {
    if (d > 0) await sleepMs(d);
    const run = await chrome.scripting
      .executeScript({
        target: { tabId },
        func: extractYoutubeSearchResults,
      })
      .catch(() => [{ result: [] }]);
    const yt = run[0]?.result;
    last = Array.isArray(yt) ? yt : [];
    if (last.length > 0) return last;
  }
  return last;
}

async function pushTab(tabId, rules) {
  const { port, token } = await loadConfig();
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.url || !isUrlAllowedByRules(tab.url, rules)) return;

  const [{ result }] = await chrome.scripting
    .executeScript({
      target: { tabId },
      func: () => {
        const t = document.body ? document.body.innerText : "";
        return (t || "").slice(0, 4000);
      },
    })
    .catch(() => [{ result: "" }]);

  let youtubeSearchResults = await fetchYoutubeSearchResultsWithRetry(
    tabId,
    tab.url
  );

  const payload = {
    tabId,
    title: tab.title || "",
    url: tab.url,
    visibleText: result || "",
    timestamp: Date.now(),
  };
  if (youtubeSearchResults.length > 0) {
    payload.youtubeSearchResults = youtubeSearchResults;
  }
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = "Bearer " + token;
  await fetch(`http://127.0.0.1:${port}/ingest`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  }).catch(() => {});
}

async function pushAllMatchingTabs() {
  const { rules } = await loadConfig();
  if (!rules.length) return;
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    if (tab.id != null && tab.url && isUrlAllowedByRules(tab.url, rules)) {
      await pushTab(tab.id, rules);
    }
  }
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "irisTick") return;
  await pushAllMatchingTabs();
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !tab?.url) return;
  const { rules } = await loadConfig();
  if (!isUrlAllowedByRules(tab.url, rules)) return;
  await pushTab(tabId, rules);
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("irisTick", { periodInMinutes: 1 });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("irisTick", { periodInMinutes: 1 });
});
