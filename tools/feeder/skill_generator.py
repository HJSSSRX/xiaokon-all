#!/usr/bin/env python3
"""喂食者核心模块 - 技能产出器"""
from pathlib import Path
import re
import yaml
from ..core import load_yaml, save_yaml, ensure_dir, now_str
from datetime import datetime


SKILL_DOMAINS = {
    "computer": {
        "name": "计算机",
        "subcategories": [
            "windows_forensics", "linux_forensics", "macos_forensics",
            "memory_forensics", "disk_forensics", "registry_analysis",
            "filesystem_analysis", "process_analysis",
            "privilege_escalation", "persistence_mechanisms",
        ],
        "dual_perspective": {
            "forensics": "从镜像反向还原攻击者行为 (what happened)",
            "offensive": "从攻击者视角利用弱点获取权限 (how to break in)",
        },
    },
    "mobile": {
        "name": "移动端",
        "subcategories": [
            "android_forensics", "ios_forensics", "app_analysis",
            "chat_forensics", "location_forensics", "device_identification",
            "mobile_hooking", "app_reversing", "mobile_pentest",
        ],
        "dual_perspective": {
            "forensics": "从手机镜像提取用户行为轨迹和关联证据",
            "offensive": "逆向/注入移动应用，绕过检测机制",
        },
    },
    "network": {
        "name": "网络",
        "subcategories": [
            "traffic_analysis", "protocol_analysis", "intrusion_detection",
            "webshell_detection", "attack_tracing",
            "port_scanning", "service_exploitation", "pivoting",
            "dns_tunneling", "c2_analysis",
        ],
        "dual_perspective": {
            "forensics": "从流量包还原攻击路径和C2通信",
            "offensive": "扫描/渗透/横向移动/隧道搭建",
        },
    },
    "server": {
        "name": "服务端",
        "subcategories": [
            "log_analysis", "web_server_forensics", "database_forensics",
            "mail_server_forensics", "middleware_forensics",
            "web_application_security", "container_escape",
        ],
        "dual_perspective": {
            "forensics": "从服务器镜像/日志追溯入侵点和数据泄露路径",
            "offensive": "Web漏洞利用/数据库提权/容器逃逸",
        },
    },
    "binary": {
        "name": "二进制",
        "subcategories": [
            "reverse_engineering", "malware_analysis",
            "exploit_development", "shellcode_analysis",
            "stack_overflow", "heap_exploitation", "format_string",
            "rop_chaining", "use_after_free", "ret2libc",
        ],
        "dual_perspective": {
            "forensics": "逆向恶意样本，提取 IOC 和加密逻辑",
            "offensive": "漏洞挖掘/Exploit编写/绕过保护机制",
        },
    },
    "web": {
        "name": "Web",
        "subcategories": [
            "sql_injection", "xss", "csrf", "ssrf",
            "file_upload", "command_injection", "file_inclusion",
            "deserialization", "template_injection", "ssi_injection",
            "authentication_bypass", "idor", "oauth_abuse",
        ],
        "dual_perspective": {
            "forensics": "审计 Web 日志和源码还原攻击入口点",
            "offensive": "渗透测试/漏洞利用/绕过WAF",
        },
    },
    "crypto": {
        "name": "密码学",
        "subcategories": [
            "classical_ciphers", "symmetric_crypto", "asymmetric_crypto",
            "hash_collision", "side_channel", "prng_bias",
            "cryptanalysis", "steganography", "digital_watermark",
        ],
        "dual_perspective": {
            "forensics": "破解加密证据/恢复被加密的数据",
            "offensive": "分析/利用密码实现缺陷",
        },
    },
    "cloud": {
        "name": "云/虚拟化",
        "subcategories": [
            "cloud_forensics", "vm_forensics", "container_forensics",
            "cloud_pentest", "serverless_exploitation",
        ],
        "dual_perspective": {
            "forensics": "从云环境/虚拟机/容器中恢复和关联证据",
            "offensive": "云服务配置利用/容器逃逸",
        },
    },
    "iot": {
        "name": "物联网/嵌入式",
        "subcategories": [
            "firmware_extraction", "uart_jtag", "spi_flash",
            "embedded_reversing", "radio_analysis",
        ],
        "dual_perspective": {
            "forensics": "从IoT设备提取固件和传感器数据",
            "offensive": "固件逆向/硬件调试接口利用",
        },
    },
}


