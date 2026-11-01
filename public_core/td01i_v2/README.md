# Public core V2：受信任 Base 与待审 Head

这是 TD-01I 的离线验证代码和未来工作流模板，不是已建立的公开远端仓库。
V1 的 28 文件、42 对象、根提交和 38 项合同全部保留；V2 不修改 V1 文件。

独立运行图门禁：

```sh
python -I -B /trusted/base/tools/public_core_incremental_gate.py \
  --repository /owned/candidate --context /trusted/event/context.json
```

退出码：`0=PASS`、`3=REVIEW_REQUIRED`、`2=BLOCKED`。报告只包含身份、相对路径和原因，
不会输出 Blob 内容。`context` 由可信调用方提供 Base、Head、Checkout、预期 Ref 和 Origin；
不得从 Head 的 Manifest、标签、工作流或现有 Ref 集合推导权限。

唯一已实现的审查传输是**独立合成实验**：仓库外的预期字节审查记录及调用方固定的 SHA256。
参数 `--synthetic-review-authority` 不是 GitHub Owner 授权接口，工作流模板不使用它。
Head 内的审批 JSON、修改后的 Hash 或验证器不能进入该信任边界。

完整本地复现，从原项目 Python 3.12 开发环境运行：

```sh
APP_ENV=test python -m backend.app.core.public_core_incremental_rehearsal \
  --output-dir /tmp/TD01I-new-evidence-directory
```

程序只在自己创建的 Git 库中写入，基于 V1 固定清单重建同一个合成根，不 Fetch/Fork/Mirror
原项目历史。实际演练两轮 PR、多提交、普通 Merge、合并后继续开发及负向场景。

独立 CI 先从已模拟审核的 Base 导出固定执行器，再验证第二个 PR。门禁通过后才安装 Head。
未授权内容不会因改写 Head 的测试或脚本而跳过第一道门禁。

验证范围分开记录：

- 原 38 项 V1 合同在同一个无父根的精确重建库中运行，保留原测试的单根语义。
- 原 24 项功能合同在独立环境中针对**已安装的实际 Head**再执行，全部 backend 源码字节与
  Head Tree 核对，检查合成 CSV/XLSX、来源、质量原因、Decimal、分箱守恒和 H7/H15。
- 新 V2 安全负例从可信 Base 的固定测试文件执行；Head 的 Ruff、Format、strict Mypy
  仍覆盖新增代码。归档必须逐文件与 Tree 完全一致，不能用 export-ignore 隐藏文件。

原依赖锁继续固定完整安装闭包。新依赖/锁变更返回 `REVIEW_REQUIRED`，R1 不自动迁移安装合同。
代码字面量公开范围仍需要独立审查；语法合法不是经营数据公开许可。

真实远端审批、Required Workflow、Branch Protection、CODEOWNERS 和首次 Bootstrap 还没有配置。
详见原项目 `docs/tech-debt/td01i-v2-r1/public-core-v2-remote-readiness.md`。
`ACTUAL_NEW_REMOTE_GITHUB_ACTIONS=NOT_RUN`，`PUBLICATION_AUTHORIZED=false`。
