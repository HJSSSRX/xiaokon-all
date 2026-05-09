"""
sim_recon.py 单测 — mock ssh_helper + mock hub HTTP.

Run:
  python3 tests/test_sim_recon.py
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import sim_recon


PASSED = 0
FAILED = 0


def t(name, cond, msg=""):
    global PASSED, FAILED
    if cond:
        print(f"[OK]   {name}")
        PASSED += 1
    else:
        print(f"[FAIL] {name}  {msg}")
        FAILED += 1


def make_mock_ssh(run_returns=None, tidb_returns=None):
    """Create mock ForensicSSH with run() / tidb() returning canned data."""
    mock = MagicMock()
    if run_returns is None:
        run_returns = ("mock stdout\n", "", 0)
    mock.run.return_value = run_returns
    if tidb_returns is None:
        tidb_returns = "mock tidb output\n"
    mock.tidb.return_value = tidb_returns
    return mock


def test_recon_server_runs_all_probes():
    """recon_server 应跑完所有 SERVER_PROBES."""
    mock_ssh = make_mock_ssh()
    results = sim_recon.recon_server(mock_ssh, hub_url="", verbose=False)
    
    expected_count = len(sim_recon.SERVER_PROBES)
    t(f"recon_server: 跑完 {expected_count} 个探针", len(results) == expected_count)
    t("recon_server: ssh.run 被调用次数正确", mock_ssh.run.call_count == expected_count)
    
    # 验证每个探针都有结果
    for name, _ in sim_recon.SERVER_PROBES:
        t(f"recon_server: 含探针结果 [{name}]", name in results)


def test_recon_server_hub_post():
    """recon_server 配置 hub_url 时应当 POST /log."""
    mock_ssh = make_mock_ssh(run_returns=("listening on 22\n", "", 0))
    
    captured_calls = []
    def mock_post(hub, path, payload, timeout=5):
        captured_calls.append((hub, path, payload))
        return True, {}
    
    with patch.object(sim_recon, "_hub_post", side_effect=mock_post):
        sim_recon.recon_server(mock_ssh, hub_url="http://test:8765",
                                role="server_analyst", verbose=False)
    
    expected = len(sim_recon.SERVER_PROBES)
    t(f"recon_server hub: 每个探针 1 次 POST (共 {expected})",
      len(captured_calls) == expected)
    t("recon_server hub: 路径都是 /log",
      all(c[1] == "/log" for c in captured_calls))
    t("recon_server hub: payload kind=finding",
      all(c[2]["kind"] == "finding" for c in captured_calls))
    t("recon_server hub: payload from=server_analyst",
      all(c[2]["from"] == "server_analyst" for c in captured_calls))
    t("recon_server hub: type=environment",
      all(c[2]["type"] == "environment" for c in captured_calls))


def test_recon_server_skip_empty_output():
    """空输出的探针不应当 POST hub."""
    mock_ssh = make_mock_ssh(run_returns=("", "", 0))
    
    captured = []
    with patch.object(sim_recon, "_hub_post",
                      side_effect=lambda *a, **k: captured.append(a) or (True, {})):
        sim_recon.recon_server(mock_ssh, hub_url="http://test", verbose=False)
    
    t("空输出的探针不 POST hub (跳过)", len(captured) == 0)


def test_recon_server_handles_errors():
    """探针 ssh.run 抛错时应当返回 error 标记, 不阻塞其他探针."""
    mock_ssh = MagicMock()
    mock_ssh.run.side_effect = Exception("connection lost")
    
    results = sim_recon.recon_server(mock_ssh, hub_url="", verbose=False)
    
    t("ssh.run 抛错: 不挂掉巡检流程",
      len(results) == len(sim_recon.SERVER_PROBES))
    t("ssh.run 抛错: 结果含 <error>",
      all("<error" in v for v in results.values()))


def test_recon_maccms():
    """recon_maccms 跑 MACCMS_PROBES."""
    mock_ssh = make_mock_ssh(run_returns=("ENTRANCE = 'user.php'\n", "", 0))
    results = sim_recon.recon_maccms(mock_ssh, hub_url="", verbose=False)
    
    expected = len(sim_recon.MACCMS_PROBES)
    t(f"recon_maccms: 跑完 {expected} 个探针", len(results) == expected)


def test_recon_tidb():
    """recon_tidb 通过 ssh.tidb 跑查询."""
    mock_ssh = make_mock_ssh(tidb_returns="db1\ndb2\nmaccms\n")
    results = sim_recon.recon_tidb(mock_ssh, container="mytidb",
                                    hub_url="", verbose=False)
    
    expected = len(sim_recon.TIDB_PROBES)
    t(f"recon_tidb: 跑完 {expected} 个查询", len(results) == expected)
    t("recon_tidb: ssh.tidb 被调用",
      mock_ssh.tidb.call_count == expected)


def test_recon_full():
    """recon_full 包含 server + maccms + tidb 三个 section."""
    mock_ssh = make_mock_ssh()
    results = sim_recon.recon_full(mock_ssh, hub_url="", verbose=False)
    
    t("recon_full: 含 server", "server" in results)
    t("recon_full: 含 maccms", "maccms" in results)
    t("recon_full: 含 tidb", "tidb" in results)


def test_recon_full_skip_options():
    """recon_full 可关闭 maccms / tidb."""
    mock_ssh = make_mock_ssh()
    results = sim_recon.recon_full(mock_ssh, hub_url="", verbose=False,
                                    do_maccms=False, do_tidb=False)
    t("do_maccms=False: 不含 maccms", "maccms" not in results)
    t("do_tidb=False: 不含 tidb", "tidb" not in results)
    t("仍含 server", "server" in results)


def test_log_finding_serialization():
    """log_finding 的 payload 应当是 JSON 可序列化."""
    captured = {}
    
    def fake_urlopen(req, timeout=5):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = req.data.decode("utf-8")
        m = MagicMock()
        m.read.return_value = b'{"ok": true}'
        m.__enter__ = lambda self: m
        m.__exit__ = lambda *args: None
        return m
    
    with patch.object(sim_recon.urllib.request, "urlopen",
                      side_effect=fake_urlopen):
        ok, _ = sim_recon.log_finding(
            "http://test:8765", "server_analyst",
            "summary text",
            detail="detail",
            kind="environment",
            related_to=["main_designer"],
        )
    
    import json
    body = json.loads(captured.get("body", "{}"))
    t("log_finding: ok=True", ok is True)
    t("log_finding: URL 含 /log", "/log" in captured.get("url", ""))
    t("log_finding: method=POST", captured.get("method") == "POST")
    t("log_finding: kind=finding", body.get("kind") == "finding")
    t("log_finding: from=server_analyst", body.get("from") == "server_analyst")
    t("log_finding: type=environment", body.get("type") == "environment")
    t("log_finding: 含 detail", body.get("detail") == "detail")
    t("log_finding: 含 related_to", body.get("related_to") == ["main_designer"])


def test_hub_post_silent_failure():
    """_hub_post 失败不应抛错, 返回 (False, error)."""
    with patch.object(sim_recon.urllib.request, "urlopen",
                      side_effect=Exception("conn refused")):
        ok, msg = sim_recon._hub_post("http://test", "/log", {"kind": "finding"})
        t("_hub_post 失败静默: ok=False", ok is False)
        t("_hub_post 失败: msg 含错误", "conn refused" in msg)


def test_hub_post_no_url_returns_false():
    """空 hub_url 直接返回 (False, ...) 不报错."""
    ok, msg = sim_recon._hub_post("", "/log", {"kind": "finding"})
    t("空 hub_url: ok=False", ok is False)


def main():
    print("=" * 60)
    print("sim_recon.py unit tests")
    print("=" * 60)

    tests = [
        test_recon_server_runs_all_probes,
        test_recon_server_hub_post,
        test_recon_server_skip_empty_output,
        test_recon_server_handles_errors,
        test_recon_maccms,
        test_recon_tidb,
        test_recon_full,
        test_recon_full_skip_options,
        test_log_finding_serialization,
        test_hub_post_silent_failure,
        test_hub_post_no_url_returns_false,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as e:
            global FAILED
            FAILED += 1
            print(f"[ERROR] {fn.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
