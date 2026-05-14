const STORAGE_KEYS = {
  allowedTabIds: "irisAllowedTabIds",
  port: "irisExtensionPort",
  token: "irisExtensionToken",
};

function log(msg) {
  document.getElementById("out").textContent = msg;
}

async function init() {
  const data = await chrome.storage.local.get([
    STORAGE_KEYS.allowedTabIds,
    STORAGE_KEYS.port,
    STORAGE_KEYS.token,
  ]);
  document.getElementById("port").value = data[STORAGE_KEYS.port] || 17777;
  document.getElementById("token").value = data[STORAGE_KEYS.token] || "";
  const allowed = new Set(data[STORAGE_KEYS.allowedTabIds] || []);
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  log(
    tab
      ? `현재 탭 id=${tab.id} 허용=${allowed.has(tab.id)}`
      : "탭 정보 없음"
  );
}

document.getElementById("allow").onclick = async () => {
  const port = parseInt(document.getElementById("port").value || "17777", 10);
  const token = document.getElementById("token").value || "";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  const data = await chrome.storage.local.get(STORAGE_KEYS.allowedTabIds);
  const set = new Set(data[STORAGE_KEYS.allowedTabIds] || []);
  set.add(tab.id);
  await chrome.storage.local.set({
    [STORAGE_KEYS.allowedTabIds]: Array.from(set),
    [STORAGE_KEYS.port]: port,
    [STORAGE_KEYS.token]: token,
  });
  log(`허용됨: tab ${tab.id}`);
};

document.getElementById("revoke").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  const data = await chrome.storage.local.get(STORAGE_KEYS.allowedTabIds);
  const set = new Set(data[STORAGE_KEYS.allowedTabIds] || []);
  set.delete(tab.id);
  await chrome.storage.local.set({
    [STORAGE_KEYS.allowedTabIds]: Array.from(set),
  });
  log(`제거됨: tab ${tab.id}`);
};

init();
