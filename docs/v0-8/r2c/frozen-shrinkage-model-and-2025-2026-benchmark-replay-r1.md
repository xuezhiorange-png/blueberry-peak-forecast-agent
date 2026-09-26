# V0.8-R2C 冻结 Shrinkage Stage A 与 benchmark replay

## 结论

R2C 按 R2B 已选定的 `SHRINKAGE_BASE_YIELD(lambda=1)`，使用 S8 完全相同的 37 条训练样本拟合 Stage A，并在 39 个 2025–2026 Base 上完成冻结 benchmark replay。结果没有打败 Global pooled-yield baseline：season-total WAPE 为 **35.8586432%**，baseline 为 **34.2993558%**，差值为 **+1.5592874 个百分点**。R2C 优于 V0.8 R1 的 39.2589322%（差值 **−3.4002890 个百分点**），但这不足以支持取代 global baseline。

2025–2026 已在 S8/S9 中查看，本轮只称 `FROZEN_BENCHMARK_REPLAY`，不是 pristine 或 unseen OOT。模型不具备生产批准；真正的未来未见产季验证仍待进行。

## 冻结输入与执行边界

- 训练集：37 行，2023–2024 为 15 行、2024–2025 为 22 行；数据 SHA-256 为 `72363ec56dae682fba80ccf984a6fedb2c57425e1fbdcea8b8fca10aca0b5aba`。41 条 blocked training rows 未纳入。
- 2025–2026 benchmark：39 个 Base，support 分层为 0/1/2 季历史分别 13/15/11 个。
- Stage A：冻结 `w=n/(n+1)`；global yield 使用 37 行的面积加权 pooled 定义，重算为 `855.5593226284052977280068913535048993216 kg/mu`。Base mean 使用 R1 冻结的“合格历史 season yield 算术平均”策略。
- Stage B shape hash 前后均为 `7ae53f5888947053057071f9b097e38b03bb8112a41de972b8e2d51fd311cb2e`。daily share 未变；39/39 条曲线的日预测总和与 season-total 预测对账。
- 预测文件在载入 benchmark actuals 评分前冻结。λ、模型族、fallback、特征及 Stage B 均未重新选择或调优；2025–2026 未用于选择或拟合。
- 两个独立 replay 的训练、模型、预测、评分及 manifest hashes 一致。benchmark 只用于本次预先冻结模型的回放评分。

## Full-39 Season-total 指标

WAPE 定义为固定 39 个 Base 上绝对误差之和除以 actual 总和；MAE 为该固定 cohort 的平均绝对误差；bias 为 `预测−实际` 的 signed kg 总和。

| 模型 | WAPE | MAE (kg) | Median APE | Bias (kg) | 高估 / 低估 Base |
|---|---:|---:|---:|---:|---:|
| Global pooled yield | 0.3429935582924604063039679242 | 422769.4831248205128205128205 | 0.3380278746096637845923721843 | -12706357.733154 | 10 / 29 |
| V0.8 R1 | 0.3925893218351959883557945280 | 483900.5883925897435897435897 | 0.3193194749526302384423707190 | -14809615.303231 | 11 / 28 |
| V0.8 R2C | 0.3585864322241786026216929885 | 441989.0605575897435897435897 | 0.3371715636364878918367474622 | -13407443.589846 | 10 / 29 |

因此，R2C 相对 global 的 WAPE delta 为 `+0.0155928739317181963177250643`，相对 R1 为 `−0.0340028896110173857341015395`。R2C 的总体低估较 R1 小，但仍比 global baseline 多低估约 1.70 百万 kg；R2C bias ratio 为 `−0.2789097549426083548248961396`。

逐 Base 绝对误差比较：R2C 对 global 为 13 胜、13 负、13 平；R2C 对 R1 为 14 胜、12 负、13 平。胜负数不替代 pooled WAPE。

## Support 分层

