# 重新设计映射（astock-data 包 → 978智能数据中心）

> 站名：978智能数据中心。域名不动：前端 tcs.999777888.xyz，后端 api.999777888.xyz。
> 设计权威：astock-data 包（原件 `~/workspace/user/files/astock-data.zip`，24 项测试，
> 行情与公司数据目前全是模拟演示）。第 1 步只做网站改动 + 仓库就绪，不换托管、不迁库、
> 不开定时任务；绿色电力试点（另一条线）不受影响。

## 1. 模块对照表

| 包模块 | 现站位置 | 第 1 步做法 | 状态 |
|---|---|---|---|
| `config/`（权重/得分/发布/新鲜度/违禁词/题材） | 新增 `config/`（仓库根目录） | 原样采用包的 5 个配置文件 + `themes/humanoid_robot.yaml`；新增 `themes/topcon_battery.yaml`（已核验数据）、`topic_filter.yaml`（榜单拆分规则）、`afdian.yaml`（会员映射，`mode: external_link_only` 只外链）、`llm.yaml`（LLM 客户端配置，provider 默认 muse） | ✅ 已做 |
| `compute/heat_index.py`（z-score 公式 v1.0） | `backend/app/services/heat_index_v2.py`（逻辑未改）+ `to_package_metrics()` 映射 + `missing_inputs()` | 已实现、已算对照（`docs/heat_comparison.md`），**未上线**；切换需用户批准并递增 version | ⏳ 待批 |
| `compute/relevance_score.py`（关联度得分） | `backend/app/services/relevance.py`（逻辑未改） | 已实现，未接线；现站分层仍走 `layering.py` 主营核验规则；接线需先补齐 revenue_share / disclosure / patent 三项输入 | ⏳ 待接线 |
| `compute/jobs.py`（关联度重算任务） | 未移植 | Postgres SQL，待第 2 步随迁移移植 | ⏳ 后续 |
| `ingest/tushare_daily.py`（日线） | 未接入 | 见第 3 节：token 已有，但账号无 `daily` 接口权限；`daily_basic` 可用。见 OPEN_ISSUES 第 2 项 | ⚠️ 受阻 |
| `ingest/quotes_intraday.py`（盘中行情） | 现站 `services/akshare_client.py` + `workers/rank_refresh.py` | 保持东财/AKShare 路线（已实测）；包的 demo 模拟行情不采用 | ✅ 保持 |
| `ingest/cninfo_announcements.py`（巨潮公告） | 无对应模块 | 未移植；包自述接口字段凭记忆、未联网验证。见 OPEN_ISSUES 第 5 项 | ⏳ 后续 |
| `extract/`（LLM 抽取 + 校验） | `backend/app/extract/llm_client.py`（可插拔客户端）+ `backend/app/publish/validator.py`（校验器逻辑未改）+ `backend/app/extract/eval_scorer.py`（评测计分） | 客户端已落地：provider 与模型走 `config/llm.yaml`，默认 **muse**（助手执行，后端不调模型、不编造端点/key）；Anthropic 仅为可选实现（模型与 key 都走配置）；校验器已落地；评测集与方法见 `docs/EXTRACTION_EVAL.md`，评测脚本 `scripts/eval_extraction.py` | ✅ 已做（评测集待冻结、评测待跑） |
| `publish/gate.py`（发布闸门） | `backend/app/publish/gate.py`（逻辑未改） | 纯函数已落地；DB 侧的版本快照/更正记录（`service.py`）是 Postgres SQL，待迁移 | ⏳ 后续 |
| `monitor/freshness.py`（新鲜度） | `backend/app/monitor/freshness.py`（逻辑未改）+ `describe_status()` 诚实标注 | 已落地并接入榜单接口；告警 webhook（ALERT_WEBHOOK_URL）未配，见 OPEN_ISSUES | ✅ 已做 |
| `flows/`（任务入口与调度） | 现站 `workers/rank_refresh.py` + 管理 API 任务 | 保持 30 分钟刷新 + 退避 + stale；包的调度器（每分钟盘中任务等）不照搬，见第 4 节 | ✅ 保持 |
| `api/app.py` + `api/repo.py`（首页/题材/公司 + 付费墙） | 现站 `routers/public.py` + `frontend/` | 付费墙改用爱发电（见 `docs/AFDIAN.md`），不做站内商户号收款；**2026-11-08 用户定：先只外链（a）**——网站保持免费公开，会员专属内容放爱发电，站里只挂链接，不做服务端核验（`config/afdian.yaml` 的 `mode: external_link_only`）；服务端核验（b）等有了付费用户再做。方法说明页“免费与会员”已按只外链口径写。repo.py 的免费额度常量未定，等用户批 | ⏳ 待批 |
| `api/admin.py`（ADMIN_TOKEN 审核） | 现站 `routers/admin.py`（JWT 管理员）+ 新增入库端点 | 保持现有 JWT 管理后台；包的 ADMIN_TOKEN 模式不引入（两套鉴权不并存） | ✅ 保持 |
| `api/auth.py`（注册登录 + 支付回调） | 现站 `deps/auth.py`（管理员 JWT） | **不做用户注册登录**：爱发电方案下本站不需要自己的账号体系；包的 `/api/pay/callback` 由爱发电 webhook + 二次确认替代——这是 (b) 阶段的事，现阶段只外链，不做回调/核验 | ❌ 不做（(a) 阶段） |
| `sql/schema.sql`（PostgreSQL） | 现站 `app/models.py`（SQLite） | 第 1 步不迁库；Postgres 迁移见 OPEN_ISSUES 第 1 项 | ⏳ 后续 |
| `web/index.html`（包的前端） | 现站 `frontend/`（Next.js） | 不采用包的静态前端；现站 Next.js 前端按骨架 6 项改（见第 2 节） | ✅ 已做 |
| `docker-compose.yml` / `Caddyfile` / `Dockerfile` | 现站 `docker-compose.yml`（未实测）+ `deploy/`（Worker 部署脚本） | 不在 mini 上装 docker；前端仍是 Cloudflare Worker `hottopics-worker`，后端仍是 mini 直跑 | ❌ 不做 |

