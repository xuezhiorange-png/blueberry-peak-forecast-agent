# S1 气候分区 authority 裁决 R3

结论：**DO_NOT_FREEZE_MAPPING**。38 基地中 23 CORE / 10 BOUNDARY / 5 UNSTABLE。K=5 候选可复现，但未达到本轮冻结门槛。
不重开 K 选择；不修改归属、阈值、特征或 R2 证据。两个 authority freeze 标记均为 false。

## 输入与执行门禁

基线 main：`f3a38630debe1328ede3f5782e08f5ca4e6db01a`。R2 的所有 manifest 文件、原始 NetCDF、profile 内部哈希已核验；完整 R2 重放产物逐文件 SHA256 相同，K5 原始标签（包括编号）完全一致。
Registry：`d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293`；source snapshot：`ddb4e9beb6a68927de882186cd3cbb7efa6b3238d56fb4f20bb2d36b8655ac70`。
R2 manifest：`e71c4279131f810dfb94118f8dabb25584aeee403cfcaff6831c09f4c2091357`；R3 manifest：`f676fbd6557ab859640b408044053a3f00c481590541f646456fff6066c00d9e`。
R3 在 socket.connect 被禁止的进程内执行；另一个全新目录再次离线执行，所有产物 byte/hash 一致。本轮没有下载或访问气象网络服务。

## 冻结算法与裁决规则

主参考为 1991–2020 KMeans K=5；完全复用 R2 七特征顺序、StandardScaler mean/scale、seed=42、n_init=20。仅对气候与海拔作诊断，不读取产量、亩产、面积、峰值或预测误差作为特征。
200 次重采样采用 default_rng(42)，每次从 38 个基地无放回抽取排序后的 30 个；每次拟合 seed 固定为 42。原基准 scaler 不重估。在抽中基地上 Hungarian 最大重叠对齐；多最优解按标签置换字典序最小确定。遗漏基地按该次拟合质心最近距离归类，再使用同一标签映射；距离并列取原标签最小。
频率分母始终为 200（含抽中与遗漏诊断）；称 RESAMPLING_ASSIGNMENT_STABILITY，不是置信区间。完整抽样索引、每次映射及38基地分配均保存。
LOFO 恰好七次：每次移除一个特征，对保留六维重新标准化，K/seed/n_init 不变；全38基地最大重叠对齐，不做替代特征或优化。Ward 仅为一致性诊断。
CORE：频率≥0.90、LOFO≥6/7、时段稳定、坐标分区稳定、源无阻断。BOUNDARY：频率≥0.70、LOFO≥4/7、坐标稳定，但未满足全部 CORE。UNSTABLE：频率<0.70、LOFO<4/7、坐标不稳或源完整性不足，任一即成立。
几何 margin=(d2−d1)/max(d2,1e−12)；d1 为已分配质心，d2 为最近其他质心，均在冻结标准化空间。不是概率。负 silhouette、Ward 分歧单列，不添加事后分类门槛。

## 分区与物理解释

| 固定ID / R2 | 描述 | 基地数 | CORE | BOUNDARY | UNSTABLE | 温度中位°C | 年降水中位mm | 海拔中位m |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| YN_CLIMATE_ZONE_01 / Z1 | 滇中南偏暖偏干型 | 8 | 7 | 1 | 0 | 17.51 | 954.1 | 1376 |
| YN_CLIMATE_ZONE_02 / Z2 | 滇西高海拔凉湿型 | 4 | 0 | 2 | 2 | 14.64 | 1859.9 | 1703 |
| YN_CLIMATE_ZONE_03 / Z3 | 滇南低海拔暖湿型 | 5 | 3 | 1 | 1 | 19.20 | 1741.5 | 949 |
| YN_CLIMATE_ZONE_04 / Z4 | 滇东/滇东南高原型 | 15 | 12 | 3 | 0 | 16.09 | 1191.6 | 1521 |
| YN_CLIMATE_ZONE_05 / Z5 | 滇中北高原较干高辐射型 | 6 | 1 | 3 | 2 | 16.39 | 1297.7 | 1678 |

