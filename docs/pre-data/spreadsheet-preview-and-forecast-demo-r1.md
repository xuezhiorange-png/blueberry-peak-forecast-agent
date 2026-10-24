# 电子表格准备与合成滚动预测演示 R1

任务：`PRE_DATA_SPREADSHEET_PREVIEW_AND_FORECAST_DEMO_R1`。

这是取得真实数据前的产品操作和工程计算演示，不改变 V0.19 正式研究范围、S6–S9 数学定义或生产预测权威。没有读取、导入或评分真实业务数据，没有训练模型。

## 页面操作

登录现有 Dashboard → 预测 → **电子表格准备**。不增加导航层级。

1. 选择 UTF-8 CSV 或 XLSX。本地 Web Worker 解析，不上传、不写数据库、不写 localStorage。
2. 选择工作表、表头行，人工对应日期、基地、农场、地块/分场、品种、重量、单位、品级、记录及时间列。缺失字段保持未映射，其他内容仍可查看。
3. 查看记录数、空白/非法重量、合法零值、日期缺口、重复风险、成员和时间缺口。声明单位和业务口径只表示用户声明，不构成来源证明。

任意文件状态固定为 `USER_FILE_PREVIEW_UNVERIFIED`。没有行记录不是确认零值。数据列对应不等于成员映射、物理口径等价或 M1 完整性已证明。页面清空、切换文件/工作表/表头/映射/单位/口径、退出登录或失去权限后，旧预测与导出均失效。

## 解析边界

- 单文件 2 MiB；展开 XML 合计 8 MiB，实际流式计数，压缩比上限 100。
- 最多 128 ZIP 项、8 张表、10,000 行、80 列、200,000 格；单格 4,096 字符，显示前 50 行。
- Worker 每次请求 8 秒上限，换文件和取消会终止 Worker。
- 拒绝宏、活动对象、外部关系、XML Entity/DOCTYPE、公式和超大稀疏坐标。CSV 中以 `=` 开头的值仅为文本；用作重量时不合法。
- 不加载外部工作簿、链接或网络数据，不执行公式/宏。XLSX 日期按工作簿日期样式解析；无法识别的文本日期交由映射质量提示，不猜测地区日期格式。
- 新增 `read-excel-file@9.3.12` 与 `fflate@0.8.3`，锁文件固定全部解析依赖。解析器在 Worker 内运行，检查后的 ZIP XML 重新打包为 STORE 后读取；不需要后端处理用户文件。

## 合成工作簿如何绑定模型输入

`backend.tests.rolling_forecast.spreadsheet_demo_package.create_demo()` 复用 S9 `create_package()` 和既有公开冻结合成 M0/M1 artifact，没有拟合过程。

每个包具有 CSV 和 XLSX 两份固定资产。XLSX 包含“说明”和“合成入库明细”，第三行为非固定中文列名表头。CSV 第一行为表头。展示的 2026-10-01 至 11-05 共 36 日来源记录，逐项来自同一 S8 合成 Day/Record，未读取预测目标标签。

绑定包含：文件原始 SHA256、12 列规范化内容 SHA256、工作表/表头/映射、S8 来源快照 Hash、冻结 Fit。日期规范为 ISO，重量规范为六位小数 kg，其他文本保留来源值。确定性 ZIP 元数据使重复生成相同内容的文件字节一致。

页面“应用合成示例列建议”仍要求明确选择 kg 和原始入库记录重量。只有原始文件、规范化内容及全部映射与登记身份一致，才启用核验。请求仅包含 Hash、列序号及固定 Origin，不包含文件字节、用户单元格、文件名或路径。

服务器独立重新核对登记工作簿和 S8 原始合成来源逐字段相同，再调用 S9 `synthetic-full` 检查。文件改名/重标记不会取得权限。缺日、晚到和口径冲突包可以预览，但不能签发 M1。

工作簿绑定 Hash 进入合成来源 reference，继而进入既有 input snapshot/context hash；不能展示一份工作簿，却使用未关联来源计算。

## 计算、保存和导出

通过核验后，调用原 S8 观测适配、原 S7 Harvest State 和冻结 Ridge，生成完整 15 日曲线并取前 7 日，使用原 PostgreSQL run/daily-row 保存、幂等和独立日行指标复算。随后 GET 重载并核对保存身份。没有新预测算法、模型训练、日行表或 Excel 导入系统。

合成参考验收值（只在测试中断言，页面不硬编码）：

| Origin | M1 H7 kg | M1 H15 kg |
|---|---:|---:|
| 2026-11-05 | 538.941049 | 1031.362335 |
| 2026-11-06 | 526.137595 | 1002.702182 |

两个 Origin 的 14 个共同目标日期，仍通过原 compare 服务计算。不同窗口的累计变化和相同目标日期的预测修正分别显示。可以切换查看两份保存结果。

`GET /api/v1/rolling-forecast-runs/{run_id}/report?format=html|csv` 导出服务器保存原值。可选 `comparison_run_id` 使用原 compare 权限与算法。HTML 以中文展示模型、口径、完整性、日曲线、单日峰、15 日内连续七日峰和研究限制；CSV 按模型逐日输出。绑定 run/result/model/Origin，切换记录使进行中的导出作废。HTML 转义并禁用脚本和远程内容，CSV 进行公式注入保护。导出不包含私有路径、参数或账号秘密。

H7 前七日累计不等于 H15 内最高连续七日累计；H15 局部高峰不等于产季高峰。入库记录重量预测不标为田间采摘量预测。没有新增 P50/P80/P90，没有实际业务误差评分。

## 隔离环境与复现

演示端点位于 `/api/v1/rolling-forecast-runs/spreadsheet-demo`（GET、POST `/verify`、POST `/issue`），仅 `APP_ENV=test` 且显式提供固定 Manifest 路径/Hash、原有 Catalog 与 principal/revision capabilities 时可用。普通管理身份没有隐式数据权限。默认配置为空，不登记正式来源，不在正常部署环境启用演示。

沿用现有 Cookie、CSRF、账号锁、资源权限与响应发送前复核。没有文件上传 API，客户端不能提供路径或重量行。普通 CSV/XLSX 预览在演示端点不可用时仍工作。

运行 Python 3.12、PostgreSQL 16 和项目锁定前端环境下的完整合成验收：

```sh
python -m backend.tests.rolling_forecast.run_spreadsheet_demo \
  --output /tmp/SYNTHETIC-pre-data-unique --browser
```

输出目录必须新建且以 SYNTHETIC 开头。该命令复用已有 S5 自有 PostgreSQL 生命周期，以及原 S4 HTTPS、真实 ASGI 登录/数据库路径；运行 S7/S8 和本次桌面/手机 E2E，生成截图、导出附件和进程/数据库清理回执。不扫描或清理其他服务。合成 fixture 使用 `synthetic-user` 和既有测试密码，仅存在于隔离测试数据库。

## 以后取得真实 Excel 时

仍须确认重量业务事件、单位、日期/时区、Base 精确成员、品级和修订规则、确认零值及每日完整性、可信可用时间、来源与冻结目标口径证明，以及单独的数据读取/登记/评价授权。此页面不自动升级任何真实来源权威，不实现任意格式数据导入、ERP 接口、真实模型训练或当前产季评分。

本次证明产品操作与计算/保存/导出通道。`STRICT_PIT_VALIDATED=false`、`PRODUCTION_ACCURACY_VALIDATED=false`；不 Ready、Merge 或 Deploy。
