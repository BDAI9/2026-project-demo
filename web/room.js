"use strict";

const roomId = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
const meKey = `moim:${roomId}`;
const $ = (id) => document.getElementById(id);
let OPT = null;
let lastRoom = null;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method, headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || "요청에 실패했어요.");
  return data;
}

function loadMe() {
  try { return JSON.parse(localStorage.getItem(meKey) || "null"); } catch { return null; }
}
function saveMe(v) {
  try { v ? localStorage.setItem(meKey, JSON.stringify(v)) : localStorage.removeItem(meKey); } catch { /* 저장 불가 환경 */ }
}

// ---------- 칩(선택 버튼) ----------
function chips(container, name, items, type, { onChange, limit } = {}) {
  container.replaceChildren();
  items.forEach(([value, label]) => {
    const wrap = el("label", "chip");
    const input = el("input");
    input.type = type; input.name = name; input.value = value;
    input.addEventListener("change", () => {
      if (limit && type === "checkbox") {
        const checked = container.querySelectorAll("input:checked");
        if (checked.length > limit) { input.checked = false; return; }
      }
      if (onChange) onChange();
    });
    wrap.append(input, el("span", "", label));
    container.append(wrap);
  });
}
const checkedValues = (c) => [...c.querySelectorAll("input:checked")].map((i) => i.value);
function setChecked(c, values) {
  const set = new Set(values.map(String));
  c.querySelectorAll("input").forEach((i) => { i.checked = set.has(i.value); });
}

function renderStyles(selected = []) {
  const type = checkedValues($("place-types"))[0];
  $("style-box").hidden = !type;
  if (!type) return;
  $("style-label").textContent = OPT.style_label[type];
  chips($("styles"), "styles", OPT.styles[type].map((s) => [s, s]), "checkbox");
  setChecked($("styles"), selected);
}

function buildForm() {
  chips($("regions"), "region", OPT.regions.map((r) => [r, r]), "radio", { onChange: () => { $("region-custom").value = ""; } });
  chips($("place-types"), "place_type", Object.entries(OPT.place_types), "radio", { onChange: () => renderStyles() });
  chips($("budgets"), "budget", Object.entries(OPT.budgets), "radio");
  chips($("atmospheres"), "atmospheres", OPT.atmospheres.map((a) => [a, a]), "checkbox", { limit: 3 });
  chips($("allergies"), "allergies", OPT.allergies.map((a) => [a, a]), "checkbox");
  $("region-custom").addEventListener("input", () => { if ($("region-custom").value) setChecked($("regions"), []); });
}

function fillForm(p) {
  $("name").value = p.name;
  if (OPT.regions.includes(p.region)) { setChecked($("regions"), [p.region]); $("region-custom").value = ""; }
  else { setChecked($("regions"), []); $("region-custom").value = p.region; }
  setChecked($("place-types"), [p.place_type]);
  renderStyles(p.styles);
  setChecked($("budgets"), p.budget ? [p.budget] : []);
  setChecked($("atmospheres"), p.atmospheres);
  setChecked($("allergies"), p.allergies);
  $("allergy-other").value = p.allergy_other || "";
}

function readForm() {
  const budget = checkedValues($("budgets"))[0];
  return {
    name: $("name").value.trim(),
    region: $("region-custom").value.trim() || checkedValues($("regions"))[0] || "",
    place_type: checkedValues($("place-types"))[0] || "",
    styles: checkedValues($("styles")),
    budget: budget ? Number(budget) : null,
    atmospheres: checkedValues($("atmospheres")),
    allergies: checkedValues($("allergies")),
    allergy_other: $("allergy-other").value.trim() || null,
  };
}

// ---------- 참여 현황 ----------
function bar(label, count, total) {
  const row = el("div", "bar");
  const fill = el("span", "fill");
  fill.style.width = total ? `${Math.round((count / total) * 100)}%` : "0";
  row.append(el("span", "bar-label", label), el("span", "track"), el("span", "bar-count", `${count}명`));
  row.querySelector(".track").append(fill);
  return row;
}

