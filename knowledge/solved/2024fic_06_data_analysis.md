---
tags: [data_analysis, mysql, sql_query, mlm_pyramid, hierarchy_analysis, financial_forensics,
  website_reconstruction, computer_forensics]
tools: [mysql, honglian_netju, sql, excel]
category: data_analysis
difficulty: medium
source: 2024FIC_finals
date: 2026-05-05
verified: false
---

# Title: 2024FIC Finals - Data Analysis (9 Questions)

## Problem
After reconstructing the "椴告槗鍏僊ALL绠＄悊绯荤粺" website, analyze the database to answer questions about members, hierarchy, orders, and financial transactions in an MLM (浼犻攢) scheme.

## Prerequisites
- Website must be reconstructed first (see server forensics writeup)
- MySQL database accessible via Docker container on port 13306
- Admin backend accessible via browser

## Solution Steps

### Q1: Members with "鎬讳唬" (Top Agent) level count
Admin backend 鈫?Member Management 鈫?filter by level "鎬讳唬".
鈫?**248**

### Q2: Total hierarchy depth (using 鎺ㄨ崘浜篿d as parent)
Export member data from admin backend. Use 寮樿仈缃戦挏 (Honglian NetJu) data analysis tool:
1. Import as organizational structure
2. Select **strict mode**
3. Tool calculates max depth automatically
鈫?**53**

### Q3: Downstream member count for member sgl01
Filter member ID = sgl01 in 缃戦挏, check downstream count.
鈫?**18001**

### Q4: Total recharge amount for sgl01's downstream members
From MySQL `member_money` table (contains recharge totals). Cross-reference with `member` table for hierarchy.
Export both tables 鈫?import into 缃戦挏 with organizational template.
鈫?**8704119** (鍏?RMB, note: database stores without decimal places)

### Q5: Paid order count
Admin backend 鈫?Order Management 鈫?filter status = "宸叉敮浠? (paid).
鈫?**31760**

### Q6: Total payment amount for paid orders
```sql
SELECT SUM(pay_money) FROM `doing_order` WHERE is_pay=1
```
鈫?**71979976** (鍏?RMB, note two decimal places in raw data)

### Q7: Bank card records in withdrawal account management
Admin backend 鈫?Withdrawal Management 鈫?Account Management 鈫?bank card records.
鈫?**6701**

### Q8: Successful withdrawal record count
Withdrawal Management 鈫?filter status = "鎵撴�炬垚鍔�".
鈫?**8403**

### Q9: Total withdrawal amount for successful payouts
```sql
SELECT SUM(need_give_money) FROM `member_deal` WHERE deal_status = 4
```
(deal_status = 4 means successful payout)
鈫?**10067655** (鍏?RMB)

## Key Takeaways
- **寮樿仈缃戦挏 (NetJu)**: Purpose-built for MLM hierarchy analysis 鈥?imports member data, calculates depth, downstream counts, financial aggregations automatically
- **Strict mode in NetJu**: Required for accurate hierarchy analysis with 鎺ㄨ崘浜篿d as parent
- **SQL for financial queries**: When admin UI doesn't show totals, query database directly
- **Key tables**:
  - `sys_user` 鈥?admin accounts
  - `member` 鈥?member info, hierarchy (鎺ㄨ崘浜篿d)
  - `member_money` 鈥?recharge/balance data
  - `doing_order` 鈥?orders (is_pay=1 for paid)
  - `member_deal` 鈥?withdrawal records (deal_status=4 for success, need_give_money for amount)
- **Decimal precision**: Database may store amounts without trailing zeros; verify decimal places
- **Member count**: Total 52908 members visible in admin backend after reconstruction

## Answer
Q1: 248
Q2: 53
Q3: 18001
Q4: 8704119
Q5: 31760
Q6: 71979976
Q7: 6701
Q8: 8403
Q9: 10067655
