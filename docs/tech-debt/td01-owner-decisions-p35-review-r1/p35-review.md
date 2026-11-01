# P35 按已批准业务边界复核 R1

任务：`TD01_OWNER_DECISIONS_FREEZE_AND_P35_REVIEW_R1`。

**P35_FILE_REVIEW=PASS：35/35 文件身份和 D02/D03/D06 边界核对通过，0 PARTIAL、0 BLOCKED。**
**P35_PUBLICATION_AUTHORIZED=false；HISTORICAL_DISPOSITION=NOT_EXECUTED。**

三项业务边界以新的 [Owner 决定](owner-decisions.md) 为依据。通过表示下表精确字节符合本次限定范围，
不表示已经上传/发布、具备完整应用迁移能力或清除了原公开历史。

读取的最新 main：`fe494971c92f1d951f5acfeb6a70b85a4aff23ac`。
原归档：`td01-public-code-delivery-r2.tar.gz`；75,047 字节；35 文件。
原 SHA256：`f74c9a618370499769e124661bc105bea08f4114efa091d3b00d7e37d9245fde`。本轮只读核对，没有重建、修改、解压重封或上传归档。

## 逐文件准入

完整 SHA256、Blob、来源提交/路径、依赖、三项边界核对与发布标志见 [机器清单](p35-file-admission.json)。
以下每一行的准入均只绑定机器清单中的既有字节；每行 `publication_authorized=false`。

| 序号 | 原包内准确路径 | 类型 | 准入 |
| ---: | --- | --- | --- |
| 1 | `README.zh-CN.md` | DELIVERY_DOCUMENTATION | PASS |
| 2 | `public-core-v1/.github/workflows/public-core.yml` | WORKFLOW_TEMPLATE | PASS |
| 3 | `public-core-v1/PUBLIC-CORE-MANIFEST.json` | IDENTITY_METADATA | PASS |
| 4 | `public-core-v1/README.md` | DOCUMENTATION | PASS |
| 5 | `public-core-v1/backend/__init__.py` | CODE_OR_TEST | PASS |
| 6 | `public-core-v1/backend/app/__init__.py` | CODE_OR_TEST | PASS |
| 7 | `public-core-v1/backend/app/etl/__init__.py` | CODE_OR_TEST | PASS |
| 8 | `public-core-v1/backend/app/etl/history/__init__.py` | CODE_OR_TEST | PASS |
| 9 | `public-core-v1/backend/app/etl/history/fingerprint.py` | CODE_OR_TEST | PASS |
| 10 | `public-core-v1/backend/app/etl/history/normalizer.py` | CODE_OR_TEST | PASS |
| 11 | `public-core-v1/backend/app/etl/history/parser.py` | CODE_OR_TEST | PASS |
| 12 | `public-core-v1/backend/app/etl/history/schemas.py` | CODE_OR_TEST | PASS |
| 13 | `public-core-v1/backend/app/etl/history/synthetic_publication.py` | CODE_OR_TEST | PASS |
| 14 | `public-core-v1/backend/app/public_core.py` | CODE_OR_TEST | PASS |
| 15 | `public-core-v1/backend/research/__init__.py` | CODE_OR_TEST | PASS |
| 16 | `public-core-v1/backend/research/v019_daily_curve.py` | CODE_OR_TEST | PASS |
| 17 | `public-core-v1/docs/tech-debt/td01c-synthetic-example/SYNTHETIC_ONLY-manifest.json` | SYNTHETIC_SAMPLE | PASS |
| 18 | `public-core-v1/docs/tech-debt/td01c-synthetic-example/SYNTHETIC_ONLY_2039_2040.csv` | SYNTHETIC_SAMPLE | PASS |
| 19 | `public-core-v1/docs/tech-debt/td01c-synthetic-example/SYNTHETIC_ONLY_2039_2040.xlsx` | SYNTHETIC_SAMPLE | PASS |
| 20 | `public-core-v1/docs/tech-debt/td01c-synthetic-example/SYNTHETIC_ONLY_2040_2041.csv` | SYNTHETIC_SAMPLE | PASS |
| 21 | `public-core-v1/docs/tech-debt/td01c-synthetic-example/SYNTHETIC_ONLY_2040_2041.xlsx` | SYNTHETIC_SAMPLE | PASS |
| 22 | `public-core-v1/pyproject.toml` | BUILD_CONFIGURATION | PASS |
| 23 | `public-core-v1/requirements-direct.txt` | BUILD_CONFIGURATION | PASS |
| 24 | `public-core-v1/requirements-lock.txt` | BUILD_CONFIGURATION | PASS |
| 25 | `public-core-v1/tests/test_public_contract.py` | CODE_OR_TEST | PASS |
| 26 | `public-core-v1/tests/test_public_safety.py` | CODE_OR_TEST | PASS |
| 27 | `public-core-v1/tools/__init__.py` | CODE_OR_TEST | PASS |
| 28 | `public-core-v1/tools/run_public_ci.py` | CODE_OR_TEST | PASS |
| 29 | `public-core-v1/tools/verify_public_core.py` | CODE_OR_TEST | PASS |
| 30 | `td01i-v2-tools/PUBLIC-CORE-V2-EXECUTORS.json` | V2_IDENTITY_METADATA | PASS |
| 31 | `td01i-v2-tools/tests/test_public_gate_v2.py` | V2_CODE_OR_TEST | PASS |
| 32 | `td01i-v2-tools/tools/public_core_incremental_gate.py` | V2_CODE_OR_TEST | PASS |
| 33 | `td01i-v2-tools/tools/public_core_v2_context.py` | V2_CODE_OR_TEST | PASS |
| 34 | `td01i-v2-tools/tools/run_public_ci_v2.py` | V2_CODE_OR_TEST | PASS |
| 35 | `td01i-v2-tools/workflow-template.yml` | V2_WORKFLOW_TEMPLATE | PASS |

