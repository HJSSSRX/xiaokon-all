"""
ssh_helper.py — SSH 助手 (用于火眼仿真起的虚拟机 / lxc 容器 / 真实远端)

设计目标:
  让 AI 角色直接 ssh 跑命令, 替代"让人类粘贴 ssh 命令再发结果"的低效流程.
  支持 paramiko (推荐) 和 subprocess+ssh.exe (零依赖, 仅密钥).

配置 (~/.forensic_ssh.yaml):
  default:
    host: 127.0.0.1
    port: 22001
    user: root
    password: forensic2026

  server:
    host: 192.168.1.50
    port: 22
    user: root
    key_file: ~/.ssh/id_rsa

  tidb_container:
    via: server          # 通过 server 跳板再 lxc-attach
    container: mytidb

用法:
  >>> from ssh_helper import ForensicSSH
  >>> ssh = ForensicSSH("server").connect()
  >>> out, err, rc = ssh.run("uname -a")
  >>> print(out)

  >>> # 直接查 maccms 数据库
  >>> result = ssh.mysql("SELECT user_name, inet_ntoa(user_last_login_ip) FROM mac_user", db="maccms")
  >>> print(result)

  >>> # 通过 lxc-attach 进容器跑命令
  >>> result = ssh.lxc_attach("mytidb", "mysql -P 4000 -u root -e 'SHOW DATABASES'")
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# 可选: paramiko (用密码时强烈推荐)
try:
    import paramiko
    HAVE_PARAMIKO = True
except ImportError:
    HAVE_PARAMIKO = False

# YAML 是必须的 (案件配置统一 YAML)
try:
    import yaml
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"], check=False)
    import yaml


CONFIG_PATH = Path.home() / ".forensic_ssh.yaml"


class SSHConfigError(Exception):
    pass


class SSHRunError(Exception):
    pass


def _load_config() -> dict:
    """加载 ~/.forensic_ssh.yaml. 不存在返回空 dict, 不报错 (允许参数直传)."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, default_flow_style=False)


