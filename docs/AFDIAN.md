# 爱发电接入结论（2026-11-08，按官方开发者文档核实）

> 结论：**服务端可核验，可以做。** 但它不是 Stripe 式的完整订阅 API，
> 有明确边界（见第 3 节）。站内不再做微信/支付宝商户号收款。
>
> **用户决定（2026-11-08）：分两步走。**
> **(a) 现在：只外链跑起来**——网站保持免费公开，会员专属内容放爱发电，
> 站里只挂链接，不做服务端核验，不锁任何站内内容，不需要 API Token。
> 方法说明页“免费与会员”已按这个口径写（`frontend/app/method/page.tsx`）。
> **(b) 以后：有了付费用户，再做服务端核验**——第 2 节的链路、第 3 节的边界、
> 第 5 节第 5–6 步（取 API Token、OAuth2 申请）全部是 (b) 阶段的事，
> 到时把 `config/afdian.yaml` 的 `mode` 改成 `server_verified` 再动手。
> 会员页文案里不再写“支付渠道尚未接入（需要商户资质）”这类说法。

## 1. 官方开放能力（有文档，不是推测）

- 开发者文档：https://guide.afdian.com/creator/developer（API + Webhook）
- OAuth2 文档：https://guide.afdian.com/creator/oauth2
- 开发者后台：https://afdian.com/dashboard/dev（取 `user_id`、生成 API Token、配 Webhook URL）
- 创作者指南：https://guide.afdian.com/new/for-new-creators

### 开放 API（只有 3 个）

| 接口 | 用途 | 关键返回 |
|---|---|---|
| `POST https://afdian.com/api/open/ping` | 连通性与签名自检 | `ec:200, em:"pong"` |
| `POST https://afdian.com/api/open/query-order` | 查历史订单（每页 50 条） | `out_trade_no / user_id / plan_id / month / total_amount / status（2=交易成功）/ custom_order_id` |
| `POST https://afdian.com/api/open/query-sponsor` | 查赞助者（默认每页 20 人） | 每人 `current_plan{plan_id, price, pay_month, expire_time（秒级时间戳）, permanent} / all_sum_amount / last_pay_time` |

认证：`user_id + API Token + MD5 签名`（`sign = md5({token}params{params}ts{ts}user_id{user_id})`，
token 只参与签名、不传给服务端）。**必须服务端调用，token 不可放前端/公开仓库。**

### 没有的东西

- 没有“查某用户在某档位是否仍有效”的单点接口：用 `query-sponsor` 按 `user_id` 过滤，
  读 `current_plan.plan_id + expire_time > now` 自行判定。
- 没有列出全部方案的接口：方案 ID 只能从创作者后台人工取。
- `query-plan` 只在第三方 CLI 里出现，官方文档全文没找到，列为未证实。

### Webhook（有，但无签名、无取消/到期事件）

- 开发者后台填通知 URL，有订单时平台 POST 该 URL；`data.type` 目前仅为 `order`。
- **官方文档没有给出任何验签方式**（推送体无 `sign` 字段、无签名头）。
  不能只凭收到回调就开通权益：必须调 `query-order` 按 `out_trade_no` 二次确认
  （校验金额与 `plan_id`），并做 `out_trade_no` 幂等。
- 事件范围：目前仅推送交易成功的订单；**没有续费/取消/到期事件**。
  爱发电没有自动续费（官方 FAQ 明确），“续费”就是一笔新订单；
  “过期”没有任何推送，只能靠定时轮询 `query-sponsor` 的 `expire_time` 发现。
- 接收方必须返回 `{"ec":200,"em":""}`，否则平台视为回调失败。

### OAuth2（身份桥，不是赞助核验）

- 仅 `authorization_code` 模式，适用于有 server 端的应用；**需私信官方人工申请**
  （提供应用名称、可信域名和 clientSecret，不提供则官方随机生成）。
- 流程：用户同意授权 → 服务端换 `user_id`（只返回用户 ID，不返回赞助/档位/有效期），
  再拿这个 ID 调 `query-sponsor` 核验赞助状态。
- 替代方案：下单链接 `custom_order_id` 写本站用户 ID（订单里原样带回），
  但该参数未出现在现版指南正文，接入前须实测确认。

## 2. 推荐链路（(b) 阶段：有了付费用户后才做；(a) 阶段只外链，不走这条链路）