## 来源、依赖及独立合成证明

来源为 F 16 文件、G 11 文件、固定规则生成的 Manifest 1 文件、I R2 附录 6 文件及本地交付说明 1 文件。
33 个 Git 来源逐一核对原 Commit+Path、Blob/SHA256；固定 Manifest 独立按原 canonical 规则计算；
交付说明按前轮封存的完整字节核对。门禁代码只保留原合同允许的一处固定 seal 字面量替换。
35 文件的归档、现存目录和原审核矩阵全部一致；未发现未知夹带。

五份合成材料与前轮冻结生成器 seed 41 的完整字节复算证据绑定，当前五文件身份未改变；
本轮未重建或替换 P35 中的五份样例，也不把标签当作来源证明。D02 的真实精确关系、D03 的真实经营数值/曲线
和 D06 的真实研究原件/训练参数/成绩均未进入 P35。11 条旧优先对象保持排除，其内容真实性未重新判断。
五个未检查压缩资产仍未准入；SOURCE_002 与真实工作簿均未读取。

21 个 Python 文件的本地导入闭包仍可解析；12 个 backend 模块完整。外部直接导入只有 openpyxl、
xlrd、pytest；最小配置和 18 包完整锁保持原字节。安装/复算的原成功证据未替换为本轮新运行。

V2 六份附录来自仍为 Draft 的 [PR #783](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/783)
的固定 `326af7d2a68b886515c248868d1e860b8b59ee75`，尚未合入本次 main 或 V1；本 PR 不复制其实现。

## 尚未解决的问题

| 对象 | 当前状态 | 对本次 PASS 的限制 |
| --- | --- | --- |
| P35 实际发布 | 未授权，等待下一次明确渠道与动作指令 | 不上传本地包，不把本 PR 视为发布许可 |
| 原历史及工作簿处置 | NOT_EXECUTED | 原件/Hash 保留，旧公开历史风险未消除；不改 Tag/Release |
| 完整原应用 | NOT_VALIDATED | PostgreSQL、前端、MCP、真实模型及全部历史依赖不在 P35 中 |
| V2 真实远端审批/保护/Actions | 未配置或 NOT_RUN | 本地技术证明不等于真实防绕过验收；不要求本轮创建远端 |

D02/D03/D06 的业务边界批准已正式记录，不再作为“等待相同业务决定”的阻断。下一步仅等待 P35
具体发布渠道/动作的正式授权；三项批准不授予真实来源读取、训练、重评分或历史改写权限。

## 验证及停止

本轮追加材料的结构/身份检查及现有公开增量、历史工作簿防护合同结果见 [验证记录](validation.json)。
本 PR 仅增加本目录六份 Markdown/JSON；不提交归档、样例、源码、模型或原始业务数据。
原 PENDING 报告和旧失败/限制事实继续保留；独立 PR 保持 Draft，等待下一次正式授权。
