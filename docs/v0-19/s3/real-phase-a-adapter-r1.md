# V0.19 S3 阶段 A 适配器 R1：开发交付，不是执行授权

TASK_ID=V0_19_S3_REAL_PHASE_A_ADAPTER_R1

基线 main：`c706d3902ff77f82fb7914474b98fe3a957b6229`。
本次仅新增独立研究代码、合成测试和说明。不读取私有 Profile、Registry、采收标签、
农场名单或面积；不生成真实预测、不评分、不训练，不改变生产代码或既有研究算法。

## 接口及信任边界

`backend/research/v019_real_phase_a_adapter.py` 提供三个相互区分的接口：

1. `validate_frozen_inputs(FrozenInputPaths, support=SupportProposal)`：只读核验，
   未来调用者仍须具有对象读取授权。五条绝对路径必须显式提供，没有目录搜索、环境
   路径 fallback 或版本替换。依次检查文件名、符号链接、普通文件、大小上限、读取期间
   状态、固定原始 SHA256、严格 JSON/CSV Schema 和候选身份。
   这次开发/CI 不对真实对象调用此接口。输入核验通过也只能返回
   `VALIDATED_CANDIDATE_ONLY_EXECUTION_BLOCKED`，不是正式 C0 或运行许可。
2. `rehearse_synthetic(fixture=...)`：只接收既有内置夹具名称，没有外部曲线、标签、
   文件或自定义真实时钟参数。复用 `register_synthetic`、`generate_synthetic`，继而复用
   原 `prepare_predictions` 和唯一 S2 候选。基线仍是既有合成冻结日值，不是假冒真实
   Fold B 的新模型。额外完整曲线展示也直接调用原 S2，不重新实现插值或计算峰值。
3. `generate_real_predictions(...)`：无条件抛出 PermissionError，先于任何文件读取。
   布尔值、环境变量、伪造授权和自称协议生效都不能启用。当前不提供真实执行或评分 CLI。

`verify_synthetic_seal` 重建原合成演练，检测成员、C0、源码或自算封存 Hash 的篡改。
Hash 是完整性身份，不是签名、访问许可或可信历史签发时间。这里没有新增权限系统。

## 固定真实来源身份（仅元数据）

| 对象 | 固定 SHA256 |
|---|---|
| Fold B reference-B.json | `a0a5cbc3c3ca5bd2b0b8860328eee73840499b38da89c11a104f83d02fd77c5b` |
| base-registry-v1.json | `502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904` |
| Registry payload | `d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293` |
| h7-candidates.csv | `ccf39c71786c5e1e9e6503aa9c7b7a76cab4c9e71144d080a85f66a8aa97b68f` |
| h15-candidates.csv | `a9059f3d00c1ec9ed3e4fafda7ef41eb75fee7902e76e3a8ed87822cd0380042` |
| 必要候选元数据 sidecar | `6054c2166c5e9800033a34bacc660a96813d0515f3f89fc61380010c0de4bf61` |

sidecar 为既有 `base-admission-metadata.json`，用于重建原候选成员 Hash 中的
Base 成员身份及历史面积权威行 Hash；不包含采收重量。本次只使用前次核验提供的
对象身份及非敏感 Schema，不把私有文件、目录、实体名、面积值或 profile 数值复制入 Git。
固定 Profile 训练成员 Hash 为
`c8b2da43696071648ac8280569fc2e28d7fa4b987f0a63b9edaae22122cc717e`，
不是重新拟合或从当前标签推导的 Hash。

原始文件 Hash 在结构解析之前检查，Registry 内部 payload Hash 亦重新计算。
测试完整结构使用 **39 个虚构 Base、面积 1、profile 日率 1**，其 Registry Hash
明确不等于真实固定值。内部纯结构校验器允许验证该虚构对象的自洽性；公开文件接口
仍强制真实固定 raw/payload 双 Hash，不能向调用者传入替代预期 Hash。
这不声称真实文件已在本轮再次读取，也不伪造真实固定对象的正向安装测试。

## C0 与 support 合同

