---
tags: [mobile, android, apk, permissions, manifest, accessibility, runtime_permissions,
  malware_triage, frida, methodology, mobile_forensics]
tools: [aapt, androguard, jadx, apktool, frida, grep]
category: mobile_forensics
difficulty: medium
source: kb_seed_2026-05-07
verified: false
related: [apk_crypto_analysis.md, anti_forensics_and_misleading.md, uninstalled_app_recovery.md,
  2022_changancup_mobile_exe_apk.md]
---

# APK 权限分析 — 看权限读懂 App 真实意图

> **核心心法**：权限是 App 能力的"证据声明"。
> **声明**（Manifest 写了）≠ **请求**（运行时 requestPermissions）≠ **授予**（用户允许）≠ **调用**（代码真用）。
> 四者差异本身就是线索。
>
> **看权限要回答四件事**：
> 1. 声明了哪些
> 2. 实际授予了哪些
> 3. 代码里哪些真用了
> 4. 用了之后数据流向哪

## 0. 四层权限信息

### L1 声明层 — `AndroidManifest.xml`

```bash
aapt dump permissions game.apk
apktool d game.apk -o out
grep -E "uses-permission|uses-feature|<permission " out/AndroidManifest.xml

python -c "
from androguard.misc import APK
a = APK('game.apk')
for p in sorted(a.get_permissions()): print(p)
"
```

| 标签 | 含义 |
|---|---|
| `<uses-permission android:name="..."/>` | App 请求的权限 |
| `<uses-permission-sdk-23>` | 仅 API 23+ 需要的（运行时权限） |
| `<permission android:name="..."/>` | App 自定义的权限（让别 app 用） |
| `<uses-feature android:required="true"/>` | 硬件依赖 |
| `android:maxSdkVersion="22"` | 仅老系统申请，新版"假装不要" — **反取证常用** |

### L2 授予层（运行时）

```bash
# 设备上
adb shell dumpsys package {pkg} | grep -A 50 "runtime permissions"

# 镜像里
cat /data/system/users/0/runtime-permissions.xml | grep -A 20 'pkg name="{pkg}"'
# Android 11+ 新格式
cat /data/system/users/0/runtime-permissions/runtime-permissions.xml
```

每条 `granted="true|false"` + `flags`：
- `USER_SET` 用户主动选
- `USER_FIXED` 用户选了"不再询问"
- `POLICY_FIXED` MDM 强制

### L3 调用层 — 代码里真用了什么

```bash
grep -rE "getSystemService\(\"location\"\)|LocationManager|FusedLocation" out/sources/
grep -rE "Camera\.|CameraManager|takePicture" out/sources/
grep -rE "MediaRecorder|AudioRecord" out/sources/
grep -rE "ContactsContract|ContentResolver.*contact" out/sources/
grep -rE "TelephonyManager|getDeviceId|getImei|getSubscriberId" out/sources/
grep -rE "SmsManager|sendTextMessage|getMessageBody" out/sources/
grep -rE "ClipboardManager|getPrimaryClip" out/sources/
grep -rE "AccessibilityService|onAccessibilityEvent" out/sources/
grep -rE "NotificationListenerService" out/sources/
```

```python
# Androguard 反向定位
from androguard.misc import AnalyzeAPK
a, d, dx = AnalyzeAPK('game.apk')
for meth in dx.get_methods():
    code = meth.get_method().get_source() if meth.get_method() else ""
    if "LocationManager" in code or "getDeviceId" in code:
        print(meth.full_name)
```

### L4 数据流层 — 拿到的数据流向哪

```bash
grep -rE "HttpURLConnection|OkHttpClient|Retrofit|new Socket" out/sources/
grep -rohE "https?://[a-zA-Z0-9./_-]+" out/sources/ | sort -u
grep -rohE "\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b" out/sources/ | sort -u
grep -rE "FileOutputStream|getExternalStorage|openFileOutput" out/sources/
grep -rE "System\.loadLibrary|JNI" out/sources/
```

---

## 1. 危险权限速查

