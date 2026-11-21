# opengame.io — 纯协议接口说明

本文档描述 `https://opengame.io/jam` 活动页的注册 / 登录 / 认领 handle / 填写资料 / 领取
sponsor 优惠码（`fal-2` = $25 fal credits）的**纯 HTTP** 调用链。

链路上没有浏览器、没有 adb、没有 Frida、没有设备、没有 RPC 转发：全部是普通 HTTP 请求，
由 `src/opengame_protocol/` 下的 Python 实现并由 `scripts/claim_coupon.py` 驱动。

所有字段均来自线上实测（2026-11-21），包括抓到的 Next.js RSC 客户端 chunk
（`/_next/static/immutable/chunks/*.js`）里的 `createServerReference` id、
`/api/jam/sponsor-code` 的响应分支，以及真实请求的 status code 与响应体。

---

## 0. 端点总览

| 用途 | 方法 | 路径 | 请求形态 |
|---|---|---|---|
| 注册/登录 | GET | `/auth/sign-in?next=<url>` | 页面 + 下发 `__Host-og_anon` |
| 注册/登录 | POST | `/auth/sign-in` | ①multipart 表单 action |
| handle 可用性 | GET | `/api/handles/availability?handle=<h>` | JSON |
| 认领 handle | POST | `/handle` | ②纯文本 server action |
| 活动意向 | POST | `/handle` | ②纯文本 server action |
| 外观/角色 | POST | `/welcome?step=avatar\|character\|profile` | ②纯文本 server action |
| 资料保存 | POST | `/welcome?step=profile` | ②纯文本 server action（带 baseline） |
| 完成引导 | POST | `/welcome?step=profile` | ②纯文本 server action（空参） |
| 当前用户 | GET | `/api/social?resource=bootstrap&input=%7B%7D` | JSON |
| **优惠码** | POST | `/api/jam/sponsor-code` | ③JSON API |

三种请求形态的线格式见第 2 节。

---

## 1. 会话模型

* `GET /auth/sign-in` 响应头下发 `__Host-og_anon`（匿名会话标识）。
* 登录成功后服务端下发 `sb-auth-auth-token` cookie（base64 JWT，内含 `user.id`、
  `email`、`email_verified`、`role`、`expires_in`（3600s）、`refresh_token`）。
  这是唯一需要持久化的凭据，`--resume` 直接把它写回 cookie jar 即可续用。
* 所有 server action 与 JSON API 都依赖该 cookie；匿名调用 sponsor-code 会被
  引导到登录页（见第 5 节状态机）。

---

## 2. 三种请求形态

### 2.1 形态①：`useActionState` 表单 action（登录卡片）

Next.js `useActionState` 包裹的 server action 必须以 `multipart/form-data` 发送，
字段名带 React 的 action ref 前缀：

```
POST /auth/sign-in
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary<rand>
Next-Action: 6092819032bb6918017b269ae557946028cdf22d53
Accept: text/x-component
Next-Router-State-Tree: %5B%22%22%2C%7B%22children%22...
Origin: https://opengame.io
Referer: https://opengame.io/auth/sign-in

_1_$ACTION_REF_2 = ""
_1_$ACTION_2:0   = {"id":"6092819032bb6918017b269ae557946028cdf22d53","bound":"$@1"}
_1_$ACTION_2:1   = {"step":"email","email":"","attempts":0}
_1_$ACTION_KEY   = <32 位 hex>
_1_next                  = /jam?perk=fal-2#sponsors
_1_email                 = jasper4650@72oaop.bond
_1_cf-turnstile-response = 
_1_og-turnstile-state     = 
_1_intent                = send | verify
_1_code                  = <8 位数字，仅 verify>
0                = [{"step":"email","email":"","attempts":0},"$K1"]
```

要点：

* `_1_$ACTION_2:1`（上一步 state）必须是 **JSON 对象**。传数组会被服务端忽略，
  表单会退回上一步。