function renderRoom(room) {
  lastRoom = room;
  $("room-title").textContent = room.title;
  document.title = `${room.title} · 모임 장소 고르기`;
  const s = room.summary;
  $("count").textContent = `${s.count}명 참여`;
  const me = loadMe();
  const people = $("people");
  people.replaceChildren();
  if (!room.participants.length) people.append(el("li", "hint", "아직 아무도 없어요. 링크를 공유해 보세요."));
  room.participants.forEach((p) => {
    const li = el("li", me && me.id === p.id ? "me" : "");
    li.append(el("strong", "", p.name + (me && me.id === p.id ? " (나)" : "")),
      el("span", "", ` ${p.region} · ${OPT.place_types[p.place_type]}${p.styles.length ? " · " + p.styles.join(", ") : ""}`));
    const allergies = [...p.allergies, ...(p.allergy_other ? [p.allergy_other] : [])];
    if (allergies.length) li.append(el("span", "tag warn", `알레르기 ${allergies.join(", ")}`));
    people.append(li);
  });

  const t = $("tallies");
  t.replaceChildren();
  if (!s.count) return;
  const group = (title, entries) => {
    const box = el("div", "tally");
    box.append(el("h3", "", title));
    entries.filter(([, c]) => c > 0).forEach(([k, c]) => box.append(bar(k, c, s.count)));
    if (box.children.length > 1) t.append(box);
  };
  group("지역", Object.entries(s.regions));
  group("장소", Object.entries(s.place_types).map(([k, c]) => [OPT.place_types[k], c]));
  Object.entries(s.styles).forEach(([type, counts]) => group(OPT.style_label[type], Object.entries(counts)));
  group("예산", Object.entries(s.budgets).map(([k, c]) => [OPT.budgets[k], c]));
  group("분위기", Object.entries(s.atmospheres));
  const al = Object.entries(s.allergies);
  if (al.length) {
    const box = el("div", "tally");
    box.append(el("h3", "", "알레르기 (추천에서 제외)"));
    al.forEach(([a, names]) => box.append(el("p", "tag warn", `${a} — ${names.join(", ")}`)));
    t.append(box);
  }
  updateRecDefaults(s);
}

function updateRecDefaults(s) {
  const reg = $("rec-region"), typ = $("rec-type");
  const regions = [...new Set([...Object.keys(s.regions), ...OPT.regions])];
  const prevR = reg.dataset.touched ? reg.value : s.region;
  const prevT = typ.dataset.touched ? typ.value : s.place_type;
  reg.replaceChildren(...regions.map((r) => { const o = el("option", "", r + (s.regions[r] ? ` (${s.regions[r]}명)` : "")); o.value = r; return o; }));
  typ.replaceChildren(...Object.entries(OPT.place_types).map(([k, v]) => { const o = el("option", "", v + (s.place_types[k] ? ` (${s.place_types[k]}명)` : "")); o.value = k; return o; }));
  if (prevR) reg.value = prevR;
  if (prevT) typ.value = prevT;
}

async function refresh() {
  try { renderRoom(await api(`/api/rooms/${encodeURIComponent(roomId)}`)); }
  catch (err) { $("room-title").textContent = err.message; }
}

// ---------- 저장 ----------
$("pref-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = $("form-status");
  const data = readForm();
  if (!data.region) { status.textContent = "지역을 골라 주세요."; return; }
  if (!data.place_type) { status.textContent = "카페·식당·술집 중 하나를 골라 주세요."; return; }
  status.textContent = "저장 중…";
  try {
    const me = loadMe();
    if (me) {
      try {
        await api(`/api/rooms/${encodeURIComponent(roomId)}/participants/${encodeURIComponent(me.id)}`, "PUT", { ...data, token: me.token });
      } catch (err) {
        if (!/권한/.test(err.message)) throw err;
        saveMe(null);  // 응답이 지워졌으면 새로 참여
        const made = await api(`/api/rooms/${encodeURIComponent(roomId)}/participants`, "POST", data);
        saveMe(made);
      }
    } else {
      saveMe(await api(`/api/rooms/${encodeURIComponent(roomId)}/participants`, "POST", data));
    }
    status.textContent = "저장했어요. 바꾸고 싶으면 수정 후 다시 저장하세요.";
    $("save-button").textContent = "수정 저장";
    $("leave-button").hidden = false;
    refresh();
  } catch (err) {
    status.textContent = err.message;
  }
});

