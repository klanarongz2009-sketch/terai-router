"""Temmo round 2: server mode (engine choice, quota, queue, HTTP), remix, GDD section fill. No network."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from terai_router.temmo import gdd, remix as R, server as S
from terai_router.temmo.pipeline import assemble

IDEA = "เกมแมวส้มเก็บปลาทูในตลาดน้ำ หลบหมาจรจัด"


# ---------- engine choice: only a real free tier, only with an adult operator ----------

def test_engine_defaults_to_local_or_mock_without_keys():
    assert S.pick_engine({}, local_ok=True)[0] == "local"
    assert S.pick_engine({}, local_ok=False)[0] == "mock"


@pytest.mark.parametrize("paid", ["anthropic", "openai", "deepseek", "gemini-image"])
def test_paid_providers_never_get_a_server_key(paid):
    env = {"TEMMO_FREE_TIER": paid, "ANTHROPIC_API_KEY": "k", "OPENAI_API_KEY": "k", "DEEPSEEK_API_KEY": "k",
           "GEMINI_API_KEY": "k", "TEMMO_OPERATOR_TERMS_OK": "1"}
    eng, notes = S.pick_engine(env, local_ok=False)
    assert eng == "mock" and "no free API tier" in notes[0]


def test_gemini_free_tier_needs_key_and_adult_operator():
    base = {"TEMMO_FREE_TIER": "gemini"}
    assert S.pick_engine(base, local_ok=True)[0] == "local"
    assert S.pick_engine(dict(base, GEMINI_API_KEY="k"), local_ok=True)[0] == "local"
    eng, notes = S.pick_engine(dict(base, GEMINI_API_KEY="k"), local_ok=True)
    assert "18+" in notes[0]
    assert S.pick_engine(dict(base, GEMINI_API_KEY="k", TEMMO_OPERATOR_TERMS_OK="1"), local_ok=True)[0] == "gemini"


# ---------- quota ----------

def test_quota_per_user_per_day_and_reset(tmp_path):
    now = [1_790_000_000.0]
    q = S.Quota(tmp_path / "q.json", limits={"build": 2, "remix": 1}, clock=lambda: now[0])
    assert q.take("a", "build") and q.take("a", "build") and not q.take("a", "build")
    assert q.take("b", "build") and q.left("a", "build") == 0
    q.refund("a", "build")
    assert q.left("a", "build") == 1
    assert S.Quota(tmp_path / "q.json", limits={"build": 2, "remix": 1}, clock=lambda: now[0]).left("a", "build") == 1
    now[0] += 86_400
    assert q.left("a", "build") == 2 and q.resets_at().endswith("T00:00:00Z")


def test_quota_ip_cap():
    q = S.Quota(None, limits={"build": 1, "remix": 1})
    assert all(q.take(f"u{i}", "build", ip="1.2.3.4") for i in range(5))
    assert not q.take("u9", "build", ip="1.2.3.4") and q.take("u9", "build", ip="5.6.7.8")


# ---------- queue + service ----------

def fake_builder(idea, out, roles, seed, screenshots):
    out.mkdir(parents=True, exist_ok=True)
    (out / "temmo.html").write_text("<html>" + idea + "</html>", encoding="utf-8")
    return {"build": {"html": str(out / "temmo.html")}, "gdd": {"title": "T"}, "test": {"passed": True}, "roles": roles}


def make_srv(tmp_path, limits=None, builder=fake_builder):
    return S.TemmoServer(tmp_path, env={}, quota=S.Quota(None, limits=limits or {"build": 2, "remix": 3}),
                         engine="mock", builder=builder)


def test_service_queue_order_quota_and_one_job_per_user(tmp_path):
    srv = make_srv(tmp_path)
    a = srv.request("alice", "build", {"idea": IDEA})
    b = srv.request("bob", "build", {"idea": "x"})
    assert a["position"] == 1 and b["position"] == 2 and a["left"] == 1
    with pytest.raises(S.TemmoError) as e:
        srv.request("alice", "build", {"idea": "again"})
    assert e.value.code == "busy" and srv.quota.left("alice", "build") == 1  # refunded
    assert srv.queue.run_once() and srv.queue.status(a["id"])["state"] == "done"
    assert srv.queue.status(b["id"])["position"] == 1
    srv.queue.run_once()
    srv.request("alice", "build", {"idea": "2"})
    srv.queue.run_once()
    with pytest.raises(S.TemmoError) as e:
        srv.request("alice", "build", {"idea": "3"})
    assert e.value.code == "quota" and e.value.status == 429


def test_service_validates_input(tmp_path):
    srv = make_srv(tmp_path)
    for user, kind, payload in [("bad user!", "build", {"idea": "x"}), ("u", "hack", {}), ("u", "build", {"idea": ""}),
                                ("u", "build", {"idea": "x" * 301}), ("u", "remix", {"game": {}})]:
        with pytest.raises(S.TemmoError):
            srv.request(user, kind, payload)
    assert srv.quota.left("u", "build") == 2


def test_failed_job_refunds_and_byok_skips_quota(tmp_path):
    def boom(*a, **k):
        raise RuntimeError("model crashed")
    srv = make_srv(tmp_path, builder=boom)
    j = srv.request("u", "build", {"idea": "x"})
    srv.queue.run_once()
    st = srv.queue.status(j["id"])
    assert st["state"] == "failed" and "crashed" in st["error"] and srv.quota.left("u", "build") == 2
    srv2 = make_srv(tmp_path)
    j = srv2.request("u", "build", {"idea": "x"}, byok={"provider": "anthropic", "key": "sk-test"})
    assert srv2.quota.left("u", "build") == 2
    assert srv2.queue.jobs[j["id"]]["payload"]["_byok"]["key"] == "sk-test"
    srv2.queue.run_once()
    assert srv2.queue.jobs[j["id"]]["payload"] == {}  # key dropped after the job
    assert "key" not in json.dumps(srv2.queue.status(j["id"]))


def test_remix_job_runs_through_queue(tmp_path):
    srv = make_srv(tmp_path)
    g = gdd.repair({}, IDEA)
    j = srv.request("u", "remix", {"game": g, "instruction": "พื้นหลังสีชมพู ง่ายขึ้น"})
    srv.queue.run_once()
    res = srv.queue.status(j["id"])["result"]
    assert res["game"]["palette"]["bg"] == "#f06292" and res["source"] == "rules"
    assert R.rule_patch("พื้นหลังสีชมพู กำแพงสีน้ำตาล")["palette"] == {"bg": "#f06292", "wall": "#6d4c41"}
    assert R.rule_patch("พื้นสีเทา พื้นหลังสีดำ")["palette"] == {"floor": "#607d8b", "bg": "#0b0d10"}


def test_http_endpoints(tmp_path):
    from http.server import ThreadingHTTPServer
    srv = make_srv(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.make_handler(srv))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        info = json.load(urllib.request.urlopen(base + "/api/info"))
        assert info["engine"] == "mock" and info["free_tier"] == ["gemini"]
        req = urllib.request.Request(base + "/api/build", json.dumps({"user": "web1", "idea": IDEA}).encode(),
                                     {"Content-Type": "application/json"})
        st = json.load(urllib.request.urlopen(req))
        assert st["state"] == "queued"
        srv.queue.run_once()
        assert json.load(urllib.request.urlopen(base + "/api/job?id=" + st["id"]))["state"] == "done"
        assert IDEA in urllib.request.urlopen(base + f"/games/{st['id']}.html").read().decode()
        assert json.load(urllib.request.urlopen(base + "/api/quota?user=web1"))["build"] == 1
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/api/build", b"{", {"Content-Type": "application/json"}))
        assert e.value.code == 400
    finally:
        httpd.shutdown()


# ---------- remix ----------

def test_rule_remix_colours_title_difficulty():
    g = gdd.repair({}, IDEA)
    new, patch, src = R.remix(g, 'ชื่อเกม "แมวส้มตะลุยตลาด" กำแพงสีน้ำตาล และพื้นหลังสีฟ้า ยากขึ้น')
    assert new["title_th"] == "แมวส้มตะลุยตลาด" and src == "rules"
    assert new["palette"]["wall"] == "#6d4c41" and new["palette"]["bg"] == "#4fc3f7"
    assert all(a["time"] == max(40, b["time"] - 15) for a, b in zip(new["levels"], g["levels"]))
    assert g["palette"] != new["palette"] or not g["palette"]  # original untouched


def test_ai_patch_is_validated():
    class P:
        name = "local"
        def complete(self, system, prompt, max_tokens):
            return '{"title": "<script>x</script>Cat", "palette": {"bg": "red", "wall": "#112233", "evil": "#000000"}, "time_delta": 999, "code": "alert(1)"}'
    g = gdd.repair({}, IDEA)
    new, patch, src = R.remix(g, "สีสวยขึ้น", P())
    assert src == "ai" and patch == {"title": "scriptx/scriptCat", "palette": {"wall": "#112233"}, "time_delta": 30}
    assert "code" not in new and "<" not in new["title"]


def test_share_export_swaps_game_data(tmp_path):
    g = gdd.repair({}, IDEA)
    built = assemble(g, {}, None, tmp_path)
    html = open(built["html"], encoding="utf-8").read()
    assert R.read_game(html)["title_th"] == g["title_th"]
    new, _, _ = R.remix(g, "title: Market Cat </script>")
    out = R.write_game(html, new)
    assert R.read_game(out)["title"] == new["title"] and "<title>Market Cat /script</title>" in out
    assert out.count("</script>") == html.count("</script>")


# ---------- design fix: no prompt leaks, fill only missing sections ----------

def test_prompt_leak_never_becomes_title():
    g = gdd.repair({"title": "title for a game about " + IDEA, "title_th": "Thai title", "sprites": {"title": "title for a game about x"}}, IDEA)
    assert g["title_th"] == "แมวส้มเก็บปลาทูในตลาดน้ำ" and g["title"] == g["title_th"]
    assert "Temmo Maze" not in json.dumps(g, ensure_ascii=False)
    assert not any(gdd.looks_like_prompt(v, IDEA) for v in g["sprites"].values())


def test_missing_sections_and_merge():
    raw = {"title": "Market Cat", "title_th": "แมวตลาดน้ำ", "tagline": "เก็บปลาทู"}
    assert gdd.missing_sections(raw, IDEA) == ["palette", "names"]
    assert gdd.merge_section(raw, "palette", {"palette": {"bg": "#000000", "wall": "#111111"}}) == []
    pal = {k: "#123456" for k in gdd.DEFAULT_PALETTE_KEYS}
    assert gdd.merge_section(raw, "palette", {"palette": pal}) == ["palette"]
    assert gdd.merge_section(raw, "names", {"names": ["ท่าน้ำ", "ตลาดเช้า", "สะพานไม้"]}) == ["level_names"]
    g = gdd.repair(raw, IDEA)
    assert [lv["name"] for lv in g["levels"]] == ["ท่าน้ำ", "ตลาดเช้า", "สะพานไม้"] and g["title"] == "Market Cat"
    t = {"title": "short English title", "title_th": "x", "tagline": "y"}
    assert gdd.merge_section(t, "text", {"title": "Fish Run", "title_th": "ปลาทู"}) == ["title"]
    assert t["title_th"] == "x"  # good values are never overwritten


def test_pipeline_fills_missing_sections_with_scripted_model(tmp_path):
    from terai_router.temmo import pipeline, providers as P
    replies = {"design": '{"tagline": "เก็บปลาทูหนีหมา", "title": "title for a game about cats"}',
               "levels": "not json", "text": '{"title": "Market Cat", "title_th": "แมวส้มตลาดน้ำ"}',
               "palette": json.dumps({"palette": {k: "#2266aa" for k in gdd.DEFAULT_PALETTE_KEYS}}),
               "names": '{"names": ["ท่าน้ำ", "ตลาดเช้า", "สะพานไม้"]}'}

    class Scripted(P.Mock):
        def complete(self, system, prompt, max_tokens=1000):
            if prompt.startswith("Design a complete game"):
                return replies["design"]
            if prompt.startswith("Make 3 levels"):
                return replies["levels"]
            if "Write the game's names" in prompt:
                return replies["text"]
            if "Pick 7 colours" in prompt:
                return replies["palette"]
            if "level names" in prompt:
                return replies["names"]
            return super().complete(system, prompt, max_tokens)

    orig = pipeline.make
    pipeline.make = lambda name, *a, **k: Scripted() if name == "mock" else orig(name, *a, **k)
    try:
        rep = pipeline.build(IDEA, tmp_path, roles={r: "mock" for r in ("design", "review", "code", "repair", "chat")},
                             test=False, voice=False, mod=False, screenshots=False)
    finally:
        pipeline.make = orig
    g = rep["gdd"]
    assert rep["fills"] == {"text": 1, "palette": 1, "names": 1}
    assert g["title"] == "Market Cat" and g["title_th"] == "แมวส้มตลาดน้ำ" and g["palette"]["bg"] == "#2266aa"
    assert [lv["name"] for lv in g["levels"]] == ["ท่าน้ำ", "ตลาดเช้า", "สะพานไม้"]


REMIX_CASES = ["พื้นหลังสีชมพู ง่ายขึ้น", "พื้นหลังสีชมพู กำแพงสีน้ำตาล ยากขึ้น", "พื้นสีเทา พื้นหลังสีดำ ศัตรูสีแดง", 'ชื่อเกม "แมวส้มตะลุยตลาด" กำแพงสีน้ำตาล และพื้นหลังสีฟ้า ยากขึ้น', "title: Market Cat, wall blue and enemy red",
               "คำโปรย: เก็บปลาทูให้ครบ", "สีสวยขึ้น", "player white, exit yellow; more time", "ชื่อ <b>{x}</b>"]


def test_remix_js_parity_with_python():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    g = gdd.repair({}, IDEA)
    js = Path(__file__).resolve().parents[1] / "docs" / "temmo" / "community.js"
    script = ("const C=require(process.argv[1]);const d=JSON.parse(require('fs').readFileSync(0,'utf8'));"
              "process.stdout.write(JSON.stringify(d.cases.map(c=>{const r=C.remix(d.game,c);return [r.patch,r.game]})))")
    got = json.loads(subprocess.run([node, "-e", script, str(js)], input=json.dumps({"game": g, "cases": REMIX_CASES}),
                                    capture_output=True, text=True, check=True).stdout)
    for case, (patch, game) in zip(REMIX_CASES, got):
        new, want, _ = R.remix(g, case)
        assert patch == want, case
        assert game == new, case
