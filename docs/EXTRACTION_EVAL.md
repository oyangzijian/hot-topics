# 内容抽取评测：评测集与评测方法（2026-11-08）

> 前置条件（RULES.md / DEPLOY.md）：**上任何模型之前，都要先在 30 份以上
> 真实文档上评测提示词，结果交用户批准后才能上线。** 换模型、换提示词、
> 换校验规则都要重新评测（评测集版本 +1）。评测没过，抽取管线保持关闭，
> 概况/时间线继续人工写——现站人形机器人那套已核验内容不受影响。

## 1. 模型与执行方式（2026-11-08 用户定）

- 抽取模型是 **Muse（即本助手）**，为默认/首选实现（`config/llm.yaml`
  `provider: muse`，客户端见 `backend/app/extract/llm_client.py`）。
- Muse 没有给后端代码直接调的 API key：后端只生成抽取任务
  （`MuseClient.extraction_job()`：提示词 + 文档 + 校验规则），抽取由助手
  在定时或手动流程里执行。**不要编造假的 Muse API 端点或 key。**
- Anthropic 只作为可选实现（模型与 key 都走配置，缺一不可）。
- 无论哪个模型抽取，输出都必须过校验器
  （`backend/app/publish/validator.py` 的 `check_statement`，直接采用包
  `astock/extract/validator.py` 的逻辑，未改）：引文必须真实存在于原文、
  数字/年份/日期须与引文一致、无评价性措辞。校验通过后才能入库——
  **绝不跳过校验直接入库**。`publish/gate.py` 的发布闸门同样适用：
  事实须带出处才能发布，概况必须人工审核。

## 2. 评测集（30 份，冻结清单，版本 v1）

### 2.1 构成

| 类别 | 份数 | 文档类型 | 覆盖题材 | 用途 |
|---|---|---|---|---|
| 年报分产品收入 | 15 | 上市公司年报“分产品/分行业营业收入构成”表（PDF 原文页） | 人形机器人 5、TOPCon电池 5、绿色电力 5 | 评 `revenue_extractor`：产品名、收入、占比 |
| 公告/研报事实陈述 | 10 | 巨潮公告、公司公告、券商研报摘要 | 人形机器人 4、TOPCon电池 3、绿色电力 3 | 评 `pipeline`：overview / timeline 陈述 |
| 政策文件 | 5 | 工信部指导意见、北京/上海/深圳人形机器人政策原文 | 人形机器人 5 | 评 `pipeline`：政策类 timeline 与定义 |

合计 30 份。选材原则：全部是真实公开文档（不是模拟数据）；覆盖三个已核验
题材；覆盖不同年份（2023–2026）与不同披露格式（表格型年报、段落型公告、
条目型政策）；每份文档只进一次评测集，评测后不再换题（防过拟合）。

### 2.2 清单文件（冻结，不随手改）

- 位置：`docs/eval_set/manifest.json`（第 1 步只定格式，清单本身在评测
  启动时由助手逐份取数后冻结；未冻结前不得开评测）。
- 每条记录字段：`id`（如 `eval-001`）、`kind`（`statements` | `revenue`）、
  `theme`、`source_url`（原始披露链接）、`retrieved_at`（取数时间）、
  `sha256`（文档原文哈希，防取数后被改）、`gold`（人工标注文件路径）、
  `doc`（文档原文路径）。
- 版本：`manifest.json` 顶层写 `version: "v1"`；增删改任何一份文档或 gold，
  版本号 +1 并在 `docs/eval_set/CHANGELOG.md` 记原因。

### 2.3 Gold 标注方法

- 年报收入项：以年报表格原文为准，逐项标 `segment / revenue / share /
  page / quote`（quote 为表格行原文）；share 以年报披露的占比为准，不重算。
- 事实陈述：以原文句子为准，逐条标 `kind / text / date / page / quote`；
  text 只复述原文，不加评价、不补数字；timeline 的 date 必须能在 quote 里
  找到对应写法。
