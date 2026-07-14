/* TASK-013 C2 Concept UI Prototype v1 — app behavior */
/* This file makes no network requests of any kind. */
/* All feedback is stored in window.localStorage only. */

(function () {
    "use strict";

    var content = window.PROTOTYPE_CONTENT;
    if (!content) {
        return;
    }

    var STORAGE_KEY = content.storageKey;
    var DRAFT_STORAGE_KEY = content.draftStorageKey;
    var FEEDBACK_VIEW = "feedback";

    function loadFeedback() {
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) {
                return { capability_feedback: [], general_feedback: "" };
            }
            var parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
                return { capability_feedback: [], general_feedback: "" };
            }
            if (!Array.isArray(parsed.capability_feedback)) {
                parsed.capability_feedback = [];
            }
            if (typeof parsed.general_feedback !== "string") {
                parsed.general_feedback = "";
            }
            return parsed;
        } catch (err) {
            return { capability_feedback: [], general_feedback: "" };
        }
    }

    function saveFeedback(state) {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            return true;
        } catch (err) {
            return false;
        }
    }

    function clearFeedback() {
        try {
            window.localStorage.removeItem(STORAGE_KEY);
            return true;
        } catch (err) {
            return false;
        }
    }

    function loadDraft() {
        try {
            var raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (err) {
            return null;
        }
    }

    function saveDraft(draft) {
        try {
            window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
            return true;
        } catch (err) {
            return false;
        }
    }

    function clearDraft() {
        try {
            window.localStorage.removeItem(DRAFT_STORAGE_KEY);
            return true;
        } catch (err) {
            return false;
        }
    }

    /* ---- View routing ---- */
    function switchView(targetView) {
        var tabs = document.querySelectorAll(".nav-tab");
        tabs.forEach(function (tab) {
            var isActive = tab.getAttribute("data-view") === targetView;
            tab.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
        var panels = document.querySelectorAll("[data-view-panel]");
        panels.forEach(function (panel) {
            var isActive = panel.getAttribute("data-view-panel") === targetView;
            if (isActive) {
                panel.removeAttribute("hidden");
                panel.setAttribute("aria-hidden", "false");
            } else {
                panel.setAttribute("hidden", "hidden");
                panel.setAttribute("aria-hidden", "true");
            }
        });
        if (targetView === FEEDBACK_VIEW) {
            closeDrawer();
        }
        if (targetView === "peak") {
            hydratePeakDraft();
        }
        if (targetView === "feedback") {
            hydrateFeedbackForm();
        }
    }

    /* ---- Overview rendering ---- */
    function renderOverview() {
        var grid = document.getElementById("overview-grid");
        if (!grid) {
            return;
        }
        grid.textContent = "";
        content.capabilities.forEach(function (cap) {
            var card = document.createElement("article");
            card.className = "capability-card";
            card.setAttribute("role", "listitem");
            card.setAttribute("data-capability-id", cap.id);

            var h3 = document.createElement("h3");
            h3.textContent = cap.name;
            card.appendChild(h3);

            var metaList = document.createElement("ul");
            metaList.className = "capability-meta";
            Object.keys(cap.meta).forEach(function (key) {
                var li = document.createElement("li");
                var labelSpan = document.createElement("span");
                labelSpan.className = "meta-label";
                labelSpan.textContent = key;
                var valueSpan = document.createElement("span");
                valueSpan.className = "meta-value";
                valueSpan.textContent = cap.meta[key];
                li.appendChild(labelSpan);
                li.appendChild(valueSpan);
                metaList.appendChild(li);
            });
            card.appendChild(metaList);

            var pill = document.createElement("span");
            pill.className = "status-pill status-pill-pending";
            pill.textContent = cap.status;
            card.appendChild(pill);

            var actions = document.createElement("div");
            actions.className = "capability-actions";

            var viewQuestionsBtn = document.createElement("button");
            viewQuestionsBtn.type = "button";
            viewQuestionsBtn.className = "btn btn-secondary";
            viewQuestionsBtn.textContent = "查看待确认问题";
            viewQuestionsBtn.addEventListener("click", function () {
                showCapabilityQuestions(cap);
            });
            actions.appendChild(viewQuestionsBtn);

            var recordFeedbackBtn = document.createElement("button");
            recordFeedbackBtn.type = "button";
            recordFeedbackBtn.className = "btn btn-primary";
            recordFeedbackBtn.textContent = "记录反馈";
            recordFeedbackBtn.addEventListener("click", function () {
                switchView(FEEDBACK_VIEW);
            });
            actions.appendChild(recordFeedbackBtn);

            card.appendChild(actions);
            grid.appendChild(card);
        });
    }

    function showCapabilityQuestions(cap) {
        var questions = {
            "SUSTAINED_PROCESSING_CAPACITY": [
                "持续加工能力的业务定义是什么？",
                "时间粒度是日 / 周 / 旬 / 月？",
                "位置粒度是工厂 / 产线 / 班组？",
                "是否受品种影响？",
                "是否纳入设备约束？",
                "是否纳入人员约束？",
                "是否纳入冷库约束？"
            ],
            "RECEIVING_PEAK_CAPACITY": [
                "峰值接收能力 = 到达能力 / 加工能力 / 缓冲能力 / 冷库接收能力？",
                "四者是否分别定义？",
                "峰值定义：绝对峰值 / 滚动窗口 / 持续时段？",
                "统计窗口是日 / 时段 / 周？",
                "数据来源：现场统计 / 业务记录 / 外部系统？",
                "是否包含异常峰值？"
            ],
            "SHIFT_STAFFING": [
                "人员数据来源：HR 系统 / 生产排班 / 现场统计？",
                "覆盖范围：单班 / 全天 / 全周？",
                "是否区分岗位技能？",
                "人员效率如何度量？",
                "缺勤因素如何纳入？"
            ],
            "SPRING_FESTIVAL_STAFFING": [
                "节假日日历来源：国家公告 / 企业内部？",
                "春节期间人员可用性如何度量？",
                "班次是否变化？",
                "生产计划是否调整？",
                "采摘与运输是否影响？"
            ],
            "VARIETY_STAGGER": [
                "品种错峰 = 自然成熟时间差 / 采摘计划错峰 / 加工计划错峰？",
                "三者是否可混用？",
                "统计口径：日 / 周 / 旬？",
                "地点口径：单厂 / 跨厂？",
                "品种口径：单一 / 多品种组合？"
            ],
            "CROSS_PLANT_DISPATCH": [
                "目标函数：降低加工峰值 / 降低运输 / 提高设备利用率 / 降低人员压力？",
                "约束：产能 / 距离 / 冷链 / 品种 / 订单 / 设备？",
                "候选工厂是否已确定？",
                "选择规则是否已确定？",
                "成本与优先级是否纳入？"
            ]
        };
        var list = questions[cap.id] || ["该能力的待确认问题列表尚未配置。"];
        var message = cap.name + " — 待确认问题：\n\n" + list.map(function (q) { return "• " + q; }).join("\n");
        window.alert(message);
    }

    /* ---- Peak draft ---- */
    function hydratePeakDraft() {
        var draft = loadDraft();
        if (!draft) {
            return;
        }
        var fields = ["peak-location", "peak-window", "peak-arrival", "peak-receiving", "peak-processing", "peak-buffer"];
        fields.forEach(function (id) {
            var el = document.getElementById(id);
            if (el && typeof draft[id] === "string") {
                el.value = draft[id];
            }
        });
    }

    function collectPeakDraft() {
        var fields = ["peak-location", "peak-window", "peak-arrival", "peak-receiving", "peak-processing", "peak-buffer"];
        var draft = {};
        fields.forEach(function (id) {
            var el = document.getElementById(id);
            draft[id] = el ? el.value : "";
        });
        return draft;
    }

    function bindPeakForm() {
        var saveBtn = document.getElementById("peak-save-draft");
        var form = document.getElementById("peak-form");
        if (!saveBtn || !form) {
            return;
        }
        saveBtn.addEventListener("click", function () {
            var ok = saveDraft(collectPeakDraft());
            var msg = document.getElementById("feedback-status");
            if (msg) {
                msg.textContent = ok ? "草稿已保存到 localStorage。" : "草稿保存失败：localStorage 不可用。";
                msg.className = "feedback-status " + (ok ? "success" : "error");
            }
        });
        form.addEventListener("reset", function () {
            clearDraft();
        });
    }

    /* ---- Feedback view ---- */
    function renderFeedbackCapabilityList() {
        var list = document.getElementById("feedback-capability-list");
        if (!list) {
            return;
        }
        list.textContent = "";
        content.capabilities.forEach(function (cap) {
            var section = document.createElement("article");
            section.className = "feedback-capability";
            section.setAttribute("data-capability-id", cap.id);

            var h3 = document.createElement("h3");
            h3.className = "panel-title";
            h3.textContent = cap.name;
            section.appendChild(h3);

            var statusGroup = document.createElement("div");
            statusGroup.className = "feedback-status-group";
            statusGroup.setAttribute("role", "group");
            statusGroup.setAttribute("aria-label", "对 " + cap.name + " 的理解状态");
            content.feedbackStatusOptions.forEach(function (opt) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "btn";
                btn.setAttribute("data-status-value", opt.value);
                btn.setAttribute("aria-pressed", "false");
                btn.textContent = opt.label;
                btn.addEventListener("click", function () {
                    var siblings = statusGroup.querySelectorAll("button");
                    siblings.forEach(function (sib) { sib.setAttribute("aria-pressed", "false"); });
                    btn.setAttribute("aria-pressed", "true");
                });
                statusGroup.appendChild(btn);
            });
            section.appendChild(statusGroup);

            var fields = [
                { id: "understanding", label: "我的理解" },
                { id: "definition_change", label: "需要修改的定义" },
                { id: "possible_source", label: "可能的数据来源" },
                { id: "extra_notes", label: "补充说明" }
            ];
            fields.forEach(function (f) {
                var grp = document.createElement("div");
                grp.className = "feedback-textarea-group";
                var lbl = document.createElement("label");
                lbl.setAttribute("for", "fb-" + cap.id + "-" + f.id);
                lbl.textContent = f.label;
                var ta = document.createElement("textarea");
                ta.id = "fb-" + cap.id + "-" + f.id;
                ta.name = "fb-" + cap.id + "-" + f.id;
                ta.rows = 2;
                ta.setAttribute("data-feedback-field", f.id);
                grp.appendChild(lbl);
                grp.appendChild(ta);
                section.appendChild(grp);
            });

            list.appendChild(section);
        });
    }

    function hydrateFeedbackForm() {
        var state = loadFeedback();
        var perCap = {};
        state.capability_feedback.forEach(function (entry) {
            if (entry && entry.capability_id) {
                perCap[entry.capability_id] = entry;
            }
        });
        content.capabilities.forEach(function (cap) {
            var section = document.querySelector(".feedback-capability[data-capability-id=\"" + cap.id + "\"]");
            if (!section) {
                return;
            }
            var entry = perCap[cap.id] || {};
            var statusVal = entry.status || "";
            var statusBtns = section.querySelectorAll(".feedback-status-group button");
            statusBtns.forEach(function (btn) {
                var matches = btn.getAttribute("data-status-value") === statusVal;
                btn.setAttribute("aria-pressed", matches ? "true" : "false");
            });
            section.querySelectorAll("textarea[data-feedback-field]").forEach(function (ta) {
                var field = ta.getAttribute("data-feedback-field");
                ta.value = (entry[field] && typeof entry[field] === "string") ? entry[field] : "";
            });
        });
        var general = document.getElementById("general-feedback");
        if (general) {
            general.value = state.general_feedback || "";
        }
    }

    function collectFeedbackFromForm() {
        var perCap = [];
        content.capabilities.forEach(function (cap) {
            var section = document.querySelector(".feedback-capability[data-capability-id=\"" + cap.id + "\"]");
            if (!section) {
                return;
            }
            var statusVal = "";
            var activeBtn = section.querySelector(".feedback-status-group button[aria-pressed=\"true\"]");
            if (activeBtn) {
                statusVal = activeBtn.getAttribute("data-status-value") || "";
            }
            var entry = { capability_id: cap.id, capability_name: cap.name, status: statusVal };
            section.querySelectorAll("textarea[data-feedback-field]").forEach(function (ta) {
                entry[ta.getAttribute("data-feedback-field")] = ta.value;
            });
            perCap.push(entry);
        });
        var general = document.getElementById("general-feedback");
        return {
            capability_feedback: perCap,
            general_feedback: general ? general.value : ""
        };
    }

    function bindFeedbackActions() {
        var saveBtn = document.getElementById("feedback-save");
        var exportBtn = document.getElementById("feedback-export");
        var clearBtn = document.getElementById("feedback-clear");
        var status = document.getElementById("feedback-status");
        function setStatus(text, cls) {
            if (status) {
                status.textContent = text;
                status.className = "feedback-status" + (cls ? " " + cls : "");
            }
        }
        if (saveBtn) {
            saveBtn.addEventListener("click", function () {
                var state = collectFeedbackFromForm();
                var ok = saveFeedback(state);
                setStatus(ok ? "反馈已保存到 localStorage。" : "反馈保存失败：localStorage 不可用。", ok ? "success" : "error");
            });
        }
        if (exportBtn) {
            exportBtn.addEventListener("click", function () {
                var state = collectFeedbackFromForm();
                var exportObj = {
                    prototype_version: content.prototypeVersion,
                    exported_at: new Date().toISOString(),
                    capability_feedback: state.capability_feedback,
                    general_feedback: state.general_feedback
                };
                var json = JSON.stringify(exportObj, null, 2);
                try {
                    var blob = new Blob([json], { type: "application/json" });
                    var url = window.URL.createObjectURL(blob);
                    var a = document.createElement("a");
                    a.href = url;
                    a.download = content.prototypeVersion + "-feedback.json";
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                    setStatus("反馈 JSON 已开始下载。", "success");
                } catch (err) {
                    setStatus("反馈 JSON 导出失败：浏览器不支持 Blob 下载。", "error");
                }
            });
        }
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                var ok = clearFeedback();
                hydrateFeedbackForm();
                setStatus(ok ? "本地反馈已清空。" : "本地反馈清空失败。", ok ? "success" : "error");
            });
        }
    }

    /* ---- Drawer ---- */
    function openDrawer() {
        var drawer = document.getElementById("feedback-drawer");
        var toggle = document.getElementById("feedback-drawer-toggle");
        if (drawer) {
            drawer.removeAttribute("hidden");
        }
        if (toggle) {
            toggle.setAttribute("aria-expanded", "true");
        }
    }
    function closeDrawer() {
        var drawer = document.getElementById("feedback-drawer");
        var toggle = document.getElementById("feedback-drawer-toggle");
        if (drawer) {
            drawer.setAttribute("hidden", "hidden");
        }
        if (toggle) {
            toggle.setAttribute("aria-expanded", "false");
        }
    }
    function bindDrawer() {
        var toggle = document.getElementById("feedback-drawer-toggle");
        var closeBtn = document.getElementById("drawer-close");
        var gotoBtn = document.getElementById("drawer-goto");
        if (toggle) {
            toggle.addEventListener("click", function () {
                var drawer = document.getElementById("feedback-drawer");
                if (drawer && drawer.hasAttribute("hidden")) {
                    openDrawer();
                } else {
                    closeDrawer();
                }
            });
        }
        if (closeBtn) {
            closeBtn.addEventListener("click", closeDrawer);
        }
        if (gotoBtn) {
            gotoBtn.addEventListener("click", function () {
                switchView(FEEDBACK_VIEW);
            });
        }
    }

    /* ---- Nav binding ---- */
    function bindNav() {
        var tabs = document.querySelectorAll(".nav-tab");
        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                var target = tab.getAttribute("data-view");
                if (target) {
                    switchView(target);
                }
            });
        });
    }

    /* ---- Init ---- */
    function init() {
        bindNav();
        renderOverview();
        bindPeakForm();
        renderFeedbackCapabilityList();
        bindFeedbackActions();
        bindDrawer();
        switchView("overview");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
