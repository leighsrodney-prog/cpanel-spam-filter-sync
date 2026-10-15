import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import sync_filters as sf

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules.example.yaml")


def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(sf.urllib.request, "urlopen", boom)


no_network = pytest.fixture(autouse=True)(_no_network)


def test_load_rules_example():
    r = sf.load_rules(EXAMPLE)
    assert r["mailboxes"] == ["info@example.com", "admin@example.com"]
    assert "Business Funding" in r["subject_contains"]
    assert r["chunk"] == 6


def test_load_rules_defaults(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("mailboxes: [a@example.com]\nfrom_contains: [x]\n")
    r = sf.load_rules(str(p))
    assert r["allow_domains"] == [] and r["chunk"] == 6 and r["spam_folder"] == ".spam"


def test_config_env_overrides():
    cfg = sf.get_config({"mailboxes": ["a@example.com"], "cpanel_url": "https://x.example/"},
                        {"CPANEL_MAILBOXES": "b@example.com, c@example.com", "CPANEL_API_TOKEN": "t"})
    assert cfg["mailboxes"] == ["b@example.com", "c@example.com"]
    assert cfg["url"] == "https://x.example" and cfg["token"] == "t"
    assert cfg["prefix"] == sf.DEFAULT_PREFIX


def test_plan_chunks():
    r = sf.load_rules(EXAMPLE)
    r["chunk"] = 3
    names = [f[0] for f in sf.plan(r, "p")]
    assert names == ["p 0 allow", "p 1 from 1", "p 2 from 2", "p 3 subject 1", "p 4 subject 2", "p 5 auth 1"]


def test_build_params():
    p = sf.build_params("a@example.com", "n", [("$header_from:", "contains", "x"), ("$header_from:", "contains", "y")],
                        ("save", ".spam"), ["n"])
    assert p == {"account": "a@example.com", "filtername": "n", "oldfiltername": "n",
                 "part1": "$header_from:", "match1": "contains", "val1": "x", "opt1": "or",
                 "part2": "$header_from:", "match2": "contains", "val2": "y",
                 "action1": "save", "dest1": ".spam"}
    with pytest.raises(ValueError):
        sf.build_params("a", "n", [], ("delete", ""), [])


def test_dry_run_makes_no_calls():
    r = sf.load_rules(EXAMPLE)
    cfg = sf.get_config(r, {})
    calls, out = [], []
    sf.sync(cfg, r, dry_run=True, call=lambda *a: calls.append(a), out=out.append)
    assert calls == [] and "== info@example.com" in out


def test_live_sync_with_mock():
    r = sf.load_rules(EXAMPLE)
    cfg = sf.get_config(r, {"CPANEL_URL": "https://cpanel.example.com", "CPANEL_USER": "u", "CPANEL_API_TOKEN": "t"})
    cfg["mailboxes"] = ["info@example.com"]
    calls = []
    def fake(c, fn, params):
        calls.append((fn, params))
        if fn == "Email/list_filters":
            return {"data": [{"filtername": "custom spam 9 old 1"}, {"filtername": "manual"}]}
        return {"status": 1, "errors": None}
    out = []
    filters = sf.sync(cfg, r, call=fake, out=out.append)
    stores = [p for fn, p in calls if fn == "Email/store_filter"]
    assert len(stores) == len(filters)
    assert any("STALE" in o for o in out)
    reorder = [p for fn, p in calls if fn == "Email/reorder_filters"][0]
    assert reorder["filter1"] == "custom spam 0 allow" and list(reorder.values())[-1] == "manual"
    assert not any(fn == "Email/delete_filter" for fn, _ in calls)
