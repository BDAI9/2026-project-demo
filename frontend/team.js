"use strict";

const byId = (id) => document.getElementById(id);
const interpretForm = byId("interpret-form");
const searchForm = byId("search-form");
const inputText = byId("condition-text");
const productMode = byId("product-mode");
const reviewPanel = byId("review-panel");
const confirmed = byId("confirmed");
let interpretationController = null;
let searchController = null;
let version = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clearResults(message = "조건을 확인한 후 결과가 나타납니다.") {
  byId("candidate-list").replaceChildren();
  byId("course-list").replaceChildren();
  byId("result-notices").replaceChildren();
  byId("attribution").hidden = true;
  byId("result-status").textContent = message;
}

function invalidateDraft() {
  version += 1;
  if (interpretationController) interpretationController.abort();
  if (searchController) searchController.abort();
  interpretationController = null;
  searchController = null;
  byId("interpret-button").disabled = false;
  byId("search-button").disabled = false;
  byId("interpret-status").textContent = "";
  confirmed.checked = false;
  reviewPanel.hidden = true;
  clearResults("입력이 바뀌었습니다. 조건 초안을 다시 확인해 주세요.");
}

interpretForm.addEventListener("input", invalidateDraft);
searchForm.addEventListener("input", (event) => {
  if (searchController) searchController.abort();
  searchController = null;
  version += 1;
  byId("search-button").disabled = false;
  // Changing any condition invalidates the previous approval and results.
  // Clicking the approval box itself must not immediately undo that click.
  if (event.target !== confirmed && event.target !== byId("limit-confirmed")) {
    confirmed.checked = false;
    byId("limit-confirmed").checked = false;
  }
  clearResults("조건을 수정했습니다. 원문과 비교한 뒤 다시 확인해 주세요.");
});

function listValue(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string").join(", ") : "";
}

function showProposal(proposal, raw) {
  byId("original-text").textContent = raw;
  byId("region").value = typeof proposal.region === "string" ? proposal.region : "";
  byId("party-size").value = Number.isInteger(proposal.people) && proposal.people >= 1 && proposal.people <= 30 ? String(proposal.people) : "";
  byId("exclusions").value = listValue(proposal.exclusions);
  byId("preferences").value = listValue(proposal.preferences);
  // Atmosphere is suggested text, not silently treated as a hard condition.
  byId("required-tags").value = "";
  byId("budget").value = "";
  byId("max-distance").value = "";
  byId("date-fields").hidden = productMode.value !== "date";
  byId("order").required = productMode.value === "date";
  const course = Array.isArray(proposal.course) ? proposal.course.map((x) => x && x.place_type) : [];
  const category = { "카페": "cafe", "식당": "restaurant", "술집": "bar" };
  const exactOrder = course.length === 2 && course.every((name) => Object.hasOwn(category, name)) && course[0] !== course[1];
  byId("order").value = exactOrder ? course.map((name) => category[name]).join(",") : "";
  confirmed.checked = false;
  const scoped = Array.isArray(proposal.course) ? proposal.course.filter((step) => step && Array.isArray(step.preferences) && step.preferences.length) : [];
  const needsLimits = productMode.value === "date" && ((course.length > 0 && !exactOrder) || scoped.length > 0);
  byId("limit-confirmation").hidden = !needsLimits;
  byId("limit-confirmed").required = needsLimits;
  byId("limit-confirmed").checked = false;
  const notices = byId("proposal-notices");
  notices.replaceChildren();
  if (productMode.value === "date" && course.length && !exactOrder) {
    notices.append(element("p", "notice", `초안의 코스: ${course.join(" → ")}. 현재 시범 검색은 카페·식당·술집 중 서로 다른 두 곳만 지원합니다. 이 코스는 그대로 검색할 수 없으므로 순서를 직접 선택해 주세요.`));
  }
  scoped.forEach((step) => notices.append(element("p", "notice", `${step.place_type || "장소"}에 대한 선호: ${step.preferences.join(", ")}. 이 시범 검색은 장소별 범위를 구분하지 않으므로 원문과 아래 조건을 직접 확인해 주세요.`)));
  if (Array.isArray(proposal.atmosphere) && proposal.atmosphere.length) {
    notices.append(element("p", "notice", `추출한 분위기: ${proposal.atmosphere.join(", ")}. 필수라면 아래 필드에 직접 입력하세요.`));
  }
  const questions = Array.isArray(proposal.clarifications) ? proposal.clarifications : [];
  questions.forEach((item) => {
    if (item && typeof item.question === "string") notices.append(element("p", "notice", `확인: ${item.question}`));
  });
  const assumptions = Array.isArray(proposal.assumptions) ? proposal.assumptions : [];
  assumptions.forEach((item) => {
    if (item && typeof item.reason === "string") notices.append(element("p", "notice", `가정: ${item.reason}`));
  });
  const warnings = Array.isArray(proposal.warnings) ? proposal.warnings : [];
  warnings.forEach((warning) => { if (typeof warning === "string") notices.append(element("p", "notice", warning)); });
  reviewPanel.hidden = false;
}

interpretForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!interpretForm.reportValidity()) return;
  const text = inputText.value.trim();
  if (!text) { byId("interpret-status").textContent = "조건을 입력해 주세요."; return; }
  if (interpretationController) interpretationController.abort();
  if (searchController) searchController.abort();
  const current = ++version;
  interpretationController = new AbortController();
  byId("interpret-button").disabled = true;
  byId("interpret-status").textContent = "조건 초안을 만들고 있습니다…";
  reviewPanel.hidden = true;
  confirmed.checked = false;
  clearResults();
  try {
    const response = await fetch("/api/interpret", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, product_mode: productMode.value }), signal: interpretationController.signal });
    const data = await response.json();
    if (current !== version) return;
    if (!response.ok || data.status !== "ok" || !data.proposal || typeof data.proposal !== "object") {
      byId("interpret-status").textContent = data.message || "조건 초안을 만들지 못했습니다.";
      return;
    }
    byId("interpret-status").textContent = "원문과 초안을 비교하고 필요한 값을 수정해 주세요.";
    showProposal(data.proposal, text);
  } catch (error) {
    if (current === version && error.name !== "AbortError") byId("interpret-status").textContent = "조건을 해석하지 못했습니다. 연결 상태를 확인해 주세요.";
  } finally {
    if (current === version) { interpretationController = null; byId("interpret-button").disabled = false; }
  }
});

function safeLink(url) {
  if (typeof url !== "string" || /[\s\x00-\x1f]/.test(url)) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.host === "web.paybooc.ai" && /^\/mer\/web\/profile\/[^/?#]+$/.test(parsed.pathname) && !parsed.search && !parsed.hash && !parsed.username && !parsed.password;
  } catch (_) { return false; }
}

function addPlaceLink(container, place, source) {
  if (source === "skill-test" && safeLink(place.eatpl_url)) {
    const link = element("a", "", "잇플 상세 보기 ↗");
    link.href = place.eatpl_url;
    link.target = "_blank";
    link.rel = "noopener";
    container.append(link);
  }
}

const STATUS_LABEL = { pass: "확인된 조건 충족", needs_verification: "확인 필요", reject: "조건 불충족" };
function badge(status) {
  const style = status === "pass" ? "badge" : status === "reject" ? "badge reject" : "badge review";
  return element("span", style, STATUS_LABEL[status] || "확인 필요");
}

function addReasons(card, reasons) {
  if (Array.isArray(reasons) && reasons.length) {
    const list = element("ul", "hint");
    reasons.filter((reason) => typeof reason === "string").forEach((reason) => list.append(element("li", "", reason)));
    if (list.childNodes.length) card.append(list);
  }
}

