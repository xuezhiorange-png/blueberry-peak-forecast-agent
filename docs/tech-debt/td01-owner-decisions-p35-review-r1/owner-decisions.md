# TD-01 Owner 业务边界决定 R1

任务：`TD01_OWNER_DECISIONS_FREEZE_AND_P35_REVIEW_R1`。
读取的最新 main：`fe494971c92f1d951f5acfeb6a70b85a4aff23ac`；Owner 指令日期为 2026-11-02（Asia/Shanghai，日精度）。

本记录来自本任务中的正式 Owner 指令。D02/D03/D06 已批准业务边界；这不授予全部文件自动发布许可，也不授权 P35 上传。

| 决定 | 正式 Owner 声明 | 状态 |
| --- | --- | --- |
| D02 | 真实基地、分场、加工厂及其精确对应关系不进入独立公开交付包。通用程序与 Schema 可以公开。 | OWNER_APPROVED |
| D03 | 真实产量、面积、逐日曲线及经营统计不进入独立公开交付包。演示使用独立生成的合成数据。 | OWNER_APPROVED |
| D06 | 历史研究原件及 Hash 保持不变。独立公开交付仅包含经过逐文件确认的技术内容及合成材料。 | OWNER_APPROVED |

机器记录：[owner-decisions.json](owner-decisions.json)。本记录按 R1 新增，不覆盖旧记录。

## 旧记录与新决定

原 F/D 文档及此前本地审核中的 PENDING/待确认状态，是当时的真实快照，原文和 Hash 均保留。
本记录只从本任务起明确三项业务边界，不把旧审核结果回写成当时已批准，也不迁移公开增量基线。
[旧记录身份索引](prior-review-index.json)保存原本地材料的逻辑定位、大小及 Hash；不复制其中数据或本机私有路径。

## 本轮的边界

允许新增决策/审核材料、只读复核固定 P35、提交这些材料并创建独立 Draft PR。
原仓库继续 Public；PR #783、23 个 Tag、23 个 Release、原模型、历史数据及冻结证据保持不变。
不重建或上传 P35，不创建新远端，不改写历史，不自动 Ready/Merge/Release/Deploy。
P35 仍绑定原 SHA256，不因三项 APPROVED 标签或本 PR 的绿色 CI 自动获得发布许可。

逐文件准入结论见 [P35 审核](p35-review.md)。`P35_PUBLICATION_AUTHORIZED=false`；历史处置未执行。
