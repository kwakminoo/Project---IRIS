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

  const payload = {
    tabId,
    title: tab.title || "",
    url: tab.url,
    visibleText: result || "",
    timestamp: Date.now(),
  };
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

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("irisTick", { periodInMinutes: 1 });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("irisTick", { periodInMinutes: 1 });
});
