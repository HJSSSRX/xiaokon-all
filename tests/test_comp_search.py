"""
comp_search.py smoke test - 验证多赛事知识库检索工具能跑.

Run:
  python3 tests/test_comp_search.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "kb" / "comp_search.py"

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
    t("comp_search.py 文件存在", TOOL.exists())


def test_help():
    rc, out, err = run_tool(["--help"])
    t("--help 退出码 0", rc == 0)
    t("--help 输出含 keywords/category/result/tech 子命令",
      all(x in out for x in ["keywords", "category", "result", "tech"]))


def test_category_no_hardcoded_choices():
    """--category 不再限制取值，传任意字符串都应尝试检索（KB 可能没数据）"""
    rc, out, err = run_tool(["--category", "computer"])
    # 可能退出 0（有数据）或 2（没 KB 根目录），二者都不是 argparse 的 usage error (2 的另一种)
    t("--category computer 不是 argparse 错误 (usage error)",
      "usage:" not in err.lower() and "invalid choice" not in err.lower())


def test_category_unknown_ok():
    """任意分类名都能被接受（不再限制为 5 个固定值）"""
    rc, out, err = run_tool(["--category", "iot_forensics"])
    t("--category iot_forensics 被接受 (非 invalid choice)",
      "invalid choice" not in err.lower())


def test_keywords_search():
    rc, out, err = run_tool(["keywords", "maccms"])
    t("keywords maccms 不 crash", rc in (0, 2), err[:200])
    rc, out, err = run_tool(["--keywords", "maccms"])
    t("--keywords maccms (顶层别名) 不 crash", rc in (0, 2), err[:200])


def test_question_natural_language():
    rc, out, err = run_tool(["question", "VC 容器密码"])
    t("question 'VC 容器密码' 不 crash", rc in (0, 2), err[:200])
    rc, out, err = run_tool(["--question", "VC 容器密码"])
    t("--question (顶层别名) 不 crash", rc in (0, 2), err[:200])


def test_tech_subcommand():
    rc, out, err = run_tool(["tech", "maccms"])
    t("tech maccms 不 crash", rc in (0, 2), err[:200])


def test_result_incorrect():
    rc, out, err = run_tool(["--result", "incorrect"])
    t("--result incorrect 不 crash", rc in (0, 2), err[:200])


def test_unknown_args():
    """未知参数应当退出码非 0"""
    rc, _, _ = run_tool(["--invalid-arg-zzz"])
    t("无效参数 -> 非 0 退出码", rc != 0)


def main():
    print("=" * 60)
    print("comp_search.py smoke test")
    print("=" * 60)

    if not TOOL.exists():
        print(f"[CRITICAL] 工具文件不存在: {TOOL}")
        return 1

    test_tool_exists()
    test_help()
    test_category_no_hardcoded_choices()
    test_category_unknown_ok()
    test_keywords_search()
    test_question_natural_language()
    test_tech_subcommand()
    test_result_incorrect()
    test_unknown_args()

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
