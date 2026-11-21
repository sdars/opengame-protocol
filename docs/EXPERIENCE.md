# 经验与教训（opengame.io 纯协议链路）

按时间顺序记录这次逆向里真正踩到的坑，以及每一条的**证据**和**修法**。
新坑直接追加到本文件末尾。

---

## 1. 目标其实不是 APK，别上逆向重型工具

一开始按“App 逆向”的惯性准备 jadx / Ghidra / Frida。实际上 `https://opengame.io/jam`
是纯 Web（Next.js App Router + RSC），**全部交互都是普通 HTTP**。

* 结论：这类目标不需要 adb、Frida、Dump、mitmproxy 绕 pinning。
* 正确的第一步是 `GET /jam` 拿 HTML → 找 `/_next/static/immutable/chunks/*.js` →
  在 chunk 里 grep `createServerReference` / `sponsor-code`，动作 id 和参数形状全在 JS 里。
* 真正需要动态手段的只有“需要浏览器执行 JS 才能拿到的运行时值”，本目标里没有。

## 2. Next.js server action 有三种线格式，猜错就白跑

| 形态 | body | 触发条件 |
|---|---|---|
| ① `useActionState` 表单 | `multipart/form-data`，字段带 `_1_$ACTION_*` 前缀 | React `useActionState` 包裹的 action |
| ② 普通 server reference | `text/plain`，内容是**参数 JSON 数组** | `createServerReference` |
| ③ 普通 API | `application/json` | 路由 handler |

* 坑 1：`useActionState` 的上一步 state 必须是 **JSON 对象**。传数组服务端直接忽略，
  表单静默退回上一步（表现为“发了码但状态还是 email”）。
* 坑 2：`saveJamInterest(answers)` 的 body 必须是 `[answers]`，
  传裸对象返回 `Those answers could not be read.`。
* 坑 3：`saveProfileDetails(new, baseline)` 有**并发校验基线**。第二参数传 `$0:0`
  或缺省 → `Your profile changed since this page loaded`。正解是重新读一次服务端
  下发的 draft 再提交（前端就是这么做的：读 draft → 提交 → 失败则重读重试）。
* 坑 4：形态② 的 body 不能是 JSON 对象，必须是数组；`claimFromHandlePage` 是
  `["handle", null]`，`welcomeFinished()` 是 `[]`。

## 3. 读 RSC payload 里的内联对象要反转义

`GET /welcome?step=profile` 的 HTML 里，`draft` / `interest` 是被转义后塞进内联
script 的：正则匹配到的是 `\"displayName\":\"...\"`，直接 `json.loads` 会失败，
必须先 `.replace('\\"', '"')` 再解析。

## 4. Flight 响应的解析

server action 响应是 React Flight：每行 `行号:JSON`，值之间用 `$@N` 引用。
解析时只需支持一层引用（`resolve()` 递归一层足够）。
登录成功的响应体里**没有** state 对象——判断登录成功要看
`Set-Cookie: sb-auth-auth-token`，而不是看响应体。

## 5. IMAP 共享收件箱必须用 UID 快照

`imap.aoog.de` 的 INBOX 有 11 万+ 封邮件，是所有别名的公共收件箱。

* 直接取“最新一封的 8 位码”会拿到上一次注册用过的旧码 → verify 失败。
* 正解：发码**前**记 `latest_uid()`，之后只接受 `UID > snapshot` 的邮件。
* 主题格式固定：`Your OpenGame sign-in code: NNNNNNNN`；另有 `Welcome to OpenGame`
  的欢迎信（同一 UID 之后），两者要区分。

## 6. Turnstile 不拦协议，但按邮箱域名计数

* sitekey `0x4AAAAAAEXt62cdsNuTd72E`，action `sign-in-code`。
* `cf-turnstile-response` 留空即可发码；服务端在缺 token 时按**邮箱域名**计数放行。
* 实测：`vmbus.de`、`625hsz-kaiyun.cyou`、`edu.vmbus.de` 都已触发
  `You've reached our limit for new accounts.`（注意 `edu.vmbus.de` 与 `vmbus.de`
  共用一个额度）；`fublcy.asia`(3 次)、`72oaop.bond`(1 次) 已用；
  `958889.xyz` 当时仍可用。
* 教训：注册阶段最容易卡住的不是协议，而是**可用邮箱域名池**，要提前准备多个后缀。

## 7. `claimedHere` / `refused` 是误导性文案，真正的闸门是服务端池

* 客户端只有在 `localStorage['og-sponsor-code-claimed:<sponsor>'] === '1'` 时才发
  `claimedHere:true`（本地已领标记）。
* 手工带上该字段，新账号 + 新出口 IP 也返回
  `This device has already claimed a fal coupon. Each person gets one.`——
  与实际情况无关，**不要把它当成反作弊结论**。
* `exhausted` 才是真实状态：服务端优惠码池为空。跨 10+ 个出口 IP、匿名/登录、
  完整 onboarding 与否，结果一致；`/jam` 的 SSR 也渲染
  `Batch 2 $25 in fal credits → All claimed`。
* 结论：客户端能做的都做完了，剩下的只能等补货 → 写了 `scripts/wait_for_offer.py`
  做轮询补货自动领取。

## 8. 优惠码载荷的字段名是 `id`（coupon）/ `url`（link），不是 `code`

从客户端 chunk 读出：

* `kind === 'coupon'` → 弹窗渲染 `a.id`（如 `FAL-OPENGAME-XXXXXX`）；
* `kind === 'code'` → 渲染 `a.url`（elevenlabs 的领取链接）；
* `kind === 'exhausted'` → 弹窗文案 `All claimed`；
* `action=claim` → 只回 `{"claimedAt":"<ISO>"}`，不回码。

一开始脚本按 `code/value/coupon` 取值，池空时永远走不到成功分支，所以没暴露；
读完 JS 才补上 `id`/`url`（`client.extract_sponsor_code()`）。

## 9. `/api/jam/sponsor-code` 的请求头是硬门槛

缺 `Origin: https://opengame.io` 或 `Referer: https://opengame.io/jam?perk=<sponsor>#sponsors`
→ `403 {"error":"Codes are handed out on opengame.io"}`。

## 10. 判定“是否线上实时响应”

Vercel 会缓存页面/接口。核对 `X-Vercel-Cache`（实测 `MISS` = 实时）比看 body 更可靠，
避免把缓存快照当成服务端现状。

## 11. 出口 IP 池的用法

* 一个端口 = 一个出口 IP；用户名格式 `<session>__<NN>_<country>`，
  `<session>__<country>` 也有效。
* 凭据放 `/root/grok/.env`（不入库），`proxy.py` 负责解析。
* 换 IP 只能改变“指纹”，改变不了服务端优惠码池状态——这一点在本目标上被反复验证。

## 12. 工程纪律（本仓库）

* Python 依赖统一装在 `/root/Knight/.venv`，所有脚本用
  `/root/Knight/.venv/bin/python` 运行。
* 主代码只放仓库源码目录；抓包、探针、dump 放 `tmp/逆向分析/<日期>/`，
  敏感产物（session token、账号记录）不入 Git。
* 收尾清理：停掉后台轮询/代理中继、删 `__pycache__`、删临时 dump。

## 13. 交付形态

最终交付 = **纯协议脚本**（`scripts/claim_coupon.py` / `scripts/wait_for_offer.py` +
`src/opengame_protocol/`）+ 协议文档（`docs/opengame_protocol.md`）+ 本文件。
链路里没有 adb、Frida、设备或任何 RPC 转发依赖。
