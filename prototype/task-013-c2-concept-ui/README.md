# TASK-013 C2 Concept UI Prototype v1

## Purpose

本目录包含一个**完全隔离的静态网页 prototype**，用于：

- 展示 TASK-013 Slice C C2 的六类业务能力概念；
- 验证术语、信息层级和交互流程是否便于业务讨论；
- 收集 Charles 与业务方对能力定义、待确认维度与可能数据来源的反馈；
- 在不执行任何业务计算的前提下，让用户体验未来产品结构。

本 prototype 不会计算产能、人员、吨数、百分比、调度建议或可执行操作。

## Scope

只读 prototype 范围内包含：

- `index.html` — 单页面应用结构（4 个主视图 + 反馈视图 + 反馈抽屉）
- `styles.css` — 视觉样式（深灰蓝背景、蓝莓紫主色、青绿/琥珀状态色）
- `app.js` — 视图路由、localStorage 反馈持久化、JSON 导出
- `content.js` — 六类能力的内容数据
- `prototype-contract.json` — 静态合同（明确 production_data_connected=false 等开关）
- `README.md` — 本说明

## How to run

```bash
python -m http.server 4173 \
    --directory prototype/task-013-c2-concept-ui
```

随后在浏览器打开：

- 桌面访问：<http://127.0.0.1:4173/index.html>
- 移动模拟：在浏览器开发者工具中切换到 375 × 812 视口

无构建步骤，无运行时依赖，无网络请求。

## How to reset local feedback

进入 **业务反馈** 视图 → 点击右下角 **清空本地反馈** 按钮。

或直接在浏览器 DevTools 中执行：

```js
localStorage.removeItem("task013-c2-concept-ui-v1-feedback");
localStorage.removeItem("task013-c2-concept-ui-v1-peak-draft");
```

## How to export feedback

进入 **业务反馈** 视图 → 点击 **导出反馈 JSON** 按钮，浏览器将下载：

```json
{
  "prototype_version": "task-013-c2-concept-ui-v1",
  "exported_at": "<browser generated ISO datetime>",
  "capability_feedback": [],
  "general_feedback": "",
  "question_feedback": [
    {
      "question_id": "C2-PROTOTYPE-SUSTAINED-001",
      "capability_id": "SUSTAINED_PROCESSING_CAPACITY",
      "status": "",
      "comment": ""
    }
  ]
}
```

`question_feedback` 数组内每个对象对应 `content.js` 中以 `C2-PROTOTYPE-` 为前缀的 33 个 prototype-only 问题 ID 之一。这些 ID 不会与 v3 matrix 中已冻结的 decision ID 重叠。

## Non-production boundary

- 不连接生产数据库。
- 不调用任何后端 API。
- 不上传、POST、发送或同步任何数据到外部系统。
- 不使用 Cookie。
- 不启用 Service Worker。
- 不集成 analytics。
- 浏览器 localStorage 是反馈数据的**唯一**持久化位置。
- Content Security Policy 严格限制 `connect-src 'none'`。

## Known limitations

1. **不计算**任何业务结果：用户填入的峰值推演草稿不会触发判断。
2. **不实现**业务规则：没有公式、阈值、系数、人员效率、班次时间、距离阈值、调度优先级、品种间隔天数。
3. **不替代**业务确认：所有能力卡上的"业务定义 / 数据来源 / 单位 / 粒度 / 规则状态"均为 `待确认` / `未配置` / `不可执行`。
4. **不展示**模拟产能数字、模拟吨数、模拟百分比、模拟调度建议。
5. **不连接**实时数据：所有状态都是概念占位。
6. 反馈仅保留在用户浏览器中。换设备 / 换浏览器 / 清缓存 = 数据丢失。

## No-data / no-rule statement

This prototype is not a forecast, capacity calculator, staffing calculator,
dispatch optimizer, or production recommendation engine.

本 prototype 不预测、不计算产能、不计算人员、不优化调度、不生成任何生产建议。

## Status

| 治理项 | 状态 |
| --- | --- |
| C2 source definition | 未完成 |
| C2 design freeze | 未完成 |
| 生产系统接入 | 未授权 |
| Ready | 未授权 |
| Merge | 未授权 |
| C2 implementation | 未授权 |
| Slice D/E | 未授权 |
| TASK-014+ | 未授权 |

## Authority

- Issue: #99
- Prototype authorization comment: 4967834240
- Source contract baseline: `task-013-c2-business-source-definition-v1.md` (in /root/, **not in this repo**)
- v3 authority matrix: `task-013-slice-c-c2-authority-matrix-v3.json` (in /root/, **not in this repo**)
