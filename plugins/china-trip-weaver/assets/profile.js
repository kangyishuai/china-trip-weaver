(function (scope) {
  "use strict";
  function transition(state, action, model) {
    if (action.type === "select") {
      if (!Number.isInteger(action.index) || action.index < 0 || action.index >= model.days.length) return state;
      return { day: action.index, preview: false };
    }
    if (action.type === "try") {
      if (!model.days[state.day].scenario.available) return state;
      return { day: state.day, preview: true };
    }
    if (action.type === "undo") return { day: state.day, preview: false };
    return state;
  }
  function timeVisibility(hasAlternative, preview) {
    return { originalHidden: !!(hasAlternative && preview), shiftedHidden: !hasAlternative || !preview };
  }
  function focusTarget(origin, triggerDisabled) {
    if (origin === "overview" || (origin === "adjacent" && triggerDisabled)) return "day";
    if (origin === "preview") return "undo";
    if (origin === "undo") return "try";
    return "trigger";
  }
  function capturePrintState(existing, currentState, detailsOpen) {
    return existing || { state: { day: currentState.day, preview: currentState.preview }, detailsOpen: detailsOpen.slice() };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { transition, timeVisibility, focusTarget, capturePrintState };
  if (typeof document === "undefined") return;

  const source = document.getElementById("prototype-model");
  const focus = document.getElementById("focus-column");
  if (!source || !focus) return;
  const model = JSON.parse(source.textContent);
  const english = document.documentElement.lang === "en";
  const rows = Array.from(document.querySelectorAll("[data-select-day]"));
  const panels = Array.from(document.querySelectorAll("[data-day-detail]"));
  const supportPanels = Array.from(document.querySelectorAll("[data-day-support]"));
  const previous = document.querySelector("[data-prev-day]");
  const next = document.querySelector("[data-next-day]");
  const position = document.querySelector("[data-day-position]");
  const live = document.getElementById("selection-announcement");
  let state = { day: 0, preview: false };
  let printSession = null;

  function dayHeading() {
    return panels[state.day] && panels[state.day].querySelector(".day-identity h3");
  }

  function paint() {
    rows.forEach((row, index) => {
      if (index === state.day) row.setAttribute("aria-current", "date");
      else row.removeAttribute("aria-current");
      row.classList.toggle("is-preview", index === state.day && state.preview);
    });
    panels.forEach((panel, index) => {
      panel.hidden = index !== state.day;
      const activePreview = index === state.day && state.preview;
      const preview = panel.querySelector("[data-try-result]");
      const tryButton = panel.querySelector("[data-try]");
      if (preview) preview.hidden = !activePreview;
      if (tryButton) tryButton.hidden = activePreview;
      panel.querySelectorAll("[data-shifted-time]").forEach((node) => {
        node.hidden = timeVisibility(true, activePreview).shiftedHidden;
      });
      panel.querySelectorAll("[data-original-time]").forEach((node) => {
        node.hidden = timeVisibility(node.hasAttribute("data-scenario-original"), activePreview).originalHidden;
      });
    });
    supportPanels.forEach((panel, index) => { panel.hidden = index !== state.day; });
    const selected = model.days[state.day];
    if (previous) previous.disabled = state.day === 0;
    if (next) next.disabled = state.day === model.days.length - 1;
    if (position) position.textContent = (state.day + 1) + " / " + model.days.length;
    live.textContent = english
      ? "Day " + (state.day + 1) + ", " + selected.city + (state.preview ? "; viewing the 30-minute-later preview" : "; original plan")
      : "第" + (state.day + 1) + "天，" + selected.city + (state.preview ? "；正在查看晚 30 分钟的假设预览" : "；显示原始行程");
  }

  function choose(index, origin, trigger) {
    const nextState = transition(state, { type: "select", index }, model);
    if (nextState === state) return;
    state = nextState;
    paint();
    if (focusTarget(origin, !!(trigger && trigger.disabled)) === "day") {
      const heading = dayHeading();
      if (origin === "overview") focus.scrollIntoView({ block: "start", behavior: "auto" });
      if (heading) heading.focus({ preventScroll: origin === "overview" });
    }
  }
  rows.forEach((row, index) => row.addEventListener("click", (event) => { event.preventDefault(); choose(index, "overview", row); }));
  if (previous) previous.addEventListener("click", () => choose(state.day - 1, "adjacent", previous));
  if (next) next.addEventListener("click", () => choose(state.day + 1, "adjacent", next));
  panels.forEach((panel) => {
    const tryButton = panel.querySelector("[data-try]");
    const undoButton = panel.querySelector("[data-undo]");
    if (tryButton) tryButton.addEventListener("click", () => {
      const nextState = transition(state, { type: "try" }, model);
      if (nextState === state) return;
      state = nextState;
      paint();
      if (focusTarget("preview", false) === "undo" && undoButton && !undoButton.hidden) undoButton.focus();
    });
    if (undoButton) undoButton.addEventListener("click", () => {
      state = transition(state, { type: "undo" }, model);
      paint();
      if (focusTarget("undo", false) === "try" && tryButton && !tryButton.hidden) tryButton.focus();
    });
  });

  function beforePrint() {
    if (printSession) return;
    const details = Array.from(document.querySelectorAll("details"));
    printSession = capturePrintState(printSession, state, details.map((item) => item.open));
    printSession.details = details;
    printSession.focused = document.activeElement;
    details.forEach((item) => { item.open = true; });
    panels.forEach((panel) => {
      panel.hidden = false;
      panel.querySelectorAll("[data-original-time]").forEach((node) => { node.hidden = false; });
      panel.querySelectorAll("[data-shifted-time]").forEach((node) => { node.hidden = true; });
    });
    supportPanels.forEach((panel) => { panel.hidden = false; });
    rows.forEach((row) => { row.classList.remove("is-preview"); });
  }

  function afterPrint() {
    if (!printSession) return;
    const saved = printSession;
    printSession = null;
    saved.details.forEach((item, index) => {
      if (item.isConnected) item.open = saved.detailsOpen[index];
    });
    state = saved.state;
    paint();
    const target = saved.focused;
    if (target && target !== document.body && target.isConnected && !target.hidden && !target.disabled && typeof target.focus === "function") {
      target.focus({ preventScroll: true });
    }
  }
  window.addEventListener("beforeprint", beforePrint);
  window.addEventListener("afterprint", afterPrint);
  paint();
  document.documentElement.classList.add("js-ready");
})(typeof globalThis !== "undefined" ? globalThis : this);
