"""
v5 角色 prompt 生成器

从 config/roles.yaml 读取角色定义, prompts/role_template_v5.md 读取模板,
渲染后输出到指定目录。

用法:
  python tools/generate_role_prompts_v5.py
  python tools/generate_role_prompts_v5.py --out-dir case/
  python tools/generate_role_prompts_v5.py --kb-base "D:\\kb\\techniques"
"""

import argparse
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from .core import load_yaml
except ImportError:
    from core import load_yaml

DEFAULT_OUT_DIR = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case")
DEFAULT_KB_BASE = r"e:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base\techniques"
ROLES_PATH = Path(__file__).resolve().parent.parent / "config" / "roles.yaml"
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "role_template_v5.md"


def main():
    parser = argparse.ArgumentParser(description="v5 角色 prompt 生成器")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help=f"输出目录 (默认: {DEFAULT_OUT_DIR})")
    parser.add_argument("--kb-base", type=str, default=DEFAULT_KB_BASE,
                        help="技巧卡根路径")
    parser.add_argument("--roles", type=Path, default=ROLES_PATH,
                        help=f"角色 YAML 文件 (默认: {ROLES_PATH})")
    parser.add_argument("--template", type=Path, default=TEMPLATE_PATH,
                        help=f"模板文件 (默认: {TEMPLATE_PATH})")
    args = parser.parse_args()

    roles = load_yaml(args.roles, default={})
    if not roles:
        print(f"ERROR: No roles found in {args.roles}")
        sys.exit(1)

    template = args.template.read_text(encoding="utf-8")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for role_short, cfg in roles.items():
        tech_paths = "\n".join(
            f"{args.kb_base}\\{t}.yaml"
            for t in cfg["techniques_to_read"]
        )

        text = template.format(
            title=cfg["title"],
            category=cfg["category"],
            techniques_paths=tech_paths,
            specific_lessons=cfg["specific_lessons"],
            evidence_desc=cfg["evidence_desc"],
            role_full=f"{cfg['category']}_analyst",
            human_collab_examples=cfg["human_collab_examples"],
            huoyan_tool_examples=cfg.get("huoyan_tool_examples",
                                          "(无角色专属示例, 见 5.2 通用例子)"),
        )

        out = args.out_dir / f"role_prompt_{role_short}_v5.md"
        out.write_text(text, encoding="utf-8")
        print(f"  OK {out}")

    print(f"\nGenerated {len(roles)} v5 role prompts -> {args.out_dir}")


if __name__ == "__main__":
    main()