| 权限 | 含义 | 警觉点 |
|---|---|---|
| `READ_SMS` / `RECEIVE_SMS` / `SEND_SMS` | 短信全权 | 银行 SMS 拦截木马 |
| `READ_CONTACTS` / `WRITE_CONTACTS` | 通讯录 | 信息收集类必备 |
| `READ_CALL_LOG` / `READ_PHONE_STATE` | 通话记录 + IMEI/IMSI | 设备识别 |
| `RECORD_AUDIO` | 录音 | 监听 |
| `CAMERA` | 摄像头 | 偷拍 |
| `ACCESS_FINE_LOCATION` / `_BACKGROUND_LOCATION` | 精确定位 | 跟踪 |
| `READ_EXTERNAL_STORAGE` / `MANAGE_EXTERNAL_STORAGE` | 全盘存储 | 偷文件 |
| `READ_LOGS` | 系统日志 | 拿其他 app 输出 |
| `SYSTEM_ALERT_WINDOW` | 悬浮窗 | 钓鱼覆盖 |
| `BIND_ACCESSIBILITY_SERVICE` | **辅助功能** | ⚠️ 银行木马、自动化诈骗，半个 root |
| `BIND_DEVICE_ADMIN` | 设备管理员 | 阻止卸载 |
| `BIND_NOTIFICATION_LISTENER_SERVICE` | 读所有通知 | 验证码窃取 |
| `INSTALL_PACKAGES` / `REQUEST_INSTALL_PACKAGES` | 安装其他 app | 下载器 |
| `WRITE_SETTINGS` / `WRITE_SECURE_SETTINGS` | 改系统设置 | 篡改安全控件 |
| `RECEIVE_BOOT_COMPLETED` | 开机启动 | 持久化 |
| `WAKE_LOCK` + `FOREGROUND_SERVICE` | 持续运行 | 后台常驻 |
| `QUERY_ALL_PACKAGES` (API 30+) | 列所有已装 app | 设备指纹 |
| `PACKAGE_USAGE_STATS` | 应用使用情况 | 行为画像 |
| `BIND_VPN_SERVICE` | VPN 接管全流量 | 数据偷传 |

---

## 2. 反常组合 = 强证据

| 组合 | 推断 |
|---|---|
| **辅助功能 + 短信 + 通讯录** | 银行木马 / 远控诈骗 |
| **录音 + 摄像头 + 定位 + 通讯录** | RAT (AhMyth/AndroRAT/Cerberus 标配) |
| **通知监听 + 短信** | 验证码拦截 |
| **辅助功能 + 悬浮窗 + 设备管理员** | 顶级权限木马，难卸载 |
| **安装 + 开机启动 + 后台服务** | 下载器 + 持久化 |
| **VPN + 全流量** | 流量代理/数据偷传 |
| **支付类 + 通知监听** | 假冒支付收款木马 |
| **手电筒 app + 通讯录 + 定位** | 名实不符，流氓应用 |

---

## 3. 声明 vs 实际使用 — 鉴别诱饵权限

```
4 种状态                                     推断
──────────────────────────────────────────────────
声明 ✅  请求 ✅  授予 ✅  调用 ✅            真实功能
声明 ✅  请求 ✅  授予 ✅  调用 ❌            诱饵 / 备用通道（待激活）
声明 ✅  请求 ❌  授予 ❌  调用 ❌            遗留 / 抄的代码没清
声明 ✅  请求 ✅  授予 ❌  调用 ✅            降级运行
声明 ❌  ─       ─        调用 ✅            反射/native 绕开（异常）
```

**"声明 ✅ 调用 ❌"特别可疑**：恶意 app 常先低调潜伏，等远程指令再激活。看代码有没有 `if (config.featureEnabled)` 之类开关。

---

## 4. 自定义权限 / signature 权限

```xml
<permission android:name="com.bad.app.SECRET"
            android:protectionLevel="signature"/>
```

