# 978智能数据中心

A 股题材数据站：题材热度榜 → 题材行业页 → 公司深度报告。
只提供数据与规则计算结果，不推荐股票。

> 设计来源：astock-data 包（原件 `~/workspace/user/files/astock-data.zip`）。
> 设计映射与取舍见 `docs/REDESIGN.md`；未解决的问题见 `docs/OPEN_ISSUES.md`；
> 爱发电接入结论见 `docs/AFDIAN.md`；新旧热度对照见 `docs/heat_comparison.md`；
> 抽取评测集与方法见 `docs/EXTRACTION_EVAL.md`。

## 目录

```
backend/     FastAPI + SQLAlchemy（SQLite，mini 上跑；Postgres 迁移见 OPEN_ISSUES 第 1 项）
frontend/    Next.js 14（部署形态：Cloudflare Worker hottopics-worker + Workers Assets）
config/      全部可调规则（热度权重、得分规则、发布策略、新鲜度阈值、违禁词、题材定义、
             榜单拆分规则、爱发电映射、LLM 客户端配置）。数值改动需用户批准（见包的 docs/RULES.md）
docs/        设计映射、问题清单、爱发电结论、热度对照、抽取评测
scripts/     heat_compare.py（新旧热度对照）、eval_extraction.py（抽取评测跑分）
deploy/      Worker 部署脚本
```

## 本地运行

```bash
# 后端
cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python seed_fixture.py        # 冻结夹具（2026-11-07 快照，非实时数据）
venv/bin/python -m pytest tests -q     # 79 项
venv/bin/uvicorn app.main:app --port 8000

# 前端
cd frontend && npm install && npm run dev   # http://localhost:3000，后端 :8000
```

生产部署：后端在 Mac mini（`~/hot-topics-backend`，LaunchAgent `com.978.hottopics`，
uvicorn 127.0.0.1:8000，经 Cloudflare Tunnel `hottopics-api` 对外为 api.999777888.xyz）；
前端是 Cloudflare Worker `hottopics-worker`（域名 tcs.999777888.xyz）。
不要往已停用的 Pages 项目 `hottopics` 上部署（动态路由 404，见部署记录）。

## 当前状态（第 1 步，2026-11-08）

- 站名 978智能数据中心；榜单拆分为题材榜 / 风格·行为榜；组合题目标注；
  新鲜度诚实标注（交易日与抓取时间分开，周末显示休市）；方法说明页 `/method`；
  领涨公司可点；og/canonical 已加。
- 热度公式仍是 v2.1 百分位加权；包的 z-score v1.0 已实现、已算对照，**未切换**，
  切换需用户批准（见 `docs/heat_comparison.md`）。
- 榜单数据仍是 2026-11-07 15:00 冻结快照；30 分钟刷新待 mini 装 AKShare 后跑通。
- 付费墙改用爱发电：网站保持公开，**(a) 先只外链**——会员专属内容放爱发电，
  站里只挂链接，不做服务端核验（见 `docs/AFDIAN.md`）；(b) 服务端核验等有了
  付费用户再做。创作者账号与档位需用户在爱发电操作。
- pending 报告仅管理员可见：公开详情/下载/列表/搜索对 pending 一律 404 或
  不返回，后台 `GET /api/admin/reports/{id}` + `/admin/reports/[id]` 读全文。
- 抽取模型改 Muse：`config/llm.yaml` 默认 provider 为 muse（助手执行，后端
  不调模型、不编造端点/key）；评测集与方法见 `docs/EXTRACTION_EVAL.md`，
  评测待跑，跑完交用户批准后才能上线。
- Tushare token 已存 mini `.env`；但账号无 `daily` 接口权限（`daily_basic` 可用），
  见 `docs/OPEN_ISSUES.md` 第 2 项。

## 凭证

任何 token/key 只存服务端环境变量（mini 的 `~/hot-topics-backend/.env`，600 权限），
绝不进仓库、不进聊天记录、不进记忆。仓库里搜不到任何凭证才算合格。