描述是相对本样本气候分布：Z2 较凉湿且海拔中位较高；Z3 最暖、低海拔；Z5 辐射中位最高，其‘较干’相对湿润 Z2/Z3，并不意味着降水低于 Z1/Z4。行政方位只是描述，不是分区依据；没有为命名调整成员。

## 冻结阻断

| 基地 | 原区 | 重采样同区频率 | LOFO | 触发门槛 |
|---|---|---:|---:|---|
| 保山由旺基地 | Z2 | 0.635 | 4/7 | frequency<0.70 |
| 元江甘庄基地 | Z3 | 0.550 | 4/7 | frequency<0.70 |
| 富民款庄基地 | Z5 | 0.470 | 2/7 | frequency<0.70, LOFO<4/7 |
| 保山杨柳基地 | Z2 | 0.685 | 5/7 | frequency<0.70 |
| 大理巍山基地 | Z5 | 0.665 | 4/7 | frequency<0.70 |

负 silhouette 基地：元江甘庄基地、富民款庄基地。Ward 分配分歧 4 个。频率 min/median=0.470/0.915；LOFO rate min/median=0.285714/1.000000。

38/38 坐标分区稳定，但12基地格点切换。SOURCE_CRS_UNCONFIRMED_WGS84_QUERY_ASSUMPTION 保留，不能推导坐标系已经核验。

## 候选 payload 与复现

Profile candidate hash：`284f79a2e0cf49525d8e41bd4d6799c38ada246b67e4211a06e88b3fba2660e1`。
Mapping candidate hash：`2f1475bcdccd6379b4e4d96ab9f3ff073ee032e51dd40103e8eea5dc1017c01c`。
ID 永久绑定本次 R2 Z1..Z5；候选均 CANDIDATE_ONLY，不得后续重聚类静默改 ID 语义。
私有目录：`/Users/charles/Documents/blueberry-area-yield-artifacts/climate-zone-r3-authority-review`；重放：`/Users/charles/Documents/blueberry-area-yield-artifacts/climate-zone-r3-authority-review-replay`。不提交原始坐标或 NetCDF。

```bash
python -m scripts.run_climate_authority_r3 \
  --source /Users/charles/Documents/blueberry-area-yield-artifacts/climate-zone-r2-source \
  --r2 /Users/charles/Documents/blueberry-area-yield-artifacts/climate-zone-r2-review-complete \
  --r2-replay /Users/charles/Documents/blueberry-area-yield-artifacts/climate-zone-r3-r2-input-replay \
  --output /absolute/path/to/a-new-private-directory
```

R2 完整重放使用既有 scripts.run_climate_study_r2.run，并在运行前禁止 socket.connect；新 R3 runner 校验该重放目录与冻结 R2 manifest 所有文件哈希。输出目录必须不存在。

## 验证与停止门

新增 focused tests 覆盖固定 K/配置、200 次抽样、遗漏基地质心归类、七次 LOFO、标签对齐、全部分类边界、输入篡改拒绝、候选哈希和离线确定性。R1/R2 测试未修改。
本地 R3 focused：19 passed；base_registry/area_yield/mcp 回归：371 passed、9 skipped。Ruff check、format（1042文件）、mypy（backend/app 444文件及R3研究脚本）、JSON/reference/hash 检查通过。
最终 exact-head CI/full-suite-canary 在 PR 和任务最终回复中记录；不能用旧 R2 CI 替代。
READY_ELIGIBLE=false；READY_AUTHORIZED=false；MERGE_AUTHORIZED=false。
停止于 COORDINATOR_S1_CLIMATE_ZONE_R3_REVIEW；不进入 S2，不实施 authority 冻结。