仅**同签名**的别的 app 能用。常见于：
- 一套恶意 app 套件（主体 + 插件）通过自定义权限通信
- 主体伪装正常，插件干脏活，分开声明躲检测

⚠️ **`PROTECTION_NORMAL` 自定义权限不需用户确认**：恶意常借此暴露 IPC。

⚠️ **自定义权限劫持**：A 先装定义 `com.x.SECRET = normal`；B 后装声明同名 = signature；A 仍生效 → 跨 app 数据泄漏。

---

## 5. System / privileged 权限

某些权限只有系统签名 / `/system/priv-app/` 下的 app 才能用：

```xml
<uses-permission android:name="android.permission.READ_PRIVILEGED_PHONE_STATE"/>
<uses-permission android:name="android.permission.MANAGE_USERS"/>
<uses-permission android:name="android.permission.WRITE_SECURE_SETTINGS"/>
```

普通用户 app 居然有这些 = 预装/伪造/root 后改放位置。看 `/data/system/packages.xml` 中 `installerPackageName` 和 `flags`。

---

## 6. 跨 API 等级演化（坑大）

| 权限 | API 级别变化 |
|---|---|
| `READ_EXTERNAL_STORAGE` | 23 才需运行时；29+ scoped storage 弱化；33+ 拆 `READ_MEDIA_IMAGES/VIDEO/AUDIO` |
| `ACCESS_BACKGROUND_LOCATION` | 29 (Android 10) 引入，单独同意 |
| `QUERY_ALL_PACKAGES` | 30 (Android 11) 引入 |
| `POST_NOTIFICATIONS` | 33 (Android 13) 才需要 |
| `BLUETOOTH_SCAN/_CONNECT/_ADVERTISE` | 31 拆出，老 BLUETOOTH/BLUETOOTH_ADMIN 兼容 |

**反取证花招**：
- `android:maxSdkVersion="22"` → 高版本根本不申请，但代码反射调用
- `targetSdkVersion` 故意低 → 沿用宽松行为，绕新版限制

---

## 7. 决策树

```
"看 APK 权限题"
   │
   ├─ Step 1: aapt / androguard 拿声明清单
   │
   ├─ Step 2: 与"危险权限表"和"反常组合表"对照
   │     └ 命中 → 怀疑分类（RAT/银行木马/广告间谍）
   │
   ├─ Step 3: 反编译看实际调用
   │     └ 对每个高危权限 grep 对应 API
   │     └ 区分"真用"vs"诱饵"
   │
   ├─ Step 4: 看运行时授予状态
   │     └ /data/system/users/0/runtime-permissions.xml
   │
   ├─ Step 5: 数据流向
   │     └ 拿到的数据通过哪个 URL/Socket/文件出去
   │
   └─ Step 6: 串证据链
         声明 + 授予 + 调用 + 数据落地 = 完整链
```

---

## 8. 命令速查

```bash
# 声明
aapt dump permissions game.apk
aapt dump badging game.apk | grep -E "uses-permission|uses-feature"

# androguard 详细
python -c "
from androguard.misc import APK
a = APK('game.apk')
print('Package:', a.get_package())
print('Min/Target SDK:', a.get_min_sdk_version(), a.get_target_sdk_version())
for p in sorted(a.get_permissions()): print('  perm:', p)
for p in sorted(a.get_declared_permissions()): print('  declared:', p)
for f in sorted(a.get_features()): print('  feature:', f)
"

# 危险权限快筛
aapt dump permissions game.apk | grep -iE \
  "READ_SMS|RECORD_AUDIO|CAMERA|FINE_LOCATION|CONTACTS|CALL_LOG|ACCESSIBILITY|DEVICE_ADMIN|NOTIFICATION_LISTENER|SYSTEM_ALERT_WINDOW|INSTALL_PACKAGES|QUERY_ALL_PACKAGES|PACKAGE_USAGE_STATS|VPN_SERVICE|WRITE_SECURE_SETTINGS"

# 运行时授予（镜像）
cat /data/system/users/0/runtime-permissions.xml \
  | grep -A 30 'pkg name="com.bad.app"'

# 反编译后调用
jadx -d out game.apk
grep -rE "getSystemService|LocationManager|TelephonyManager|SmsManager|MediaRecorder|ClipboardManager|AccessibilityService|NotificationListenerService|VpnService" out/sources/

# 数据出口
grep -rohE "https?://[a-zA-Z0-9./_-]+" out/sources/ | sort -u
grep -rohE "\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b" out/sources/ | sort -u

# Frida 实时
frida -U -f com.target.app --no-pause -l perm_hook.js
```