* `0` 字段是 `[state, "$K1"]` 的 JSON 数组。
* `cf-turnstile-response` 可以为空：Turnstile sitekey
  `0x4AAAAAAEXt62cdsNuTd72E`、action `sign-in-code`，服务端在无 token 时按
  **邮箱域名**计数放行（同一域名约 3~4 次后返回 `ACCOUNT_LIMIT`）。

响应是 React Flight（`text/x-component`），`parse_flight()` 解析 `行号:JSON` 记录，
`$@N` 引用可解析一层。

### 2.2 形态②：普通 server reference

`createServerReference` 生成的 action：**纯文本 body = 参数 JSON 数组**，
`Content-Type: text/plain;charset=UTF-8`。

```
POST /handle
Content-Type: text/plain;charset=UTF-8
Next-Action: 605ff96286ee0aded22fc192db4556cb8a1d5f9f2e
Accept: text/x-component

["pebble76",null]                # claimFromHandlePage(handle, errand)
[{"participating":true,...}]     # saveJamInterest(answers)  ← 必须包一层数组
["circle.classic.white"]        # saveAvatarLook(look)
["c3.classic.regular..."]       # saveCharacterLook(look)
[{"displayName":...}, {draft}]   # saveProfileDetails(new, baseline)
[]                               # welcomeFinished()
```

* `saveJamInterest` 传裸对象会返回 `Those answers could not be read.`。
* `saveProfileDetails` 第二个参数是**并发校验基线**（服务端此前下发的 draft）。
  传 `$0:0` 或缺省会得到 `Your profile changed since this page loaded`；
  重新读一次 draft 再提交即可（客户端行为即如此）。

### 2.3 形态③：普通 JSON API

```
POST /api/jam/sponsor-code
Content-Type: application/json
Origin: https://opengame.io
Referer: https://opengame.io/jam?perk=fal-2#sponsors

{"sponsor":"fal-2","action":"open|claim|warm","claimedHere":true?}
```

* 缺 `Origin`/`Referer` → `403 {"error":"Codes are handed out on opengame.io"}`。
* `action=claim` → `{"claimedAt":"<ISO8601>"}` 或 `{"claimedAt":null}`。
* `action=warm` → `204`（前端 hover 预热用，无业务含义）。

---

## 3. Action id 表

| 名称 | Next-Action id |
|---|---|
| signIn | `6092819032bb6918017b269ae557946028cdf22d53` |
| signInWithGoogle | `406c22d75bdc1dab1289532ce6b3971a675bca6635` |
| claimFromHandlePage | `605ff96286ee0aded22fc192db4556cb8a1d5f9f2e` |
| renameTo | `40194b4d7a8766c0c17d7c2cf6f25706fe222f3a55` |
| saveJamInterest | `40c70d59bc67f324382a96cbc041ee1fc67b66521c` |
| saveAvatarLook | `406c9f63e7bfc52580f9f57101799502bfce4fe048` |
| saveCharacterLook | `40df74d27444b943f91034902148e7ea913a682eb0` |
| saveProfileDetails | `601461909aac6b848b74520bb64ef28525a163efa7` |
| saveWelcomeInterest | `40d1f4411208330539719ab77dfc0f78f1b4879923` |
| welcomeFinished | `008a08d1454909055c4ee71760d1b98666afc2de34` |
| connectX | `406d161fea338d0390188feee5b347e49f356d789a` |

Action id 随站点发版变化；重新获取的方法：抓 `/_next/static/immutable/chunks/*.js`，
grep `createServerReference(` 后的 40 位 hex。

---

## 4. 登录状态机

站点常量（来自客户端 chunk）：OTP 长度 8、TTL 600s、重发冷却 300s、尝试上限 5。

