"""
ssh_helper.py 单测 — 不连真实 SSH, 用 mock subprocess.

Run:
  python3 tests/test_ssh_helper.py
"""
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import ssh_helper
from ssh_helper import ForensicSSH, SSHConfigError, list_configs, add_config


# ─── 测试套件 ───

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


def test_init_with_direct_params():
    """直传参数初始化."""
    ssh = ForensicSSH(host="1.2.3.4", user="root", password="pwd", port=2222)
    t("直传 host/user/password 初始化", ssh.host == "1.2.3.4")
    t("直传 port", ssh.port == 2222)
    t("直传 user", ssh.user == "root")
    t("直传 password", ssh.password == "pwd")


def test_init_missing_host():
    """缺 host 应当报错."""
    try:
        ForensicSSH(user="root", password="x")
        t("缺 host 应报错", False, "should raise SSHConfigError")
    except SSHConfigError:
        t("缺 host 应报错", True)


def test_init_missing_user():
    """缺 user 应当报错."""
    try:
        ForensicSSH(host="1.2.3.4", password="x")
        t("缺 user 应报错", False, "should raise SSHConfigError")
    except SSHConfigError:
        t("缺 user 应报错", True)


def test_init_with_named_config():
    """从 ~/.forensic_ssh.yaml 读配置."""
    # 写一个临时配置, 不污染用户目录: monkey-patch CONFIG_PATH
    tmp_cfg = Path(tempfile.gettempdir()) / "test_forensic_ssh.yaml"
    tmp_cfg.write_text(
        "test_host:\n  host: 10.0.0.1\n  port: 2200\n  user: tester\n  password: testpwd\n",
        encoding="utf-8",
    )
    original = ssh_helper.CONFIG_PATH
    ssh_helper.CONFIG_PATH = tmp_cfg
    try:
        ssh = ForensicSSH("test_host")
        t("从配置读 host", ssh.host == "10.0.0.1")
        t("从配置读 port", ssh.port == 2200)
        t("从配置读 user", ssh.user == "tester")
    finally:
        ssh_helper.CONFIG_PATH = original
        tmp_cfg.unlink(missing_ok=True)


def test_init_unknown_config_name():
    """不存在的配置名应当报错."""
    try:
        ForensicSSH("definitely_not_exist_12345")
        t("不存在配置名应报错", False, "should raise SSHConfigError")
    except SSHConfigError:
        t("不存在配置名应报错", True)


def test_run_via_subprocess_mock():
    """run() 走 subprocess 后端 (mock subprocess.run)."""
    ssh = ForensicSSH(host="1.2.3.4", user="root", key_file="~/key", backend="subprocess")
    ssh._connected = True  # 跳过真实 connect

    fake_completed = MagicMock(stdout="hello\n", stderr="", returncode=0)
    with patch.object(ssh_helper.subprocess, "run", return_value=fake_completed) as mock_run:
        out, err, rc = ssh.run("echo hello")
        t("run subprocess: stdout 正确", out == "hello\n")
        t("run subprocess: returncode=0", rc == 0)
        # 验证调用参数包含 ssh + key + 命令
        called_args = mock_run.call_args[0][0]
        t("run subprocess: 含 ssh", "ssh" in called_args)
        t("run subprocess: 含 -p 端口参数", "-p" in called_args)
        t("run subprocess: 含 -i 私钥参数", "-i" in called_args)
        t("run subprocess: 含命令", called_args[-1] == "echo hello")


def test_run_or_raise_failure():
    """run_or_raise 在 rc != 0 时抛错."""
    ssh = ForensicSSH(host="1.2.3.4", user="root", key_file="~/key", backend="subprocess")
    ssh._connected = True

    fake = MagicMock(stdout="", stderr="permission denied", returncode=1)
    with patch.object(ssh_helper.subprocess, "run", return_value=fake):
        try:
            ssh.run_or_raise("ls /root")
            t("run_or_raise 失败应抛 SSHRunError", False, "no exception raised")
        except ssh_helper.SSHRunError as e:
            t("run_or_raise 失败应抛 SSHRunError",
              "rc=1" in str(e) and "permission denied" in str(e))


