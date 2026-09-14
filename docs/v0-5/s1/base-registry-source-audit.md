# S1 基地登记与业务季边界审计

TASK_ID=V0_5_S1_BASE_REGISTRY_AND_BUSINESS_BOUNDARY_R1

本次是新 v0.5 数据准备层，不接入 v0.4 产品预测。开始主线
`6baeb880ad88e7e277eacd696fe622c7ae721327`。新增模块
`backend/app/base_registry`，没有调用 fit、predict、数据库或 MCP。

## 来源与登记

实际读取桌面原文件 `基地位置亩数.xlsx`，Sheet1、4列、39条数据。
文件 SHA256：`73329a1f7315f81ce7cf24d59dc7b3a49507520cd179a205b7267a5b430db7d7`。
三个面积单元格是字面加法公式，逐一核对缓存：1099+391=1490、2829+236=3065、
1082+348=1430。只允许数值和明确的字面加法，不执行任意公式。
原始名称、成员文本、坐标和面积公式全部保留；以本次用户确认将面积解释为基地投产面积，
不分摊成员面积，不引用736亩或旧杨柳393.4亩。新杨柳基地394亩、版纳基地735亩不回写旧产品。

`BASE_REGISTRY_V1` canonical payload hash：
`d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293`。
base_id 是精确基地名称 canonical JSON SHA256 的前24位加前缀，导入时同时检查名称和ID重复。
登记顺序按ID排序。字段覆盖来源、review、历史覆盖、有效期和气候分区占位。
行政区字段、坐标系、有效期和 applicability 未有充分authority时为null/NOT_ESTABLISHED，
不根据名称伪造县乡或历史生效日期。所有登记均待Coordinator review。

## 位置与海拔

39个输入均通过经度/纬度数值范围检查，无0/0、无自动反转。重复坐标会标REQUIRES_REVIEW。
使用[公开云南省边界](https://geo.datav.aliyun.com/areas_v3/bound/530000.json)进行点在多边形内的
区域合理性筛查，保存完整响应、查询时间与hash：38个YUNNAN_CORE、1个OUT_OF_YUNNAN。
乡丰蓝莓基地113.81,23.34按省外登记，不当错误，也不强制加入云南气候带。
这是区域筛查，不是测绘位置或行政界线认证；未明确的原始坐标系仍待核验。

用[Open-Meteo Elevation API](https://open-meteo.com/en/docs/elevation-api)对39个原始代表点
批量查询，39个获得有限海拔值，0个查询缺失。来源为Copernicus DEM GLO-90（2021），
约90米栅格。依据供应方要求归属Open-Meteo与Copernicus，
参考[Copernicus DEM DOI](https://doi.org/10.5270/ESA-c5d3d65)。
这是研究阶段一次DEM取样，不是天气接入或商业运行服务许可声明。
保存请求URL、原坐标、原响应、原值、规范化值、UTC取回时间和内容hash。
**输入坐标系尚未确证：查询按供应方WGS84要求使用原数值，未做暗中坐标转换，
状态为DEM_ESTABLISHED_CRS_REVIEW_REQUIRED，不等于现场海拔测量通过。**
只使用一个DEM来源，未声称多源交叉验证。查询失败保留null/NOT_ESTABLISHED。
不做气候区拟合或行政区代替气候区：CLIMATE_ZONE_MAPPING_FROZEN=false。

## 成员身份与汇总

74个工作簿成员名称中73个可对应、1个未对应（腾冲德宏农场），0个跨基地歧义。
三个历史来源合计144个不同农场标签：73个EXACT、1个AUTHORIZED_ALIAS、70个UNRESOLVED。
这两个分母不同：前者是工作簿成员，后者是全部源标签，不能混为一个覆盖率。
唯一使用的旧授权alias是建水南庄基地→建水南庄农场，证据在
[R4用户确认](../../../configs/confirmed_total_r4.json)；没有相似名称匹配。
回龙两种“实验/试验”与面甸三个名称都保留工作簿列举，不自动合并实体或把汇总替代明细。
每个输入farm-day只进入一个基地；多目标归属标AMBIGUOUS并排除，源量=归属量+排除量需精确对账。

历史输入复用[R6已授权切片配置](../../../configs/frozen_evidence_expansion_r6.json)的
2324/2425原始日聚合以及[R7明确授权原始XLS](../../../configs/three_season_r7.json)。
前两季重验原artifact和源hash，第三季读取原XLS并复用既有严格解析器。
不读取旧sealed TEST，不把仓库旧2425来源和新附件拼接。
三来源分别93761、202072、233171条原始记录；原始来源hash见机器证据。

## 产物与可重复执行

按项目既有私有artifact纪律，业务位置、面积及日量明细保留在本机受控目录，不提交原始XLS或完整明细到Git：

`/Users/charles/Documents/blueberry-area-yield-artifacts/base-registry-s1-final/`

- `base-registry-v1.json`、`base-registry-normalized.csv`
- `elevation-enrichment.json`、`region-screen.json`
- `source-manifest.json`、`member-farm-mapping.csv`、`member-coverage.csv`
- `base-daily-ledger.csv`、`business-season-boundary-audit.csv`
- `summary.json`、`old_artifact_hashes.json`、`artifact-manifest.json`

文件独占创建、权限0600；目录0700。`base-registry-s1`是初次本地检查产物，
`base-registry-s1-replay`是冻结来源重放，不覆盖任何历史产物。交付以final为准。
Git提交代码、配置、聚合统计、方法及hash清单；私有产物需经授权本地转交，不能仅靠Git重建原始业务数据。

```sh
.venv/bin/python -m scripts.run_base_registry_s1 \
  --workbook /Users/charles/Desktop/基地位置亩数.xlsx \
  --history-root /Users/charles/Documents/blueberry-area-yield-artifacts \
  --source-25-26 /Users/charles/Documents/blueberry-area-yield-artifacts/source-25-26-r7/原果入库汇总表.xls \
  --enrichment-from /Users/charles/Documents/blueberry-area-yield-artifacts/base-registry-s1-final \
  --output /Users/charles/Documents/blueberry-area-yield-artifacts/base-registry-s1-new-replay
```

输出目录必须不存在。首次取海拔与省界时省略enrichment-from；重放时使用冻结快照而不重新联网。
使用相同source/config/enrichment，registry、daily与边界审计字节hash一致。
历史文件前后逐文件SHA检查，v0.4及R1–R7既有artifact未变化。

边界结论见[业务季审计](business-season-boundary-audit.md)，统计与文件hash见
[机器证据](evidence.json)。本次不声称S1未来zone任务、模型准确率或v0.5发布完成。

## 本地验证

- 新S1专项：21 passed。
- S1加area_yield：274 passed / 7 skipped（本地未启用的既有外部集成用例）。
- MCP、Core、Agent、Trial、旧empirical路径：716 passed / 2 skipped。
- 仓库ruff check、ruff format --check（1031文件）、mypy backend/app（444文件）通过。
- JSON、5个本地文档引用、私有文件hash清单与diff检查通过。
- final/replay的registry JSON、normalized CSV、日ledger、边界audit和summary五文件逐字一致。
- full CI/full-suite-canary由本PR最新HEAD执行；本地focused测试不冒充full suite。