## 2. 第 1 步网站改动清单（已做，均在本仓库）

- **站名**：全站改为 978智能数据中心（标题、logo、页脚、SEO 描述、og 标签）。
- **榜单拆分**：`/api/topics/rank` 返回 `topics`（题材榜）与 `styles`（风格/行为榜），
  规则来自 `config/topic_filter.yaml`，各自重排名；首页两个页签切换。
- **组合题材标注**：多板块映射的题材标“组合题材”，方法说明页写清均值与单板的区别。
- **新鲜度诚实标注**：接口返回 `trade_date`（数据所属交易日）、`fetched_at`（抓取时间，
  ISO +08:00）、`market_status`（trading / closed / market_closed）、`stale` 与
  `stale_reason`；周末显示“休市，展示最近交易日收盘”，只有交易日刷新失败才标 stale
  并写清原因。首页状态条用人能读的格式（2026年11月7日（周五）· 23:00（+08:00））。
- **领涨公司可点**：快照新增 `leading_code`，首页领涨公司链接到公司页；同时新增
  `up_count` / `down_count` / `limit_up_count` / `turnover_amount` / `trend`（近 5 次热度）
  字段；涨跌幅按 A 股习惯红涨绿跌；支持按热度分/涨跌幅排序。
- **方法说明页**：新增 `/method`（热度公式、口径、数据来源、更新频率、新鲜度口径、
  新公式审议状态、免费与会员、免责声明）。
- **SEO 与页脚**：`metadataBase` + 各页 canonical（首页/方法/题材/公司）+ og 标签；
  页脚放完整免责声明、数据口径链接与方法说明页链接。HTTPS 强制跳转是 Cloudflare
  侧设置（见 OPEN_ISSUES 第 9 项），代码里做不了。
- **内部话术清理**：面向读者的文案里不再出现“修正版规格 v2 §6.1”等内部说法；
  后端代码注释里的规格引用保留（不面向读者）。
- **发布闸门（纯函数层）**：`publish/validator.py` + `publish/gate.py` 已落地；
  事实入库的 DB 侧流程（版本快照、更正记录、审核队列）待第 2 步随迁移做。
- **配置化**：热度权重、得分规则、发布策略、新鲜度阈值、违禁词、题材定义、榜单拆分
  规则、爱发电映射、LLM 客户端配置全部收进 `config/`；数值改动需用户批准（RULES.md）。