$("leave-button").addEventListener("click", async () => {
  const me = loadMe();
  if (!me) return;
  try {
    await api(`/api/rooms/${encodeURIComponent(roomId)}/participants/${encodeURIComponent(me.id)}`, "DELETE", { token: me.token });
  } catch { /* 이미 지워짐 */ }
  saveMe(null);
  $("pref-form").reset();
  renderStyles();
  $("save-button").textContent = "저장하기";
  $("leave-button").hidden = true;
  $("form-status").textContent = "내 응답을 지웠어요.";
  refresh();
});

// ---------- 추천 ----------
["rec-region", "rec-type"].forEach((id) => $(id).addEventListener("change", (e) => { e.target.dataset.touched = "1"; }));

function resultCard(r, i, source) {
  const li = el("li", "result");
  const inner = r.eatpl_url ? el("a", "result-link") : el("div", "result-link disabled");
  if (r.eatpl_url) { inner.href = r.eatpl_url; inner.target = "_blank"; inner.rel = "noopener"; }
  const head = el("div", "result-head");
  head.append(el("span", "rank", String(i + 1)), el("strong", "", r.name));
  if (r.business_type) head.append(el("span", "tag", r.business_type));
  inner.append(head);
  if (r.address) inner.append(el("p", "addr", r.address));
  const reasons = el("ul", "reasons");
  r.reasons.forEach((x) => reasons.append(el("li", "", x)));
  if (!r.reasons.length) reasons.append(el("li", "muted", "선호와 겹치는 정보가 적어요"));
  inner.append(reasons);
  r.cautions.forEach((c) => inner.append(el("p", "caution", c)));
  const est = r.estimate;
  inner.append(el("p", "fine", est.source === "ai" ? "AI 추정 포함" : "업종 정보 기준"));
  inner.append(el("p", "go", r.eatpl_url ? "잇플에서 보기 →" : source === "sample" ? "가상 가게라 잇플 링크가 없어요" : "잇플 링크 없음"));
  li.append(inner);
  return li;
}

$("rec-button").addEventListener("click", async () => {
  const status = $("rec-status");
  status.textContent = "가게를 찾고 추정하는 중… (처음엔 몇 초 걸려요)";
  $("results").replaceChildren(); $("rec-warnings").replaceChildren();
  $("excluded-box").hidden = true;
  try {
    const data = await api(`/api/rooms/${encodeURIComponent(roomId)}/recommend`, "POST",
      { region: $("rec-region").value, place_type: $("rec-type").value });
    data.warnings.forEach((w) => $("rec-warnings").append(el("p", "notice", w)));
    status.textContent = data.status === "ok"
      ? `${data.region} ${OPT.place_types[data.place_type]} 추천 ${data.results.length}곳 · ${data.summary.count}명의 선호 반영`
      : data.message;
    data.results.forEach((r, i) => $("results").append(resultCard(r, i, data.source)));
    if (data.excluded.length) {
      $("excluded-box").hidden = false;
      $("excluded-count").textContent = `(${data.excluded.length})`;
      $("excluded").replaceChildren(...data.excluded.map((x) => el("li", "", `${x.name} — ${x.reason}`)));
    }
  } catch (err) {
    status.textContent = err.message;
  }
});

// ---------- 시작 ----------
$("share-link").value = location.href;
$("copy-link").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(location.href); $("copy-link").textContent = "복사됨"; }
  catch { $("share-link").select(); }
  setTimeout(() => { $("copy-link").textContent = "링크 복사"; }, 1500);
});

(async () => {
  OPT = await api("/api/options");
  if (OPT.data_source === "sample") {
    $("source-note").hidden = false;
    $("source-note").textContent = "샘플 모드: 잇플 기관명이 설정되지 않아 홍대·성수·강남의 가상 가게로 추천해요.";
  }
  buildForm();
  await refresh();
  const me = loadMe();
  const mine = me && lastRoom && lastRoom.participants.find((p) => p.id === me.id);
  if (mine) {
    fillForm(mine);
    $("save-button").textContent = "수정 저장";
    $("leave-button").hidden = false;
  } else if (me) {
    saveMe(null);
  }
  setInterval(() => { if (!document.hidden) refresh(); }, 5000);
})();
