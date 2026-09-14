# S1 R2：用户明确授权德宏身份对应

TASK_ID=V0_5_S1_BASE_IDENTITY_ALIAS_CORRECTION_R2

继续PR #624，前一HEAD：`046d558a856a6f923079004c9a31f9048c59e861`。
业务所有人明确确认历史“德宏盈江农场”与登记成员“腾冲德宏农场”是同一实体。
配置方向为**历史身份 → 登记成员身份**：

```json
"德宏盈江农场": ["腾冲德宏农场", "USER_EXPLICIT_CONFIRMATION_2026-09-14"]
```

保留建水南庄基地→建水南庄农场原授权。不推断其他别名、不模糊匹配。
农场原始名称和原始XLS未改写。唯一业务变化是新增显式alias。

## 实际重放

同一原工作簿、三季授权源与hash，复用R1冻结的海拔和省界快照，**没有重新联网查询**。
新私有目录：`/Users/charles/Documents/blueberry-area-yield-artifacts/base-registry-s1-r2/`。
R1 final和此前历史目录未覆盖，前后逐文件SHA检查通过。

39个基地、74个登记成员现为74 resolved / 0 unresolved / 0 ambiguous。
144个历史标签为73 EXACT、2 AUTHORIZED_ALIAS、69 UNRESOLVED。
“登记成员均有至少一期对应”不等于“每个成员每季资料齐全”；69个其余源标签不会被强行绑定。

| 产季 | 新增归属kg | 排除量减少kg | R2已归属kg | R2排除kg | 来源总量kg |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023–2024 | 0.000000 | 0.000000 | 11656395.430000 | 18491816.276000 | 30148211.706000 |
| 2024–2025 | 0.000000 | 0.000000 | 30590748.252000 | 11849270.376000 | 42440018.628000 |
| 2025–2026 | 385882.423000 | 385882.423000 | 48703277.896000 | 1691642.683000 | 50394920.579000 |

各季均验证来源总量=基地归属量+排除量。新增量全部只进入腾冲德宏基地。
前两季该历史标签没有可归属记录，不能把第三季数量回填过去。

全基地业务域已记录小计增加376045.802000 kg，达到74401316.749000 kg。
尾果小计增加9836.621000 kg，达到16549104.829000 kg。
汇总尾果占比0.182624→0.181957，六位展示差为-0.000667。
所有小计仍包括PARTIAL样本，不能冒充完整业务季标签。

117条base-season审计中**仅腾冲德宏基地2025–2026一条发生变化**：

- 业务域小计16849.666000→392895.468000 kg。
- 尾果小计515.622000→10352.243000 kg。
- 首个正量日2026-02-24→2025-11-19。
- 业务域峰日2026-03-06→2026-04-15，峰量836.396000→10072.467000 kg。
- 尾果峰量515.622000→10352.243000 kg，尾果峰大于业务峰由false变true。
- 对应成员1→2，移除成员身份缺口；业务窗口来源缺数原因保留。

因此“至少一季尾果峰超过业务峰”的基地数24→25，新增腾冲德宏基地。
完整性规则不改变：117样本仍82 PARTIAL、35 BLOCKED、0 COMPLETE，不生成不合格亩产。

## Hash与冻结边界

BASE_REGISTRY_HASH_CHANGED=false。
Registry JSON和normalized CSV逐字未变，原因是原始基地定义、所有位置/面积/海拔、
region以及登记内历史季数量/粗粒度状态均未改变。不得仅因alias变化强改registry hash。
其canonical hash仍为：

`d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293`

单独新增`mapping-authority.json`，版本`BASE_MEMBER_MAPPING_R2`，绑定原工作簿hash、
完整授权alias列表及exact-first/no-fuzzy/no-multi-assignment策略。
mapping authority canonical hash：

`6fb7212cc1edd090cf63ff2d938fc5e7b7a0c4b9020b7fdca14e499119b2496e`

文件SHA与canonical payload hash分开记录于[机器证据](alias-correction-r2-evidence.json)。
R1文档及evidence作为原阶段快照保留，当前身份结论以本R2为准。
BASE实体、04-15、投产面积、坐标、海拔、region、模型、v0.4 authority、数据库、MCP和部署均未改变。

## 重放和检查

继续使用R1 runner命令，output换成新的不存在目录，enrichment-from指向R1 final。
runner不允许覆盖输出，新版额外生成mapping authority版本/hash。
新增真实名称的定向测试：授权证据必填、名称变体不匹配、唯一归属，保留所有原S1测试。
本地focused及相关回归、静态检查后推送；CI/full-suite-canary只认修订后HEAD。
Ready与Merge均未授权，PR保持Draft。

本地结果：S1专项22 passed；S1/area_yield/MCP相关回归330 passed / 9 skipped。
ruff、format、mypy backend/app及runner、JSON/引用/diff检查通过。
R2与R2-replay七个核心产物逐字一致；文件hash清单核验通过。
另直接核对源日聚合：该历史名称在前两季均0条，在2526有133条日聚合，
合计385882.423 kg，与新增归属量完全一致。
