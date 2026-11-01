# PR #783：V2 合成来源逐字节复算修正

本轮仅修正原 Draft PR #783 的合成来源证明。复审起点为
`6af6e107b8edfd5e6ace52ad3a5abf3885c42a6b`；不改变 V1、TD-01F、预测数学、
原仓库 CI 判据或已封存的运行报告。既有 V2 R1 报告仍表示其当时实际运行结果。

## 已证明的问题

在独立合成 Git 仓库中，取 V1 中实际由 seed 41 生成的五文件，声明为 seed 43。
四份 CSV/XLSX 的内容及 Manifest 内的行数据保持相互一致，Manifest 的 seed、
来源标识、导出 Hash 和独立模拟审查中的全部 Blob/SHA256 均合法匹配。
但内容不是冻结生成器对声明 seed 43 的输出。

修正前门禁实际返回 **PASS**；新增要求其阻断的回归实际失败。
这证明独立审查的内容身份匹配及 Manifest 自洽，不能代替生成器来源证明。
修正前失败 JUnit 和报告单独保留，不覆盖为成功结果。

## 最小修正及执行顺序

1. 保留仓库配置、对象集合、禁止 Blob、完整提交图和可信 Base 的既有检查。
2. 仍固定 V1 Root `04457546f5577d4e44effb808154a6aa08b45846` 及原 Manifest seal。
   `_bootstrap()` 先验证原 Blob 和源码 SHA256；不使用 Head 的生成器、依赖文件或新 Hash。
3. 从上述已验证 Root 的明确 `backend/` 源码 Blob 建立仓库外临时源码目录，
   再次验证写入字节的 Blob/SHA256。生成器仍为
   `backend/app/etl/history/synthetic_publication.py`，来源为
   `TD01C_INDEPENDENT_GENERATOR_V1`，不修改它的实现或冻结 Hash。
4. 使用可信执行器的 Python 3.12 启动独立 `-I -B` 子进程：忽略用户 site、
   `PYTHONPATH` 和待审工作目录；只加入已验证源码目录。seed 取自仓库外、
   独立固定的合成审查声明，绝不从待审 Manifest 选择 seed 或生成器。
5. 从原 Root 的锁文件核对运行依赖版本：openpyxl 3.1.5、et_xmlfile 2.0.0、
   xlrd 2.0.2。关闭可选 XML 后端以固定容器生成路径。复算本身不联网、不安装
   Head 代码、不读取任何待审 CSV/XLSX/Manifest，也不接受真实来源路径。
6. 冻结生成器真实执行 `export(generate(seed), ...)`，重建完整五文件。
   随后逐文件比较提交 Blob 的**完整字节**，包括 Manifest 和 XLSX 完整 ZIP 容器，
   而非仅比较表格值或 PR 提供的 Hash。任一不一致返回
   `SYNTHETIC_GENERATOR_OUTPUT_MISMATCH / BLOCKED`。
7. 无法执行可信复算、依赖不匹配、子进程失败或超出执行界限时返回
   `SYNTHETIC_REGENERATION_UNAVAILABLE / BLOCKED`；不回退为仅验证 Hash。
   子进程 stderr 不进入公开报告。临时源码和生成文件在调用退出时清理。

每次验证只在内存中按 seed 缓存本次可信复算结果；不会接受 Head 提供的预期输出缓存。
公开报告只增加生成器身份、seed 和五文件 Hash，不回显源行、私有路径或异常正文。

## 回归范围

- 保留原有 28 项负向演练，另增自洽伪合成包回归。
- 单独验证：仅修改 XLSX ZIP comment、保持单元格不变，并同步更新 Manifest 和
  全部审查 Hash，仍必须阻断。这覆盖完整容器字节而非单元格比较。
- 验证复算失败不得通过，以及可信源码复算先于任何新增合成 Blob 正文读取。
- 独立安装环境中增加真正生成包通过、伪 seed 内容阻断、容器变化阻断三项公开合同。
  原 V1 38 项不变；V2 原 12 项全部保留，现要求 15 项均通过。原仓库工作流不变。
- V2 当前执行器身份清单随本次源码更新，仍不构成审查授权；旧提交、V1 清单、
  TD-01F 24 PASS / 1 BLOCKED 和原 V2 R1 报告均不回写。

实际修正前后、独立进程和独立 CI 结果见同目录
`td01i-v2-r2-synthetic-provenance.json`。最终 GitHub CI 以新 HEAD 的 PR 回执为准。

## 不变的限制

独立子进程是来源和解释器隔离，不是已经验证的 OS 沙箱或任意第三方依赖供应链证明。
执行环境须来自可信 Base；依赖不齐时失败关闭，不从 PR 安装替代依赖。
真实远端 Owner 审查、Required Checks、Branch Protection 和防绕过仍未配置，
新公开远端 Actions 仍为 NOT_RUN。本轮不授予公开发布权限，不读取真实工作簿、
SOURCE_002 或业务原件，不重写真实 Git 历史，不 Ready、Merge、发布或部署。
