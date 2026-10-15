# S5 前端依赖安全审计 R1

审计对象：基线 `89641834ab7a0bd902a23f9243325da5c163d518` 的原锁文件。
执行 npm ci、npm audit --json、npm audit --omit=dev --json、npm explain 和
静态构建产物检查；原始 JSON 与来源 SHA256 见新 S5 evidence。**没有升级依赖**。
当前完整安装仍报告 7 个受影响包（5 high、2 moderate）；只审生产依赖报告
1 个 high（react-router）。这不是 7 个独立漏洞，也不是零风险证明。

| 包 / 实际版本 | 范围 / 链路 | 公告与修复候选 | 当前运行可达性和措施 |
| --- | --- | --- | --- |
| react-router 7.18.1 | 生产直接依赖；React SPA | GHSA-qwww-vcr4-c8h2；>=7.18.2，npm 建议7.18.4 | 公告限定 unstable RSC APIs。本仓库是 BrowserRouter/Routes + Vite static build，没有 RSC server/action；源码和 build 无 RSC server handler。当前该漏洞触发面未发现；未来启用 SSR/RSC 必须先修复与复审 |
| brace-expansion 5.0.9 | eslint → config-array → minimatch，开发工具 | GHSA-q2hr-2g5m-vwhr / GHSA-qhr7-859c-m2p7 / GHSA-6j4f-fj2g-mc7p；>=5.0.12 覆盖本次告警 | 不在浏览器 production dependencies；嵌套不可信 glob 可影响工具。禁止将工具公开为服务，后续最小锁更新建议 |
| nanoid 3.3.16 | Vite → postcss，构建依赖 | GHSA-2v37-7h3g-55p8；>=3.3.18 | 特定 custom generator + size=0；不在生产依赖树。当前 build 使用受控源码，不是任意生成服务；升级待独立范围 |
| source-map-js 1.2.1 | postcss/jsdom 间接工具依赖 | GHSA-68fv-2mgg-jv7q；>=1.2.2 | 不可信 indexed source map offsets 引发 DoS；静态产品不提供此解析服务，CI/build 仍需修复治理 |
| undici 8.9.0 | jsdom 间接开发依赖 | GHSA-3wwx-pv8p-q78v、GHSA-pmjh-fq2x-6v4x、GHSA-r53p-7pc4-xj5r、GHSA-rfgv-xxqx-mfg5、GHSA-3xpg-4rpp-hhhm、GHSA-2jfj-6hjv-fm6j、GHSA-2gqq-gqf2-x968、GHSA-w293-vg96-wgc3、GHSA-8436-99hf-9mmv、GHSA-rx4f-c7p8-82vq；>=8.10.2 | Node HTTP/WebSocket/cache/TLS 特定路径；不在静态浏览器运行依赖中。测试工具访问不可信网络仍有风险，不用此版本搭建代理服务 |
| @vitest/mocker 4.1.10 | Vitest 间接开发依赖 | GHSA-82fw-gwwq-j7x9；>=4.1.11 | mock redirect 路径穿越，工具服务暴露或不可信测试代码时有风险。测试仅受控代码/loopback，禁止公网 Vitest |
| vitest 4.1.10 | 直接测试工具 | GHSA-82fw-gwwq-j7x9；>=4.1.11 | 同上；不能因仅为 dev 就忽略工具链风险 |

原始 npm 输出中的每条 advisory（含 severity/range/url）是证据索引，不以本表
代替漏洞库扫描，也不自动宣称补丁兼容。主要公告核验：
[React Router 官方安全公告](https://github.com/remix-run/react-router/security/advisories/GHSA-qwww-vcr4-c8h2)、
[Vitest 公告](https://github.com/advisories/GHSA-82fw-gwwq-j7x9)、
[undici TLS 公告](https://github.com/advisories/GHSA-w293-vg96-wgc3)。

## 结论与剩余风险

`DEPENDENCY_SECURITY_AUDIT=COMPLETED_WITH_OPEN_ADVISORIES`。
`PRODUCTION_REACHABLE_HIGH_RISK=NOT_IDENTIFIED_IN_CURRENT_STATIC_SPA_SCOPE`，不是
依赖无漏洞或未来部署安全承诺；当前 formal pilot/production 均未部署。
以现有入口/构建代码和公告触发条件作范围判断，不以 CI 绿色、仅包名或计数代替。

最小后续修复建议：react-router补丁、vitest补丁及四个间接依赖锁内兼容更新，
逐项验证解析关系、锁文件、unit/build/browser 与新审计；不得 npm audit fix --force。
这涉及冻结前端依赖，不在本轮 S5 test-only/config/runbook 范围，因此本 PR 不修改
package.json/package-lock，也不写成已闭合。若启用 RSC、公开开发服务器、接入
不可信构建输入，以上可达性前提失效，应标为试运行 BLOCKED 并另行最小修复授权。
