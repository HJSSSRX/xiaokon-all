---
tags: [mobile, geolocation, gps, exif, wifi, bssid, cell_id, ip_geo, ocr, geoguessr,
  knowledgec, routined, methodology, mobile_forensics]
tools: [exiftool, tesseract, paddleocr, sqlite3, folium, qgis, mmdblookup, plistutil,
  strings]
category: mobile_forensics
difficulty: medium
source: kb_seed_2026-05-07
verified: false
related: [uninstalled_app_recovery.md, anti_forensics_and_misleading.md, timestamps_reference.md]
---

# 位置 / 活动区域取证

> **核心心法**：位置信息分布在 8 类源头里，没有任何单一源完整。**没拍 GPS 的照片 ≠ 没法定位**。视觉 OCR + WiFi BSSID + 同时段聊天 三处一拼，多数能锁到 50 米内。

## 0. 八类源头

1. **照片元数据** — EXIF GPS / thumbcache
2. **App 自身定位库** — Google/高德/百度/微信/滴滴/运动
3. **系统级位置缓存** — Android LocationManager、iOS `consolidated.db` / `routined`
4. **WiFi BSSID** — 路由器 MAC 反查
5. **基站 Cell ID** — LAC/CID 反查
6. **IP 地理库** — 流量包 / 登录日志
7. **照片视觉信息** — 路牌、店招、车牌、阴影、建筑
8. **文本/聊天/搜索/社交关联**

---

## 1. 照片 EXIF GPS ★★★

### 取数
```bash
exiftool -GPS* -DateTimeOriginal *.jpg
exiftool -ee -GPS* video.mp4

# 批扫整个手机，输出 TSV
find {extract} -type f \( -iname "*.jpg" -o -iname "*.heic" -o -iname "*.mp4" \) \
  -print0 | xargs -0 exiftool -filename -gpslatitude# -gpslongitude# \
  -datetimeoriginal -gpsaltitude 2>/dev/null > photo_gps.tsv
```

### 关键字段
| 字段 | 含义 |
|---|---|
| `GPSLatitude` / `GPSLongitude` | 度分秒 |
| `GPSLatitudeRef` / `GPSLongitudeRef` | N/S, E/W |
| `GPSAltitude` / `GPSAltitudeRef` | 海拔，**能区分楼层** |
| `GPSDateStamp` + `GPSTimeStamp` | **UTC**，对比本地能查时区 |
| `GPSImgDirection` | 拍摄朝向，0=正北 |
| `GPSSpeed` / `GPSSpeedRef` | 拍摄时速度，区分行车/步行 |
| `GPSDOP` | 精度，<5 = 精确 |

iOS HEIC 直接支持。Apple 还在 EXIF 里写 **Run Time**、**当时温度**（部分机型）。

### 坑
- 用户关"位置标记"→ EXIF 没 GPS，但 `Photos.sqlite`/`PhotoData/` 系统级仍可能有
- 批量擦 EXIF 工具会留 mtime 变化，但 SQLite 索引可能漏网
- 微信发图**剥 EXIF**，转账图无 GPS，但**接收方相册原图**可能有
- 转 KML 一次看：`exiftool -p kml.fmt -filename {extract}/DCIM/ > tracks.kml`

---

## 2. App 自身定位库 ★★★

| App | 数据库 / 路径 | 关键 |
|---|---|---|
| **Google Maps (Android)** | `com.google.android.apps.maps/databases/gmm_myplaces.db` | 收藏地点、家/公司 |
| Google Maps timeline | `com.google.android.apps.maps/files/timeline-state` | 历史轨迹（云端是金矿） |
| **高德** | `com.autonavi.minimap/databases/` | `search_history`, `favorite_points` |
| **百度地图** | `com.baidu.BaiduMap/databases/` | `mybookmark`, `search_history` |
| **微信** | 解密后 `EnMicroMsg.db.message type=48` | XML 含 `<location x="lng" y="lat" label="..."/>` |
| **滴滴** | `com.sdu.didi.psnger/databases/` | 历史订单含起终点 |
| **运动 app**（Keep/Strava/小米运动） | `databases/track.db` 等 | GPS 轨迹点 |
| **支付宝/美团** | `databases/` | 收货地址、消费地点 |
| **Apple Maps (iOS)** | `MapsSync_*.sqlitedb` | 搜索/收藏 |
| **iOS Significant Locations** | `cache_encryptedB.db` (加密) / `routined-cache.sqlite` | 系统记录的"常去地点" |

```sql
-- 微信发的位置消息
SELECT createTime, content FROM message WHERE type = 48;

-- iOS Significant Locations
SELECT datetime(ZCREATIONDATE+978307200,'unixepoch'),
       ZLATITUDE, ZLONGITUDE, ZLABEL
FROM ZRTLEARNEDLOCATIONOFINTERESTMO;
```

---

