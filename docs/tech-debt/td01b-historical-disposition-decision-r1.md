# TD-01B：供 Owner 决定的历史处置顺序

本文件是决策建议，未授权也未执行可见性修改、历史重写、强推、Tag/Release
删除或重签发。本轮 Draft PR 只保护未来 Tree/归档/打包。

## 先确认公开许可，再决定控制范围

数据责任人应针对两个精确 Blob 分别确认公开许可的主体、范围、时间、条件及
可核验来源。保管或研究授权不能代替公开许可。若确有有效公开许可，可在新版本
记录中关联原对象与证据；不改原件、不回填历史批准时间，也不因此自动解除现有
防再引入保护。许可尚缺或不允许公开时，应决定临时限制访问和完整历史处置。

| 可选动作 | 能达到的效果 | 无法达到的效果 / 影响 |
| --- | --- | --- |
| 普通提交取消追踪和添加防护 | 新 Tree、未来源码归档及标准包不再带两个文件 | 不改变祖先、23 个 Tag 或23 个 Release 的源码引用 |
| 临时 Private（需 Owner 单独批准） | 限制随后匿名读取该仓库 | 不撤回既往克隆/下载；公开 Fork 仍公开并脱离网络；需检查协作者、集成、Pages、Actions/计划资格和发布访问 |
| 完整历史清除（需另行精确授权） | 在所有受控 Ref 中移除目标对象的可达引用 | 改写引入点及其后代 Commit/Tree；23 个 Tag/Release 目标、签名、PR、固定 SHA 合同需协调，不能单靠普通提交完成 |

可见性变化的 Fork/功能影响见 [GitHub 官方说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)。
账户计划及组织策略未在本轮核验，不能预先承诺功能不受影响。

## 历史清除必须先解决的兼容性约束

当前 main 虽无工作簿，仍继承引入历史；清除这些祖先会改变 main 及大量公开分支的
Commit ID。开发前快照共有 742 个 Branch/Tag 可达引入提交，709 个 Branch 的当前
Tree、全部23个 Tag 仍含文件。23个 Release 的独立 assets 为0，但其源码目标仍受影响。

当前代码有真实固定身份依赖，不能直接重写后改 expected Hash 让测试变绿：

- `.github/workflows/ci.yml` 与 `backend/tests/historical_source.py` 要求固定提交
  `320f2046e3105b1b55da9cb037892571110b584a` 的历史源码存在。
- `backend/tests/local_auth/test_runtime_evidence_contract.py` 还核对
  `e9812e82067dceae444ff0707ceeb2f560c1018e` 的历史合同。
- `backend/tests/td03g_historical_source.py` 使用基线
  `0124371b433d1b3c34e5e59a2a9a5e621a570f3b`；其他 V0.18/V0.19 证据也保留
  历史源码、Git SHA、Blob/内容 Hash 绑定。

源码正文不变时，其 Blob/内容 Hash 可保持；祖先和 Tree 改变后，Commit SHA 不会
保持。已有注释 Tag 对象及签名、Release 指向、PR 差异和历史部署/复算定位可能失效。
仅为使 CI 通过而保留受影响旧 Commit 在公共 Ref 中可达，会继续保留业务 Blob，
与完整清除目标矛盾。

因此执行前必须单独授权并审查**历史源码定位的版本化兼容迁移**：只保留获准的
源码历史字节，验证原内容 Hash 和安全断言不变，建立旧身份至新干净定位的明确映射；
旧证据的事实与 Hash 不覆盖。若合同不允许这种迁移，历史改写处置保持 BLOCKED。
本任务没有实施此迁移，也没有改写冻结合同。

## 如获授权，建议分步操作及停止条件

1. Owner 先确认公开许可结论、临时访问限制及通知范围；必要时单独授权 Private。
   记录生效前 Ref/Release、协作者和必要自动化状态。不复制原始业务数据作为本轮证据。
2. 冻结写入与发布，协调所有开放 PR 和维护者。明确历史备份的保管人、加密位置、
   访问权限和保存期限；复制历史数据的权限须另行给出。本轮不创建此类备份。
3. 在获准的隔离副本上枚举全部分支、Tag、PR/缓存引用与附件。用批准工具做离线
   清除预演，形成旧→新 Commit/Tree/Tag 映射。发现额外对象或范围外变化即停止。
4. 对预演结果执行历史源码兼容迁移、全部合同、Golden、Canary、PostgreSQL、E2E
   及打包验证；检查部署/研究复算的固定 SHA 定位。任何授权、Hash、业务结果或
   覆盖变化无法解释时停止，不自动修改断言、删除证据或改用合成业务来源。
5. Owner 审核精确 Ref/Tag/Release 清单、不可逆影响、维护窗口及回滚方案后，再
   单独批准远端历史发布、强推及 Tag/Release 处理。没有这一步批准，不能发布预演结果。
6. 与 GitHub 协调可处理的缓存视图、PR 引用和对象回收；支持资格及是否清除由 GitHub
   判断，不能承诺本地改写即可撤回所有副本。协作者重新克隆，避免旧历史合回。
7. 远端重新枚举全部受控 Ref，验证目标 Blob 不再可达、预期源码身份与权限正确，
   执行最终 CI/源码归档/包验证并核对 Release。Fork、旧克隆、搜索缓存和既往下载
   分别登记，未验证项保持 UNKNOWN，不写“全网已清除”。

Git SHA/签名变化、重新污染、PR/缓存与第三方副本限制见
[GitHub 敏感数据清除说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。
这里引用的是处置机制，不把 `PUBLICATION_AUTHORITY_NOT_PROVEN` 等同于已确认泄露。

## 回滚与不可逆风险

普通防护提交可在新的审查提交中恢复配置，历史 Tag 无须改动；恢复业务文件追踪
仍须新的明确授权。Private 可在单独授权后恢复 Public，但已变化的 Fork 网络、
访问和下载结果不能靠切换保证还原。历史清除前的受控备份可用于私下恢复代码和
核对证据；把污染旧 Ref 重新公开会再次暴露对象，不能作为自动回滚。

曾被外部下载的副本无法由本仓库操作收回。只要来源许可、范围、兼容迁移、备份
权限或平台协同任一不确定，停止不可逆步骤并保留当前非破坏性保护。
本轮保持 `HISTORICAL_EXPOSURE_ELIMINATED=false`。
