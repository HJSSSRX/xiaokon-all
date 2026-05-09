"""
一键跑所有测试. 比赛前 / 改完代码后调一下.

Run:
  python3 tests/run_all.py
"""
import subprocess
import sys
from pathlib import Path

TESTS = [
    ("test_collab_hub.py",         "Hub 老端点 (findings/answers/questions/session/files)"),
    ("test_hub_v04_endpoints.py",  "Hub v0.4 新端点 (needs/heartbeat/answer-lock)"),
    ("test_dashboard_heartbeat.py","Dashboard 心跳列 (静态 + e2e)"),
    ("test_ssh_helper.py",         "SSH 助手 (init/run/lxc-attach/mysql/quote)"),
    ("test_sim_recon.py",          "仿真巡检 (server/maccms/tidb)"),
    ("test_fic_kb_search.py",      "知识库检索 (v5 prompt 强依赖)"),
    ("test_huoyan_adapter.py",     "火眼 MCP-Server 客户端 (HTTP mock)"),
    ("test_multi_machine.py",      "多机协作工具 (setup_machine/build_kb_index/safe_push)"),
    ("test_parse_yaml.py",         "YAML 格式回归 (老测试)"),
    ("test_prompt_gen.py",         "Prompt 生成 (老测试)"),
]

ROOT = Path(__file__).resolve().parent

def main():
    print("=" * 70)
    print("AutoForensicAI 测试总运行器")
    print("=" * 70)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test_file, desc in TESTS:
        path = ROOT / test_file
        if not path.exists():
            print(f"[SKIP] {test_file}  (文件不存在)")
            skipped += 1
            continue
        
        print(f"\n{'─' * 70}")
        print(f"运行: {test_file}  -- {desc}")
        print(f"{'─' * 70}")
        
        r = subprocess.run([sys.executable, str(path)],
                          capture_output=False)
        if r.returncode == 0:
            passed += 1
            print(f"[OK]   {test_file}")
        else:
            failed += 1
            print(f"[FAIL] {test_file}  rc={r.returncode}")
    
    print()
    print("=" * 70)
    print(f"测试套件汇总: PASSED={passed}  FAILED={failed}  SKIPPED={skipped}")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