### Frida 模板：实时记录权限调用

```javascript
Java.perform(function() {
  var Ctx = Java.use("android.content.ContextWrapper");
  Ctx.checkSelfPermission.implementation = function(p) {
    console.log("[checkSelfPermission] " + p);
    Java.use("java.lang.Throwable").$new().printStackTrace();
    return this.checkSelfPermission(p);
  };

  var Act = Java.use("android.app.Activity");
  Act.requestPermissions.implementation = function(perms, code) {
    console.log("[requestPermissions] " + JSON.stringify(perms));
    return this.requestPermissions(perms, code);
  };

  // 高危服务绑定
  var Svc = Java.use("android.app.Service");
  Svc.onCreate.implementation = function() {
    var name = this.getClass().getName();
    if (name.indexOf("Accessibility") >= 0 ||
        name.indexOf("Notification") >= 0 ||
        name.indexOf("Vpn") >= 0) {
      console.log("[Service.onCreate] " + name);
    }
    return this.onCreate();
  };
});
```

---

## 9. 常见坑

- **新旧权限名同时声明**：`BLUETOOTH` + `BLUETOOTH_SCAN` 都写，兼容多版本
- **`maxSdkVersion` 反取证**：声明 max=22 → 高版本"看不到"
- **`<uses-feature>` 不是权限**：只是硬件依赖，对 Play Store 过滤设备用
- **隐式权限**：某些 ContentProvider 不需声明就能查（早期 Android）
- **反射 / native 绕开声明**：调用时不走标准 API，Manifest 没记录但实际能干 → 必看 native 字符串
- **自定义权限劫持**（前述）
- **runtime-permissions.xml 路径变**：Android 11+ 移到 `/data/system/users/0/runtime-permissions/`
- **Doze / 电池优化白名单**：`/data/system/deviceidle.xml`，恶意 app 求白名单 = 想后台常驻
- **VPN 服务**：`BIND_VPN_SERVICE` 一旦授予能截全部流量
- **可访问性服务**是 Android 上最危险的能力，单独拿到能模拟点击 + 读屏 = 半个 root
- **同名权限不同含义**：自定义和系统同名 → protection level 决定真实效力
- **签名权限组**：`<permission-group>` 把多个权限打包，授予一个等于授予全组（老 Android）

---

## 10. 实战证据链

```
1. AndroidManifest 声明权限清单                      （能力声明）
2. 危险组合命中（如 录音+摄像+定位+短信）            （威胁画像）
3. 代码里 grep 到 RECORD_AUDIO/CAMERA 等真实调用    （能力使用）
4. runtime-permissions.xml 显示用户已授予           （执行授权）
5. URL grep + 流量包印证数据上传到 C2 服务器        （数据流出）
6. Frida 运行时验证 hook 到 hook checkSelfPermission（动态印证）
```

任意 4 项匹配 = 强证据；6 项全有 = 铁证。

---

## 11. KB 联动

| 场景 | 跳哪 |
|---|---|
| APK 加解密分析 | `mobile/apk_crypto_analysis.md` |
| AhMyth RAT 实战权限 | `wp_index/美亚杯-2024团队赛.md` Q27-Q30 |
| 已卸载 app 权限残留 | `mobile/uninstalled_app_recovery.md` (L1) |
| 安卓模拟器 + 录屏 RAT | `solved/2022_changancup_mobile_exe_apk.md` |
| 反取证 / 权限滥用伪装 | `mobile/anti_forensics_and_misleading.md` |
