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
    var PENDING_TRIGGER = null; // last button that opened the question dialog, for focus return
    if (typeof window !== "undefined") {
        window.__PROTOTYPE_DEBUG__ = {
            getPendingTrigger: function () { return PENDING_TRIGGER; }
        };
    }

    /* ---- Storage helpers ---- */
    function loadFeedback() {
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) {
                return {
                    capability_feedback: [],
                    general_feedback: "",
                    question_feedback: []
                };
            }
            var parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
                return {
                    capability_feedback: [],
                    general_feedback: "",
                    question_feedback: []
                };
            }
            if (!Array.isArray(parsed.capability_feedback)) {
                parsed.capability_feedback = [];
            }
            if (typeof parsed.general_feedback !== "string") {
                parsed.general_feedback = "";
            }
            if (!Array.isArray(parsed.question_feedback)) {
                parsed.question_feedback = [];
            }
            return parsed;
        } catch (err) {
            return {
                capability_feedback: [],
                general_feedback: "",
                question_feedback: []
            };
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

    /* ---- Peak draft status helper (visible in current page) ---- */
    function setPeakDraftStatus(text, cls) {
        var el = document.getElementById("peak-draft-status");
        if (!el) {
            return;
        }
        el.textContent = text;
        el.className = "peak-draft-status" + (cls ? " " + cls : "");
    }

    /* ---- View routing ---- */
    function switchView(targetView, options) {
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
            hydrateFeedbackForm();
            if (options && options.focusCapabilityId) {
                window.setTimeout(function () {
                    focusAndHighlightCapability(options.focusCapabilityId);
                }, 50);
            }
        }
        if (targetView === "peak") {
            hydratePeakDraft();
        }
    }

    function focusAndHighlightCapability(capabilityId) {
        var section = document.querySelector(".feedback-capability[data-capability-id=\"" + capabilityId + "\"]");
        if (!section) {
            return;
        }
        section.scrollIntoView({ behavior: "smooth", block: "start" });
        section.classList.remove("highlight-target");
        // Force reflow to restart animation
        void section.offsetWidth;
        section.classList.add("highlight-target");
        window.setTimeout(function () {
            section.classList.remove("highlight-target");
        }, 1600);
        var firstControl = section.querySelector("button, textarea, input, select");
        if (firstControl) {
            firstControl.focus();
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
                openCapabilityQuestionDialog(cap, viewQuestionsBtn);
            });
            actions.appendChild(viewQuestionsBtn);

            var recordFeedbackBtn = document.createElement("button");
            recordFeedbackBtn.type = "button";
            recordFeedbackBtn.className = "btn btn-primary";
            recordFeedbackBtn.textContent = "记录反馈";
            recordFeedbackBtn.addEventListener("click", function () {
                switchView(FEEDBACK_VIEW, { focusCapabilityId: cap.id });
            });
            actions.appendChild(recordFeedbackBtn);

            card.appendChild(actions);
            grid.appendChild(card);
        });
    }

    /* ---- Capability question dialog ---- */
    function bindCapabilityDialog() {
        var dialog = document.getElementById("capability-question-dialog");
        if (!dialog) {
            return;
        }
        // Use the native <dialog> close flow: when Escape is pressed (or form submitted
        // with method="dialog"), the browser dispatches a cancel event followed by close.
        // We rely on the browser's built-in focus restoration to the opener, but capture
        // PENDING_TRIGGER to verify behavior.
        dialog.addEventListener("close", function () {
            if (window.__PROTOTYPE_DEBUG__) {
                window.__PROTOTYPE_DEBUG__.lastCloseFired = true;
                window.__PROTOTYPE_DEBUG__.closePENDING = PENDING_TRIGGER ? PENDING_TRIGGER.textContent : "null";
            }
            if (PENDING_TRIGGER && typeof PENDING_TRIGGER.focus === "function") {
                // Defer focus restoration to next microtask so the browser's own
                // post-close focus restore does not race with ours.
                window.requestAnimationFrame(function () {
                    try {
                        PENDING_TRIGGER.focus({ preventScroll: true });
                    } catch (err) {
                        PENDING_TRIGGER.focus();
                    }
                });
            }
            PENDING_TRIGGER = null;
        });
    }

    function openCapabilityQuestionDialog(cap, triggerButton) {
        var dialog = document.getElementById("capability-question-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }
        var title = document.getElementById("capability-dialog-title");
        var subtitle = document.getElementById("capability-dialog-subtitle");
        var list = document.getElementById("capability-dialog-list");
        if (!title || !subtitle || !list) {
            return;
        }
        title.textContent = cap.name + " — 待确认问题";
        subtitle.textContent = "以下问题仅用于业务讨论；勾选后可在「业务反馈 → 逐问题反馈」中记录状态与备注。";
        list.textContent = "";
        var questions = getQuestionsForCapability(cap.id);
        if (questions.length === 0) {
            var li = document.createElement("li");
            li.textContent = "该能力的待确认问题列表尚未配置。";
            list.appendChild(li);
        } else {
            questions.forEach(function (q) {
                var li = document.createElement("li");
                li.textContent = q.text;
                list.appendChild(li);
            });
        }
        PENDING_TRIGGER = triggerButton || null;
        dialog.showModal();
        // Focus management: focus the close button after open
        var closeBtn = document.getElementById("capability-dialog-close");
        if (closeBtn) {
            window.setTimeout(function () { closeBtn.focus(); }, 0);
        }
    }

    function closeCapabilityQuestionDialog() {
        var dialog = document.getElementById("capability-question-dialog");
        if (!dialog || !dialog.open) {
            return;
        }
        var trigger = PENDING_TRIGGER;
        PENDING_TRIGGER = null;
        dialog.close();
        if (trigger && typeof trigger.focus === "function") {
            try {
                trigger.focus({ preventScroll: false });
            } catch (err) {
                trigger.focus();
            }
        }
    }

    function bindCapabilityDialog() {
        var dialog = document.getElementById("capability-question-dialog");
        if (!dialog) {
            return;
        }
        dialog.addEventListener("close", function () {
            if (window.__PROTOTYPE_DEBUG__) {
                window.__PROTOTYPE_DEBUG__.lastCloseFired = true;
                window.__PROTOTYPE_DEBUG__.closePENDING = PENDING_TRIGGER ? PENDING_TRIGGER.textContent : "null";
            }
            if (PENDING_TRIGGER && typeof PENDING_TRIGGER.focus === "function") {
                try {
                    PENDING_TRIGGER.focus({ preventScroll: false });
                } catch (err) {
                    PENDING_TRIGGER.focus();
                }
            }
            PENDING_TRIGGER = null;
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && dialog.open) {
                e.preventDefault();
                dialog.close();
            }
        });
    }

    function getQuestionsForCapability(capabilityId) {
        return (content.questions || []).filter(function (q) {
            return q.capability_id === capabilityId;
        });
    }

    /* ---- Peak draft ---- */
    function hydratePeakDraft() {
        var draft = loadDraft();
        if (!draft) {
            setPeakDraftStatus("");
            return;
        }
        var fields = ["peak-location", "peak-window", "peak-arrival", "peak-receiving", "peak-processing", "peak-buffer"];
        var anyValue = false;
        fields.forEach(function (id) {
            var el = document.getElementById(id);
            if (el && typeof draft[id] === "string") {
                el.value = draft[id];
                if (draft[id].length > 0) {
                    anyValue = true;
                }
            }
        });
        if (anyValue) {
            setPeakDraftStatus("已恢复本地保存的草稿。", "success");
        } else {
            setPeakDraftStatus("");
        }
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
            if (ok) {
                setPeakDraftStatus("草稿已保存到 localStorage。", "success");
            } else {
                setPeakDraftStatus("草稿保存失败：localStorage 不可用。", "error");
            }
        });
        var clearBtn = document.getElementById("peak-clear-draft");
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                // Reset form fields
                var fields = ["peak-location", "peak-window", "peak-arrival", "peak-receiving", "peak-processing", "peak-buffer"];
                fields.forEach(function (id) {
                    var el = document.getElementById(id);
                    if (el) {
                        el.value = "";
                    }
                });
                var ok = clearDraft();
                if (ok) {
                    setPeakDraftStatus("草稿已清空。", "success");
                } else {
                    setPeakDraftStatus("草稿清空失败：localStorage 不可用。", "error");
                }
            });
        }
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

    function renderQuestionFeedbackList() {
        var list = document.getElementById("feedback-question-list");
        if (!list) {
            return;
        }
        list.textContent = "";
        (content.questions || []).forEach(function (q) {
            var item = document.createElement("div");
            item.className = "feedback-question-item";
            item.setAttribute("data-question-id", q.id);
            item.setAttribute("data-capability-id", q.capability_id);

            var idEl = document.createElement("span");
            idEl.className = "question-id";
            idEl.textContent = q.id;
            item.appendChild(idEl);

            var textEl = document.createElement("span");
            textEl.className = "question-text";
            textEl.textContent = q.text;
            item.appendChild(textEl);

            var controls = document.createElement("div");
            controls.className = "question-controls";

            var statusGroup = document.createElement("div");
            statusGroup.className = "status-group";
            statusGroup.setAttribute("role", "group");
            statusGroup.setAttribute("aria-label", "对 " + q.id + " 的理解状态");
            content.feedbackStatusOptions.forEach(function (opt) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "btn";
                btn.setAttribute("data-question-status-value", opt.value);
                btn.setAttribute("aria-pressed", "false");
                btn.textContent = opt.label;
                btn.addEventListener("click", function () {
                    var siblings = statusGroup.querySelectorAll("button");
                    siblings.forEach(function (sib) { sib.setAttribute("aria-pressed", "false"); });
                    btn.setAttribute("aria-pressed", "true");
                });
                statusGroup.appendChild(btn);
            });
            controls.appendChild(statusGroup);

            var ta = document.createElement("textarea");
            ta.rows = 1;
            ta.setAttribute("data-question-comment", "1");
            ta.setAttribute("aria-label", q.id + " 备注");
            ta.placeholder = "备注（可选）";
            controls.appendChild(ta);

            item.appendChild(controls);
            list.appendChild(item);
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
        // question feedback
        var perQ = {};
        state.question_feedback.forEach(function (entry) {
            if (entry && entry.question_id) {
                perQ[entry.question_id] = entry;
            }
        });
        document.querySelectorAll(".feedback-question-item").forEach(function (item) {
            var qid = item.getAttribute("data-question-id");
            var entry = perQ[qid] || {};
            var statusVal = entry.status || "";
            item.querySelectorAll("button[data-question-status-value]").forEach(function (btn) {
                var matches = btn.getAttribute("data-question-status-value") === statusVal;
                btn.setAttribute("aria-pressed", matches ? "true" : "false");
            });
            var ta = item.querySelector("textarea[data-question-comment]");
            if (ta) {
                ta.value = (entry.comment && typeof entry.comment === "string") ? entry.comment : "";
            }
        });
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
        var perQ = [];
        document.querySelectorAll(".feedback-question-item").forEach(function (item) {
            var qid = item.getAttribute("data-question-id");
            var capId = item.getAttribute("data-capability-id");
            var statusVal = "";
            var activeBtn = item.querySelector("button[data-question-status-value][aria-pressed=\"true\"]");
            if (activeBtn) {
                statusVal = activeBtn.getAttribute("data-question-status-value") || "";
            }
            var commentVal = "";
            var ta = item.querySelector("textarea[data-question-comment]");
            if (ta) {
                commentVal = ta.value;
            }
            perQ.push({
                question_id: qid,
                capability_id: capId,
                status: statusVal,
                comment: commentVal
            });
        });
        return {
            capability_feedback: perCap,
            general_feedback: general ? general.value : "",
            question_feedback: perQ
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
                    general_feedback: state.general_feedback,
                    question_feedback: state.question_feedback
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
        renderQuestionFeedbackList();
        bindFeedbackActions();
        bindDrawer();
        bindCapabilityDialog();
        switchView("overview");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
