# TD-01G：独立安装的合成公开核心与 CI 等价验收

TASK_ID：`BLUEBERRY_TD01G_CLEAN_PUBLIC_CI_AND_EXECUTABLE_CORE_R1`。
基线 `d070331756a83e9a0247157298204a34271fe3f0`，PR #780已合并。
Owner本轮工作边界为：真实身份关系、经营数量/曲线及原始冻结证据保持私有；公开数据仅独立合成。
该边界不是远端仓库创建、公开发布、可见性改变、历史改写、Ready/Merge或部署许可。

## 已完成的实际功能

- `backend/app/public_core.py`：独立安装的CLI，复用原TD-01C生成器、原规范化/Schema/指纹与原V0.19日曲线函数，不复制求解器。
- `backend/app/core/public_core_rehearsal.py`：复用TD-01F受控临时Git库、Git读写边界、候选身份与合成完整内容绑定；只从当前HEAD取得已登记源码。
- `public_core/td01g_v1/`：最小pyproject、完整依赖锁、公开合同/安全测试、只读对象门禁、独立安装与测试脚本，以及未来Actions工作流模板。
- [新版候选清单](td01g-public-core-candidates-r1.json)：27个精确Source Path/Blob/SHA256登记，加生成的公开Manifest，共28文件。未知文件不能只凭PUBLIC_CODE或SYNTHETIC_ONLY标签入库。

独立CLI支持`generate`、`curve`和`demo`，输入为受限整数seed与唯一版本配置。
生成98行、两个虚构产季的CSV/XLSX、Manifest和质量报告；读取并验证自己生成的CSV/XLSX完整内容。
缺失重量、真实合成零值、负量、日期错误和重复风险均保留，不补零、不注册正式业务来源。
`--source`或Python接口的非空真实来源参数在文件访问前拒绝。

曲线入口实际调用`generate_candidate`和`select_window`，输出28日六位Decimal kg、同一origin的
H7/H15逐日结果、分箱守恒和确定性证明。随机量仅用于构造明确合成输入，不是模型拟合或调参。
所有运行报告均声明：DATA_CLASS=SYNTHETIC_ONLY、REAL_FORECAST_VALIDATED=false、
STRICT_REAL_PIT_VALIDATED=false、PRODUCTION_MODEL_ADMITTED=false。

## 从 TD-01F 到本版的精确差额

| 对象 | TD-01F | TD-01G |
| --- | --- | --- |
| 候选文件 | 18文件，借用既有开发环境 | 复用其中16份原字节，新增11份明确审阅源码/构建模板，加1份生成Manifest，共28文件 |
| 根pyproject | 原项目完整依赖和CLI绑定 | 新的最小原型包；原项目pyproject没有修改 |
| 原完整合成测试文件 | 24 PASS / 1 BLOCKED历史审计材料依赖 | 原文件、断言和旧结果全部保留；该文件不被改造成新公开测试入口 |
| 公开验收 | 原完整测试在新根实际失败 | 新的明确限定范围38 PASS / 0 BLOCKED；不包含历史审计登记，也不把旧阻断改为PASS |
| 安装证明 | 已有环境中的子集运行 | 无system-site-packages的新venv，完整锁安装、归档包安装、pip check和安装路径证明 |
| 旧Commit / Tag / 私有输入 | 原CI三处旧Commit预检阻断 | 新公开核心不要求它们存在，不引入Blob恢复或旧基线替换 |
| 原完整服务 | 未验证 | 仍不迁移PostgreSQL、Frontend、MCP、真实S6模型或历史研究资料 |

原TD-01F清单、四份报告及失败证据没有修改；它的1项真实阻断继续在新机器报告中单独登记。
没有删除原测试、增加skip/xfail、过滤warning、改旧Hash、弱化Golden或CI判据。

## 安装与可复核依赖闭包

直接runtime只有openpyxl/xlrd；解析、规范化、合成与日曲线入口的本地模块逐一登记在
[导入和环境闭包](td01g-public-core-r1/import-and-environment-closure.json)。构建与测试工具也显式登记。
原项目依赖、uv.lock、backend/constraints-ci.txt和运行时API版本均未修改。

新的`requirements-direct.txt`明确8个直接runtime/build/test要求；`requirements-lock.txt`
固定完整18包及其发布wheel SHA256（含不同平台的同版本候选），安装强制require-hashes、binary-only。
安装后额外只有本地原型包`blueberry-public-core==0.0.0`，实际19个distribution与锁闭包精确相等。
它不是GitHub Release，也不修改已发布v0.21.0身份。

