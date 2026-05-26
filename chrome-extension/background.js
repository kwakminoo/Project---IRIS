// MV3 — 허용된 탭만 주기적으로 Iris 로컬 API로 전송

const STORAGE_KEYS = {
  allowedTabIds: "irisAllowedTabIds",
  port: "irisExtensionPort",
  token: "irisExtensionToken",
};

async function loadConfig() {
  const data = await chrome.storage.local.get([
    STORAGE_KEYS.allowedTabIds,
    STORAGE_KEYS.port,
    STORAGE_KEYS.token,
  ]);
  const allowed = new Set(data[STORAGE_KEYS.allowedTabIds] || []);
  const port = data[STORAGE_KEYS.port] || 17777;
  const token = data[STORAGE_KEYS.token] || "";
  return { allowed, port, token };
}

function sensitiveUrl(url) {
  if (!url) return true;
  return /checkout|payment|billing|password|signin|login|auth\/|oauth|wallet|card/i.test(
    url
  );
}

/** YouTube 검색 결과에서 watch 링크·제목만 수집 (최대 8, Shorts·광고 제외). */
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
      pushCandidate(a.textContent || a.innerText || a.getAttribute("title"), a.href || a.getAttribute("href"));
    });
    if (out.length >= 8) break;
  }
  return out.slice(0, 8);
}

async function pushTab(tabId) {
  const { allowed, port, token } = await loadConfig();
  if (!allowed.has(tabId)) return;
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || !tab.url || sensitiveUrl(tab.url)) return;
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const t = document.body ? document.body.innerText : "";
      return (t || "").slice(0, 4000);
    },
  }).catch(() => [{ result: "" }]);

  let youtubeSearchResults = [];
  if (/youtube\.com\/results/i.test(tab.url)) {
    const [{ result: yt }] = await chrome.scripting
      .executeScript({
        target: { tabId },
        func: extractYoutubeSearchResults,
      })
      .catch(() => [{ result: [] }]);
    youtubeSearchResults = Array.isArray(yt) ? yt : [];
  }

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

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "irisTick") return;
  const { allowed } = await loadConfig();
  for (const id of allowed) {
    await pushTab(id);
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !tab?.url) return;
  if (!/youtube\.com\/results/i.test(tab.url)) return;
  const { allowed } = await loadConfig();
  if (!allowed.has(tabId)) return;
  await pushTab(tabId);
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("irisTick", { periodInMinutes: 1 });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("irisTick", { periodInMinutes: 1 });
});
