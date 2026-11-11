"use strict";

const form = document.querySelector("#search-form");
const mode = document.querySelector("#mode");
const region = document.querySelector("#region");
const regionHint = document.querySelector("#region-hint");
const status = document.querySelector("#status");
const notices = document.querySelector("#notices");
const courses = document.querySelector("#courses");
const placeOptions = document.querySelector("#place-options");
const sourceNote = document.querySelector("#source-note");
const submit = document.querySelector("#submit");
let activeRequest = null;
let requestNumber = 0;

region.value = "가상 지역";
mode.addEventListener("change", () => {
  if (mode.value === "sample") {
    if (!region.value.trim()) region.value = "가상 지역";
    regionHint.textContent = "샘플 데이터는 ‘가상 지역’에서 볼 수 있습니다.";
  } else {
    if (region.value === "가상 지역") region.value = "";
    regionHint.textContent = "주소에 포함될 지역을 입력해 주세요. 반경 검색은 지원하지 않습니다.";
  }
});

// A previous response must not be displayed as if it matched edited inputs.
form.addEventListener("input", () => {
  if (activeRequest) activeRequest.abort();
  activeRequest = null;
  requestNumber++;
  submit.disabled = false;
  notices.replaceChildren();
  courses.replaceChildren();
  placeOptions.replaceChildren();
  sourceNote.hidden = true;
  status.hidden = false;
  status.textContent = "조건이 변경됐어요. 다시 검색해 주세요.";
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function safeLink(url) {
  if (typeof url !== "string" || /[\s\x00-\x1f]/.test(url)) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.host === "web.paybooc.ai" && /^\/mer\/web\/profile\/[^/?#]+$/.test(parsed.pathname) && !parsed.search && !parsed.hash && !parsed.username && !parsed.password;
  } catch (_) { return false; }
}

function showCourse(course, index, source) {
  const card = element("article", "course-card");
  const cardHeader = element("div", "card-header");
  cardHeader.append(element("span", "course-number", `COURSE ${String(index + 1).padStart(2, "0")}`));
  cardHeader.append(element("span", course.status === "needs_review" ? "badge review" : "badge", course.status === "needs_review" ? "조건 확인 필요" : "조건 충족"));
  card.append(cardHeader);
  const stops = element("ol", "stops");
  course.places.forEach((place, stopIndex) => {
    const li = element("li", "stop");
    li.append(element("span", "stop-number", String(stopIndex + 1)));
    const content = element("div", "stop-content");
    content.append(element("h3", "place-name", place.name));
    content.append(element("p", "place-address", place.address || "주소 정보 없음"));
    if ((source === "eatpl" || source === "skill-test") && safeLink(place.eatpl_url)) {
      const link = element("a", "place-link", "잇플 상세 보기 ↗");
      link.href = place.eatpl_url;
      link.target = "_blank";
      link.rel = "noopener";
      content.append(link);
    }
    li.append(content);
    stops.append(li);
  });
  card.append(stops);
  const metrics = element("div", "metrics");
  metrics.append(element("span", "metric", course.distance_m == null ? "거리 정보 없음" : `직선거리 ${Math.round(course.distance_m).toLocaleString("ko-KR")}m`));
  metrics.append(element("span", "metric", course.total_per_person_krw == null ? "1인 가격 정보 없음" : `1인 ${Math.round(course.total_per_person_krw).toLocaleString("ko-KR")}원`));
  card.append(metrics);
  if (Array.isArray(course.reasons) && course.reasons.length) {
    const reason = element("p", "reason", course.reasons.join(" · "));
    card.append(reason);
  }
  courses.append(card);
}

function showPlaceOptions(places, count) {
  if (!Array.isArray(places) || places.length === 0) return;
  placeOptions.append(element("h3", "", `조건 적용 전 조회된 장소 ${count}곳 (최대 10곳 표시)`));
  places.forEach((place) => {
    const card = element("article", "course-card");
    card.append(element("h3", "place-name", place.name));
    card.append(element("p", "place-address", place.address || "주소 정보 없음"));
    if (safeLink(place.eatpl_url)) {
      const link = element("a", "place-link", "잇플 상세 보기 ↗");
      link.href = place.eatpl_url;
      link.target = "_blank";
      link.rel = "noopener";
      card.append(link);
    }
    placeOptions.append(card);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const chosen = new FormData(form).get("order");
  const budgetValue = document.querySelector("#budget").value;
  const distanceValue = document.querySelector("#distance").value;
  const order = chosen === "restaurant-first" ? ["restaurant", "cafe"] : ["cafe", "restaurant"];
  const constraints = [];
  if (document.querySelector("#quiet-cafe").checked) {
    constraints.push({id: "quiet-cafe", owner_id: "local-user", field: "quiet", operator: "eq", value: true,
      strength: "hard", scope: "stop", stop_index: order.indexOf("cafe")});
  }
  if (document.querySelector("#no-seafood").checked) {
    constraints.push({id: "no-seafood", owner_id: "local-user", field: "contains_seafood", operator: "eq", value: false,
      strength: "hard", scope: "stop", stop_index: order.indexOf("restaurant")});
  }
  const input = {
    mode: mode.value,
    region: region.value.trim(),
    order,
    constraints,
    max_total_per_person_krw: budgetValue === "" ? null : Number(budgetValue),
    max_leg_distance_m: distanceValue === "" ? null : Number(distanceValue),
  };
  if (!input.region) { region.setCustomValidity("지역을 입력해 주세요."); region.reportValidity(); region.setCustomValidity(""); return; }
  if (activeRequest) activeRequest.abort();
  activeRequest = new AbortController();
  const current = ++requestNumber;
  submit.disabled = true;
  status.hidden = false;
  status.textContent = "조건에 맞는 장소를 찾고 있어요…";
  notices.replaceChildren();
  courses.replaceChildren();
  placeOptions.replaceChildren();
  sourceNote.hidden = true;
  try {
    const response = await fetch("/api/search", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(input), signal: activeRequest.signal});
    const data = await response.json();
    if (current !== requestNumber) return;
    if (!response.ok || data.status === "error") {
      status.textContent = data.message || "장소를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.";
      return;
    }
    if (data.status === "empty" || !Array.isArray(data.courses) || data.courses.length === 0) {
      status.textContent = data.message || "조건에 맞는 코스를 찾지 못했어요. 지역이나 조건을 바꿔 다시 검색해 주세요.";
    } else {
      status.textContent = data.message || `${data.courses.length}개의 코스를 찾았어요.`;
      data.courses.forEach((course, index) => showCourse(course, index, data.source));
    }
    if (data.source === "skill-test") showPlaceOptions(data.place_options, data.place_count);
    const label = data.source === "mock" ? "샘플 데이터 · 가상 장소" : data.source === "skill-test" ? "k-skill 개인 단발 테스트 · 팀 서비스 이용조건 확인 필요" : "실제 잇플 데이터";
    notices.append(element("p", "data-label", label));
    if (data.source === "skill-test") notices.append(element("p", "notice", data.cache_hit === true ? "프록시 캐시 응답입니다." : data.cache_hit === false ? "프록시 캐시 미사용 응답입니다." : "캐시 사용 여부를 확인하지 못했습니다."));
    if (data.truncated) notices.append(element("p", "notice", "검색 결과가 최대 반환 건수에 도달했습니다. 더 좁은 지역이나 업종으로 검색해 보세요."));
    sourceNote.hidden = false;
    sourceNote.textContent = data.source === "mock" ? "샘플 데이터의 장소, 가격, 좌표는 모두 가상의 정보입니다." : "eat.pl 잇플 · BC카드 결제 데이터 기반";
  } catch (error) {
    if (current !== requestNumber || error.name === "AbortError") return;
    status.textContent = "장소를 불러오지 못했어요. 연결 상태를 확인하고 다시 시도해 주세요.";
  } finally {
    if (current === requestNumber) { submit.disabled = false; activeRequest = null; }
  }
});