这固定Python包版本和制品身份，不固定OS镜像、Python二进制或硬件；初始bootstrap来自可信Python3.12的ensurepip，随后pip也按锁固定。
公开目标为Python3.12/macOS arm64及Linux x86_64；本地已验证macOS；Linux将由本PR原仓库Canary中的独立安装合同执行，取得结果前不记为PASS。
版本固定与完整传递依赖/Hash验证的区别参考[pip重复安装](https://pip.pypa.io/en/stable/topics/repeatable-installs/)
及[Hash检查](https://pip.pypa.io/en/stable/topics/secure-installs/)。

## 实际命令及证据

在原项目Python3.12环境执行组装器（输出目录必须不存在）：

```sh
python -m backend.app.core.public_core_rehearsal --output-dir /tmp/TD01G-rehearsal
```

它在全新git init目录构造代码根，无原历史、Remote、Tag、Alternates或父提交；随后执行与
`public_core/td01g_v1/workflow.yml`模板相同的公开脚本。公开脚本使用隔离解释器启动源码门禁，
防止未知同名模块在检查前被执行。新venv与安装产物位于源码根以外，安装的是先通过门禁的Git archive，
不会借用原开发包或在源码中遗留build/egg-info。

逐命令保留exit code、stdout/stderr Hash及原始日志/JUnit；任何失败继续抛出，已有输出不覆盖。
安装后在源码树外运行两个独立进程，实际生成全部CSV/XLSX与逐日曲线，所有产物Hash完全一致。
导入探针验证12个本地模块及openpyxl/xlrd均来自新venv；无私有配置或旧Git身份依赖。

本地最终结果：[CI等价报告](td01g-public-core-r1/local-ci-equivalent.json)：
**LOCAL_CI_EQUIVALENT=PASS，公开测试38 PASS，strict Mypy 14源码文件PASS。**
对象核验为28文件、42对象、唯一无父根、0 Remote、0 Tag、无Alternates/已知经营Blob；测试前后保持一致。
[导出文件身份](td01g-public-core-r1/exported-file-identities.json)记录每份实际Blob/SHA256。
只有门禁代码中的Manifest seal字面量按已审模板替换；其他源码和已登记合成文件保持原字节。
模板归一化不是任意内容豁免，修改映射/Hash/标签不能通过未变的信任根。
该代码审查边界不声称抵御可以任意改写门禁Python实现的攻击者。

未来工作流包括对象/文件门禁、Python3.12独立安装、Ruff、Format、strict Mypy、合成/日曲线/反向安全合同。
只读checkout-shaped origin/main与detached HEAD有本地测试；未创建或运行新远端仓库，
**ACTUAL_NEW_REMOTE_GITHUB_ACTIONS=NOT_RUN**。V1只准入这个已封存根，后续公开源码或历史范围变化须更新并审阅版本化允许清单。

## 保留的失败与限制

首次全新安装及安装路径证明成功，CI等价检查实际在Ruff失败：模板位置与导出位置的本地包识别不同。
已显式固定known-first-party，未放宽规则；第一次FAIL及日志仍保留。依赖清单使用正常pip文本格式，
没有修改旧增量门禁的后缀或业务数据识别规则。随后独立新环境完成最终全流程PASS。

前置main CI #41265226227最终为**FAILURE**：合成PostgreSQL备份恢复测试，以及桌面/手机撤销会话E2E失败。
[脱敏失败登记](td01g-public-core-r1/predecessor-ci-failure.json)保留路径、错误类型与日志Hash。
TD-01G源码不在该失败SHA中，但其真实根因尚未证明；本轮不重跑前置CI、不修改这些业务测试，
也不把本PR后续绿灯当作该main验收成功。前置失败尚待独立闭合，最终总体结论应保留此限制。

新根的完整预测服务、真实模型、数据库、前端和MCP不在本任务范围；旧历史审计、222项非代码依赖
及公开增量旧基线迁移没有因此完成。真实经营资料、SOURCE_002、原始XLS、历史评分及模型参数未读取或改动。
当前限制性工作边界不是历史清理/公开发布授权；原公开历史暴露未消除。本轮到一个Draft PR及原仓库完整exact-head CI为止。