## 3. 系统级位置缓存 ★★★

### Android
```
/data/system/locationsettings.xml
/data/data/com.google.android.location/
/data/misc/location/
/data/data/com.android.providers.settings/databases/settings.db
  → settings 表 'location_providers_allowed'
/data/data/com.google.android.gms/databases/herrevad   # GMS 网络位置缓存
```

### iOS
```
/private/var/mobile/Library/Caches/locationd/
  cache_encryptedA.db, cache_encryptedB.db        ⚠️ 加密
/private/var/mobile/Library/Caches/com.apple.routined/
  routined-cache.sqlite                            # Significant Locations
/private/var/mobile/Library/CoreDuet/Knowledge/
  knowledgeC.db                                    # /location/visit
/private/var/root/Library/Caches/locationd/clients.plist
```

```sql
-- iOS knowledgeC visits
SELECT datetime(ZSTART_DATE+978307200,'unixepoch'),
       ZVALUE_STRING
FROM ZOBJECT WHERE ZSTREAM_NAME = '/visit';
```

---

## 4. WiFi BSSID 反查 ★★★

每个家用路由器 MAC 唯一 → 反查地理库 → **哪怕手机从没开 GPS**也能定位。

### 取数
```bash
# Android
cat /data/misc/wifi/WifiConfigStore.xml          # 当前/历史 SSID + BSSID
cat /data/misc/wifi/wpa_supplicant.conf          # 旧 ROM
strings /data/misc/wifi/WifiConfigStore.xml | grep -E "SSID|BSSID|key"

# iOS
plutil -p /private/var/preferences/SystemConfiguration/com.apple.wifi.plist
```

### 反查 API
- **WiGLE** https://wigle.net — 全球众包 WiFi/蓝牙地图，需 API key
- **Mylnikov** https://www.mylnikov.org — 免费 BSSID → 经纬度
- **Apple LS** — 私有协议，`iSniff-GPS` 模拟请求
- **Google Geolocation API** — 付费

```python
import requests
mac = "AA:BB:CC:DD:EE:FF"
r = requests.get(f"https://api.mylnikov.org/geolocation/wifi?v=1.1&data=open&bssid={mac}")
print(r.json())  # {"data":{"lat":...,"lon":...,"range":...}}

# WiGLE
auth = ('USER', 'KEY')
r = requests.get("https://api.wigle.net/api/v2/network/search",
                 params={"netid": mac}, auth=auth)
```

精度：城市核心区 50m，郊区 1km+，新装路由没数据。

---

## 5. 基站 Cell ID（LAC + CID）★★

手机从未开 GPS、未连 WiFi，但只要联过基站就有痕迹。

### 取数
```
/data/data/com.android.providers.telephony/databases/telephony.db
logcat 里的 "RIL_REQUEST_GET_NEIGHBORING_CELL_IDS"
mmssms.db 短信发送时附带 cell info
```

### 反查
- **OpenCellID** https://opencellid.org（免费，需注册）
- **CellMapper** https://www.cellmapper.net

```python
import requests
r = requests.get("https://opencellid.org/cell/get",
                 params={"key": "...", "mcc": 460, "mnc": 0,
                         "lac": 12345, "cellid": 67890})
```

中国 mcc=460，mnc：移动 0/2/7、联通 1/6、电信 3/5/11。

---

## 6. IP 地理库 ★

```bash
mmdblookup --file GeoLite2-City.mmdb --ip 1.2.3.4
curl https://ipinfo.io/1.2.3.4/json
curl https://ip-api.com/json/1.2.3.4
```

⚠️ 城市级精度，VPN/CDN 会失真，**仅辅助**。

---

## 7. 照片视觉信息 ★★★（无 GPS 时的杀手锏）

| 看什么 | 能推什么 |
|---|---|
| 路牌、门牌、店招 | 直接给地名，OCR 后搜 |
| 车牌前 2 位 | 省份缩写 + 城市字母 |
| 公交站牌 | 站名 + 路线 |
| 出租车颜色 | 北京黄、上海蓝、广州红 |
| 阴影长度 + 方向 | 经度 + 季节 + 时刻 |
| 建筑风格 | 南方骑楼 / 北方四合院 / 江南水乡 |
| 植被 | 椰子树 = 华南 |
| 插座形状 | 中国 8 字 / 欧标 / 美标 / 英标 |
| 文字字符集 | 简/繁/日/韩/泰 |
| 倒影里的招牌 | 玻璃/水面反射，常被忽略 |
| 天气 / 雾霾水平 | 比对气象历史定日期 |

### OCR 工具
```bash
tesseract image.jpg out -l chi_sim+eng
paddleocr --image_dir image.jpg --lang ch
```

PaddleOCR 中文最强；Google Lens / 百度识图 在线效果好。