```
用户在网站点“成为会员”
  → 跳爱发电档位下单（URL 带 custom_order_id=本站用户 ID，或走 OAuth2 拿爱发电 user_id）
  → Webhook 收单（仅作触发）
  → 服务端调 query-order 按订单号二次确认（金额 + plan_id + 幂等）
  → 调 query-sponsor（按 user_id 过滤）读 current_plan.plan_id + expire_time 判定本站放行与否
  → 过期无推送：靠定时轮询 query-sponsor 收回权限
```

权限判断只在服务端（对应包 RULES.md 的要求：锁定的字段不得下发到客户端，
不得改为前端隐藏）。会员判定模块位置（第 2 步实现）：`backend/app/services/afdian.py`
（签名 + query-order/query-sponsor 客户端）与 `backend/app/routers/membership.py`
（webhook 接收 + 轮询任务），凭证只读环境变量 `AFDIAN_USER_ID` / `AFDIAN_TOKEN`。

有效期口径（官方规则）：1 个月 = 31 天，从发电当日算；过期后仅赞助者可见内容都不可见；
高档位涵盖低档位；升档（补差价）不延长剩余天数；多月一次付清时以 `query-sponsor` 的
`expire_time` 为准，订单只作辅助。

## 3. 边界与风险

1. Webhook 无签名：必须二次确认 + 幂等；回调 URL 不要只认来源 IP。
2. 无到期/取消推送：会员过期只能靠定时轮询收回权限；轮询间隔决定回收延迟。
3. 身份绑定二选一：OAuth2（需人工申请）或 `custom_order_id`（须实测）；不要用昵称匹配（可重复）。
4. 待实测项：`query-sponsor` 的 `user_id` 过滤与 `per_page` 参数、`custom_order_id` 回传、
   `query-plan` 是否存在——三者均只在官方文章版/第三方处出现，未在现版指南正文证实。
5. 未找到可靠来源：提现是否需身份证实名、赞助名单是否可导出 CSV、档位最低价 5 元
   ——三项均未在官方现版文档中证实，上线前以提现页实际要求为准。
6. API Token 属于创作者账号本人（查的是“我的订单/我的赞助者”），本站只需核验自己
   这一个创作者时完全够用。

## 4. 创作者入驻与费率（官方指南核实）

- 步骤：手机号/邮箱注册 → https://afdian.com/apply 申请成为创作者（填主页信息）
  → https://afdian.com/setting/plan 设多个按月档位（写清各档回馈）
  → 社交平台发一条带主页链接的动态 → https://afdian.com/apply/certify 申请认证。
- 认证的实质是“你是本人”的人工确认（发主页链接 + 私信反馈），官方 FAQ 称一般 24 小时内完成；
  未认证不能被搜索/出现在发现页。**官方入驻指南没有任何要求个人创作者提供营业执照的表述。**
- 费率：总费率 6%，创作者得 94%（其中 1% 为支付宝/微信支付手续费，5% 为平台服务费）。
  每月赞助中“当月的部分”于下个月 1 号白天进入余额，可随时提现。
- 无自动扣款：用户一次可选付多个月，平台按月逐月结算给创作者。

## 5. 需要用户做的事（按顺序，全部用户自己在爱发电操作）

1. 在 https://afdian.com 注册账号（手机号或邮箱）。
2. 在 https://afdian.com/apply 申请成为创作者，填主页信息（封面、简介、创作类型）。
3. 在 https://afdian.com/setting/plan 设置赞助档位（建议 2–3 档；各档价格与回馈由用户定，
   例如：月度会员解锁深度报告全文、得分明细与出处；高档位涵盖低档位，描述里写全）。
4. 在社交平台发一条带爱发电主页链接的动态，然后到 https://afdian.com/apply/certify 申请认证。
5. （(b) 阶段才需要）认证通过后，在 https://afdian.com/dashboard/dev 生成 API Token（只给服务端用），
   并把创作者主页链接、各档位的 plan_id（在 https://afdian.com/dashboard/plans 查看）
   发给我，我填进 `config/afdian.yaml` 并接会员判定。(a) 阶段只外链，不需要 Token，别急着生成。
6. （(b) 阶段、如走 OAuth2 身份桥）私信爱发电官方申请 OAuth2，提供应用名称、可信域名；
   官方告知 clientID/clientSecret 后转给我（走安全通道，不直接发聊天里）。

**不要做的事**：不要把爱发电账号密码发给我；API Token 与 clientSecret 只存服务端
环境变量，不进仓库、不进聊天记录。
