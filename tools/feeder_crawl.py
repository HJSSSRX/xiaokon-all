#!/usr/bin/env python3
"""
喂食者 - 知识库爬虫工具

用法:
    python tools/feeder_crawl.py crawl <url> [--output <dir>]
    python tools/feeder_crawl.py parse <html_file>
    python tools/feeder_crawl.py organize <json_file> <kb_dir>
    python tools/feeder_crawl.py link <kb_dir>
    python tools/feeder_crawl.py batch <url_file>

快捷指令: "小空自己托"

外部存储配置:
    --storage <path>           命令行指定外部存储路径
    $env:FEEDER_STORAGE=path   环境变量配置外部存储（单独硬盘）

示例:
    # 使用外部硬盘 E 盘存储
    python tools/feeder_crawl.py crawl https://example.com --storage E:\feeder_data
    
    # 使用环境变量配置
    $env:FEEDER_STORAGE = "F:\knowledge_feeder"
    python tools/feeder_crawl.py batch urls.txt
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("请先安装依赖: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("请先安装依赖: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent

FEEDER_STORAGE_ENV = "FEEDER_STORAGE"
DEFAULT_FEEDER_DIR = REPO_ROOT / "data" / "feeder"

def get_feeder_storage_path() -> Path:
    """获取喂食者存储路径，支持外部硬盘配置"""
    custom_path = os.environ.get(FEEDER_STORAGE_ENV)
    if custom_path:
        path = Path(custom_path)
        path.mkdir(parents=True, exist_ok=True)
        print(f"📦 使用外部存储: {path}")
        return path
    path = DEFAULT_FEEDER_DIR
    path.mkdir(parents=True, exist_ok=True)
    print(f"📦 使用默认存储: {path}")
    return path


class FeederCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def crawl_url(self, url: str) -> dict:
        """爬取单个URL并提取结构化数据"""
        result = {
            "url": url,
            "title": "",
            "questions": [],
            "answers": [],
            "evidence": [],
            "relationships": []
        }

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            result["title"] = soup.title.string if soup.title else ""
            
            questions = self._extract_questions(soup, url)
            answers = self._extract_answers(soup, url)
            evidence = self._extract_evidence(soup, url)
            
            result["questions"] = questions
            result["answers"] = answers
            result["evidence"] = evidence
            result["relationships"] = self._build_relationships(questions, answers, evidence)
            
        except Exception as e:
            print(f"爬取失败 {url}: {e}", file=sys.stderr)
        
        return result

    def _extract_questions(self, soup, base_url):
        """提取题目信息"""
        questions = []
        q_patterns = [
            r"[Qq]uestion\s*[0-9]+[.:]\s*",
            r"[问题题目][0-9]+[.:]\s*",
            r"Challenge\s*[0-9]+[.:]\s*"
        ]
        
        for pattern in q_patterns:
            for tag in soup.find_all(text=re.compile(pattern)):
                text = tag.strip()
                if len(text) > 10:
                    qid = self._generate_qid(text)
                    questions.append({
                        "qid": qid,
                        "text": text,
                        "source": base_url,
                        "category": self._infer_category(text)
                    })
        
        return questions

    def _extract_answers(self, soup, base_url):
        """提取答案信息"""
        answers = []
        a_patterns = [
            r"[Aa]nswer\s*[0-9]*[.:]\s*",
            r"[答案解答][0-9]*[.:]\s*",
            r"[Ff]lag\s*[=:]\s*",
            r"flag\{.*?\}"
        ]
        
        for pattern in a_patterns:
            for tag in soup.find_all(text=re.compile(pattern)):
                text = tag.strip()
                answers.append({
                    "text": text,
                    "source": base_url,
                    "type": self._infer_answer_type(text)
                })
        
        return answers

    def _extract_evidence(self, soup, base_url):
        """提取检材信息"""
        evidence = []
        
        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(base_url, href)
            ext = Path(urlparse(full_url).path).suffix.lower()
            
            if ext in [".zip", ".rar", ".7z", ".e01", ".dd", ".img", ".pcap", ".pcapng"]:
                evidence.append({
                    "url": full_url,
                    "filename": link.text.strip() or Path(urlparse(full_url).path).name,
                    "type": self._infer_evidence_type(ext),
                    "source": base_url
                })
        
        return evidence

    def _build_relationships(self, questions, answers, evidence):
        """建立题目、答案、检材之间的对应关系"""
        relationships = []
        
        for i, q in enumerate(questions):
            rel = {
                "question_qid": q["qid"],
                "answers": [],
                "evidence": [],
                "solutions": []
            }
            
            if i < len(answers):
                rel["answers"].append(answers[i].get("text", ""))
            
            for e in evidence:
                if q["category"] in e["type"] or self._match_evidence(q["text"], e["filename"]):
                    rel["evidence"].append(e["url"])
            
            relationships.append(rel)
        
        return relationships

    def _generate_qid(self, text):
        """生成唯一题目ID"""
        num_match = re.search(r"[0-9]+", text)
        num = num_match.group() if num_match else "0"
        return f"FEEDER-{num}"

    def _infer_category(self, text):
        """从题目推断分类"""
        text = text.lower()
        if any(k in text for k in ["windows", "registry", "memory", "disk", "event"]):
            return "computer"
        if any(k in text for k in ["android", "ios", "mobile", "apk", "wechat"]):
            return "mobile"
        if any(k in text for k in ["linux", "server", "docker", "log"]):
            return "server"
        if any(k in text for k in ["network", "pcap", "http", "tcp", "dns"]):
            return "internet"
        if any(k in text for k in ["binary", "reverse", "malware", "ghidra"]):
            return "binary"
        return "computer"

    def _infer_answer_type(self, text):
        if "flag" in text.lower():
            return "flag"
        if re.match(r"[0-9a-fA-F]{32,}", text):
            return "hash"
        return "text"

    def _infer_evidence_type(self, ext):
        if ext in [".e01", ".dd", ".img"]:
            return "disk_image"
        if ext in [".pcap", ".pcapng"]:
            return "network_capture"
        return "archive"

    def _match_evidence(self, question_text, evidence_name):
        """判断检材是否与题目匹配"""
        q_words = set(re.findall(r"[a-zA-Z0-9]{3,}", question_text.lower()))
        e_words = set(re.findall(r"[a-zA-Z0-9]{3,}", evidence_name.lower()))
        return len(q_words & e_words) > 0


class FeederOrganizer:
    @staticmethod
    def organize_to_kb(data: dict, kb_dir: str):
        """将爬取数据组织到知识库"""
        kb_path = Path(kb_dir)
        kb_path.mkdir(parents=True, exist_ok=True)
        
        for rel in data.get("relationships", []):
            qid = rel["question_qid"]
            category = FeederCrawler()._infer_category(rel.get("question_text", ""))
            
            entry = {
                "qid": qid,
                "category": category,
                "question_no": int(qid.split("-")[-1]),
                "result": "not_answered",
                "question": rel.get("question_text", ""),
                "official_answer": rel["answers"][0] if rel["answers"] else "",
                "our_actual_answer": "",
                "method_summary": "",
                "keywords": FeederOrganizer._extract_keywords(rel),
                "lessons": []
            }
            
            file_path = kb_path / "solved" / f"{qid}.yaml"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(entry, f, allow_unicode=True, sort_keys=False)
            
            print(f"创建知识库条目: {file_path}")

    @staticmethod
    def _extract_keywords(rel):
        text = " ".join([rel.get("question_text", "")] + rel.get("answers", []))
        keywords = re.findall(r"[a-zA-Z]{4,}", text.lower())
        return list(set(keywords))[:10]


def cmd_crawl(args):
    crawler = FeederCrawler()
    result = crawler.crawl_url(args.url)
    
    output_dir = Path(args.output) if args.output else get_feeder_storage_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"crawl_{Path(urlparse(args.url).path).name or 'output'}.json"
    output_path = output_dir / filename
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"爬取完成，结果保存到: {output_path}")
    print(f"提取到 {len(result['questions'])} 个题目")
    print(f"提取到 {len(result['answers'])} 个答案")
    print(f"提取到 {len(result['evidence'])} 个检材")


def cmd_parse(args):
    with open(args.html_file, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    crawler = FeederCrawler()
    result = {
        "questions": crawler._extract_questions(soup, "file://" + args.html_file),
        "answers": crawler._extract_answers(soup, "file://" + args.html_file),
        "evidence": crawler._extract_evidence(soup, "file://" + args.html_file)
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_organize(args):
    with open(args.json_file, encoding="utf-8") as f:
        data = json.load(f)
    
    FeederOrganizer.organize_to_kb(data, args.kb_dir)


def cmd_link(args):
    """建立知识库条目之间的关联"""
    kb_path = Path(args.kb_dir)
    solved_dir = kb_path / "solved"
    
    if not solved_dir.exists():
        print(f"知识库目录不存在: {solved_dir}", file=sys.stderr)
        return
    
    entries = []
    for yaml_file in solved_dir.glob("*.yaml"):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                entry = yaml.safe_load(f)
                entry["_file"] = yaml_file.name
                entries.append(entry)
        except Exception as e:
            print(f"解析失败 {yaml_file}: {e}", file=sys.stderr)
    
    for entry in entries:
        related = []
        keywords = set(entry.get("keywords", []))
        
        for other in entries:
            if entry["qid"] == other["qid"]:
                continue
            
            other_keywords = set(other.get("keywords", []))
            if len(keywords & other_keywords) > 1:
                related.append(other["qid"])
        
        entry["related_entries"] = related
        
        with open(solved_dir / entry["_file"], "w", encoding="utf-8") as f:
            yaml.dump(entry, f, allow_unicode=True, sort_keys=False)
        
        print(f"更新 {entry['qid']}: 关联 {len(related)} 个条目")


def cmd_batch(args):
    """批量爬取多个URL"""
    with open(args.url_file, encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    crawler = FeederCrawler()
    all_results = []
    
    for url in urls:
        print(f"正在爬取: {url}")
        result = crawler.crawl_url(url)
        all_results.append(result)
    
    output_dir = get_feeder_storage_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "batch_results.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n批量爬取完成，结果保存到: {output_path}")
    total_q = sum(len(r["questions"]) for r in all_results)
    total_a = sum(len(r["answers"]) for r in all_results)
    total_e = sum(len(r["evidence"]) for r in all_results)
    print(f"总计: {total_q} 题目, {total_a} 答案, {total_e} 检材")


def main():
    parser = argparse.ArgumentParser(description="喂食者 - 知识库爬虫工具")
    parser.add_argument("--storage", help="外部存储路径（如 E:\\feeder_data）")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    
    p_crawl = subparsers.add_parser("crawl", help="爬取单个URL")
    p_crawl.add_argument("url", help="目标URL")
    p_crawl.add_argument("--output", help="输出目录")
    
    p_parse = subparsers.add_parser("parse", help="解析HTML文件")
    p_parse.add_argument("html_file", help="HTML文件路径")
    
    p_organize = subparsers.add_parser("organize", help="组织到知识库")
    p_organize.add_argument("json_file", help="JSON数据文件")
    p_organize.add_argument("kb_dir", help="知识库目录")
    
    p_link = subparsers.add_parser("link", help="建立条目关联")
    p_link.add_argument("kb_dir", help="知识库目录")
    
    p_batch = subparsers.add_parser("batch", help="批量爬取")
    p_batch.add_argument("url_file", help="URL列表文件")
    
    args = parser.parse_args()
    
    if args.storage:
        os.environ[FEEDER_STORAGE_ENV] = args.storage
    
    if args.cmd == "crawl":
        cmd_crawl(args)
    elif args.cmd == "parse":
        cmd_parse(args)
    elif args.cmd == "organize":
        cmd_organize(args)
    elif args.cmd == "link":
        cmd_link(args)
    elif args.cmd == "batch":
        cmd_batch(args)


if __name__ == "__main__":
    main()