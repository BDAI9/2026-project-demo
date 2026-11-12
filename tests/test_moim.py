"""모임 장소 추천 테스트. 실제 잇플·OpenRouter는 호출하지 않는다. 실행: python -m pytest -q"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlreq

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moim import eatpl, estimate, options  # noqa: E402
from moim.recommend import recommend, summarize  # noqa: E402
from moim.server import App, make_handler  # noqa: E402
from moim.store import Store  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "EATPL_INSTITUTION", "EATPL_ENV"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "t.sqlite3"))


def person(name, **kw):
    base = {"name": name, "region": "홍대", "place_type": "restaurant", "styles": [], "budget": None,
            "atmospheres": [], "allergies": []}
    base.update(kw)
    return options.validate_preference(base)


# ---------------------------------------------------------------- 입력 검증
def test_validate_rejects_style_of_other_type():
    with pytest.raises(ValueError):
        person("a", place_type="cafe", styles=["일식"])


def test_validate_limits_atmospheres_and_unknown_fields():
    with pytest.raises(ValueError):
        person("a", atmospheres=options.ATMOSPHERES[:4])
    with pytest.raises(ValueError):
        options.validate_preference({**person("a"), "hack": 1})


def test_custom_region_and_other_allergy_allowed():
    p = person("a", region="망원", allergy_other="키위")
    assert p["region"] == "망원" and p["allergy_other"] == "키위"


# ---------------------------------------------------------------- 집계
def test_votes_pick_region_and_type():
    s = summarize([person("a"), person("b", region="성수", place_type="bar"), person("c", place_type="cafe"),
                   person("d")])
    assert s["region"] == "홍대" and s["place_type"] == "restaurant"
    assert s["allergies"] == {}


def test_allergies_collected_with_names():
    s = summarize([person("a", allergies=["땅콩"]), person("b", allergies=["땅콩"], allergy_other="키위")])
    assert s["allergies"] == {"땅콩": ["a", "b"], "키위": ["b"]}


# ---------------------------------------------------------------- 추천 (샘플 + 규칙)
def test_allergy_high_risk_excluded_and_popular_style_first(store):
    people = [person("윤아", styles=["일식", "한식"], allergies=["갑각류(새우·게)"]),
              person("민수", styles=["한식"]), person("지영", styles=["중식"])]
    out = recommend(people, eatpl.SampleClient(), store)
    names = [r["name"] for r in out["results"]]
    excluded = [x["name"] for x in out["excluded"]]
    assert out["status"] == "ok" and out["source"] == "sample"
    assert any("횟집" in n for n in excluded) and any("초밥" in n for n in excluded)
    assert not any("횟집" in n or "초밥" in n for n in names)
    assert "한식" in names[0] or "백반" in names[0]  # 2명이 원한 한식이 1위
    assert "3명 중 2명이 원하는 한식" in out["results"][0]["reasons"]


def test_override_region_and_type(store):
    out = recommend([person("a")], eatpl.SampleClient(), store, region="성수", place_type="cafe")
    assert out["region"] == "성수" and out["place_type"] == "cafe"
    assert out["results"] and all(r["category"] == "cafe" for r in out["results"])


def test_empty_region(store):
    out = recommend([person("a", region="제주")], eatpl.SampleClient(), store)
    assert out["status"] == "empty"


def test_no_participants(store):
    with pytest.raises(ValueError):
        recommend([], eatpl.SampleClient(), store)


# ---------------------------------------------------------------- AI 추정 (가짜 OpenRouter)
def fake_ai(monkeypatch, responder):
    calls = []

    def post(api_key, model, messages, timeout=30):
        calls.append(model)
        return responder(model, json.loads(messages[1]["content"]))

    monkeypatch.setattr(estimate, "_post", post)
    return calls


def test_ai_estimates_drive_budget_and_atmosphere(monkeypatch, store):
    def responder(model, user):
        items = []
        for p in user["가게"]:
            cheap = "분식" in p["이름"]
            items.append({"id": p["id"], "price_band": 1 if cheap else 4,
                          "atmospheres": ["활기찬"] if cheap else ["조용한"], "styles": [],
                          "allergy_risk": {a: "low" for a in user["요청한 알레르기"]}})
        return json.dumps({"places": items}, ensure_ascii=False)

    fake_ai(monkeypatch, responder)
    people = [person("a", budget=1, atmospheres=["활기찬"]), person("b", budget=1, atmospheres=["활기찬"])]
    out = recommend(people, eatpl.SampleClient(), store, api_key="test")
    top = out["results"][0]
    assert "분식" in top["name"]
    assert top["estimate"]["source"] == "ai"
    assert any("예산 맞는 사람 2/2" in r for r in top["reasons"])


def test_ai_cannot_lower_rule_allergy_risk(monkeypatch, store):
    def responder(model, user):
        return json.dumps({"places": [{"id": p["id"], "allergy_risk": {"생선": "low"}} for p in user["가게"]]})

    fake_ai(monkeypatch, responder)
    out = recommend([person("a", allergies=["생선"])], eatpl.SampleClient(), store, api_key="test")
    assert any("횟집" in x["name"] for x in out["excluded"])  # 규칙의 high가 AI의 low보다 우선


def test_ai_falls_back_through_models_then_rules(monkeypatch, store):
    from urllib import error
    monkeypatch.setenv("OPENROUTER_MODEL", "busy:free,broken:free")

    def responder(model, user):
        if model == "busy:free":
            raise error.HTTPError("u", 429, "busy", {}, None)
        return "모르겠어요"

    calls = fake_ai(monkeypatch, responder)
    out = recommend([person("a")], eatpl.SampleClient(), store, api_key="test")
    assert calls[:2] == ["busy:free", "broken:free"]
    assert out["status"] == "ok" and out["warnings"] and "AI 추정에 실패" in out["warnings"][0]
    assert out["results"][0]["estimate"]["source"] == "rule"


def test_ai_results_cached(monkeypatch, store):
    def responder(model, user):
        return json.dumps({"places": [{"id": p["id"], "price_band": 2} for p in user["가게"]]})

    calls = fake_ai(monkeypatch, responder)
    recommend([person("a")], eatpl.SampleClient(), store, api_key="test")
    n = len(calls)
    recommend([person("b")], eatpl.SampleClient(), store, api_key="test")
    assert len(calls) == n  # 두 번째는 캐시 사용


def test_ai_invalid_values_dropped():
    c = estimate._clean_ai({"price_band": 9, "atmospheres": ["없는분위기", "조용한"], "styles": ["일식", "x"],
                            "allergy_risk": {"땅콩": "maybe"}}, "restaurant", ["땅콩"])
    assert c["price_band"] is None and c["atmospheres"] == ["조용한"] and c["styles"] == ["일식"]
    assert c["allergy_risk"] == {"땅콩": "unknown"}


# ---------------------------------------------------------------- 잇플 클라이언트 (가짜 서버)
class FakeEatpl(BaseHTTPRequestHandler):
    received = []
    reply = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeEatpl.received.append(body)
        status, payload = FakeEatpl.reply
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def fake_eatpl(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeEatpl)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(eatpl, "DEV_URL", f"http://127.0.0.1:{srv.server_port}/api/mer")
    FakeEatpl.received = []
    yield FakeEatpl
    srv.shutdown()


def test_eatpl_request_and_mapping(fake_eatpl, store):
    url = "https://web.paybooc.ai/mer/web/profile/abc123"
    fake_eatpl.reply = (200, {"rspCode": "00000", "data": [
        {"merNm": "실제 카페", "merAddr": "서울 마포구", "merUrl": url, "merTpbuzNm": "카페", "allSaleRnk": 3},
        {"merNm": "나쁜 링크", "merAddr": "서울", "merUrl": "https://evil.example/x", "merTpbuzNm": "카페"},
        {"merNm": "", "merAddr": "x"}]})
    client = eatpl.EatplClient("BDAI", store.next_trace_number)
    places = client.search("홍대", "카페")
    sent = fake_eatpl.received[0]
    assert sent["instNm"] == "BDAI" and sent["location"] == "홍대" and sent["merTpbuzNm"] == "카페"
    assert sent["trnsTrceNo"].startswith("BDAI") and len(sent["trnsTrceNo"]) == 4 + 18
    assert [p["name"] for p in places] == ["실제 카페", "나쁜 링크"]
    assert places[0]["eatpl_url"] == url and places[1]["eatpl_url"] is None
    client.search("홍대")
    assert fake_eatpl.received[1]["trnsTrceNo"] != sent["trnsTrceNo"]  # 순번 증가


@pytest.mark.parametrize("reply, msg", [
    ((403, {}), "IP 등록"), ((500, {}), "HTTP 500"), ((200, {"rspCode": "E001"}), "E001")])
def test_eatpl_errors(fake_eatpl, store, reply, msg):
    fake_eatpl.reply = reply
    with pytest.raises(eatpl.EatplError, match=msg):
        eatpl.EatplClient("BDAI", store.next_trace_number).search("홍대")


def test_recommend_reports_eatpl_error(fake_eatpl, store):
    fake_eatpl.reply = (403, {})
    out = recommend([person("a")], eatpl.EatplClient("BDAI", store.next_trace_number), store)
    assert out["status"] == "error" and "IP" in out["message"]


def test_make_client_uses_env(monkeypatch, store):
    assert eatpl.make_client(store).source == "sample"
    monkeypatch.setenv("EATPL_INSTITUTION", "BDAI")
    assert eatpl.make_client(store).source == "eatpl"


# ---------------------------------------------------------------- HTTP 서버 전체 흐름
@pytest.fixture
def server(store):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(store, eatpl.SampleClient())))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def call(base, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urlreq.Request(base + path, data=data, method=method,
                         headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlreq.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urlreq.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_room_flow(server):
    status, room = call(server, "/api/rooms", "POST", {"title": "테스트"})
    assert status == 201
    rid = room["id"]
    s, me = call(server, f"/api/rooms/{rid}/participants", "POST",
                 {"name": "윤아", "region": "성수", "place_type": "cafe", "styles": ["디저트·케이크"],
                  "budget": 2, "atmospheres": [], "allergies": []})
    assert s == 201 and me["token"]
    s, got = call(server, f"/api/rooms/{rid}")
    assert s == 200 and got["summary"]["count"] == 1 and "token" not in json.dumps(got)
    # 다른 사람 토큰으로 수정 불가
    s, _ = call(server, f"/api/rooms/{rid}/participants/{me['id']}", "PUT",
                {"token": "wrong", "name": "x", "region": "홍대", "place_type": "bar"})
    assert s == 403
    s, _ = call(server, f"/api/rooms/{rid}/participants/{me['id']}", "PUT",
                {"token": me["token"], "name": "윤아", "region": "성수", "place_type": "bar", "styles": ["이자카야"]})
    assert s == 200
    s, rec = call(server, f"/api/rooms/{rid}/recommend", "POST", {})
    assert s == 200 and rec["place_type"] == "bar" and rec["results"]
    s, _ = call(server, f"/api/rooms/{rid}/participants/{me['id']}", "DELETE", {"token": me["token"]})
    assert s == 200 and call(server, f"/api/rooms/{rid}")[1]["summary"]["count"] == 0


def test_http_errors(server):
    assert call(server, "/api/rooms/nope1234")[0] == 404
    rid = call(server, "/api/rooms", "POST", {})[1]["id"]
    s, err = call(server, f"/api/rooms/{rid}/participants", "POST", {"name": "a", "region": "홍대", "place_type": "pub"})
    assert s == 400 and "하나" in err["message"]
    s, err = call(server, f"/api/rooms/{rid}/recommend", "POST", {})
    assert s == 400 and "참여" in err["message"]
    with urlreq.urlopen(server + f"/r/{rid}") as r:
        assert r.status == 200 and "모임 장소" in r.read().decode()
