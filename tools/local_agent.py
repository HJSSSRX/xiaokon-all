#!/usr/bin/env python3
"""Local Agent — 低算力 AI 接入 AutoForensicAI 协作系统.

两种模式:
  offline  纯本地 (断网比赛, Ollama / vLLM / llama.cpp)
  remote   API 远程 (DeepSeek / OpenAI / Anthropic)

用法:
  # 离线模式 (默认)
  python tools/local_agent.py --role mobile_analyst

  # 远程模式
  python tools/local_agent.py --mode remote --role computer_analyst

  # 指定模型
  python tools/local_agent.py --model qwen2.5:14b

配置: config/agent.yaml
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ─── 路径 ───
_TOOLS_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))

# ─── 安全白名单: 允许执行的取证工具 ───
_ALLOWED_TOOLS = {
    # 取证核心
    "vol3", "volatility3", "vol.py",
    "strings", "exiftool", "file", "stat", "md5sum", "sha256sum", "sha1sum",
    "sqlite3", "sqlite3.exe",
    "tshark", "tcpdump", "nmap",
    "binwalk", "foremost", "testdisk", "photorec",
    "john", "hashcat", "zip2john", "rar2john",
    "steghide", "zsteg", "exif", "identify", "ffprobe",
    "regripper", "rip", "chainsaw", "hayabusa",
    "base64", "xxd", "hexdump", "od",
    "grep", "find", "ls", "cat", "head", "tail", "wc", "sort", "uniq", "cut", "awk", "sed",
    "python3", "python", "py",
    "adb", "7z", "unzip", "tar", "mount", "losetup",
    # Windows 命令
    "dir", "type", "findstr", "icacls", "reg", "powershell",
    # 项目工具
    "kb_search", "comp_search",
}
_DENIED_PATTERNS = [
    r"rm\s+(-rf?|--)", r"del\s+/[fsq]", r"format\s", r"mkfs",
    r">\s*/dev/", r"dd\s+if=", r"shutdown", r"reboot",
    r"curl\s", r"wget\s", r"nc\s", r"netcat",
    r"pip\s+install", r"npm\s+install", r"apt\s", r"yum\s",
    r"chmod\s+777", r"eval\s", r"exec\s", r"systemctl",
]


# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

def _load_agent_config(path=None):
    import yaml as _yaml
    p = Path(path or _PROJECT_DIR / "config" / "agent.yaml")
    if not p.exists():
        raise FileNotFoundError(f"Agent config not found: {p}")
    return _yaml.safe_load(p.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════
# Model Backends — 支持 6 种推理后端
# ═══════════════════════════════════════════════════════════════════

class OpenAIBackend:
    """OpenAI-compatible /v1/chat/completions — 兼容绝大多数推理引擎.

    支持的引擎: vLLM, llama.cpp (server), LM Studio, LocalAI, Ollama(v1),
               text-generation-webui (OpenAI extension), DeepSeek, Groq, 等.
    """
    name = "openai"

    def __init__(self, endpoint, model, api_key="", max_tokens=2048, temperature=0.1):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, messages):
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        req = urllib.request.Request(
            f"{self.endpoint}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            return f"[HTTP {e.code}] {e.read().decode('utf-8', errors='replace')[:500]}"
        except Exception as e:
            return f"[Error] {e}"


class OllamaBackend:
    """Ollama 原生 /api/chat — 无需 OpenAI 兼容层，直接调 Ollama 原生协议。

    优势: 支持 Ollama 特有参数 (num_ctx, num_predict, keep_alive 等)
    """
    name = "ollama"

    def __init__(self, endpoint, model, api_key="", max_tokens=2048, temperature=0.1):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, messages):
        url = f"{self.endpoint}/api/chat"
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))["message"]["content"]
        except urllib.error.HTTPError as e:
            return f"[HTTP {e.code}] {e.read().decode('utf-8', errors='replace')[:500]}"
        except Exception as e:
            return f"[Error] {e}"


class KoboldBackend:
    """KoboldCPP /api/v1/generate — 兼容 Kobold 系列推理引擎.

    适用: KoboldCPP, KoboldAI United, text-generation-webui (Kobold mode)
    """
    name = "kobold"

    def __init__(self, endpoint, model, api_key="", max_tokens=2048, temperature=0.1):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, messages):
        # Kobold 用 prompt 字符串，将 messages 拼接
        prompt_parts = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                prompt_parts.append(f"<|system|>\n{content}\n")
            elif role == "user":
                prompt_parts.append(f"<|user|>\n{content}\n")
            elif role == "assistant":
                prompt_parts.append(f"<|assistant|>\n{content}\n")
        prompt = "".join(prompt_parts) + "<|assistant|>\n"

        url = f"{self.endpoint}/api/v1/generate"
        body = {
            "prompt": prompt,
            "max_length": self.max_tokens,
            "temperature": self.temperature,
            "max_context_length": 8192,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))["results"][0]["text"]
        except urllib.error.HTTPError as e:
            return f"[HTTP {e.code}] {e.read().decode('utf-8', errors='replace')[:500]}"
        except Exception as e:
            return f"[Error] {e}"


class OobaboogaBackend:
    """text-generation-webui (oobabooga) /api/v1/chat — 原生 Chat API。

    适用: oobabooga text-generation-webui (非 OpenAI 扩展模式)
    """
    name = "oobabooga"

    def __init__(self, endpoint, model, api_key="", max_tokens=2048, temperature=0.1):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, messages):
        # oobabooga /api/v1/chat 用 user_input / history 格式
        history = []
        user_input = ""
        for m in messages:
            if m["role"] == "system":
                history.append(["<|system|>", m["content"]])
            elif m["role"] == "user":
                if history:
                    history.append([user_input, ""])
                user_input = m["content"]
            elif m["role"] == "assistant":
                if history:
                    history[-1][1] = m["content"]

        url = f"{self.endpoint}/api/v1/chat"
        body = {
            "user_input": user_input,
            "history": {"internal": history, "visible": []},
            "mode": "chat",
            "max_new_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["results"][0]["history"]["visible"][-1][1]
        except urllib.error.HTTPError as e:
            return f"[HTTP {e.code}] {e.read().decode('utf-8', errors='replace')[:500]}"
        except Exception as e:
            return f"[Error] {e}"


class AnthropicBackend:
    """Anthropic Messages API — Claude 系列模型。"""
    name = "anthropic"

    def __init__(self, endpoint, model, api_key="", max_tokens=4096, temperature=0.1):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, messages):
        url = f"{self.endpoint}/messages"
        system = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            elif m["role"] == "user":
                user_msgs.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                user_msgs.append({"role": "assistant", "content": m["content"]})

        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": user_msgs,
        }
        if system:
            body["system"] = system

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))["content"][0]["text"]
        except urllib.error.HTTPError as e:
            return f"[HTTP {e.code}] {e.read().decode('utf-8', errors='replace')[:500]}"
        except Exception as e:
            return f"[Error] {e}"


# ── 后端注册表 ────────────────────────────────────────────────────

BACKENDS = {
    "openai": OpenAIBackend,         # vLLM, llama.cpp, LM Studio, LocalAI, Groq
    "ollama": OllamaBackend,         # Ollama 原生
    "kobold": KoboldBackend,         # KoboldCPP
    "oobabooga": OobaboogaBackend,   # text-generation-webui
    "anthropic": AnthropicBackend,   # Claude API
}


def _create_backend(config):
    """根据配置创建后端实例。

    配置优先级: mode.{backend} 字段 → mode 推断 → 默认 openai
    """
    mode = config["agent"]["mode"]
    section = config.get(mode, {})
    backend_name = section.get("backend", "")

    api_key = os.environ.get(section.get("api_key_env", ""), section.get("api_key", ""))
    endpoint = section.get("endpoint", "http://localhost:11434/v1")
    model = section.get("model", "qwen2.5:7b")
    max_tokens = section.get("max_tokens", 2048)
    temperature = section.get("temperature", 0.1)

    # 1) 显式指定 backend
    if backend_name and backend_name in BACKENDS:
        return BACKENDS[backend_name](endpoint, model, api_key, max_tokens, temperature)

    # 2) remote 模式: 从 provider 字段推断
    if mode == "remote":
        provider = section.get("provider", "")
        if provider == "anthropic":
            return AnthropicBackend(endpoint, model, api_key, max_tokens, temperature)
        return OpenAIBackend(endpoint, model, api_key, max_tokens, temperature)

    # 3) offline 模式: 从 endpoint 路径推断
    ep = endpoint.lower()
    if "/api/chat" in ep or ("ollama" in ep and "/v1" not in ep):
        return OllamaBackend(endpoint, model, api_key, max_tokens, temperature)
    if "kobold" in ep or "generate" in ep:
        return KoboldBackend(endpoint, model, api_key, max_tokens, temperature)
    if "oobabooga" in ep or "text-generation" in ep:
        return OobaboogaBackend(endpoint, model, api_key, max_tokens, temperature)

    # 默认: OpenAI-compatible（最通用）
    return OpenAIBackend(endpoint, model, api_key, max_tokens, temperature)


# ═══════════════════════════════════════════════════════════════════
# KB Search
# ═══════════════════════════════════════════════════════════════════

def _kb_search(query, kb_root):
    """用项目自带的 kb_search 搜索, 返回摘要字符串."""
    try:
        from kb_search import consultant_search, extract_search_terms
        from kb_search import search_by_tags, search_by_tools, search_by_text

        kb = Path(kb_root)
        if not kb.exists():
            return "(知识库目录不存在)"

        tags, tools, text_terms = extract_search_terms(query)
        scored = {}
        if tags:
            for f, fm, preview in search_by_tags(kb, tags):
                scored[str(f)] = (scored.get(str(f), (0,))[0] + 2, fm, preview)
        if tools:
            for f, fm, preview in search_by_tools(kb, tools):
                scored[str(f)] = (scored.get(str(f), (0,))[0] + 2, fm, preview)
        for term in text_terms:
            for f, context in search_by_text(kb, term):
                scored[str(f)] = (scored.get(str(f), (0,))[0] + 1, None, context)

        if not scored:
            return "(知识库中未找到相关内容)"

        ranked = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)[:3]
        lines = []
        for filepath, (score, fm, ctx) in ranked:
            name = Path(filepath).name
            lines.append(f"[{score}pts] {name}")
            if fm:
                lines.append(f"  Tags: {fm.get('tags', [])}  Tools: {fm.get('tools', [])}")
            if ctx:
                lines.append(f"  {ctx[:300]}")
        return "\n".join(lines)
    except Exception as e:
        return f"(KB搜索异常: {e})"


# ═══════════════════════════════════════════════════════════════════
# Tool Sandbox
# ═══════════════════════════════════════════════════════════════════

def _validate_command(cmd):
    """检查命令是否在安全白名单内, 拒绝危险操作."""
    cmd_stripped = cmd.strip()

    # 禁止模式检查
    for pat in _DENIED_PATTERNS:
        if re.search(pat, cmd_stripped, re.IGNORECASE):
            return False, f"禁止: 匹配危险模式 '{pat}'"

    # 白名单: 取第一个词 (去掉路径)
    first_word = cmd_stripped.split()[0] if cmd_stripped.split() else ""
    base = os.path.basename(first_word)

    if base in _ALLOWED_TOOLS:
        return True, ""

    # 特殊: 允许 python/python3 运行项目内脚本
    if base in ("python3", "python", "py"):
        parts = cmd_stripped.split()
        if len(parts) >= 2:
            script = parts[1]
            if script.startswith("tools/") or script in ("-c", "-m"):
                return True, ""
        return False, f"Python 脚本路径不在允许范围: {cmd_stripped[:80]}"

    # 允许 WSL 路径格式
    if "wsl" in base.lower():
        return True, ""

    return False, f"工具不在白名单: '{base}'"


def _run_tool(cmd, cwd, timeout=120):
    """在指定目录执行命令, 返回 stdout+stderr (截断)."""
    ok, err = _validate_command(cmd)
    if not ok:
        return f"[拒绝执行] {err}"

    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True,
            timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        out = result.stdout
        if result.stderr:
            out += "\n[stderr]\n" + result.stderr
        if len(out) > 3000:
            out = out[:1500] + "\n... (截断) ...\n" + out[-1500:]
        return out or "(命令无输出, rc={})".format(result.returncode)
    except subprocess.TimeoutExpired:
        return f"[超时] 命令超过 {timeout}s 被终止"
    except Exception as e:
        return f"[执行异常] {e}"


# ═══════════════════════════════════════════════════════════════════
# Hub Client
# ═══════════════════════════════════════════════════════════════════

def _hub_post(hub_url, role, action, payload):
    """向 Hub 发送 POST /log。复用 role_log 协议。"""
    url = f"{hub_url.rstrip('/')}/log"
    body = {"role": role, "action": action, **payload}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _hub_get_unsolved(hub_url, role):
    """从 Hub 获取未解题目列表。"""
    try:
        url = f"{hub_url.rstrip('/')}/questions?role={role}&status=unsolved"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════
# Prompt Builder
# ═══════════════════════════════════════════════════════════════════

def _load_compact_template():
    p = _TOOLS_DIR.parent / "prompts" / "agent_compact.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "{title}\n{role_full}\n{evidence_desc}\n{case_dir}\n{questions_summary}\n{kb_context}\n{last_action}"


def _load_roles_config():
    import yaml as _yaml
    p = _PROJECT_DIR / "config" / "roles.yaml"
    if p.exists():
        return _yaml.safe_load(p.read_text(encoding="utf-8"))
    return {}


def _build_prompt(template, role_key, case_dir, questions, kb_context, last_action):
    roles = _load_roles_config()
    role_info = roles.get(role_key, roles.get("computer", {}))
    title = role_info.get("title", role_key)
    evidence = role_info.get("evidence_desc", "未知检材")
    role_full = role_key

    q_summary = "\n".join(
        f"- Q{q.get('qid','?')}: {q.get('title','')} (状态:{q.get('status','unsolved')})"
        for q in (questions or [{"qid": "?", "title": "等待Hub返回题目"}])
    ) if questions else "(等待Hub返回题目列表)"

    return (
        template
        .replace("{title}", str(title))
        .replace("{role_full}", str(role_full))
        .replace("{evidence_desc}", str(evidence))
        .replace("{case_dir}", str(case_dir))
        .replace("{questions_summary}", q_summary)
        .replace("{kb_context}", kb_context or "(暂未检索)")
        .replace("{last_action}", last_action or "(首轮)")
    )


# ═══════════════════════════════════════════════════════════════════
# Response Parser
# ═══════════════════════════════════════════════════════════════════

def _parse_response(text):
    """解析小模型输出, 提取操作指令."""
    if not text:
        return {"type": "unknown", "content": "(空响应)"}

    # 检查是不是错误信息
    if text.startswith("[Error]") or text.startswith("[HTTP"):
        return {"type": "error", "content": text}

    # TOOL: command
    m = re.search(r'TOOL:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        return {"type": "tool", "command": m.group(1).strip()}

    # KB_SEARCH: query
    m = re.search(r'KB_SEARCH:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        return {"type": "kb_search", "query": m.group(1).strip()}

    # ANSWER: <answer>
    m = re.search(r'ANSWER:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        ans = m.group(1).strip()
        # try to extract confidence
        conf_m = re.search(r'confidence[:=]\s*(\w+)', text, re.IGNORECASE)
        conf = conf_m.group(1) if conf_m else "single_source_high"
        # try to extract qid
        qid_m = re.search(r'(?:qid|Q)["\s:=]*(\w+)', text)
        qid = qid_m.group(1) if qid_m else "?"
        return {"type": "answer", "qid": qid, "answer": ans, "confidence": conf}

    # LOG_NEED: description
    m = re.search(r'LOG_NEED:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        return {"type": "log_need", "description": m.group(1).strip()}

    # 如果模型直接输出了答案而没有指令前缀
    # 尝试找最后一行的简短文本作为答案
    lines = [l.strip() for l in text.strip().split("\n") if l.strip() and not l.startswith("#")]
    if lines and len(lines[-1]) < 200:
        return {"type": "answer", "qid": "?", "answer": lines[-1], "confidence": "single_source_high"}

    return {"type": "unknown", "content": text[:500]}


# ═══════════════════════════════════════════════════════════════════
# Main Agent Loop
# ═══════════════════════════════════════════════════════════════════

class LocalAgent:
    def __init__(self, config_path=None, role_override=None, mode_override=None,
                 model_override=None, endpoint_override=None, backend_override=None):
        self.config = _load_agent_config(config_path)
        if mode_override:
            self.config["agent"]["mode"] = mode_override
        if role_override:
            self.config["agent"]["role"] = role_override
        target = self.config["agent"]["mode"]
        if model_override:
            self.config[target]["model"] = model_override
        if endpoint_override:
            self.config[target]["endpoint"] = endpoint_override
        if backend_override:
            self.config[target]["backend"] = backend_override

        self.mode = self.config["agent"]["mode"]
        self.role = self.config["agent"]["role"]
        self.hub_url = self.config["agent"]["hub_url"]
        self.case_dir = self.config["agent"]["case_dir"]
        self.kb_root = self.config["agent"]["kb_root"]
        self.max_rounds = self.config["agent"]["max_rounds"]
        self.tool_timeout = self.config["agent"]["tool_timeout"]

        self.backend = _create_backend(self.config)
        self.template = _load_compact_template()
        self.messages = []
        self.round = 0

    def _system_prompt(self, questions, kb_context, last_action):
        return _build_prompt(
            self.template, self.role, self.case_dir,
            questions, kb_context, last_action
        )

    def run(self):
        backend_name = getattr(self.backend, "name", "?")
        print(f"╔══════════════════════════════════════════════╗")
        print(f"║  AutoForensicAI Local Agent                 ║")
        print(f"║  Mode: {self.mode:<10} Backend: {backend_name:<14} ║")
        print(f"║  Role: {self.role:<28} ║")
        print(f"║  Model: {self.backend.model:<28} ║")
        print(f"║  Hub: {self.hub_url:<30} ║")
        print(f"╚══════════════════════════════════════════════╝")
        print()

        questions = _hub_get_unsolved(self.hub_url, self.role)
        kb_context = ""
        last_action = "首轮启动"

        while self.round < self.max_rounds:
            self.round += 1
            print(f"\n{'='*50}")
            print(f"  Round {self.round}/{self.max_rounds}")
            print(f"{'='*50}")

            # 刷新题目列表
            if self.round % 5 == 0:
                questions = _hub_get_unsolved(self.hub_url, self.role)
                if questions:
                    print(f"  Hub: {len(questions)} 题待解")

            # 构建系统提示
            system = self._system_prompt(questions, kb_context, last_action)

            # 构建消息
            self.messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": "分析当前状态, 输出下一步操作."},
            ]

            # 调用模型
            print(f"  → 调用 {self.backend.model} ...")
            response = self.backend.chat(self.messages)
            print(f"  ← 响应 ({len(response)} chars)")
            print(f"  {response[:200]}...")

            # 解析
            action = _parse_response(response)
            print(f"  Action: {action['type']}")

            if action["type"] == "tool":
                cmd = action["command"]
                print(f"  Run: {cmd[:100]}")
                result = _run_tool(cmd, self.case_dir, self.tool_timeout)
                last_action = f"执行: {cmd[:100]}\n结果:\n{result[:800]}"
                # 追加到消息历史
                self.messages.append({"role": "assistant", "content": response})
                self.messages.append({"role": "user", "content": f"命令输出:\n{result[:1500]}"})
                print(f"  → {len(result)} chars output")

            elif action["type"] == "kb_search":
                print(f"  Search: {action['query'][:80]}")
                kb_context = _kb_search(action["query"], self.kb_root)
                last_action = f"知识库搜索: {action['query']}\n结果:\n{kb_context[:500]}"
                print(f"  → {len(kb_context)} chars")

            elif action["type"] == "answer":
                qid = action["qid"]
                ans = action["answer"]
                conf = action["confidence"]
                print(f"  Answer Q{qid}: {ans} ({conf})")
                result = _hub_post(self.hub_url, self.role, "log_answer", {
                    "qid": qid, "answer": ans, "confidence": conf,
                })
                last_action = f"提交答案 Q{qid}: {ans} ({conf}) → Hub响应: {result}"
                print(f"  → Hub: {result.get('status', result)}")

            elif action["type"] == "log_need":
                desc = action["description"]
                print(f"  Need: {desc[:80]}")
                result = _hub_post(self.hub_url, self.role, "log_need", {
                    "item": desc,
                })
                last_action = f"求助: {desc} → Hub响应: {result}"
                print(f"  → Hub: {result.get('status', result)}")

            elif action["type"] == "error":
                print(f"  ✗ 模型调用错误: {action['content'][:200]}")
                last_action = f"错误: {action['content'][:200]}"
                time.sleep(3)  # 错误时等3秒再重试

            else:
                print(f"  ? 无法解析模型输出, 等待下一轮")
                last_action = f"无法解析: {response[:300]}"

            # 已完成全部题目?
            if action["type"] == "answer":
                questions = _hub_get_unsolved(self.hub_url, self.role)
                if not questions:
                    print(f"\n  ✓ 所有题目已解决!")
                    break

            # 轮次间隔
            time.sleep(1)

        print(f"\n{'='*50}")
        print(f"  Agent 结束. 共 {self.round} 轮.")
        print(f"{'='*50}")


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="AutoForensicAI Local Agent — 低算力AI接入"
    )
    parser.add_argument("--mode", choices=["offline", "remote"],
                        help="offline=纯本地 | remote=API远程 (默认用config)")
    parser.add_argument("--backend", choices=list(BACKENDS),
                        help=f"推理后端: {', '.join(BACKENDS)}")
    parser.add_argument("--role", default="computer_analyst",
                        help="角色 (default: computer_analyst)")
    parser.add_argument("--model", help="覆盖模型名")
    parser.add_argument("--endpoint", help="覆盖API endpoint")
    parser.add_argument("--config", help="配置文件路径 (default: config/agent.yaml)")
    parser.add_argument("--list-roles", action="store_true", help="列出所有可用角色")
    parser.add_argument("--list-backends", action="store_true", help="列出所有支持的后端及兼容引擎")

    args = parser.parse_args()

    if args.list_backends:
        print("支持的后端:")
        for name, cls in BACKENDS.items():
            doc = cls.__doc__.strip().split("\n")[0] if cls.__doc__ else "(无描述)"
            print(f"  {name:<12} — {doc}")
        print(f"\n兼容的推理引擎:")
        print(f"  openai    → vLLM, llama.cpp, LM Studio, LocalAI, DeepSeek, Groq, ...")
        print(f"  ollama    → Ollama 原生 API")
        print(f"  kobold    → KoboldCPP")
        print(f"  oobabooga → text-generation-webui")
        print(f"  anthropic → Claude (Anthropic API)")
        return

    if args.list_roles:
        roles = _load_roles_config()
        for k, v in roles.items():
            print(f"  {k}: {v.get('title', '?')} — {v.get('evidence_desc', '?')}")
        return

    agent = LocalAgent(
        config_path=args.config,
        role_override=args.role,
        mode_override=args.mode,
        model_override=args.model,
        endpoint_override=args.endpoint,
        backend_override=args.backend,
    )
    agent.run()


if __name__ == "__main__":
    main()