- 标注人：助手先标，用户抽查（每类至少抽 3 份复核）；标注争议以原文为准，
  标不出的写“无”，不猜。
- Gold 本身也要过校验器：gold 陈述的数字必须在 quote 里，gold 收入份额
  加总应在 0.95–1.05 之间；gold 不合格先修 gold，不改计分口径。

## 3. 评测方法

### 3.1 流程

1. 冻结评测集（manifest v1 + gold 全部就绪，sha256 核对通过）。
2. 冻结提示词与配置（`config/llm.yaml` 的 `prompt_version` 与 provider、
   `PIPELINE_PROMPT` 文本；评测期间不改提示词）。
3. 逐份执行抽取：
   - muse：助手按 `extraction_job()` 的 prompt 逐份执行，输出 JSON
     （`{"statements": [...]}` 或 `{"items": [...]}`）落到
     `docs/eval_set/outputs/<provider>/<prompt_version>/<doc-id>.json`。
   - anthropic：同一 prompt 由脚本直调，输出落同一目录结构。
   每份输出只跑一次，不挑最好的一次（防 cherry-pick）。
4. 每条输出过校验器（`check_statement` + `date_in_quote`），记录
   `validator_issues`（抽取下标 → 问题列表）。
5. 计分：`scripts/eval_extraction.py --manifest docs/eval_set/manifest.json`
   调用 `backend/app/extract/eval_scorer.py`，输出评测报告 JSON。
6. 报告交用户批准：通过才上线；不通过先改提示词/配置，再重测（评测集不变）。

### 3.2 指标定义（计分口径见 `eval_scorer.py`）

- **漏抽率 miss_rate** = 漏抽的 gold 陈述 / gold 总数。漏抽 = gold 里有、
  抽取里没有。匹配按 (kind, 去空白正文) 精确匹配，不模糊匹配。
- **误抽 false_total** = 抽出的陈述不在 gold 中（不管校验是否拦截，都算误抽）。
- **校验拦截率 interception_rate** = 误抽中被校验器拦截的 / 误抽总数。
- **漏网 escaped** = 误抽中校验通过的条数（校验后仍漏网的错误陈述）。
- **收入份额误差**：按产品名归一化匹配，逐项记份额绝对误差，取最大值。
- 分项报告：按 kind（overview / timeline）与按题材分别列漏抽/误抽，
  便于定位是提示词问题还是某类文档问题。

### 3.3 报告格式

评测报告（JSON + 一页文字摘要）包含：评测集版本、provider、prompt_version、
30 份逐份得分表、汇总指标（漏抽率/误抽数/拦截率/漏网数/收入最大误差）、
漏抽与误抽的典型例子（各举 3 条，附原文与 gold 对照）、结论（通过/不通过
+ 不通过的原因与下一步改法）。报告存 `docs/eval_set/reports/`，随汇报交用户。

## 4. 通过门槛

| 指标 | 门槛 | 性质 |
|---|---|---|
| 漏网 escaped | 必须为 0 | 硬门槛：校验后仍漏网的错误陈述一条都不能上线 |
| 漏抽率 miss_rate | ≤ 20% | 建议值，需用户批准 |
| 收入份额最大绝对误差 | ≤ 0.01 | 建议值，需用户批准 |
| 误抽数 / 拦截率 | 只报告，不设硬门槛 | 用于判断提示词是否需要收紧 |

门槛本身属于业务决策：上面“建议值”在用户批准前不算正式门槛；用户批了
哪个数，就把哪个数写进 `config/llm.yaml` 的 `eval` 段与本节表格。

## 5. 维护规则

- 新增题材时，评测集补 5 份以上该题材文档（年报 2 + 公告/研报 2 + 政策 1），
  版本 +1，补完后重测一次。
- 换模型（muse ↔ anthropic 或换具体模型）、换提示词、换校验规则（改
  `banned_words.txt` 或 `check_statement`），一律重测 30 份并重新交用户批准；
  旧评测报告保留，不删除。
- 评测集文档只存原文与 gold，不存任何 key；输出文件只含抽取结果，不含凭证。
