// 허용 목록에 있는 탭에서만 동작 (background 가 주기적으로 스크립트 실행)

chrome.storage.local.get(["irisAllowedTabIds"], (data) => {
  const allowed = new Set(data.irisAllowedTabIds || []);
  chrome.runtime.sendMessage({ type: "irisPing", allowed: allowed.has(0) });
});
