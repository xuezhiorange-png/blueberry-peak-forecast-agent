/* TASK-013 C2 Concept UI Prototype v1 — capability content + question catalog */
/* No business numbers, thresholds, formulas, or production data are encoded. */
/* All values are explicit placeholders reflecting unconfirmed business sources. */
/* All question IDs use independent prototype-only prefix C2-PROTOTYPE-* and do NOT */
/* collide with v3 matrix decision IDs. */

window.PROTOTYPE_CONTENT = (function () {
    "use strict";

    var capabilities = [
        {
            id: "SUSTAINED_PROCESSING_CAPACITY",
            name: "持续加工能力",
            status: "待业务来源确认",
            meta: {
                "业务定义": "待确认",
                "数据来源": "未配置",
                "单位": "待确认",
                "时间粒度": "待确认",
                "位置粒度": "待确认",
                "品种粒度": "待确认",
                "规则状态": "不可执行"
            }
        },
        {
            id: "RECEIVING_PEAK_CAPACITY",
            name: "峰值接收能力",
            status: "待业务来源确认",
            meta: {
                "业务定义": "待确认",
                "数据来源": "未配置",
                "单位": "待确认",
                "时间粒度": "待确认",
                "位置粒度": "待确认",
                "品种粒度": "待确认",
                "规则状态": "不可执行"
            }
        },
        {
            id: "SHIFT_STAFFING",
            name: "班次人员能力",
            status: "待业务来源确认",
            meta: {
                "业务定义": "待确认",
                "数据来源": "未配置",
                "单位": "待确认",
                "时间粒度": "待确认",
                "位置粒度": "待确认",
                "品种粒度": "待确认",
                "规则状态": "不可执行"
            }
        },
        {
            id: "SPRING_FESTIVAL_STAFFING",
            name: "春节人员能力",
            status: "待业务来源确认",
            meta: {
                "业务定义": "待确认",
                "数据来源": "未配置",
                "单位": "待确认",
                "时间粒度": "待确认",
                "位置粒度": "待确认",
                "品种粒度": "待确认",
                "规则状态": "不可执行"
            }
        },
        {
            id: "VARIETY_STAGGER",
            name: "品种错峰",
            status: "待业务来源确认",
            meta: {
                "业务定义": "待确认",
                "数据来源": "未配置",
                "单位": "待确认",
                "时间粒度": "待确认",
                "位置粒度": "待确认",
                "品种粒度": "待确认",
                "规则状态": "不可执行"
            }
        },
        {
            id: "CROSS_PLANT_DISPATCH",
            name: "跨厂调度",
            status: "待业务来源确认",
            meta: {
                "业务定义": "待确认",
                "数据来源": "未配置",
                "单位": "待确认",
                "时间粒度": "待确认",
                "位置粒度": "待确认",
                "品种粒度": "待确认",
                "规则状态": "不可执行"
            }
        }
    ];

    var questions = [
        { id: "C2-PROTOTYPE-SUSTAINED-001", capability_id: "SUSTAINED_PROCESSING_CAPACITY", text: "持续加工能力的业务定义是什么？" },
        { id: "C2-PROTOTYPE-SUSTAINED-002", capability_id: "SUSTAINED_PROCESSING_CAPACITY", text: "时间粒度是日 / 周 / 旬 / 月？" },
        { id: "C2-PROTOTYPE-SUSTAINED-003", capability_id: "SUSTAINED_PROCESSING_CAPACITY", text: "位置粒度是工厂 / 产线 / 班组？" },
        { id: "C2-PROTOTYPE-SUSTAINED-004", capability_id: "SUSTAINED_PROCESSING_CAPACITY", text: "是否受品种影响？" },
        { id: "C2-PROTOTYPE-SUSTAINED-005", capability_id: "SUSTAINED_PROCESSING_CAPACITY", text: "是否纳入设备约束？" },
        { id: "C2-PROTOTYPE-SUSTAINED-006", capability_id: "SUSTAINED_PROCESSING_CAPACITY", text: "是否纳入人员约束？" },
        { id: "C2-PROTOTYPE-SUSTAINED-007", capability_id: "SUSTAINED_PROCESSING_CAPACITY", text: "是否纳入冷库约束？" },

        { id: "C2-PROTOTYPE-RECEIVING-001", capability_id: "RECEIVING_PEAK_CAPACITY", text: "峰值接收能力 = 到达能力 / 加工能力 / 缓冲能力 / 冷库接收能力？" },
        { id: "C2-PROTOTYPE-RECEIVING-002", capability_id: "RECEIVING_PEAK_CAPACITY", text: "四者是否分别定义？" },
        { id: "C2-PROTOTYPE-RECEIVING-003", capability_id: "RECEIVING_PEAK_CAPACITY", text: "峰值定义：绝对峰值 / 滚动窗口 / 持续时段？" },
        { id: "C2-PROTOTYPE-RECEIVING-004", capability_id: "RECEIVING_PEAK_CAPACITY", text: "统计窗口是日 / 时段 / 周？" },
        { id: "C2-PROTOTYPE-RECEIVING-005", capability_id: "RECEIVING_PEAK_CAPACITY", text: "数据来源：现场统计 / 业务记录 / 外部系统？" },
        { id: "C2-PROTOTYPE-RECEIVING-006", capability_id: "RECEIVING_PEAK_CAPACITY", text: "是否包含异常峰值？" },

        { id: "C2-PROTOTYPE-SHIFT-001", capability_id: "SHIFT_STAFFING", text: "人员数据来源：HR 系统 / 生产排班 / 现场统计？" },
        { id: "C2-PROTOTYPE-SHIFT-002", capability_id: "SHIFT_STAFFING", text: "覆盖范围：单班 / 全天 / 全周？" },
        { id: "C2-PROTOTYPE-SHIFT-003", capability_id: "SHIFT_STAFFING", text: "是否区分岗位技能？" },
        { id: "C2-PROTOTYPE-SHIFT-004", capability_id: "SHIFT_STAFFING", text: "人员效率如何度量？" },
        { id: "C2-PROTOTYPE-SHIFT-005", capability_id: "SHIFT_STAFFING", text: "缺勤因素如何纳入？" },

        { id: "C2-PROTOTYPE-SPRING-001", capability_id: "SPRING_FESTIVAL_STAFFING", text: "节假日日历来源：国家公告 / 企业内部？" },
        { id: "C2-PROTOTYPE-SPRING-002", capability_id: "SPRING_FESTIVAL_STAFFING", text: "春节期间人员可用性如何度量？" },
        { id: "C2-PROTOTYPE-SPRING-003", capability_id: "SPRING_FESTIVAL_STAFFING", text: "班次是否变化？" },
        { id: "C2-PROTOTYPE-SPRING-004", capability_id: "SPRING_FESTIVAL_STAFFING", text: "生产计划是否调整？" },
        { id: "C2-PROTOTYPE-SPRING-005", capability_id: "SPRING_FESTIVAL_STAFFING", text: "采摘与运输是否影响？" },

        { id: "C2-PROTOTYPE-VARIETY-001", capability_id: "VARIETY_STAGGER", text: "品种错峰 = 自然成熟时间差 / 采摘计划错峰 / 加工计划错峰？" },
        { id: "C2-PROTOTYPE-VARIETY-002", capability_id: "VARIETY_STAGGER", text: "三者是否可混用？" },
        { id: "C2-PROTOTYPE-VARIETY-003", capability_id: "VARIETY_STAGGER", text: "统计口径：日 / 周 / 旬？" },
        { id: "C2-PROTOTYPE-VARIETY-004", capability_id: "VARIETY_STAGGER", text: "地点口径：单厂 / 跨厂？" },
        { id: "C2-PROTOTYPE-VARIETY-005", capability_id: "VARIETY_STAGGER", text: "品种口径：单一 / 多品种组合？" },

        { id: "C2-PROTOTYPE-DISPATCH-001", capability_id: "CROSS_PLANT_DISPATCH", text: "目标函数：降低加工峰值 / 降低运输 / 提高设备利用率 / 降低人员压力？" },
        { id: "C2-PROTOTYPE-DISPATCH-002", capability_id: "CROSS_PLANT_DISPATCH", text: "约束：产能 / 距离 / 冷链 / 品种 / 订单 / 设备？" },
        { id: "C2-PROTOTYPE-DISPATCH-003", capability_id: "CROSS_PLANT_DISPATCH", text: "候选工厂是否已确定？" },
        { id: "C2-PROTOTYPE-DISPATCH-004", capability_id: "CROSS_PLANT_DISPATCH", text: "选择规则是否已确定？" },
        { id: "C2-PROTOTYPE-DISPATCH-005", capability_id: "CROSS_PLANT_DISPATCH", text: "成本与优先级是否纳入？" }
    ];

    var feedbackStatusOptions = [
        { value: "understood", label: "理解正确" },
        { value: "needs_adjustment", label: "需要调整" },
        { value: "not_applicable", label: "不适用" },
        { value: "unsure", label: "尚不确定" }
    ];

    return {
        prototypeVersion: "task-013-c2-concept-ui-v1",
        capabilities: capabilities,
        questions: questions,
        feedbackStatusOptions: feedbackStatusOptions,
        storageKey: "task013-c2-concept-ui-v1-feedback",
        draftStorageKey: "task013-c2-concept-ui-v1-peak-draft"
    };
}());
