---
tags: [pve, proxmox, virtualization, linux, qemu, vm_management, snapshot, task_history,
  network_config, cloud]
tools: [pve_web_ui, qm, ssh]
category: virtualization
difficulty: medium
source: 2024FIC_finals
date: 2026-05-05
verified: false
---

# Title: 2024FIC Finals - PVE Virtualization (10 Questions)

## Problem
Given a PVE (Proxmox Virtual Environment) system with sys.E01 + data.E01 images, answer 10 questions about the virtual machine platform configuration, VMs, and operations history.

## Evidence
- sys.E01 (~8.6GB) 鈥?PVE system partition
- data.E01 (~34GB) 鈥?PVE data partition
- **Must mount sys first, then data** (order matters; reversed order causes "system not found")

## Solution Steps

### Setup: Emulating PVE
1. Mount sys.E01 first, then data.E01 in forensic tool
2. PVE web UI at https://192.168.71.133:8006
3. Configure subnet IP and DHCP to match 192.168.71.x
4. Login: root / 123456 (forensic tool bypasses password)

### Q1: PVE platform version
Check pve-manager version in software info, or login to web UI.
鈫?**8.1.4**

### Q2: PVE web management address
Displayed immediately upon boot.
鈫?**https://192.168.71.133:8006**

### Q3: Total number of VMs
Switch to "Folder View" in top-left dropdown. Count VM icons.
鈫?**7**

### Q4: vmbr1 network subnet
Check network configuration in PVE web UI 鈫?Node 鈫?Network.
鈫?**192.168.100.0/24**

### Q5: "120(Luck)" VM smbios uuid
Double-click Luck VM 鈫?Options 鈫?SMBIOS settings.
鈫?**e9990cd6-6e60-476c-bd37-1a524422a9a8**

### Q6: User "Lu2k" VM permissions count
Server View 鈫?Permissions tab. Count Lu2k entries.
鈫?**4**

### Q7: Last shell history command
Check `.bash_history` or shell history in PVE.
鈫?**lxc-attach 110**

### Q8: Last VM destruction time (multiple choice)
A.2024-03-13 10:34:20  B.2024-03-22 18:06:15  C.2024-03-22 18:15:17  D.2024-03-22 18:20:55
Check PVE node 鈫?Task History, filter for `qmdestroy`.
鈫?**C. 2024-03-22 18:15:17**

### Q9: openEuler image download start time (multiple choice)
A.2024-03-12 12:03:12  B.2024-03-12 12:04:19  C.2024-03-12 12:10:09  D.2024-03-12 12:11:02
Task History 鈫?filter download tasks.
鈫?**B. 2024-03-12 12:04:19**

### Q10: Cloud phone snapshot time (multiple choice)
A.2024-03-12 11:02:32  B.2024-03-12 11:24:11  C.2024-03-13 10:34:20  D.2024-03-13 9:43:23
Check each VM for snapshot info. node2 has snapshot "瀹夎�呮墜鏈�".
鈫?**D. 2024-03-13 9:43:23**

## Key Takeaways
- **Image mount order matters**: sys.E01 first, data.E01 second for PVE emulation
- **PVE Task History**: Searchable/filterable 鈥?use task type filters (qmdestroy, download, etc.)
- **vCPU limit**: Free PVE license limits to 2 vCPUs; need `qm set <vmid> --cores 2` to reduce before starting VMs
- **Snapshot forensics**: Check all VMs individually for snapshot records, useful for timeline reconstruction
- **LXC containers**: Use `lxc-attach <id>` to enter container shells directly
- **Folder view vs Server view**: Folder view shows all VMs clearly; Server view shows permissions

## Answer
Q1: 8.1.4
Q2: https://192.168.71.133:8006
Q3: 7
Q4: 192.168.100.0/24
Q5: e9990cd6-6e60-476c-bd37-1a524422a9a8
Q6: 4
Q7: lxc-attach 110
Q8: C (2024-03-22 18:15:17)
Q9: B (2024-03-12 12:04:19)
Q10: D (2024-03-13 9:43:23)