- SOURCE_002，2025–2026，目标 2025-08-05—2026-04-15；排除 04-16。
- 39 Base；75 个已映射农场；9 个未解决农场继续阻断，不能自动映射、删除或判为无影响。
- H7 9,672 个，39×248 origins；H15 9,360 个，39×240 origins。
- 逐成员核验日期、窗口、来源、身份 Hash、成员唯一性及 Base×origin 完整集合和顺序，
  不按数量或误差选样本。成员缺失、重复、乱序、替换、越界和身份漂移均拒绝。
- 所有候选仍为 `C0_CANDIDATE_ONLY`；正式 C0=0；完整产季准入=0。
- `SupportProposal` 必须显式给出，不暗中批准新参数。保留 2025-07-01 season anchor；
  完整 support 必须覆盖全部目标日期，结束 2026-04-15；开始不得晚于 08-05。
  其状态只能是 PROPOSED_NOT_EFFECTIVE。具体 support 尚须 Owner 预注册批准。
- 合成正向测试用原有 21 日完整 support。两条曲线先在完整 support 上生成，再切
  H7/H15；不按查询窗口重新插值或归一化。测试比对切片与完整曲线值和共同前缀。

已知限制强制保留：物理口径等价 NOT_PROVEN、历史面积 known_at NOT_PROVEN、
未解决农场影响 NOT_PROVEN_UNAFFECTED_NOT_LOCALLY_ATTRIBUTABLE。
不得因 Hash 匹配或 19,032 个结构成员验证成功而自动改变这些状态。

## 输出与时间身份

合成输出封存：Base、origin、cutoff、完整 support 日期和两条日曲线、查询日期与
日值、输入来源 Hash、两条 forecast Hash、候选结果来源 Hash、C0 和原预测 seal、
五个执行模块当前源码 Hash、唯一方法配置 Hash、失败原因和整体 seal。
缺输入和物理口径阻断仍保留原成员，没有缩小 C0。

身份始终为 RETROSPECTIVE_REPLAY / EXPOSED_HISTORICAL_BENCHMARK /
STRICT_PIT=false / PRODUCTION_ELIGIBLE=false。
合成时间明确为 EXPLICIT_SIMULATED_CLOCK_NOT_REAL_EXECUTION_TIME，晚于历史 origin，
computed_at=issued_at，不倒填为目标前签发。未来真实运行必须记录实际 computed_at、
issued_at、sealed_at；当前不伪造真实运行时间或历史输入可用时点。
既有严格评分器和十项指标完全不变，也没有在本模块增加跨来源评分豁免。

## 测试、复现及后续门禁

专项测试先验证 RED：模块尚不存在时 ImportError；随后实施并进行 GREEN 回归。
测试覆盖：完整候选结构、日期/来源/成员/面积/物理口径负向、九农场限制、伪造授权、
真实执行先拒绝、标签/评分访问观察器、确定性、源码漂移、重算 seal 伪造、完整曲线切片、
失败成员保留、原始晚签发、符号链接、严格解析及只读失败无副作用。无 skip/xfail/retry。

本地命令：

```sh
python -m pytest backend/tests/area_yield/test_v0_19_real_phase_a_adapter.py -q
ruff check .
ruff format --check .
mypy backend/research/v019_real_phase_a_adapter.py backend/tests/area_yield/test_v0_19_real_phase_a_adapter.py
```

本次源码身份在运行 seal 中计算；已有研究源码的历史身份以基线固定 Git blob 验证，
不新增“未来工作树必须永远等于本次测试源码”的合同。机器证据记录本地检查，
最终提交 SHA、完整 CI 和独立审查分别由 GitHub 实际记录确定，不能预填成功。

最终本地源码专项 37 passed（重复执行）；V0.19 S0/S1/S2/S3 与 V0.18 历史合同
合计 548 passed / 0 failed / 0 skipped。全仓 Ruff、1512 文件 Format 及新模块与测试
Mypy 通过。没有以这些离线结果替代真实数据、PostgreSQL 或浏览器验收；后两者的
既有回归由最终 exact-head CI 执行并单独报告。

真实运行仍需独立批准：研究协议、九农场的精确权威或明确限定成员的条件研究、
正式 H7/H15 C0、support/origin/cutoff、实际输入读取与执行边界，以及真实执行接线及验收。
真实执行当前仍刻意不接通；必须另获授权后实施，不是本次已有一个可启用的开关。
阶段 B 的标签读取、评分及真实结论继续独立授权；S3_FORMAL_COMPLETE=false。