- **pending 报告仅管理员可见（硬性，2026-11-08 已上线验证，现站做法带过来）**：
  公开列表只返回 done（`status` 参数公开端忽略），公开详情/下载对 pending 一律 404
  （不泄露存在性），公开搜索只搜 done；后台新增 `GET /api/admin/reports/{id}`
  读全文（iframe 沙箱渲染），审核列表页链到 `/admin/reports/[id]`；
  爱发电会员也不能绕过这条——会员解锁只放行已审核通过的内容。
  测试见 `backend/tests/test_pending_visibility.py`（公开 4 项 + 管理 1 项），
  另有两处旧测试（`test_ingest.py`）已按新规则改写：pending 时公开端为空/404，
  审核通过后才可见。
- **爱发电只外链（2026-11-08 用户定）**：`config/afdian.yaml` 的
  `mode: external_link_only`；方法说明页“免费与会员”已改成只外链的说法，
  不再写“会员身份由服务端向爱发电核验”，也不写“支付渠道尚未接入（需要商户资质）”。
- **抽取模型改 Muse（2026-11-08 用户定）**：`config/llm.yaml` 默认 provider 为 muse
  （助手执行，后端不调模型、不编造端点/key）；Anthropic 仅为可选实现；
  评测集与方法见 `docs/EXTRACTION_EVAL.md`，计分见
  `backend/app/extract/eval_scorer.py`，跑分脚本 `scripts/eval_extraction.py`。

## 3. Tushare 实测结果（2026-11-08，mini 上实测）

- token 有效（56 字符，存于 mini `~/hot-topics-backend/.env`，值不入仓库与汇报）。
- `pro.daily(trade_date="20261106")`：**无权限**——“抱歉，您没有接口(daily)访问权限”。
  包的 `TushareDaily` 同时调 `daily` + `daily_basic`，`daily` 一挂整任务失败。
- `pro.daily_basic`：可用（20261106 返回 5573 行，含 total_mv、pe_ttm）。
- `pro.stock_basic`：可用（5579 行）；`pro.trade_cal`：可用。
- 结论：包的日线采集器不能原样跑。修复方案见 OPEN_ISSUES 第 2 项（改用
  `daily_basic` + AKShare 补 OHLC/成交额，或给账号赚积分开 `daily` 权限）。

## 4. 刻意没照搬包的地方（附理由）

- **调度频率**：包是盘中每分钟行情 + 每分钟热度；现站是用户定的 30 分钟刷新。
  每分钟拉东财会触发限流（2026-11-07 实测：拉 9 个板块成分股即 502 + 约 5 分钟封禁），
  且 mini 上 AKShare 未装、刷新从未跑通过。先让 30 分钟刷新真正跑通，再谈加密。
- **抽取模型**：包写死 Anthropic（`extract/pipeline.py` 与
  `revenue_extractor.py` 里 `anthropic.Anthropic()` + 默认模型
  `claude-sonnet-5-5`）；本站改成可插拔客户端（`backend/app/extract/llm_client.py`），
  默认模型是 Muse——由助手在定时/手动流程里执行，后端不直接调模型、不编造
  端点/key；Anthropic 只作为其中一种可选实现。输出无论谁抽取，都必须过校验器。
- **用户注册登录**：包有 users/sessions；爱发电方案下本站不需要自己的账号体系，
  会员身份走爱发电 OAuth2 或 custom_order_id 绑定（见 `docs/AFDIAN.md`）。
  ——但这是 (b) 阶段的事，现阶段只外链，不做身份绑定。
- **支付回调**：包的 `/api/pay/callback` 是 HMAC 验签的通用契约；爱发电 webhook 无签名，
  改为“回调仅作触发 + 调 query-order 二次确认 + out_trade_no 幂等”。
- **静态前端**：包的 `web/index.html` 是 164 行静态页；现站 Next.js 前端已上线且有
  15 条路由，不推倒重来。
- **Docker/Caddy**：mini 没有 docker，也不装；部署仍走现有 Cloudflare Worker + mini 直跑。

## 5. 数据与内容现状（第 1 步未动，全部保留）

- 人形机器人：保留 23 家 / 待复核 3 家，六大维度与行业报告已导入（2497 字）。
- TOPCon电池：保留 49 家 / 待复核 31 家。
- 绿色电力：另一条线正在跑试点（主营核验分层 → 白名单 → 3–5 家报告推送），
  其入库端点与 mini 后端不要动；试点完成后数据按现有分层表结构入库。
- 报告：绿的谐波、兆威机电 2 份定位级样本报告；stockreport 推送入库端点
  （`POST /api/admin/ingest/report`，按 (code, trade_date) upsert）保持。