def generate_skill_from_source(data: dict, kb_dir: str) -> str:
    """从知识来源产出技能"""
    kb_path = Path(kb_dir)

    domain, subcategory = _infer_domain_from_source(data)

    skill_dir = kb_path / "skills" / domain
    ensure_dir(skill_dir)

    title = data.get("title", "unknown").strip()
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", title[:50])

    text_content = data.get("text_content", "")
    code_blocks = data.get("code_blocks", [])

    skill_entry = {
        "name": title,
        "domain": domain,
        "category": subcategory,
        "summary": _generate_summary(text_content),
        "description": text_content[:1000] if text_content else "",
        "sources": [f"sources/articles/{domain}/{safe_name}"],
        "practice": [],
        "techniques": _extract_techniques(text_content),
        "tools": _extract_tools(text_content, code_blocks),
        "commands": _extract_commands(code_blocks),
        "difficulty": _infer_difficulty(text_content),
        "prerequisites": [],
        "related_skills": [],
        "tags": _extract_tags(data),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    skill_file = skill_dir / f"{safe_name}.yaml"
    with open(skill_file, "w", encoding="utf-8") as f:
        yaml.dump(skill_entry, f, allow_unicode=True, sort_keys=False)

    print(f"[SKILL] 从知识来源产出技能: {skill_file}")

    _update_skill_index(kb_path, domain, safe_name, skill_entry)

    return str(skill_file)


def generate_skill_from_practice(data: dict, kb_dir: str) -> str:
    """从解题实践产出技能"""
    kb_path = Path(kb_dir)

    domain, subcategory = _infer_domain_from_practice(data)

    skill_dir = kb_path / "skills" / domain
    ensure_dir(skill_dir)

    competition = data.get("competition", "unknown")
    question_id = data.get("question_id", "unknown")
    title = data.get("title", f"{competition}_{question_id}")

    skill_name = f"{competition}_{question_id}"
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", skill_name)

    skill_entry = {
        "name": f"{title} - 技能总结",
        "domain": domain,
        "category": subcategory,
        "summary": f"从 {competition} {question_id} 题目中总结的技能",
        "description": data.get("solution", ""),
        "sources": [],
        "practice": [f"practice/solved/{competition}/{question_id}"],
        "techniques": data.get("key_techniques", []),
        "tools": data.get("tools_used", []),
        "commands": data.get("commands_used", []),
        "difficulty": data.get("difficulty", "medium"),
        "prerequisites": [],
        "related_skills": [],
        "tags": data.get("tags", []),
        "key_findings": data.get("key_findings", []),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    skill_file = skill_dir / f"{safe_name}.yaml"
    with open(skill_file, "w", encoding="utf-8") as f:
        yaml.dump(skill_entry, f, allow_unicode=True, sort_keys=False)

    print(f"[SKILL] 从解题实践产出技能: {skill_file}")

    _update_skill_index(kb_path, domain, safe_name, skill_entry)

    return str(skill_file)


def merge_skills(kb_dir: str, skill_paths: list, output_name: str) -> str:
    """合并多个技能为一个综合技能"""
    kb_path = Path(kb_dir)

    merged_skill = {
        "name": output_name,
        "domain": "",
        "category": "",
        "summary": "",
        "description": "",
        "sources": [],
        "practice": [],
        "techniques": [],
        "tools": [],
        "commands": [],
        "difficulty": "medium",
        "prerequisites": [],
        "related_skills": [],
        "tags": [],
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    for skill_path in skill_paths:
        skill_file = kb_path / skill_path
        if skill_file.exists():
            with open(skill_file, "r", encoding="utf-8") as f:
                skill_data = yaml.safe_load(f)

            if not merged_skill["domain"]:
                merged_skill["domain"] = skill_data.get("domain", "")
            if not merged_skill["category"]:
                merged_skill["category"] = skill_data.get("category", "")

            merged_skill["sources"].extend(skill_data.get("sources", []))
            merged_skill["practice"].extend(skill_data.get("practice", []))
            merged_skill["techniques"].extend(skill_data.get("techniques", []))
            merged_skill["tools"].extend(skill_data.get("tools", []))
            merged_skill["commands"].extend(skill_data.get("commands", []))
            merged_skill["tags"].extend(skill_data.get("tags", []))

    for key in ["sources", "practice", "techniques", "tools", "commands", "tags"]:
        merged_skill[key] = list(set(merged_skill[key]))

    safe_name = re.sub(r'[\\/:*?"<>|]', "_", output_name)
    domain = merged_skill["domain"] or "computer"
    skill_file = kb_path / "skills" / domain / f"{safe_name}.yaml"
    skill_file.ensure_dir(parent)

    with open(skill_file, "w", encoding="utf-8") as f:
        yaml.dump(merged_skill, f, allow_unicode=True, sort_keys=False)

    print(f"[SKILL] 合并技能: {skill_file}")

    return str(skill_file)


def _infer_domain_from_source(data: dict) -> tuple:
    """从知识来源推断领域"""
    text = (data.get("title", "") + " " + data.get("text_content", "")[:1000]).lower()

    if any(kw in text for kw in ["windows", "注册表", "registry", "ntfs", "mft"]):
        return "computer", "windows_forensics"
    elif any(kw in text for kw in ["linux", "ubuntu", "centos", "ext4"]):
        return "computer", "linux_forensics"
    elif any(kw in text for kw in ["内存", "memory", "volatility", "进程", "process"]):
        return "computer", "memory_forensics"
    elif any(kw in text for kw in ["磁盘", "disk", "e01", "vmdk", "镜像"]):
        return "computer", "disk_forensics"
    elif any(kw in text for kw in ["android", "apk", "安卓"]):
        return "mobile", "android_forensics"
    elif any(kw in text for kw in ["ios", "iphone", "ipad", "苹果"]):
        return "mobile", "ios_forensics"
    elif any(kw in text for kw in ["微信", "wechat", "qq", "聊天"]):
        return "mobile", "chat_forensics"
    elif any(kw in text for kw in ["pcap", "流量", "traffic", "wireshark", "网络"]):
        return "network", "traffic_analysis"
    elif any(kw in text for kw in ["webshell", "木马", "后门"]):
        return "network", "webshell_detection"
    elif any(kw in text for kw in ["日志", "log", "access.log", "nginx", "apache"]):
        return "server", "log_analysis"
    elif any(kw in text for kw in ["数据库", "database", "mysql", "sql"]):
        return "server", "database_forensics"
    elif any(kw in text for kw in ["逆向", "reverse", "ida", "ghidra", "汇编"]):
        return "binary", "reverse_engineering"
    elif any(kw in text for kw in ["pwn", "exploit", "漏洞", "溢出", "uaf"]):
        return "binary", "exploit_development"
    elif any(kw in text for kw in ["恶意", "malware", "病毒", "木马"]):
        return "binary", "malware_analysis"
    elif any(kw in text for kw in ["rsa", "aes", "des", "加密", "解密", "密码"]):
        return "crypto", "encryption_decryption"
    elif any(kw in text for kw in ["隐写", "stego", "lsb", "图片隐藏"]):
        return "crypto", "steganography"
    elif any(kw in text for kw in ["docker", "k8s", "容器", "kubernetes"]):
        return "cloud", "container_forensics"
    elif any(kw in text for kw in ["虚拟机", "vm", "vmware", "kvm"]):
        return "cloud", "vm_forensics"

    return "computer", "general"


def _infer_domain_from_practice(data: dict) -> tuple:
    """从解题实践推断领域"""
    domain = data.get("domain", "").lower()
    tags = [t.lower() for t in data.get("tags", [])]
    text = " ".join(tags)

    if domain in ["computer", "c"]:
        if any(kw in text for kw in ["内存", "memory", "volatility"]):
            return "computer", "memory_forensics"
        return "computer", "general"
    elif domain in ["mobile", "m"]:
        return "mobile", "android_forensics"
    elif domain in ["network", "n"]:
        return "network", "traffic_analysis"
    elif domain in ["server", "s"]:
        return "server", "log_analysis"
    elif domain in ["binary", "b"]:
        return "binary", "exploit_development"

    return _infer_domain_from_source({"title": "", "text_content": text})


def _generate_summary(text: str) -> str:
    """生成技能摘要"""
    if not text:
        return ""
    sentences = text.split("。")
    return sentences[0][:100] if sentences else text[:100]


def _extract_techniques(text: str) -> list:
    """提取技术点"""
    techniques = []
    keywords = ["注入", "溢出", "逆向", "解密", "分析", "提取", "恢复", "检测", "追踪", "绕过"]
    for kw in keywords:
        if kw in text:
            techniques.append(kw)
    return techniques[:5]


def _extract_tools(text: str, code_blocks: list) -> list:
    """提取工具"""
    tools = []
    tool_keywords = [
        "volatility", "wireshark", "ida", "ghidra", "sqlmap",
        "burpsuite", "nmap", "foremost", "binwalk", "tshark",
    ]
    text_lower = text.lower()
    for tool in tool_keywords:
        if tool in text_lower:
            tools.append(tool)
    return tools


def _extract_commands(code_blocks: list) -> list:
    """提取命令"""
    commands = []
    for cb in code_blocks[:5]:
        code = cb.get("code", "")
        lines = code.split("\n")
        for line in lines:
            line = line.strip()
            if line and (line.startswith("$") or line.startswith("#") or
                        line.startswith("python") or line.startswith("vol") or
                        line.startswith("tshark")):
                commands.append(line[:100])
    return commands[:10]


def _infer_difficulty(text: str) -> str:
    """推断难度"""
    if any(kw in text for kw in ["基础", "入门", "简单", "basic"]):
        return "easy"
    elif any(kw in text for kw in ["高级", "进阶", "复杂", "advanced"]):
        return "hard"
    return "medium"


def _extract_tags(data: dict) -> list:
    """提取标签"""
    text = data.get("title", "") + " " + data.get("text_content", "")[:500]
    keywords = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return list(set(keywords))[:10]


def _update_skill_index(kb_path: Path, domain: str, name: str, entry: dict):
    """更新技能索引"""
    index_file = kb_path / "skills" / "_index.yaml"
    index_data = {"skills": {}}

    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            index_data = yaml.safe_load(f) or {"skills": {}}

    if domain not in index_data.get("skills", {}):
        index_data["skills"][domain] = []

    index_data["skills"][domain].append({
        "name": entry["name"],
        "path": f"skills/{domain}/{name}.yaml",
        "category": entry.get("category", ""),
        "tags": entry.get("tags", []),
    })

    with open(index_file, "w", encoding="utf-8") as f:
        yaml.dump(index_data, f, allow_unicode=True, sort_keys=False)