### GeoGuessr 思路
- 把识别出的店招丢 **百度地图**（对店招检索更全）
- 建筑特征丢 **Google Earth** 卫星图比对
- **街景比对**：百度街景 / Google Street View

---

## 8. 文本 / 聊天 / 搜索 / 社交 ★★

```bash
# 微信解密库扫地名
sqlite3 EnMicroMsg.db "SELECT createTime, content FROM message
 WHERE content LIKE '%路%' OR content LIKE '%号%' OR content LIKE '%店%'
    OR content LIKE '%地铁%' OR content LIKE '%站%'
    OR content LIKE '%医院%' OR content LIKE '%学校%'"

# 输入法词库（搜过的地名）
strings /data/data/com.sohu.inputmethod.sogou/files/usrdict/* | head

# 浏览器搜索
sqlite3 chrome/History "SELECT term FROM keyword_search_terms"

# 短信里的取件码 / 外卖
sqlite3 mmssms.db "SELECT * FROM sms WHERE body LIKE '%送达%' OR body LIKE '%取件%'"
```

---

## 9. 构建活动区域图

### 9.1 数据汇总
统一格式：
```
timestamp_utc, lat, lon, source, accuracy_m
2026-05-07 14:00:00, 39.9042, 116.4074, photo_exif, 5
2026-05-07 14:30:00, 39.9043, 116.4075, wechat_loc, 50
2026-05-07 14:30:05, 39.9040, 116.4070, wifi_bssid, 200
```

### 9.2 可视化
```python
import folium
m = folium.Map(location=[39.9, 116.4], zoom_start=12)
for ts, lat, lon, src, acc in points:
    folium.CircleMarker([lat, lon], radius=3,
        popup=f"{ts}<br>{src}").add_to(m)
m.save("heatmap.html")
```

或：QGIS + heatmap 插件 / Google MyMaps 导入 KML。

### 9.3 行为模式
- **3 个聚类簇** = 家 / 公司 / 常去（餐厅、学校）
- **凌晨 2-6 点** = 99% 是家
- **工作日 9-18 点** = 公司
- **周末高频** = 兴趣点
- **时间空窗** = 关机/出境/刻意躲避，要追问

---

## 10. 跨源交叉验证

某关键时刻 X 多源印证：

| 源 | 是否到位 |
|---|---|
| EXIF GPS | ✅ |
| WiFi BSSID 同坐标 ±100m | ✅ |
| 同时段微信发位置 | ✅ |
| 健康 app 步数/心率 | ✅ |
| 基站 cell | ✅ |
| 叫车订单起点 | ✅ |

6 项匹配 = 铁证。EXIF 说 A 但 WiFi 说 B → 大概率 EXIF 被改。

---

## 11. 决策树

```
"嫌疑人某时间段在哪 / 活动区域"
   │
   ├─ Step 1: EXIF GPS 全相册批扫
   ├─ Step 2: App 定位库（地图/微信/滴滴/运动）
   ├─ Step 3: 系统级缓存（iOS routined+knowledgeC / Android GMS）
   ├─ Step 4: WiFi BSSID 反查
   ├─ Step 5: 基站 cell ID 反查
   ├─ Step 6: 视觉 OCR + GeoGuessr
   └─ Step 7: 文本/聊天/搜索关联
```

---

## 12. 常见坑

- **EXIF 时间本地、GPS 时间 UTC**：不一致 = 改过时区，反取证强信号
- **微信图片转发 EXIF 没了**：原图在发送方相册才有
- **iOS Significant Locations 加密**：需 Keychain key
- **WiFi BSSID 精度**：核心区 50m，郊区 1km+
- **Cell ID 库不全**：新建 / 室内分布基站没数据
- **VPN 出口 IP 不可信**：靠 SSID/BSSID
- **照片背景反取证**：嫌疑人故意截带误导地标，看光线/阴影是否物理一致
- **Google timeline 云端是金矿**：需要嫌疑人账户授权
- **运动 app 轨迹精度**：无 GPS 时按步数估距，**别当 GPS 用**
- **iOS 飞行模式**：仍记 WiFi 扫描，不上报
- **Android mock location**：开发者选项可改 GPS 数值，但 WiFi/cell 改不了
- **HEIC + Live Photo**：除了主图还有 .MOV 副本，时间戳/GPS 偶尔不一致

---

## 13. 实战证据链示例

```
1. 嫌疑人凌晨 2 点 EXIF GPS 在 X 坐标         （照片层）
2. 同时段连接的 WiFi BSSID 反查 = X 附近 50m   （网络层）
3. 同时段基站 cell 反查 = X 附近 500m         （运营商层）
4. 同时段微信发"我在家了"                     （行为层）
5. 同时段健康 app 步数停止 = 静止             （生理层）
6. iOS routined "Home" label 坐标 = X         （系统层）
```

任意 4 项匹配 = 强证据；6 项全匹配 = 铁证不可撼动。
