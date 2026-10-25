# V0_20 S3 — 合成业务验收

## 可复现步骤

环境复用项目锁定的 Python3.12、Node22、PostgreSQL16 与原 HTTPS/ASGI 业务fixture。新 runner 只定点创建/停止自己的 SYNTHETIC PG/TLS 资源；农事准备自身不调用后端，不写数据库。

```sh
python -m backend.tests.agronomic_history.v0_20_assets
python -m pytest -q backend/tests/agronomic_history
cd frontend
npx prettier --write 'src/dashboard/agronomic/*.json'
npm run typecheck
npm run lint
npm run format:check
npm run test:unit -- --run
```

生成器确定固定工作簿原字节和语义内容；仓库JSON排版随后使用锁定版本Prettier。排版不参与工作簿Hash或规范化词汇Hash；一致性测试比较JSON内容和每个原字节来源身份。

完整业务回归（从仓库根运行，输出目录必须全新）：

```sh
python -m backend.tests.agronomic_history.run_v0_20 \
  --output /tmp/SYNTHETIC-v0-20-business-acceptance --browser
```

runner复用已有PG保存/重载、实际业务ASGI、TLS MCP和Dashboard登录。覆盖新农事PC/手机流程及旧电子表格预测、滚动预测和原业务流；不读取真实采收或农事文件。

## 业务样例

公开fixture包含两个合成产季2023–2024和2024–2025、两个基地来源、两个品种、三个来源地块、明确的常绿/落叶促早制度。注册表三种制度全部保留，负向测试拒绝自然落叶制度下不在V0.9适用范围的加温声明，不擅自改变制度。宽表与长表分别真实生成/解析XLSX后得到18条面积、36条管理事件、36条物候，共90条；每季45条。CSV长表演示同样18条面积。合成参考仅为合成连接，地块权威仍null，模型准入0。

负面样例保留：未知促早方式、多次剪枝与重复修订、种植/投产面积矛盾、面积有效期重叠、来源地块未匹配、月精度开花记录、计划操作混有实际观测时间。规范化、JSON/CSV/HTML均保留原因，不自动删记录、补零、选Winner或预测农艺效果。

浏览器验收会下载全部五文件，验证实际字节Hash、相同输入重做版本一致、修改映射旧结果失效、显式旧版本不变、清空/退出移除数据；监听请求证明本地流程没有POST。测试附件包含桌面/手机的映射、总体、冲突与人工CSV画面及五文件。

新增单测先记录失败再修正实现，覆盖修订循环/分叉、分来源物候顺序、null与零、时间逆序、映射边界、合成重标记拒绝、HTML/CSV安全和ZIP逐文件校验。现有预测合成数值由原回归验证，本版不计算新模型结果。

实际检查命令和GitHub最终HEAD CI结果见PR验收回执；本文件不预填尚未运行的绿色结论。工程Draft交付通过仍不代表独立复审完成或合并后main CI通过。
