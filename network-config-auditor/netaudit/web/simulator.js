"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const bridge = window.NetAuditBridge;
  if(!bridge || !byId("simulator")) return;
  const MAX_HISTORY = 20, MAX_HISTORY_BYTES = 16 * 1024 * 1024;
  const vendorNames = {cisco:"Cisco IOS / IOS XE",huawei:"Huawei VRP",h3c:"H3C Comware",ruijie:"Ruijie RGOS"};
  const modeNames = {exec:"执行视图",config:"全局配置视图",interface:"接口视图",vlan:"VLAN 视图",vty:"VTY 视图",acl:"ACL 视图"};
  const outcomeNames = {applied:"可修改",mode:"可切换视图",show:"只读查看",noop:"无需更改",blocked:"当前不能运行",unsupported:"尚不支持",invalid:"参数不合法"};
  let current = null, original = null, candidate = null, plan = null;
  let history = [], historyBytes = 0, epoch = 0, commandRevision = 0, goalRevision = 0;
  let pending = null, requestSerial = 0, importing = bridge.readInput().importing;
  let workspaceMode = "sim";

  function element(tag, text, cls) {
    const item = document.createElement(tag);
    if(text !== undefined) item.textContent = text;
    if(cls) item.className = cls;
    return item;
  }
  function status(message) { byId("sim-status").textContent = message; }
  function showMode(mode) {
    workspaceMode = mode === "audit" ? "audit" : "sim";
    const audit = workspaceMode === "audit";
    byId("simulator").hidden = audit;
    byId("audit-workspace").hidden = !audit;
    byId("audit-settings").hidden = !audit;
    byId("pipeline").hidden = !audit;
    byId("mode-sim").setAttribute("aria-pressed",String(!audit));
    byId("mode-audit").setAttribute("aria-pressed",String(audit));
  }
  function normalizedState(value) {
    if(!value || typeof value.config !== "string" || !Object.hasOwn(vendorNames,value.vendor) || !value.context || typeof value.prompt !== "string") {
      throw new Error("模拟返回的数据不完整，请重新载入备份。");
    }
    return {config:value.config,vendor:value.vendor,context:{...value.context},prompt:value.prompt,
      inventory:value.inventory || {},capabilities:value.capabilities || [],limitations:value.limitations || []};
  }
  function clearCandidate(message="尚无候选变更", clearOutput=true) {
    candidate = null;
    byId("sim-preview-state").textContent = message;
    if(clearOutput) {
      byId("sim-output").hidden = true;
      byId("sim-results").replaceChildren();
      byId("sim-diff").textContent = "";
      byId("sim-outcome").textContent = "";
    }
    refresh();
  }
  function clearPlan() {
    plan = null;
    byId("sim-plan-result").replaceChildren();
    byId("sim-plan-result").hidden = true;
    byId("sim-use-plan").hidden = true;
    refresh();
  }
  function abortRequest(kind) {
    if(pending && (!kind || pending.kind === kind)) {
      pending.controller.abort();
      pending = null;
      requestSerial++;
    }
  }
  function refresh() {
    const busy = Boolean(pending), ready = Boolean(current), source = bridge.readInput();
    byId("sim-load").disabled = busy || importing || !source.config.trim();
    byId("sim-plan").disabled = !ready || busy || !byId("sim-goal").value.trim();
    byId("sim-preview").disabled = !ready || busy || !byId("sim-commands").value.trim();
    byId("sim-apply").disabled = !candidate || busy || !candidate.canApply;
    byId("sim-use-plan").disabled = !plan || plan.status !== "ready" || busy;
    byId("sim-goal").disabled = !ready;
    byId("sim-commands").disabled = !ready;
    byId("sim-undo").disabled = !ready || !history.length || busy;
    byId("sim-reset").disabled = !ready || busy;
    byId("sim-export").disabled = !ready || busy;
    byId("sim-audit").disabled = !ready || busy || byId("run").disabled;
    byId("simulator").setAttribute("aria-busy",String(busy));
    byId("sim-history").textContent = `可撤销 ${history.length} 步 · 历史 ${(historyBytes / 1024 / 1024).toFixed(1)} / 16 MiB（最多 20 步）。仅保存在当前页面，关闭即清除。`;
  }
  function renderCurrent() {
    window.NetAuditHighlights?.refresh("sim-commands",{vendor:current?.vendor || "auto"});
    byId("audit-target-note").textContent = current ? "审查对象：当前已应用的模拟副本。尚未应用的预览不会参与审查。" : "审查对象：左侧原始备份。载入模拟后，将审查当前已应用的练习副本。";
    byId("sim-session-label").textContent = current ? vendorNames[current.vendor] : "等待载入";
    byId("sim-prompt").textContent = current ? current.prompt : "尚未载入配置";
    byId("sim-context").textContent = current ? (modeNames[current.context.mode] || current.context.mode) : "执行视图";
    byId("sim-source-state").textContent = current ? "练习副本已载入。左侧仍是原始备份；重新导入、编辑或更换厂商会结束本次练习。" : "导入后点击「载入模拟」，建立独立的练习副本。";
    const root = byId("sim-capabilities"); root.replaceChildren();
    for(const entry of current?.capabilities || []) {
      const row = element("div",undefined,"sim-capability");
      const button = element("button",entry.command,"secondary"); button.type = "button";
      button.addEventListener("click",() => {
        if(pending || !current) return;
        const input = byId("sim-commands");
        input.value = input.value.trimEnd() + (input.value.trim() ? "\n" : "") + entry.command;
        commandsChanged();input.focus();
      });
      row.append(button,element("p",entry.reason));root.append(row);
    }
    if(!current) root.append(element("p","载入模拟后，根据当前视图给出可用命令。","hint"));
    const limitations = byId("sim-limitations"); limitations.replaceChildren();
    for(const text of current?.limitations || []) limitations.append(element("li",text));
    byId("sim-inventory").textContent = current ? JSON.stringify(current.inventory,null,2) : "尚未载入配置。";
    refresh();
  }
  function endSession() {
    epoch++;commandRevision++;goalRevision++;abortRequest();
    current = original = null;history = [];historyBytes = 0;
    byId("sim-commands").value = "";byId("sim-goal").value = "";
    clearCandidate();clearPlan();renderCurrent();
    status("备份或厂商已改变，请点击「载入模拟」建立新的练习副本。");
    bridge.invalidateAudit("输入已改变，请重新载入模拟或审查当前备份。");
  }
  async function request(kind,path,payload,onSuccess) {
    abortRequest();
    const controller = new AbortController(), id = ++requestSerial, version = epoch;
    pending = {kind,controller,id};refresh();
    const timer = setTimeout(() => controller.abort(),15000);
    try {
      const value = await bridge.post(path,payload,{signal:controller.signal});
      if(epoch !== version || pending?.id !== id) return;
      onSuccess(value);
    } catch(error) {
      if(epoch !== version || pending?.id !== id) return;
      status(error.name === "AbortError" ? "本地处理超时，请缩短命令后重试；当前配置未改变。" : "未完成：" + error.message);
    } finally {
      clearTimeout(timer);
      if(pending?.id === id) {pending = null;refresh();}
    }
  }
  function payload(commands="",state=current) {
    return {config:state.config,vendor:state.vendor,commands,context:state.context};
  }
  function loadSession() {
    const source = bridge.readInput();
    if(importing || !source.config.trim()) return;
    epoch++;commandRevision++;goalRevision++;abortRequest();
    current = original = null;history = [];historyBytes = 0;
    byId("sim-commands").value = "";byId("sim-goal").value = "";
    clearCandidate();clearPlan();renderCurrent();showMode("sim");
    bridge.invalidateAudit("正在建立新的模拟副本，旧审查结果已清除。");
    status("正在解析备份并建立独立练习副本…");
    void request("load","/api/simulate",{config:source.config,vendor:source.vendor,commands:""},value => {
      current = normalizedState(value);
      original = {config:source.config,vendor:current.vendor};
      renderCurrent();status("已载入。可以用中文描述目标，或输入命令先预览；原始备份会一直保留。");
    });
  }
  function commandsChanged() {
    window.NetAuditHighlights?.refresh("sim-commands",{vendor:current?.vendor || "auto"});
    commandRevision++;abortRequest("preview");
    clearCandidate("命令已更改，请重新预览。");status("命令已更改，请点击「预览运行」；当前练习副本未改变。");refresh();
  }
  function goalChanged() {
    goalRevision++;abortRequest("plan");clearPlan();status("目标已更改，请点击「生成命令草案」。每次描述一个具体目标。");refresh();
  }
  function renderPlan(value) {
    plan = value;
    const root = byId("sim-plan-result");root.replaceChildren();root.hidden = false;
    const planLabels = {ready:"草案已准备好", "needs-input":"还需要补充信息",unsupported:"暂不支持这个目标",blocked:"当前条件不满足"};
    root.append(element("h4",planLabels[value.status] || "请核对目标"),element("p",value.summary || "请补充具体目标、接口名和参数。"));
    if(value.steps?.length) {
      const list = element("ol"), commands = [];
      for(const item of value.steps) {
        const row = element("li"), code = element("code",item.command);
        row.append(code,element("p",item.reason));list.append(row);
        commands.push(code);
      }
      window.NetAuditHighlights?.decorateAll(commands,{vendor:current?.vendor || "auto"});
      root.append(list);
    }
    if(value.questions?.length) {
      const list = element("ul");for(const question of value.questions) list.append(element("li",question));root.append(list);
    }
    if(value.commands) root.append(element("pre",value.commands));
    byId("sim-use-plan").hidden = !(value.status === "ready" && typeof value.commands === "string" && value.commands.trim());
    if(byId("sim-use-plan").hidden) plan = null;
    status(value.status === "ready" ? "草案已生成。先阅读每步理由，再放入命令区预览；尚未执行任何变更。" : (value.summary || "请按提示补充目标。"));
    refresh();
  }
  function planGoal() {
    if(!current || pending) return;
    const goal = byId("sim-goal").value.trim(), version = goalRevision;
    if(!goal) return;
    clearPlan();status("正在根据目标和当前配置准备命令草案…");
    void request("plan","/api/plan",{config:current.config,vendor:current.vendor,goal,context:current.context},value => {
      if(goalRevision !== version) return;
      renderPlan(value);
    });
  }
  function renderPreview(value,commands,version) {
    const proposed = normalizedState(value), summary = value.summary || {};
    const results = Array.isArray(value.results) ? value.results : [];
    const failed = Boolean(summary.rolled_back) || results.some(item => ["blocked","unsupported","invalid"].includes(item.status));
    const changed = proposed.config !== current.config || JSON.stringify(proposed.context) !== JSON.stringify(current.context);
    candidate = {state:proposed,epoch,commandRevision:version,commands,canApply:!failed && changed};
    const root = byId("sim-results"), commandNodes = [];root.replaceChildren();
    for(const item of results) {
      const card = element("article",undefined,"sim-command-result " + (Object.hasOwn(outcomeNames,item.status) ? item.status : "invalid"));
      const head = element("div",undefined,"sim-command-result-head");
      const code = element("code",item.command);
      head.append(element("span",outcomeNames[item.status] || "无法判断","sim-result-badge"),code);
      commandNodes.push(code);
      card.append(head,element("p",item.reason || "请核对命令的适用条件。"));
      if(item.suggestion) card.append(element("p","建议：" + item.suggestion,"sim-suggestion"));
      if(item.output) card.append(element("pre",item.output));
      if(item.rolled_back) card.append(element("p","整批回滚：此行也不会应用。","sim-rolled-back"));
      root.append(card);
    }
    window.NetAuditHighlights?.decorateAll(commandNodes,{vendor:current?.vendor || "auto"});
    const message = failed ? "本批有命令未通过，整批配置和视图变更都不会应用。请根据下方理由修改后重试。" : changed ? "预览完成，当前练习副本尚未改变。核对差异后，点击「应用本次预览」。" : "查看完成，没有配置或视图变化，无需应用。";
    byId("sim-outcome").textContent = message;
    byId("sim-outcome").dataset.state = failed ? "blocked" : "ready";
    byId("sim-diff").textContent = value.diff || (failed ? "整批回滚，无配置差异。" : "没有配置文本差异；仅查看命令或视图切换不会改变备份文本。");
    byId("sim-output").hidden = false;
    byId("sim-preview-state").textContent = failed ? "整批不应用" : changed ? "等待您确认应用" : "无需应用";
    status(message);refresh();
  }
  function previewCommands() {
    if(!current || pending) return;
    const commands = byId("sim-commands").value, version = commandRevision;
    if(!commands.trim()) return;
    if(new TextEncoder().encode(commands).length > 64 * 1024 || commands.split(/\r\n|[\n\r\u0085\u2028\u2029]/).length - (/\r\n$|[\n\r\u0085\u2028\u2029]$/.test(commands) ? 1 : 0) > 200) {
      clearCandidate("命令超过 200 行或 64 KiB，请分批练习。");status("命令超过 200 行或 64 KiB，请分批练习。");return;
    }
    clearCandidate("正在预览…");status("正在预览命令及前置条件，当前练习副本不会自动改变…");
    void request("preview","/api/simulate",payload(commands),value => {
      if(commandRevision !== version || commands !== byId("sim-commands").value) return;
      renderPreview(value,commands,version);
    });
  }
  function remember() {
    const snapshot = {config:current.config,vendor:current.vendor,context:{...current.context}};
    snapshot.bytes = snapshot.config.length * 2 + snapshot.context.target.length * 2 + 128;
    history.push(snapshot);historyBytes += snapshot.bytes;
    while(history.length > MAX_HISTORY || historyBytes > MAX_HISTORY_BYTES) historyBytes -= history.shift().bytes;
  }
  function applyCandidate() {
    if(!candidate?.canApply || pending || candidate.epoch !== epoch || candidate.commandRevision !== commandRevision || candidate.commands !== byId("sim-commands").value) return;
    remember();current = candidate.state;epoch++;
    clearCandidate("本次预览已应用；输入下一条命令继续练习。",false);clearPlan();
    byId("sim-outcome").textContent = "本次预览已应用到练习副本。左侧原始备份未改变；可以继续输入命令、撤销或按需审查。";
    byId("sim-commands").value = "";commandRevision++;
    renderCurrent();bridge.invalidateAudit("模拟配置或视图已改变，请按需重新审查当前副本。");
    status("已应用到练习副本。下一条命令将从当前视图继续；可撤销本步。");
  }
  function restore(kind) {
    if(!current || pending || (kind === "undo" && !history.length)) return;
    const target = kind === "undo" ? history[history.length - 1] : {...original,context:{mode:"exec",target:""}};
    epoch++;commandRevision++;goalRevision++;clearCandidate();clearPlan();
    status(kind === "undo" ? "正在恢复上一步的配置和视图…" : "正在从原始备份恢复练习副本…");
    void request(kind,"/api/simulate",payload("",target),value => {
      current = normalizedState(value);
      if(kind === "undo") historyBytes -= history.pop().bytes;
      else {history = [];historyBytes = 0;}
      byId("sim-commands").value = "";
      renderCurrent();bridge.invalidateAudit("练习副本已恢复，旧审查结果已清除。请按需重新审查。");
      status(kind === "undo" ? "已撤销上一步，配置和命令行视图均已恢复。" : "已重置为原始备份，练习历史已清除。可以开始新的目标。");
    });
  }
  function exportConfig() {
    if(!current || pending) return;
    const blob = new Blob([current.config],{type:"text/plain;charset=utf-8"});
    const url = URL.createObjectURL(blob), link = element("a");
    link.href = url;link.download = "netaudit-" + current.vendor + "-practice.cfg";
    link.click();setTimeout(() => URL.revokeObjectURL(url),1000);
    status("已导出当前已应用的模拟配置（不包含尚未应用的预览）。文件保留原文和凭据，请按敏感文件保存。");
  }

  bridge.setAuditConfigProvider(() => current ? {config:current.config,vendor:current.vendor} : null);
  window.addEventListener("netaudit:source-change",endSession);
  window.addEventListener("netaudit:import-state",event => { importing = Boolean(event.detail.importing);refresh(); });
  window.addEventListener("netaudit:audit-view",() => showMode("audit"));
  byId("mode-sim").addEventListener("click",() => showMode("sim"));
  byId("mode-audit").addEventListener("click",() => showMode("audit"));
  byId("sim-load").addEventListener("click",loadSession);
  byId("sim-goal").addEventListener("input",goalChanged);
  byId("sim-commands").addEventListener("input",commandsChanged);
  byId("sim-commands").addEventListener("keydown",event => {
    if((event.ctrlKey || event.metaKey) && event.key === "Enter") {event.preventDefault();previewCommands();}
  });
  byId("sim-plan").addEventListener("click",planGoal);
  byId("sim-use-plan").addEventListener("click",() => {
    if(!plan || pending || plan.status !== "ready") return;
    byId("sim-commands").value = plan.commands;commandsChanged();byId("sim-commands").focus();
    status("草案已放入命令区，尚未模拟或应用。请阅读后点击「预览运行」。");
  });
  byId("sim-preview").addEventListener("click",previewCommands);
  byId("sim-apply").addEventListener("click",applyCandidate);
  byId("sim-undo").addEventListener("click",() => restore("undo"));
  byId("sim-reset").addEventListener("click",() => restore("reset"));
  byId("sim-export").addEventListener("click",exportConfig);
  byId("sim-audit").addEventListener("click",() => {if(current && !pending) byId("run").click();});
  showMode("sim");renderCurrent();
})();
