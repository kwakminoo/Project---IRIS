// URL 규칙 상태 ping (실제 ingest는 background)

chrome.storage.local.get(
  [IRIS_STORAGE.allowedUrlRules, IRIS_STORAGE.allowedTabIds],
  (data) => {
    const rules = migrateLegacyTabIdsToRules(
      data[IRIS_STORAGE.allowedUrlRules],
      data[IRIS_STORAGE.allowedTabIds]
    );
    chrome.runtime.sendMessage({
      type: "irisPing",
      allowedUrlRules: rules,
    });
  }
);
