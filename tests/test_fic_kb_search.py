"""
fic_kb_search.py smoke test - 验证 v5 prompt 强制依赖的工具能跑.

v5 prompt 强制要求每个角色启动时跑:
  python3 e:\项目\自动化取证\tools\fic_kb_search.py --category {role_category}
  python3 e:\项目\自动化取证\tools\fic_kb_search.py --result incorrect

如果这工具坏了, v5 prompt 强依赖会一起塌方.

Run:
  python3 tests/test_fic_kb_search.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "fic_kb_search.py"

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


def run_tool(args):
    """跑工具, 返回 (returncode, stdout 长度). UTF-8 强制."""
    r = subprocess.run(
        [sys.executable, str(TOOL)] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    return r.returncode, r.stdout, r.stderr


def test_tool_exists():
    t("fic_kb_search.py 文件存在", TOOL.exists())


def test_help():
    rc, out, err = run_tool(["--help"])
    t("--help 退出码 0", rc == 0)
    t("--help 输出含 keywords/category/result/tech 子命令",
      all(x in out for x in ["keywords", "category", "result", "tech"]))


def test_category_subcommands():
    """v5 prompt 5 个角色每个调一次 --category"""
    for cat in ["computer", "mobile", "server", "internet", "binary"]:
        rc, out, err = run_tool(["--category", cat])
        t(f"--category {cat} 退出码 0", rc == 0)
        t(f"--category {cat} 输出非空", len(out) > 100)
        t(f"--category {cat} 输出含 FIC2026", "FIC2026" in out)


def test_result_incorrect():
    """v5 prompt 强制 --result incorrect 看错题"""
    rc, out, err = run_tool(["--result", "incorrect"])
    t("--result incorrect 退出码 0", rc == 0)
    # 我们这次错了 12 题, 应该看到大量 ❌ 标记
    cross_count = out.count("❌")
    t(f"--result incorrect 含 12 个错答 (实际 {cross_count})",
      cross_count >= 10)


def test_keywords_search():
    """关键词搜索: 子命令 + 位置参数 (nargs='+'), 也支持顶层 --keywords"""
    # 子命令形式
    rc, out, err = run_tool(["keywords", "maccms"])
    t("keywords maccms 退出码 0", rc == 0, err[:200])
    t("keywords maccms 输出非空", len(out) > 50)
    # 顶层别名形式 (v5 prompt 用这种)
    rc, out, err = run_tool(["--keywords", "maccms"])
    t("--keywords maccms (顶层别名) 退出码 0", rc == 0, err[:200])
    t("--keywords maccms 输出非空", len(out) > 50)


def test_question_natural_language():
    """自然语言提问: 子命令 + 位置参数, 也支持顶层 --question"""
    rc, out, err = run_tool(["question", "VC 容器密码"])
    t("question 'VC 容器密码' 退出码 0", rc == 0, err[:200])
    t("question 输出非空", len(out) > 50)
    rc, out, err = run_tool(["--question", "VC 容器密码"])
    t("--question (顶层别名) 退出码 0", rc == 0, err[:200])
    t("--question 输出非空", len(out) > 50)


def test_tech_subcommand():
    """技巧卡检索 (v5 prompt 强制读)"""
    rc, out, err = run_tool(["tech", "maccms"])
    t("tech maccms 退出码 0", rc == 0, err[:200])
    t("tech maccms 输出非空", len(out) > 20)


def test_unknown_args():
    """未知参数应当退出码非 0"""
    rc, _, _ = run_tool(["--invalid-arg-zzz"])
    t("无效参数 -> 非 0 退出码", rc != 0)


def main():
    print("=" * 60)
    print("fic_kb_search.py smoke test")
    print("=" * 60)

    if not TOOL.exists():
        print(f"[CRITICAL] 工具文件不存在: {TOOL}")
        return 1

    test_tool_exists()
    test_help()
    test_category_subcommands()
    test_result_incorrect()
    test_keywords_search()
    test_question_natural_language()
    test_tech_subcommand()
    test_unknown_args()

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