```
GET  /auth/sign-in?next=/jam%3Fperk%3Dfal-2%23sponsors   → cookie __Host-og_anon
POST /auth/sign-in  intent=send    → {"step":"code","email":...,"attempts":0,
                                      "notice":"Sent. If it is not there in a minute,
                                                 check the spam folder."}
     邮件主题: "Your OpenGame sign-in code: NNNNNNNN"
POST /auth/sign-in  intent=verify  → 下发 sb-auth-auth-token cookie
                                      （响应体是 react fragment，无 state 对象）
```

错误态（实测原文）：

* 域名额度用尽 → `{"step":"email",...,"error":"You've reached our limit for new
  accounts. Each person may have one OpenGame account."}`（按邮箱域名计数）
* 码错误 → `{"step":"code",...,"error":...}`，`attempts` 递增，上限 5 次。

邮件读取：IMAP `imap.aoog.de:993`（SSL），登录 `chatgpt@958889.xyz`，
所有别名转发到同一收件箱。**必须用 UID 快照**：请求发码前记录 `latest_uid()`，
只接受 UID 更大的邮件，否则会拿到上一次已经用过的码。

---

## 5. sponsor 优惠码状态机（`POST /api/jam/sponsor-code`）

响应体恒为一个对象，判别字段是 `kind`：

| `kind` | 触发条件 | 载荷 |
|---|---|---|
| `sign-in` | 未登录 | `{"kind":"sign-in","href":"/auth/sign-in?next=%2Fjam%3Fperk%3Dfal-2%23sponsors"}` |
| `handle` | 已登录但没有 handle | `{"kind":"handle","href":"/welcome?next=..."}` |
| `coupon` | 池中有货（fal / fal-2） | `{"kind":"coupon","id":"FAL-OPENGAME-XXXXXX","claimedAt":null}` |
| `code` | 池中有货（elevenlabs） | `{"kind":"code","url":"https://...","claimedAt":null}` |
| `exhausted` | 池已空 | `{"kind":"exhausted"}` |
| `refused` | 非个人码 sponsor（meshy 等）或设备已领过 | `{"kind":"refused","message":"We could not load your code. If one was set aside for you, it stays yours. Try again in a minute."}` |

`sponsor` 取值与文案（客户端常量 `PERSONAL_CODE_KINDS` / `PERSONAL_CODE_NAMES` /
`PERSONAL_COUPON_REDEEM`）：

| sponsor | 类型 | 名称 | 额度 | 兑换说明 |
|---|---|---|---|---|
| `fal-2` | coupon | fal | $25 | Add a payment method. You will not be charged. |
| `fal` | coupon | fal | $50 | Add billing details. |
| `elevenlabs` | link | ElevenLabs | 一个月 Creator plan | — |

除这三个之外的所有 sponsor id 都是 `refused`（实测 `fal-1` / `fal-3` / `fal-4` / `fal_2` /
`FAL-2` / `elevenlabs-1` / `elevenlabs-2` / `meshy` / `chroma` 全部落到
`{"kind":"refused","message":"We could not load your code. If one was set aside for you,
it stays yours. Try again in a minute."}`）。2026-11-21 实测三个合法 sponsor 的
`open` 结果分别是 `fal-2 → exhausted`、`fal → exhausted`、`elevenlabs → exhausted`，
即服务端码池全部为空。

### `claimedHere` 的真实语义

客户端 `j()` 只有在 `localStorage['og-sponsor-code-claimed:' + sponsor] === "1"` 时才带上
`claimedHere:true`（本地已领过标记）。带上它，服务端会返回：

```
{"kind":"refused","message":"This device has already claimed a fal coupon. Each person gets one."}
```

这是**误导性文案**：新账号 + 新出口 IP 手工带上该字段同样得到该文案，说明它只是
“本地已领过”的回执通道，真正的闸门在服务端优惠码池。

### 领取动作

```
POST /api/jam/sponsor-code {"sponsor":"fal-2","action":"open"}   → {"kind":"coupon","id":"FAL-OPENGAME-XXXXXX",...}
POST /api/jam/sponsor-code {"sponsor":"fal-2","action":"claim"}  → {"claimedAt":"2026-11-21T...Z"}
POST /api/jam/sponsor-code {"sponsor":"fal-2","action":"open"}   → 回读，id 保持不变
```

