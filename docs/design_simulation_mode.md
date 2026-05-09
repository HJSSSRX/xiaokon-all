# 仿真环境模式设计

> **目标**: AI agent 能直接 SSH/HTTP 进入仿真起的"原案件电脑/服务器", 像在真机上一样跑命令。
> **场景**: 火眼仿真 / VMware / lxc 起虚拟机 / WSL 跑服务器
> **价值**: 跳过文件级分析, 直接进运行环境查应用真实状态

---

## 一、为什么需要仿真?

| 静态分析 | 仿真分析 |
|---|---|
| 看 maccms.php 配置文件, 推断后台地址 | 直接打开网站, 看实际跳转 |
| 解析 db 文件, 跑 sqlite 查 | 直接连 mysql, 跑 SQL |
| 提取 LXC 容器 rootfs | 直接 lxc-attach 进容器 |
| 读 nginx config, 推断伪静态规则 | curl 测试实际 URL rewrite |

**仿真的根本优势**: **应用的"运行时状态"** 静态看不到 (e.g. session/cache/连接池/动态生成的文件)。

---

## 二、4 种仿真模式

### 2.1 模式 A: 火眼仿真 (商业方案)

火眼证据分析有"仿真"功能, 一键把 E01 启动成虚拟机:

```
火眼证据分析 → 选检材 → 仿真 → 自动:
  1. 检测 OS (Windows/Linux)
  2. 修复 driver / 网络配置
  3. 启动 VirtualBox / Hyper-V
  4. 暴露 RDP / SSH 端口给宿主
  5. 提供凭据 (跳过密码)
```

**优点**: 一键, 自动处理所有兼容问题
**缺点**: 商业软件, 资源大 (8GB+ RAM), GUI

**AI 集成**:
```python
import subprocess

def huoyan_simulate(case_id: str, evidence_id: str) -> dict:
    """启动火眼仿真, 返回 ssh/rdp 连接信息"""
    r = subprocess.run([
        "opencli", "huoyan", "simulate",
        "--case", case_id,
        "--evidence", evidence_id,
        "--json"
    ], capture_output=True, text=True)
    info = json.loads(r.stdout)
    # info = {"ssh_port": 22001, "ssh_user": "root", "ssh_pass": "<auto>"}
    return info

# 用法
info = huoyan_simulate("default", "server")
import paramiko
ssh = paramiko.SSHClient()
ssh.connect("127.0.0.1", port=info["ssh_port"], username=info["ssh_user"], password=info["ssh_pass"])
stdin, stdout, _ = ssh.exec_command("lxc-ls -f")
print(stdout.read().decode())
```

### 2.2 模式 B: 直接跑 lxc 容器 (Linux 服务器专属)

服务器检材里如果包含 lxc 容器, 可以提取出来直接跑:

```bash
# 1. 从 server.E01 提取容器目录
sudo dissect.target ... mount /mnt/server
ls /mnt/server/var/lib/lxc/

# 2. 复制容器到本地 lxc 主机
sudo cp -r /mnt/server/var/lib/lxc/mytidb /var/lib/lxc/

# 3. 启动
sudo lxc-start -n mytidb -d
sudo lxc-attach -n mytidb

# 4. 容器内验证服务
ss -tlnp | grep 4000   # TiDB 在监听
mysql -P 4000 -u root  # 直连
```

**集成 collab_hub**:
```python
# server_analyst prompt 内
import subprocess

def attach_tidb(query: str) -> str:
    r = subprocess.run([
        "sudo", "lxc-attach", "-n", "mytidb", "--",
        "mysql", "-P", "4000", "-u", "root", "-e", query
    ], capture_output=True, text=True)
    return r.stdout

# 直接查
result = attach_tidb("SELECT vod_pic FROM maccms.mac_vod LIMIT 5")
log_finding(f"TiDB mac_vod 前 5 条 vod_pic: {result}")
```

### 2.3 模式 C: VMware/VirtualBox 直接挂 vmdk

如果检材是 .vmdk / .vdi:

```bash
# VirtualBox CLI
VBoxManage createvm --name "case-pc" --register
VBoxManage modifyvm "case-pc" --memory 4096 --cpus 2
VBoxManage storagectl "case-pc" --name "SATA" --add sata
VBoxManage storageattach "case-pc" --storagectl "SATA" --port 0 \
    --device 0 --type hdd --medium D:\case\disk.vmdk
VBoxManage startvm "case-pc" --type headless

# 等启动后 SSH (假设原系统装了 SSH)
ssh user@127.0.0.1 -p 2222
```

### 2.4 模式 D: Web 应用单独起 (轻量)

不需要整机仿真, 只起 web 应用:

```bash
# 提取 maccms 代码 + 数据库导出
mkdir maccms_replay && cd maccms_replay
cp -r /mnt/server/var/www/html/maccms .
mysqldump 导出 .sql

# 本地起
docker run -d --name maccms-replay \
    -v $(pwd)/maccms:/var/www/html \
    -p 8080:80 \
    php:7.4-apache

# 导入数据库
docker run -d --name mysql-replay -p 3306:3306 -e MYSQL_ROOT_PASSWORD=x mysql:5.7
mysql -h 127.0.0.1 -uroot -px maccms < dump.sql

# 浏览器访问 http://localhost:8080
```

---

## 三、5 个角色的仿真需求

| 角色 | 需要的仿真 | 价值 |
|---|---|---|
| **server** | lxc TiDB 容器 + maccms web | ⭐⭐⭐⭐⭐ 必须 (本次 4 题靠它) |
| **internet** | 同 server (mac_vod 在 TiDB) | ⭐⭐⭐⭐ |
| **mobile** | Android 模拟器 + ROM | ⭐⭐⭐ 火眼内建够用 |
| **computer** | Windows VM (开 UOSAI / 看桌面) | ⭐⭐⭐ 火眼内建够用 |
| **binary** | 跑 .exe 看动态行为 | ⭐⭐ 一般 IDA 够用 |

---

## 四、AI 直接 SSH 控制的 ssh_helper

```python
# tools/ssh_helper.py
"""SSH 助手: AI 直接控制远端 (仿真起的虚拟机/容器)"""
import paramiko
import json
from pathlib import Path

CONFIG = Path.home() / ".forensic_ssh.yaml"

class ForensicSSH:
    def __init__(self, name: str = "default"):
        import yaml
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.cfg = cfg[name]
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def connect(self):
        self.ssh.connect(
            hostname=self.cfg["host"],
            port=self.cfg.get("port", 22),
            username=self.cfg["user"],
            password=self.cfg.get("password"),
            key_filename=self.cfg.get("key_file"),
        )
        return self

    def run(self, cmd: str, timeout: int = 60) -> tuple[str, str, int]:
        stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        return out, err, rc

    def lxc_attach(self, container: str, cmd: str) -> tuple[str, str, int]:
        return self.run(f"sudo lxc-attach -n {container} -- {cmd}")

    def mysql(self, query: str, db: str = "", port: int = 3306) -> str:
        out, _, _ = self.run(f"mysql -h 127.0.0.1 -P {port} -u root {db} -e \"{query}\"")
        return out

    def tidb(self, query: str, db: str = "maccms") -> str:
        return self.lxc_attach("mytidb",
            f"mysql -h 127.0.0.1 -P 4000 -u root {db} -e \"{query}\"")[0]

# 角色 prompt 内用法
ssh = ForensicSSH("server").connect()
result = ssh.tidb("SELECT vod_pic FROM mac_vod LIMIT 5")
log_finding(f"TiDB mac_vod: {result}", related_to=["internet_analyst"])
```

`~/.forensic_ssh.yaml` 配置:
```yaml
default:
  host: 127.0.0.1
  port: 22001
  user: root
  password: <auto>

server:
  host: 127.0.0.1
  port: 22001
  user: root
  password: forensic2026
```

---

## 五、仿真启动 → 自动注入 collab_hub finding

仿真启动后, 自动跑探测脚本, 把环境信息推到 hub:

```python
# tools/sim_recon.py
"""仿真起来后自动巡检 + log_finding"""
from ssh_helper import ForensicSSH
from role_log import log_finding

def recon_server(ssh):
    # 1. 系统信息
    out, _, _ = ssh.run("cat /etc/os-release")
    log_finding(f"Server OS: {out[:200]}")
    
    # 2. 容器列表
    out, _, _ = ssh.run("sudo lxc-ls -f")
    log_finding(f"LXC containers: {out}")
    
    # 3. 监听端口
    out, _, _ = ssh.run("ss -tlnp")
    log_finding(f"Listening ports: {out}")
    
    # 4. Web 站点
    out, _, _ = ssh.run("ls /var/www/html/")
    log_finding(f"Web sites: {out}")
    
    # 5. 数据库
    for port, name in [(3306, "mysql"), (4000, "tidb")]:
        out, _, _ = ssh.run(f"mysql -h 127.0.0.1 -P {port} -u root -e 'SHOW DATABASES'")
        if out:
            log_finding(f"{name} on port {port}: {out}")

if __name__ == "__main__":
    ssh = ForensicSSH("server").connect()
    recon_server(ssh)
```

---

## 六、和知识库联动

每次仿真起来, 跑过的命令 + 找到的服务**自动入 KB**:

```python
# tools/sim_to_kb.py
"""把仿真巡检结果作为 retrospective 入 KB"""
import yaml
from datetime import date

def append_sim_recon_to_kb(role: str, recon_data: dict):
    out = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base") / \
          "retrospectives" / f"{role}_analyst" / \
          f"{date.today().isoformat()}_sim_recon.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump({
        "role": f"{role}_analyst",
        "topic": "仿真环境巡检",
        "content": yaml.safe_dump(recon_data, allow_unicode=True),
        "tags": ["simulation", "recon"],
        "actionable": "下次起服务器仿真后立即跑这个巡检脚本",
    }, allow_unicode=True), encoding="utf-8")
```

---

## 七、风险

### 7.1 性能
- 4-8GB RAM 仿真整机, 笔记本可能爆
- 应对: 用模式 D (单独起 web 应用) 替代整机

### 7.2 网络
- 仿真起的虚拟机要不要联网? **绝不**, 案件机可能含恶意软件
- 应对: VirtualBox 用 hostonly 网络, 仿真机和宿主之间通信即可

### 7.3 完整性
- 启动虚拟机会**写入磁盘** (修改时间戳/事件日志/系统状态)
- 应对: 永远用**写时复制 (CoW)** 模式 (vmdk 链接克隆 / lxc snapshot)
  - 原始检材永远只读

### 7.4 恶意软件
- 案件机可能含勒索/木马, 仿真起来后会激活
- 应对:
  - 不联网 (强制)
  - 不挂宿主磁盘
  - 跑完销毁虚拟机

---

## 八、分阶段实施

### 阶段 1 (本场比赛, 立即可做)
- [ ] 写 `tools/ssh_helper.py` (上面有完整代码, ~80 行)
- [ ] 写 `tools/sim_recon.py` (~50 行)
- [ ] 在 server_analyst v5 prompt 加"启动后立即跑 sim_recon"

### 阶段 2 (1-2 周)
- [ ] 火眼仿真 OpenCLI 适配器 (见 design_huoyan_cli.md 阶段 3)
- [ ] 模式 D (web 单独起) 的 docker-compose 模板库

### 阶段 3 (1-3 个月)
- [ ] 仿真起来自动入 KB
- [ ] 跨案件复用 (sim_recon 历史数据沉淀)

---

## 九、TLDR

**仿真模式的核心价值**: 让 AI **从静态分析升级到动态查询**。

**短期 (本场)**: 写 `ssh_helper.py` + `sim_recon.py`, 让 server_analyst/internet_analyst **直接跑 SQL**, 不再让人类粘贴命令。

**这是相比 v5 prompt 人机协作模式的真正升级路径**:
- v5 人机协作: 人类粘贴命令, AI 解析输出 → **慢, 可能粘错**
- 仿真 SSH: AI 直接 ssh, 跑 + 解析 → **快, 准确, 无人值守**

**配合修复 #1 的 /needs**:
- mobile_analyst 通过 log_need 求 server_analyst "查 mac_user 表里某用户的 IP"
- server_analyst 直接 `ssh.tidb("SELECT inet_ntoa(user_last_login_ip) FROM mac_user WHERE ...")`
- 自动 fulfill_need
- 全程**人类零介入** (除非起仿真本身需要)
