# 版本身份与更新规则

TD-02 决策：区分工程发布、组件元数据与源码身份，保留当前运行时兼容性。
[version-manifest.json](version-manifest.json) 是人工审核的已发布工程版本及组件清单，
不被服务加载，不是自动升级器，也不声称包含它的每个提交都已经发布。

## 当前身份

| 身份 | 权威来源 | 当前值与解释 |
| --- | --- | --- |
| GitHub 工程 Release | 正式 Release、不可变 Annotated Tag 及解引用后的 commit | `v0.21.0` → `3bf2e172822f8b375cf30a0e2c0fcb96ebade722`；研究准备工程版 |
| Python 包 | [pyproject.toml](pyproject.toml) 的 `project.version`；[uv.lock](uv.lock) 的根包记录 | `0.2.0`；历史保留的组件打包元数据，不代表工程只实现到 V0.2 |
| 前端应用包 | [frontend/package.json](frontend/package.json) 与 [package-lock.json](frontend/package-lock.json) 的根版本 | `0.2.0`，`private=true`；不是当前工程 Release 的证明 |
| FastAPI 服务 | [backend/app/core/version.py](backend/app/core/version.py) 的 `APP_VERSION` | `0.2.0`；供 create_app、OpenAPI info.version、health live/ready 使用的兼容字段 |
| API 路由版本 | 各路由冻结合同，例如 `/api/v1/…` | 与工程 Release、包版本均不是同一命名空间；本次不改路由或响应 schema |
| 实际源码 | `git rev-parse --verify HEAD` + `git status --porcelain=v1` | 每次构建/运行实测；不能用上述任一版本号代替 SHA 或省略 dirty 状态 |

v0.21.0 发布时这些组件字段已经是 0.2.0。TD-02 承认其历史漂移，选择保留兼容值并显式记录，
不把已发布 Tag 的源码事后修改为 0.21.0，也不把尚未发布的 main 冒充同一份发布源码。
TD-01 合并提交 `5977fdc1ce3d7393b235bd646d93d18a83781679` 及本次 TD-02 都属于
v0.21.0 之后的开发变更，不构成 v0.21.1 或 V0.22 发布。

组件版本不强制彼此相等，也不强制等于工程版本；本清单要求每个组件的源字段、锁文件及
实际服务使用者与其声明分别一致。当前 0.2.0 不足以唯一定位包/服务代码，必须同时记录
实际源码 SHA（已安装构建还应记录其实际构建身份，不能用旁边 checkout 的 SHA 冒充）。
本次不发布新的 Python/npm 分发包、不新增响应字段、不修改模型/fit/data/schema 版本。

## 每次开发与发布怎样更新

1. 开发前核对 main、最近正式 Release 和目标模块合同。最新已发布版本与当前源码分别报告，
   不能根据 `docs/v0-*` 目录或分支名推断已发布版本。历史快照不因后来合并而回写。
2. 普通修复不自动提升任何版本号。若不变更组件版本，维持清单与现有源字段/锁文件一致，
   用实际提交 SHA 识别修复；在 CHANGELOG 的 Unreleased 记录，不能伪造发布日期。
3. 若未来确需变更包或服务版本，必须在一个明确授权的变更中说明兼容性：Python 同步
   pyproject/uv 根包，前端同步 package/package-lock 两个根版本，服务同步 APP_VERSION 的
   health/OpenAPI 消费者和契约验证。先审查历史源码 Hash 绑定；不自动改写旧 Hash/证据或
   Golden 预期。独立组件发布不能误更新工程 Release 记录。
4. 工程发布另获 Owner 明确授权后，先检查冻结范围、最终目标 SHA、PR CI、合并后 main CI、
   Tag/Release 是否已存在及发布说明。版本数字无需追平组件数字；必须明确这次各组件版本
   是否保持、为什么保持。不得从单项 PASS 推导发布许可。
5. 已发布的 Tag/Release 不覆盖、不重签、不移动。发布前只能写明确的待发布说明，不能把
   未存在的 Release 填成事实；发布成功且远程核验之后，才更新本清单的已发布记录和导航。
   该记录可在后续文档提交登记，因此不要求记录所在提交等于其引用的发布提交。
6. 发布后从 GitHub 重新读取目标、发布状态和 CI。Release 只是工程交付，来源许可、严格 PIT、
   真实精度、模型晋级和部署仍独立。V0.19/V0.20 是已合并阶段，不能补造同名独立 Release。

本次没有足够理由引入运行时 Git 探测、自动版本插件、统一发布平台或迁移 API。
若未来需要组件独立发布或 API build-info，可另立受限任务；不在 TD-02 扩展。

## 可执行检查

在项目 Python 3.12 测试环境运行（只读代码与元数据，不连接业务数据库）：

```sh
APP_ENV=test python -m pytest backend/tests/test_version_contract.py backend/tests/test_health.py -q
python -m ruff check .
python -m ruff format --check .
python -m mypy backend/app backend/research
git rev-parse --verify HEAD
git status --porcelain=v1
```

合同测试检查各组件和锁文件、实际 FastAPI/OpenAPI 版本、发布记录与 checkout 身份分离、
开发导航有效性及 TD-01 两份 XLS 未被重新追踪。已有 health 精确响应测试保持原断言。
CI 不访问 GitHub 来推断“最新版本”；实时 Release/Tag 核验属于有授权的发布步骤。
