const DEFAULT_PORT = 17777;

function log(msg) {
  document.getElementById("out").textContent = msg;
}

function renderRuleCheckboxes(selectedRules) {
  const box = document.getElementById("rulesBox");
  box.innerHTML = "";
  const selected = new Set(selectedRules || []);
  for (const def of listSiteRuleDefinitions()) {
    const row = document.createElement("div");
    row.className = "rule-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = "rule_" + def.id;
    cb.checked = selected.has(def.id);
    cb.dataset.ruleId = def.id;
    const label = document.createElement("label");
    label.htmlFor = cb.id;
    label.textContent = def.label;
    row.appendChild(cb);
    row.appendChild(label);
    box.appendChild(row);
  }
}

function collectSelectedRules() {
  const out = [];
  document.querySelectorAll("#rulesBox input[type=checkbox]").forEach((el) => {
    if (el.checked && el.dataset.ruleId) out.push(el.dataset.ruleId);
  });
  return out;
}

async function loadStoredRules() {
  const data = await chrome.storage.local.get([
    IRIS_STORAGE.allowedUrlRules,
    IRIS_STORAGE.allowedTabIds,
  ]);
  return migrateLegacyTabIdsToRules(
    data[IRIS_STORAGE.allowedUrlRules],
    data[IRIS_STORAGE.allowedTabIds]
  );
}

async function init() {
  const data = await chrome.storage.local.get([
    IRIS_STORAGE.port,
    IRIS_STORAGE.token,
  ]);
  const port =
    typeof data[IRIS_STORAGE.port] === "number"
      ? data[IRIS_STORAGE.port]
      : DEFAULT_PORT;
  const token = data[IRIS_STORAGE.token] || "";
  document.getElementById("port").value = port;
  document.getElementById("token").value = token;
  if (data[IRIS_STORAGE.port] == null) {
    await chrome.storage.local.set({ [IRIS_STORAGE.port]: DEFAULT_PORT });
  }

  const rules = await loadStoredRules();
  renderRuleCheckboxes(rules);

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let tabLine = "";
  if (tab?.url) {
    const allowed = isUrlAllowedByRules(tab.url, rules);
    tabLine =
      `현재 탭 URL 허용=${allowed}\n` +
      (tab.url.length > 80 ? tab.url.slice(0, 80) + "…" : tab.url);
  }
  const enabled = rules.length
    ? rules.map((id) => SITE_RULES[id]?.label || id).join(", ")
    : "(없음)";
  log(`활성 규칙: ${enabled}\n포트=${port}\n${tabLine}`);
}

async function saveSettings() {
  const port = parseInt(document.getElementById("port").value || "17777", 10);
  const token = document.getElementById("token").value || "";
  const rules = collectSelectedRules();
  await chrome.storage.local.set({
    [IRIS_STORAGE.allowedUrlRules]: rules,
    [IRIS_STORAGE.port]: port,
    [IRIS_STORAGE.token]: token,
    [IRIS_STORAGE.allowedTabIds]: [],
  });
  log(
    rules.length
      ? `저장됨. 규칙 ${rules.length}개 — 모든 해당 URL 탭에서 전송합니다.`
      : "저장됨. 활성 규칙 없음 (Iris로 전송 안 함)."
  );
  await init();
}

document.getElementById("save").addEventListener("click", () => saveSettings());

init();