def test_lxc_attach_command_construction():
    """lxc_attach 应当包装 sudo lxc-attach -n <name> -- bash -c ..."""
    ssh = ForensicSSH(host="1.2.3.4", user="root", key_file="~/key", backend="subprocess")
    ssh._connected = True

    captured = {}
    fake = MagicMock(stdout="", stderr="", returncode=0)

    def capture(*args, **kwargs):
        captured["cmd"] = args[0]
        return fake

    with patch.object(ssh_helper.subprocess, "run", side_effect=capture):
        ssh.lxc_attach("mytidb", "mysql -P 4000 -e 'SHOW DATABASES'")
        cmd_str = " ".join(captured["cmd"])
        t("lxc_attach: 含 sudo", "sudo" in cmd_str)
        t("lxc_attach: 含 lxc-attach", "lxc-attach" in cmd_str)
        t("lxc_attach: 含容器名", "mytidb" in cmd_str)


def test_mysql_command_construction():
    """mysql() 拼接 mysql -h -P -u -e."""
    ssh = ForensicSSH(host="1.2.3.4", user="root", key_file="~/key", backend="subprocess")
    ssh._connected = True

    captured = {}
    fake = MagicMock(stdout="result\n", stderr="", returncode=0)

    def capture(*args, **kwargs):
        captured["cmd"] = args[0]
        return fake

    with patch.object(ssh_helper.subprocess, "run", side_effect=capture):
        out = ssh.mysql("SELECT 1", db="maccms", port=3306, password="pwd")
        cmd_str = " ".join(captured["cmd"])
        t("mysql: 含 mysql 命令", "mysql" in cmd_str)
        t("mysql: 含 -h 127.0.0.1", "-h 127.0.0.1" in cmd_str)
        t("mysql: 含 -P 3306", "-P 3306" in cmd_str)
        t("mysql: 含 -u root", "-u root" in cmd_str)
        t("mysql: 含数据库名", "maccms" in cmd_str)
        t("mysql: 含查询 SELECT 1", "SELECT 1" in cmd_str)
        t("mysql: 返回 stdout", out == "result\n")


def test_sh_quote():
    """shell 单引号转义."""
    t("sh_quote: 空字符串", ForensicSSH._sh_quote("") == "''")
    t("sh_quote: 纯字母数字不引", ForensicSSH._sh_quote("hello123") == "hello123")
    t("sh_quote: 纯路径不引", ForensicSSH._sh_quote("/usr/bin/sh") == "/usr/bin/sh")
    t("sh_quote: 含空格要引", ForensicSSH._sh_quote("hello world") == "'hello world'")
    t("sh_quote: 含单引号要转", ForensicSSH._sh_quote("it's") == "'it'\"'\"'s'")


def test_timeout_handling():
    """超时返回 rc=-1 + 错误信息."""
    ssh = ForensicSSH(host="1.2.3.4", user="root", key_file="~/key", backend="subprocess")
    ssh._connected = True

    import subprocess as sp
    with patch.object(ssh_helper.subprocess, "run",
                      side_effect=sp.TimeoutExpired(cmd="x", timeout=1)):
        out, err, rc = ssh.run("sleep 60", timeout=1)
        t("超时: rc=-1", rc == -1)
        t("超时: err 含 timeout", "timeout" in err.lower())


def test_add_and_list_configs():
    """add_config + list_configs."""
    tmp_cfg = Path(tempfile.gettempdir()) / "test_forensic_ssh_add.yaml"
    tmp_cfg.unlink(missing_ok=True)
    original = ssh_helper.CONFIG_PATH
    ssh_helper.CONFIG_PATH = tmp_cfg
    try:
        add_config("hostA", host="10.0.0.1", user="root", password="x")
        add_config("hostB", host="10.0.0.2", user="admin", port=2222)
        names = list_configs()
        t("add_config + list_configs: 含 hostA", "hostA" in names)
        t("add_config + list_configs: 含 hostB", "hostB" in names)
        t("add_config + list_configs: 共 2 个", len(names) == 2)
    finally:
        ssh_helper.CONFIG_PATH = original
        tmp_cfg.unlink(missing_ok=True)


# ─── 入口 ───

def main():
    print("=" * 60)
    print("ssh_helper.py unit tests")
    print("=" * 60)

    tests = [
        test_init_with_direct_params,
        test_init_missing_host,
        test_init_missing_user,
        test_init_with_named_config,
        test_init_unknown_config_name,
        test_run_via_subprocess_mock,
        test_run_or_raise_failure,
        test_lxc_attach_command_construction,
        test_mysql_command_construction,
        test_sh_quote,
        test_timeout_handling,
        test_add_and_list_configs,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as e:
            global FAILED
            FAILED += 1
            print(f"[ERROR] {fn.__name__}: {e}")

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
