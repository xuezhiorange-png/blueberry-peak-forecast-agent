# TD-01F：干净公开代码仓库的本地可行性验证

任务 `BLUEBERRY_TD01F_CLEAN_PUBLIC_REPOSITORY_FEASIBILITY_R1`。
Owner授权本地隔离验证、实现测试和一个Draft PR；没有授权真实数据读取、远端仓库创建、
可见性改变、历史重写、强推、Tag/Release操作、Ready、Merge或部署。

## 实际功能与边界

`backend/app/core/clean_public_repository.py`消费固定Hash的显式候选清单，逐个验证当前HEAD的
Path、普通Blob类型、Git OID和SHA256。只读取获准检查的代码/构建元数据；来源数据及未知路径
在内容读取前拒绝。已知XLS和压缩资产身份无论改名为哪种后缀均阻断。
现有PUBLIC_CODE分类没有被当作无经营字面量的证明。候选限定为13个经过具体代码审阅的
代码/测试/构建文件和5个TD-01C完整再生成匹配的合成产物；其余文件不获得公开准入。

只通过git init创建本进程拥有的临时Git库，无Remote、Alternates、旧父提交或Tag。
Git子进程复用TD-01E禁网络/惰性抓取/外部配置的机制，不从原仓库fetch、fork或mirror。
所有Git写入只能针对本验证器登记的临时库。代码保持原字节；TD-01C工作簿在读取前与
独立生成器的完整输出身份绑定，不通过文件名或SYNTHETIC标签取得资格。

对象核验覆盖全部可达和悬空对象、唯一根提交、所有Ref、配置/Alternates、Git Tree、
文件Hash和工作目录增量。测试前后均核对，不以“当前Tree无XLS”推定历史已安全。
这里的PASS仅证明明确候选和对象边界，不是通用DLP证明或全仓公开许可。

## 已实际运行的隔离结果

18个文件，30个Git对象，唯一新根 `c49d84578fee75eed2f1ad6d912441b5594f387f`；
0父提交、0Remote、0Tag、无Alternates，已知XLS Blob及阻断压缩资产不存在。
隔离库中原代码13文件（其中1个构建元数据）逐字节不变，5个合成文件匹配现有生成器。

- Ruff、Format通过；strict Mypy实际检查10个应用/研究源码文件。
- 纯日曲线实际计算21个合成日，检查分箱守恒及H7为H15前缀，不训练、不读取真实标签。
- 原TD-01C测试文件完整保留：24通过，1失败。该失败明确缺少
  `td01c-public-derived-audit-summary.json`，对应测试还依赖原风险登记、Ref增量和742行清单。
  没有导出未审的历史报告来凑绿色，也没有改断言、增加skip或将失败解释为PASS。
- 原CI的320f2046、e9812e82、0124371b Commit预检各实际返回128，说明旧Commit未复制，
  同时说明原CI不能原样迁入。原仓库完整PR CI仍照常运行，不以这个子集代替它。
- PostgreSQL、Frontend和完整应用运行在隔离库中均未验证；历史报告、配置、额外代码等依赖
  未取得新公开候选资格，明确BLOCKED/NOT_VERIFIED，不宣称全项目已迁移。

命令（项目Python 3.12环境；输出目录须不存在）：

```sh
python -m backend.app.core.clean_public_repository --output-dir /tmp/TD01F-local-rehearsal
python -m pytest backend/tests/ci/test_clean_public_repository.py -q
```

输出目录0700、文件0600，保留四份报告、每个检查的stdout/stderr及原始JUnit；拒绝覆盖。
提交的脱敏报告位于[td01f-rehearsal-r1](td01f-rehearsal-r1/clean-repository-manifest.json)。
临时库在对象与测试后核验完成后由其实际拥有者清理，报告和失败证据在库外留存。

## 可直接复用、仍阻断和未验证的内容

可运行子集包括规范化、Decimal指纹、显式Schema、独立合成生成/容器检查及纯日曲线计算。
没有把实际入库记录、田间采收量或SOURCE_002净重声明等价。
TD-01E的65项历史代码身份、222项非代码依赖、174个身份相关消费者直接复用现有机器清单，
不重新扫描1658个文件；65项代码身份核验不等于其在新公开库已获准导出或所有消费者可运行。
其余测试按历史依赖阻断或未验证分类，不从路径推测成功。

D02/D03/D06均为OWNER_PENDING；参见[精简决定](td01f-owner-boundary-decisions-r1.md)及
[方案对照与停止条件](td01f-options-and-migration-dependencies-r1.md)。
实际源、PIT、历史回测、模型参数、预测数学、旧Hash、Tag和Release保持原样。
真实历史公开风险未消除；本轮没有执行任何生产训练、评分、模型晋级或V0.22开发。
