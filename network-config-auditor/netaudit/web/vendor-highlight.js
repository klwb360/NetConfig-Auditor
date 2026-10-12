"use strict";
(() => {
  const syntax = window.NetAuditVendorSyntax;
  if(!syntax) return;
  const names = {cisco:"Cisco",huawei:"华为",h3c:"H3C",ruijie:"锐捷",shared:"共享",unknown:"未识别"};
  const colored = new Set(["cisco","huawei","h3c","ruijie","shared"]);
  const editors = new Map();
  const node = (tag,text,cls) => {
    const item = document.createElement(tag);
    if(text !== undefined) item.textContent = text;
    if(cls) item.className = cls;
    return item;
  };
  function shortLabel(line) {
    if(line.category === "shared") return line.vendors.length === 2 ? line.vendors.map(vendor => names[vendor]).join("/") : "通用·共享";
    return (names[line.category] || "") + (line.basis === "context" ? "·共享" : "");
  }
  class EditorHighlights {
    constructor(input) {
      this.input = input;
      this.shell = input.closest(".vendor-editor");
      this.overlay = this.shell.querySelector(".vendor-editor-overlay");
      this.legend = document.getElementById(input.id + "-vendor-legend");
      this.summary = document.getElementById(input.id + "-vendor-summary");
      this.currentLine = node("p",undefined,"vendor-current-line");
      this.currentLine.id = input.id + "-vendor-current";
      this.summary.after(this.currentLine);
      input.setAttribute("aria-describedby",input.getAttribute("aria-describedby") + " " + this.currentLine.id);
      this.vendor = "auto";
      this.kind = input.id === "config" ? "config" : "commands";
      this.text = null;this.classifiedVendor = null;this.lines = [];this.lineStarts = [];this.frame = 0;
      this.chips = new Map();
      for(const [category,label] of Object.entries(names)) {
        const chip = node("span",undefined,"vendor-key");chip.dataset.vendorCategory = category;
        chip.append(node("i",undefined,"vendor-swatch"),node("span",label),node("b","0"));
        this.chips.set(category,chip);this.legend.append(chip);
      }
      input.addEventListener("input",() => this.schedule());
      input.addEventListener("scroll",() => this.schedule(),{passive:true});
      input.addEventListener("compositionend",() => this.schedule());
      input.addEventListener("select",() => this.updateCurrentLine());
      input.addEventListener("keyup",() => this.updateCurrentLine());
      input.addEventListener("click",() => this.updateCurrentLine());
      this.resizeObserver = new ResizeObserver(() => this.schedule());
      this.resizeObserver.observe(input);
      this.schedule();
    }
    schedule(options={}) {
      if(options.vendor !== undefined) this.vendor = options.vendor;
      if(!this.frame) this.frame = requestAnimationFrame(() => {
        this.frame = 0;this.update();
      });
    }
    update() {
      const text = this.input.value;
      if(text !== this.text || this.classifiedVendor !== this.vendor) {
        this.text = text;this.classifiedVendor = this.vendor;
        try {
          this.lines = syntax.classifyLines(text,{vendor:this.vendor,kind:this.kind});
          this.lineStarts = [];
          let offset = 0;
          for(const line of this.lines) {this.lineStarts.push(offset);offset += line.text.length + 1;}
          const counts = Object.fromEntries(Object.keys(names).map(key => [key,0]));
          let contextual = 0;
          for(const line of this.lines) {
            if(Object.hasOwn(counts,line.category)) counts[line.category]++;
            if(line.basis === "context") contextual++;
          }
          for(const [category,chip] of this.chips) chip.querySelector("b").textContent = String(counts[category]);
          this.summary.textContent = text ? `按行识别 · ${Object.entries(counts).filter(([,count]) => count).map(([key,count]) => `${names[key]} ${count} 行`).join("，") || "仅有空行或注释"}${contextual ? `；其中 ${contextual} 行共享语法按当前厂商标注` : ""}。` : "输入后显示指令的厂商颜色与行数。";
          this.shell.dataset.highlightState = "ready";
        } catch(error) {
          // Highlighting is advisory; never alter or reject the underlying text.
          this.lines = [];this.lineStarts = [];
          for(const chip of this.chips.values()) chip.querySelector("b").textContent = "—";
          this.summary.textContent = error instanceof RangeError ? "文本过长或超过 30,000 行，暂不显示底色；原文仍可编辑。" : "暂时无法高亮，原文仍可编辑。";
          this.shell.dataset.highlightState = "unavailable";
        }
      }
      this.updateCurrentLine();
      this.paint();
    }
    updateCurrentLine() {
      if(!this.text || !this.lines.length) {this.currentLine.textContent = "";return;}
      const position = this.input.selectionDirection === "backward" ? this.input.selectionStart : this.input.selectionEnd;
      let low = 0, high = this.lineStarts.length;
      while(low < high) {
        const mid = (low + high) >>> 1;
        if(this.lineStarts[mid] <= position) low = mid + 1;else high = mid;
      }
      const index = Math.max(0,low - 1);
      const line = this.lines[index];
      this.currentLine.textContent = line ? `光标第 ${index + 1} 行：${line.label}${line.basis === "context" ? "（兼容 " + line.vendors.map(vendor => names[vendor]).join(" / ") + "）" : ""}。` : "";
    }
    paint() {
      const input = this.input, style = getComputedStyle(input);
      const lineHeight = parseFloat(style.lineHeight), paddingTop = parseFloat(style.paddingTop);
      const height = input.clientHeight, width = input.clientWidth;
      this.overlay.style.left = "0px";
      this.overlay.style.top = (input.offsetTop + input.clientTop) + "px";
      this.overlay.style.width = (input.offsetLeft + input.clientLeft + width) + "px";
      this.overlay.style.height = height + "px";
      if(!height || !width || !Number.isFinite(lineHeight) || lineHeight <= 0) {
        this.overlay.replaceChildren();return;
      }
      const first = Math.max(0,Math.floor((input.scrollTop - paddingTop) / lineHeight) - 2);
      const end = Math.min(this.lines.length,Math.ceil((input.scrollTop + height - paddingTop) / lineHeight) + 2);
      const fragment = document.createDocumentFragment();
      for(let index = first;index < end;index++) {
        const line = this.lines[index];
        if(!colored.has(line.category)) continue;
        const row = node("div",undefined,"vendor-editor-line");
        row.dataset.lineNumber = String(index + 1);row.dataset.vendorCategory = line.category;
        row.dataset.vendorBasis = line.basis;
        row.style.top = (paddingTop + index * lineHeight - input.scrollTop) + "px";
        row.style.height = lineHeight + "px";
        const label = node("span",shortLabel(line),"vendor-line-label");
        label.title = line.label + (line.reason ? "：" + line.reason : "");
        row.append(label);fragment.append(row);
      }
      this.overlay.replaceChildren(fragment);
    }
  }
  for(const input of document.querySelectorAll(".vendor-editor textarea")) editors.set(input.id,new EditorHighlights(input));
  function refresh(id,options={}) { editors.get(id)?.schedule(options); }
  function refreshSource() { refresh("config",{vendor:document.getElementById("vendor")?.value || "auto"}); }
  window.addEventListener("netaudit:source-change",refreshSource);
  window.addEventListener("resize",() => { for(const editor of editors.values()) editor.schedule(); });
  document.fonts?.ready.then(() => { for(const editor of editors.values()) editor.schedule(); });
  function decorateLine(commandNode,line) {
    if(!line || !colored.has(line.category)) return;
    commandNode.classList.add("vendor-command");
    commandNode.dataset.vendorCategory = line.category;
    const badge = node("span",shortLabel(line),"vendor-command-label");
    badge.dataset.vendorCategory = line.category;
    badge.title = line.label + (line.reason ? "：" + line.reason : "");
    commandNode.after(badge);
  }
  function decorateAll(commandNodes,options={}) {
    const texts = commandNodes.map(item => item.textContent);
    const lines = syntax.classifyLines(texts.join("\n"),{...options,kind:"commands"});
    let index = 0;
    for(let item = 0;item < commandNodes.length;item++) {
      decorateLine(commandNodes[item],lines[index]);
      index += texts[item].split(/\r\n|[\n\r]/).length;
    }
  }
  window.NetAuditHighlights = Object.freeze({refresh,decorateAll});
  refreshSource();
})();