| 历史 support | n | Global WAPE | R1 WAPE | R2C WAPE | 解读 |
|---|---:|---:|---:|---:|---|
| 0 | 13 | 0.2819225473780435968592031667 | 0.2819225473780435968592031667 | 0.2819225473780435968592031667 | R2C 与 global 预测完全相同 |
| 1 | 15 | 0.3519370380584095063462341256 | 0.5411249450720242022947563917 | 0.4386897050370896896751757952 | R2C 未胜 global；该组也未重现 R2B support-1 的 temporal validation 方向 |
| 2 | 11 | 0.3889622349960694394236272972 | 0.2930768913138939074595224946 | 0.3211396082705310843948332075 | R2C 胜 global，但弱于 R1；support=2 的权重外推不能视为 R2B 直接验证 |

总体上，R2C 的 WAPE 不及 global baseline。虽然 support=2 子组优于 global，这一收益没有抵消 support=1 组退化。R2B 在 11 个 temporal validation support-1 Base 上选出的 λ=1 shrinkage WAPE 为 `0.302782961397559568419654371030744204094146089631995360973140`，低于该验证组 global 的 `0.322550160333010518255048633486880676366691141015690368576661`；但 2025–2026 冻结 benchmark 的总体方向不一致，不能据此宣称可泛化提升。

## Daily 与峰值数量指标

Stage B shape 相同，正比例 scale 不会改变模型预测的峰值日期或 rolling-7 起始日期；R1→R2C 的单日峰日期变化数和 rolling-7 起始日变化数均为 0。数量误差如下：

| 指标 | Global | R1 | R2C |
|---|---:|---:|---:|
| Full-39 daily WAPE | 0.5812862592207732948356517114 | 0.6292132974633544144280801218 | 0.5871408241634609795631468040 |
| 单日 peak quantity WAPE | 0.3022025958947355416785549739 | 0.3404074580806719157106758536 | 0.2954285405168558428809517302 |
| Rolling-7 quantity WAPE | 0.2831406887616327543355090948 | 0.3348116783694683981147325588 | 0.2770877685043859274695617846 |

峰值 quantity 指标虽略优于 global，但 peak date 没有因 Stage A 改变而改善；不得把日期不变宣传为 Stage A 的 timing 提升。

## Common-30 V0.7 比较

V0.7 只覆盖 common 30，以下均在同一 30 个 Base 上计算，不与 full-39 指标混算：

| 指标 | V0.7 | Global | R1 | R2C |
|---|---:|---:|---:|---:|
| Season-total WAPE | 0.3565703507552211518045530094 | 0.3718680320214416088905949004 | 0.4295085823774648217328803026 | 0.3890780340614061982750043191 |
| Daily WAPE | 0.7391211072773783730171586934 | 0.5783462535574595492170871309 | 0.6375486158927208783266126936 | 0.5861361621853635586144186390 |
| 单日 peak quantity WAPE | 0.4523239714810114995308642954 | 0.3126617824414381213818458107 | 0.3644422981872252148259636832 | 0.3059418111292892973122516007 |
| Rolling-7 quantity WAPE | 0.4444987003783528082386557904 | 0.2873476075436469115881475284 | 0.3561760399332264772455906911 | 0.2816900671962069478289861114 |

## 最终状态

- `R2C_BENCHMARK_RESULT=R2C_BENCHMARK_WORSE_THAN_GLOBAL_BASELINE`（仅指 full-39 season-total WAPE 数值更高）。
- `TEMPORAL_VALIDATION_AND_FROZEN_BENCHMARK_DIRECTION_CONSISTENT=false`。
- R2C 不应基于本轮结果取代 global pooled yield 作为默认 Stage A；停止当前 λ=1 候选推进，不继续搜索 λ 或其他模型。
- `MODEL_PRODUCTION_READY=false`，`PRISTINE_FUTURE_VALIDATION_PENDING=true`；2025–2026 是已看过的冻结 benchmark，不是新的独立 OOT。
- 未创建 PR，未执行 Ready、Merge、Deployment 或 Stage B 选择/调优。全仓库 CI 未运行；本地 focused tests、Ruff、mypy 结果单独记录在最终回执。

机器汇总见 [`R2C evidence`](../evidence/r2c-frozen-shrinkage-model-and-benchmark-replay-r1.json)。逐 Base、逐日预测与实际数据仅保存在权限受限的私有 replay artifact 中。
