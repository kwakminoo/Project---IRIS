/**
 * URL(출처) 기준 허용 — 탭 ID와 무관.
 * background·popup·content 공용. 새 사이트는 SITE_RULES에 항목만 추가.
 */

const IRIS_STORAGE = {
  allowedUrlRules: "irisAllowedUrlRules",
  port: "irisExtensionPort",
  token: "irisExtensionToken",
  /** @deprecated 탭 ID 방식 */
  allowedTabIds: "irisAllowedTabIds",
};

const SENSITIVE_URL =
  /checkout|payment|billing|password|signin|login|auth\/|oauth|wallet|card/i;

/** @type {Record<string, { id: string, label: string, match: (url: string) => boolean }>} */
const SITE_RULES = {
  youtube_site: {
    id: "youtube_site",
    label: "YouTube (*.youtube.com)",
    match: isYoutubeUrl,
  },
  netflix_site: {
    id: "netflix_site",
    label: "Netflix (*.netflix.com)",
    match: isNetflixUrl,
  },
  google_site: {
    id: "google_site",
    label: "Google (google.com / google.co.kr)",
    match: isGoogleSiteUrl,
  },
  naver_site: {
    id: "naver_site",
    label: "Naver (*.naver.com)",
    match: isNaverUrl,
  },
};

const SITE_RULE_ORDER = [
  "youtube_site",
  "netflix_site",
  "google_site",
  "naver_site",
];

function hostnameOf(url) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function hostMatchesSuffix(hostname, suffix) {
  const h = (hostname || "").toLowerCase();
  const s = suffix.toLowerCase();
  return h === s || h.endsWith("." + s);
}

function isYoutubeUrl(url) {
  return hostMatchesSuffix(hostnameOf(url), "youtube.com");
}

function isNetflixUrl(url) {
  return hostMatchesSuffix(hostnameOf(url), "netflix.com");
}

function isGoogleSiteUrl(url) {
  const h = hostnameOf(url);
  if (!h) return false;
  const ok =
    h === "google.com" ||
    h === "www.google.com" ||
    h === "google.co.kr" ||
    h === "www.google.co.kr";
  return ok;
}

function isNaverUrl(url) {
  return hostMatchesSuffix(hostnameOf(url), "naver.com");
}

function isSensitiveUrl(url) {
  if (!url) return true;
  return SENSITIVE_URL.test(url);
}

function isUrlAllowedByRules(url, rules) {
  if (!url || isSensitiveUrl(url)) return false;
  const set = new Set(rules || []);
  for (const ruleId of set) {
    const def = SITE_RULES[ruleId];
    if (def && def.match(url)) return true;
  }
  return false;
}

function listSiteRuleDefinitions() {
  return SITE_RULE_ORDER.map((id) => SITE_RULES[id]).filter(Boolean);
}

function migrateLegacyTabIdsToRules(existingRules, allowedTabIds) {
  let rules = Array.isArray(existingRules) ? [...existingRules] : [];
  if (
    rules.length === 0 &&
    Array.isArray(allowedTabIds) &&
    allowedTabIds.length > 0
  ) {
    if (!rules.includes("youtube_site")) rules.push("youtube_site");
  }
  return rules;
}

// content script / non-module scripts
if (typeof globalThis !== "undefined") {
  globalThis.IRIS_STORAGE = IRIS_STORAGE;
  globalThis.SITE_RULES = SITE_RULES;
  globalThis.SITE_RULE_ORDER = SITE_RULE_ORDER;
  globalThis.isUrlAllowedByRules = isUrlAllowedByRules;
  globalThis.isSensitiveUrl = isSensitiveUrl;
  globalThis.isYoutubeUrl = isYoutubeUrl;
  globalThis.listSiteRuleDefinitions = listSiteRuleDefinitions;
  globalThis.migrateLegacyTabIdsToRules = migrateLegacyTabIdsToRules;
}