class ForensicSSH:
    """
    取证 SSH 助手. 支持 paramiko (优选) 或 subprocess+ssh.exe (零依赖).

    构造:
      ForensicSSH("server")            # 从 ~/.forensic_ssh.yaml 读 server 配置
      ForensicSSH(host="1.2.3.4", user="root", password="x", port=22)  # 直传
    """

    def __init__(
        self,
        name: Optional[str] = None,
        *,
        host: Optional[str] = None,
        port: int = 22,
        user: Optional[str] = None,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        backend: str = "auto",  # auto / paramiko / subprocess
    ):
        # 1. 从配置读
        if name:
            cfg = _load_config().get(name)
            if not cfg:
                raise SSHConfigError(
                    f"~/.forensic_ssh.yaml 没有配置 '{name}'. "
                    f"现有: {list(_load_config().keys())}"
                )
            self.name = name
            self.host = cfg.get("host")
            self.port = cfg.get("port", 22)
            self.user = cfg.get("user")
            self.password = cfg.get("password")
            self.key_file = cfg.get("key_file")
        else:
            self.name = "(direct)"
            self.host = host
            self.port = port
            self.user = user
            self.password = password
            self.key_file = key_file

        # 2. 参数覆盖配置
        if host: self.host = host
        if user: self.user = user
        if password: self.password = password
        if key_file: self.key_file = key_file

        if not self.host or not self.user:
            raise SSHConfigError(f"host 和 user 必填. 当前: host={self.host}, user={self.user}")

        # 3. 后端选择
        if backend == "auto":
            # 有密码且装了 paramiko → paramiko
            # 否则 → subprocess (要求密钥配置好)
            if self.password and HAVE_PARAMIKO:
                self.backend = "paramiko"
            elif shutil.which("ssh"):
                self.backend = "subprocess"
            elif HAVE_PARAMIKO:
                self.backend = "paramiko"
            else:
                raise SSHConfigError(
                    "没有可用的 SSH 后端. 装 paramiko (pip install paramiko) "
                    "或确保 ssh.exe 在 PATH."
                )
        else:
            self.backend = backend

        # 4. 内部状态
        self._client = None  # paramiko.SSHClient
        self._connected = False

    # ─── 连接 ───

    def connect(self):
        """建立连接 (paramiko 用, subprocess 是无状态的)."""
        if self.backend == "paramiko":
            if not HAVE_PARAMIKO:
                raise SSHConfigError("backend=paramiko 但未装 paramiko. pip install paramiko")
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {"hostname": self.host, "port": self.port, "username": self.user, "timeout": 10}
            if self.password:
                kwargs["password"] = self.password
            if self.key_file:
                kwargs["key_filename"] = os.path.expanduser(self.key_file)
            self._client.connect(**kwargs)
            self._connected = True
        else:  # subprocess
            # 验证 ssh.exe 可达 + key 可用
            if not shutil.which("ssh"):
                raise SSHConfigError("ssh.exe 不在 PATH")
            self._connected = True
        return self

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
        self._connected = False

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.close()

    # ─── 命令执行 ───

    def run(self, cmd: str, *, timeout: int = 60) -> Tuple[str, str, int]:
        """
        跑命令, 返回 (stdout, stderr, returncode).
        不抛错 (除非连接断开). returncode != 0 由调用方判断.
        """
        if not self._connected:
            self.connect()

        if self.backend == "paramiko":
            stdin, stdout, stderr = self._client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            rc = stdout.channel.recv_exit_status()
            return out, err, rc

        else:  # subprocess
            ssh_args = ["ssh", "-o", "StrictHostKeyChecking=no",
                        "-o", "BatchMode=yes",   # 不交互 (强制密钥)
                        "-p", str(self.port)]
            if self.key_file:
                ssh_args += ["-i", os.path.expanduser(self.key_file)]
            ssh_args += [f"{self.user}@{self.host}", cmd]
            try:
                r = subprocess.run(
                    ssh_args, capture_output=True, text=True,
                    timeout=timeout, encoding="utf-8", errors="replace",
                )
                return r.stdout, r.stderr, r.returncode
            except subprocess.TimeoutExpired:
                return "", f"timeout after {timeout}s", -1
            except FileNotFoundError:
                return "", "ssh.exe not found in PATH", -1

    def run_or_raise(self, cmd: str, *, timeout: int = 60) -> str:
        """跑命令, 失败抛错. 适合"必须成功"的场景."""
        out, err, rc = self.run(cmd, timeout=timeout)
        if rc != 0:
            raise SSHRunError(f"cmd={cmd!r} rc={rc} stderr={err[:500]}")
        return out

    # ─── 高级方法 ───

    def lxc_attach(self, container: str, cmd: str, *, timeout: int = 60) -> Tuple[str, str, int]:
        """通过 sudo lxc-attach 进容器跑命令."""
        full = f"sudo lxc-attach -n {container} -- bash -c {self._sh_quote(cmd)}"
        return self.run(full, timeout=timeout)

    def mysql(self, query: str, *, db: str = "", port: int = 3306,
              user: str = "root", password: str = "", host: str = "127.0.0.1") -> str:
        """直接跑 mysql 查询, 返回 stdout."""
        cmd_parts = [f"mysql -h {host} -P {port} -u {user}"]
        if password:
            cmd_parts.append(f"-p{self._sh_quote(password)}")
        if db:
            cmd_parts.append(db)
        cmd_parts.append(f"-e {self._sh_quote(query)}")
        out, _, _ = self.run(" ".join(cmd_parts))
        return out

    def tidb(self, query: str, *, db: str = "maccms", container: str = "mytidb") -> str:
        """通过 lxc-attach 进 TiDB 容器跑查询."""
        inner = f"mysql -h 127.0.0.1 -P 4000 -u root {db} -e {self._sh_quote(query)}"
        out, _, _ = self.lxc_attach(container, inner)
        return out

    def file_get(self, remote_path: str) -> bytes:
        """读取远端文件内容."""
        if self.backend == "paramiko":
            sftp = self._client.open_sftp()
            try:
                with sftp.open(remote_path, "rb") as f:
                    return f.read()
            finally:
                sftp.close()
        else:
            # subprocess: 用 ssh cat
            out, _, rc = self.run(f"cat {self._sh_quote(remote_path)}")
            if rc != 0:
                raise SSHRunError(f"file_get failed: {remote_path}")
            return out.encode("utf-8")

    @staticmethod
    def _sh_quote(s: str) -> str:
        """安全的 shell 单引号转义."""
        if not s:
            return "''"
        if all(c.isalnum() or c in "@%+=:,./-_" for c in s):
            return s
        return "'" + s.replace("'", "'\"'\"'") + "'"


# ─── 便捷函数 ───

def list_configs() -> list:
    """列出 ~/.forensic_ssh.yaml 里所有配置名."""
    return list(_load_config().keys())


def add_config(name: str, host: str, user: str, *, port: int = 22,
               password: Optional[str] = None, key_file: Optional[str] = None):
    """添加/更新一个 SSH 配置."""
    cfg = _load_config()
    cfg[name] = {"host": host, "user": user, "port": port}
    if password:
        cfg[name]["password"] = password
    if key_file:
        cfg[name]["key_file"] = key_file
    _save_config(cfg)


# ─── 自检 ───

def selftest():
    """快速自检: 显示后端 + 配置 + 是否能解析参数."""
    print("=" * 50)
    print("ssh_helper.py selftest")
    print("=" * 50)
    print(f"paramiko 可用: {HAVE_PARAMIKO}")
    print(f"ssh.exe 可达: {bool(shutil.which('ssh'))}")
    print(f"配置文件: {CONFIG_PATH}")
    print(f"已配置 host: {list_configs()}")
    print()

    # 验证类初始化不崩
    try:
        ForensicSSH(host="127.0.0.1", user="test", password="x")
        print("✓ 直传参数初始化 OK")
    except Exception as e:
        print(f"✗ 直传参数失败: {e}")

    try:
        ForensicSSH(host="127.0.0.1", user="test", key_file="~/.ssh/id_rsa", backend="subprocess")
        print("✓ subprocess 后端初始化 OK")
    except Exception as e:
        print(f"✗ subprocess 后端失败: {e}")

    print()
    print("用法示例:")
    print("  >>> from ssh_helper import ForensicSSH, add_config")
    print("  >>> add_config('server', host='192.168.1.50', user='root', password='x')")
    print("  >>> with ForensicSSH('server') as ssh:")
    print("  ...     out, err, rc = ssh.run('uname -a')")
    print("  ...     print(out)")


if __name__ == "__main__":
    selftest()
