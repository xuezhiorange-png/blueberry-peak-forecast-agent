/* TASK-013 C2 Concept UI Prototype v1 — capability content */
/* No business numbers, thresholds, formulas, or production data are encoded. */
/* All values are explicit placeholders reflecting unconfirmed business sources. */

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

    var feedbackStatusOptions = [
        { value: "understood", label: "理解正确" },
        { value: "needs_adjustment", label: "需要调整" },
        { value: "not_applicable", label: "不适用" },
        { value: "unsure", label: "尚不确定" }
    ];

    return {
        prototypeVersion: "task-013-c2-concept-ui-v1",
        capabilities: capabilities,
        feedbackStatusOptions: feedbackStatusOptions,
        storageKey: "task013-c2-concept-ui-v1-feedback",
        draftStorageKey: "task013-c2-concept-ui-v1-peak-draft"
    };
}());