`claimedAt` 一旦有值，该账号在 fal-2 上就固定拿到同一个 coupon id（与前端
“Your coupon ID is yours … You copied this coupon ID on …” 文案一致）。

---

## 6. 活动页 SSR 校验

`GET /jam`（带会话）会渲染每个 sponsor 的批次状态，可用来交叉验证 API：

* fal Batch 1 `$50 in fal credits` → `Offer ended`
* fal Batch 2 `$25 in fal credits` → `All claimed`
* elevenlabs `A free month of the Creator plan, with 131,000 credits` → `All claimed`

本仓库 2026-11-21 的实测：SSR 与 API 结论一致（fal-2 池已空）。

---

## 7. curl 最小复现

```bash
# 1. 取匿名 cookie
curl -sS -c jar.txt 'https://opengame.io/auth/sign-in?next=%2Fjam%3Fperk%3Dfal-2%23sponsors' > /dev/null

# 2. 发码（multipart 表单 action，字段见 2.1）
curl -sS -b jar.txt -c jar.txt 'https://opengame.io/auth/sign-in' \
  -H 'Next-Action: 6092819032bb6918017b269ae557946028cdf22d53' \
  -H 'Accept: text/x-component' \
  -H 'Origin: https://opengame.io' \
  -H 'Referer: https://opengame.io/auth/sign-in' \
  -F '_1_$ACTION_REF_2=' \
  -F '_1_$ACTION_2:0={"id":"6092819032bb6918017b269ae557946028cdf22d53","bound":"$@1"}' \
  -F '_1_$ACTION_2:1={"step":"email","email":"","attempts":0}' \
  -F '_1_$ACTION_KEY=0123456789abcdef0123456789abcdef' \
  -F '_1_next=/jam?perk=fal-2#sponsors' \
  -F '_1_email=user@example.com' \
  -F '_1_cf-turnstile-response=' \
  -F '_1_og-turnstile-state=' \
  -F '_1_intent=send' \
  -F '0=[{"step":"email","email":"","attempts":0},"$K1"]'

# 3. 换 session（把 NNNNNNNN 换成邮件里的 8 位码，intent=verify，
#    _1_$ACTION_2:1 改为 {"step":"code","email":"...","attempts":0}）

# 4. 认领 handle（纯文本 action）
curl -sS -b jar.txt 'https://opengame.io/handle' \
  -H 'Next-Action: 605ff96286ee0aded22fc192db4556cb8a1d5f9f2e' \
  -H 'Content-Type: text/plain;charset=UTF-8' \
  -H 'Accept: text/x-component' \
  -H 'Origin: https://opengame.io' \
  -d '["myhandle",null]'

# 5. 优惠码
curl -sS -b jar.txt 'https://opengame.io/api/jam/sponsor-code' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://opengame.io' \
  -H 'Referer: https://opengame.io/jam?perk=fal-2#sponsors' \
  -d '{"sponsor":"fal-2","action":"open"}'
```

---

## 8. 实现位置

| 文件 | 职责 |
|---|---|
| `src/opengame_protocol/actions.py` | action id、路由、router state tree、站点常量 |
| `src/opengame_protocol/client.py` | HTTP 客户端：三种请求形态、flight 解析、sponsor API |
| `src/opengame_protocol/identity.py` | 真人特征姓名 / handle / 邮箱前缀 / 密码 / bio |
| `src/opengame_protocol/mailbox.py` | IMAP 读取 8 位码（UID 快照） |
| `src/opengame_protocol/proxy.py` | SOCKS5 出口池、出口 IP 查询 |
| `scripts/claim_coupon.py` | 端到端 CLI（注册 → 领码 → 回读） |
| `scripts/wait_for_offer.py` | 优惠码池补货轮询 + 自动领取 |
