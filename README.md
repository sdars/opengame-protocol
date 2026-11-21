# opengame.io — 注册 / 登录 / 领取 $25 fal 优惠码（纯协议实现）

`https://opengame.io/jam` 活动的**纯 HTTP** 链路实现：注册 → 邮件验证码登录 → 认领 handle →
填写资料 → 调用 `/api/jam/sponsor-code` 领取 `fal-2`（$25 in fal credits）优惠码。

链路中**没有浏览器、没有 adb、没有 Frida、没有设备、没有 RPC 转发**：
全部是普通 HTTP 请求 + IMAP 读验证码。

* 接口协议细节： [`docs/opengame_protocol.md`](docs/opengame_protocol.md)
* 踩坑与经验： [`docs/EXPERIENCE.md`](docs/EXPERIENCE.md)

## 环境

```bash
# Python 依赖统一装在 /root/Knight/.venv（不污染系统环境）
/root/Knight/.venv/bin/pip install requests PySocks
```

## 用法

```bash
# 1) 端到端：注册 → 登录 → 认领 handle → 填资料 → 领优惠码
/root/Knight/.venv/bin/python scripts/claim_coupon.py \
    --domain 958889.xyz \
    --out tmp/逆向分析/2026-11-21/runs/account_958889.json

# 2) 优惠码池补货后自动领取（轮询 + 领取 + 回读）
/root/Knight/.venv/bin/python scripts/wait_for_offer.py \
    --resume tmp/逆向分析/2026-11-21/runs/account_958889.json \
    --poll 180 --hours 12

# 3) 复用已有账号/会话
/root/Knight/.venv/bin/python scripts/claim_coupon.py \
    --resume tmp/逆向分析/2026-11-21/runs/account_958889.json
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--domain` | 注册用邮箱后缀（默认 `fublcy.asia`） |
| `--email` / `--name` | 指定邮箱 / 显示名 |
| `--sponsor` | sponsor id（默认 `fal-2` = $25；`fal` = $50；`elevenlabs` = 链接） |
| `--proxy-off` | 不走 SOCKS5 出口池，直连 |
| `--proxy-offset` | 出口池端口偏移，一个端口一个出口 IP |
| `--wait --poll 120 --wait-hours 72` | 池空时持续轮询，补货即自动领取 |
| `--resume <file>` | 复用账号记录与会话 cookie |
| `--out <file>` | 账号/优惠码记录落盘位置 |

## 目录结构

```
src/opengame_protocol/
  actions.py    action id、路由、router state tree、站点常量
  client.py     HTTP 客户端（三种请求形态 + flight 解析 + sponsor API）
  identity.py   真人特征姓名 / handle / 邮箱前缀 / 密码 / bio
  mailbox.py    IMAP 读 8 位验证码（UID 快照防旧码）
  proxy.py      SOCKS5 出口池
  socks_bridge.py  本地 SOCKS5 认证中继（仅调试抓包用，不在交付链路里）
scripts/
  claim_coupon.py   端到端 CLI
  wait_for_offer.py 优惠码池补货轮询 + 自动领取
docs/
  opengame_protocol.md  接口协议说明
  EXPERIENCE.md        经验教训
tmp/逆向分析/<日期>/   抓包、JS 静态分析、探针、账号记录（不进 Git）
```

## 当前状态（2026-11-21 实测）

协议链路已全部闭合并有实测响应为证：

| 步骤 | 结果 |
|---|---|
| 发码 | `{"step":"code","notice":"Sent. ..."}` |
| 验证 | 下发 `sb-auth-auth-token`，登录成功 |
| 认领 handle | `{"status":"taken","handle":"pebble76","ogNumber":3992}` |
| 活动意向 | `{"ok":true,"interest":{...}}` |
| 保存资料 | `{"ok":true}`，显示名读回一致 |
| 领优惠码 | `{"kind":"exhausted"}` ← 服务端 fal-2 码池已空 |

`fal-2` 池为空是服务端状态（`/jam` SSR 同时渲染 `Batch 2 → All claimed`），
跨 10+ 个出口 IP、匿名/登录均一致；池一旦补货，`scripts/wait_for_offer.py`
会自动 `open → claim → 回读` 并落盘优惠码 id。