function renderResult(data) {
  const notes = byId("result-notices");
  const source = data.source;
  notes.append(element("p", "notice", source === "sample" ? "샘플 데이터 · 모든 장소는 가상입니다." : "k-skill 개인 단발 테스트 · 팀 서비스 이용 조건 확인 필요"));
  if (source === "skill-test") notes.append(element("p", "hint", data.cache_hit === true ? "프록시 캐시 응답입니다." : data.cache_hit === false ? "프록시 캐시 미사용 응답입니다." : "캐시 사용 여부 미확인"));
  if (data.truncated) notes.append(element("p", "notice", "최대 조회 건수에 도달해 결과가 일부일 수 있습니다. 지역을 더 좁혀 보세요."));
  const attribution = byId("attribution");
  attribution.hidden = false;
  attribution.textContent = source === "sample" ? "샘플 가격, 장소 및 좌표는 가상의 정보입니다." : "eat.pl 잇플 · BC카드 결제 데이터 기반";
  if (Array.isArray(data.candidates) && data.candidates.length) {
    const list = byId("candidate-list");
    list.append(element("h3", "", "장소 후보"));
    data.candidates.forEach((place) => {
      const card = element("article", "card");
      card.append(badge(place.status), element("h3", "", place.name || "이름 미확인"), element("p", "", place.address || "주소 정보 없음"));
      card.append(element("p", "", place.price_per_person_krw == null ? "1인 가격 정보 없음" : `1인 ${Number(place.price_per_person_krw).toLocaleString("ko-KR")}원`));
      addReasons(card, place.reasons);
      addPlaceLink(card, place, source);
      list.append(card);
    });
  }
  if (Array.isArray(data.courses) && data.courses.length) {
    const list = byId("course-list");
    list.append(element("h3", "", "추천 코스"));
    data.courses.forEach((course) => {
      const card = element("article", "card");
      card.append(badge(course.status));
      const stops = element("ol", "");
      (Array.isArray(course.places) ? course.places : []).forEach((place) => {
        const stop = element("li", "");
        stop.append(element("strong", "", place.name || "이름 미확인"), element("p", "", place.address || "주소 정보 없음"));
        addPlaceLink(stop, place, source);
        stops.append(stop);
      });
      card.append(stops, element("p", "", course.distance_m == null ? "거리 정보 없음" : `장소 간 직선거리 ${Math.round(Number(course.distance_m)).toLocaleString("ko-KR")}m`));
      addReasons(card, course.reasons);
      list.append(card);
    });
  }
}

const csv = (value) => [...new Set(value.split(",").map((x) => x.trim()).filter(Boolean))];
searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!searchForm.reportValidity() || !confirmed.checked) return;
  const region = byId("region").value.trim();
  if (!region) { byId("result-status").textContent = "지역을 입력해 주세요."; return; }
  const budget = byId("budget").value;
  const distance = byId("max-distance").value;
  const input = {
    product_mode: productMode.value,
    source: byId("source").value,
    region,
    party_size: Number(byId("party-size").value),
    excluded_terms: csv(byId("exclusions").value),
    preferred_cuisines: csv(byId("preferences").value),
    required_tags: csv(byId("required-tags").value),
    category_order: productMode.value === "date" ? byId("order").value.split(",") : [],
    max_budget_per_person: budget === "" ? null : Number(budget),
    max_leg_distance_m: productMode.value === "date" && distance !== "" ? Number(distance) : null,
    confirmed: true,
  };
  if (searchController) searchController.abort();
  const current = ++version;
  searchController = new AbortController();
  byId("search-button").disabled = true;
  clearResults("조건을 반영해 장소를 찾고 있습니다…");
  try {
    const response = await fetch("/api/team-search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input), signal: searchController.signal });
    const data = await response.json();
    if (current !== version) return;
    if (!response.ok || data.status === "error") {
      byId("result-status").textContent = data.message || "조회하지 못했습니다. 다시 시도해 주세요.";
      return;
    }
    byId("result-status").textContent = data.message || (data.status === "empty" ? "조회한 후보 중 조건에 맞는 결과가 없습니다." : "조회 결과를 확인해 주세요.");
    renderResult(data);
  } catch (error) {
    if (current === version && error.name !== "AbortError") byId("result-status").textContent = "조회하지 못했습니다. 연결 상태를 확인해 주세요.";
  } finally {
    if (current === version) { searchController = null; byId("search-button").disabled = false; }
  }
});
