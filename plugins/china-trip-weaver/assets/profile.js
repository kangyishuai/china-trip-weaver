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
  if (typeof module !== "undefined" && module.exports) module.exports = { transition };
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

  function paint() {
    rows.forEach((row, index) => {
      if (index === state.day) row.setAttribute("aria-current", "date");
      else row.removeAttribute("aria-current");
      row.classList.toggle("is-preview", index === state.day && state.preview);
    });
    panels.forEach((panel, index) => {
      panel.hidden = index !== state.day;
      const preview = panel.querySelector("[data-try-result]");
      const tryButton = panel.querySelector("[data-try]");
      if (preview) preview.hidden = !(index === state.day && state.preview);
      if (tryButton) tryButton.hidden = index === state.day && state.preview;
      panel.querySelectorAll("[data-shifted-time]").forEach((node) => {
        node.hidden = !(index === state.day && state.preview);
      });
      panel.querySelectorAll("[data-original-time]").forEach((node) => {
        node.hidden = index === state.day && state.preview;
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

  function choose(index, moveFocus) {
    state = transition(state, { type: "select", index }, model);
    paint();
    if (moveFocus) focus.scrollIntoView({ block: "start", behavior: "auto" });
  }
  rows.forEach((row, index) => row.addEventListener("click", (event) => { event.preventDefault(); choose(index, true); }));
  if (previous) previous.addEventListener("click", () => choose(state.day - 1, false));
  if (next) next.addEventListener("click", () => choose(state.day + 1, false));
  panels.forEach((panel) => {
    const tryButton = panel.querySelector("[data-try]");
    const undoButton = panel.querySelector("[data-undo]");
    if (tryButton) tryButton.addEventListener("click", () => { state = transition(state, { type: "try" }, model); paint(); });
    if (undoButton) undoButton.addEventListener("click", () => { state = transition(state, { type: "undo" }, model); paint(); });
  });
  paint();
  document.documentElement.classList.add("js-ready");
})(typeof globalThis !== "undefined" ? globalThis : this);
