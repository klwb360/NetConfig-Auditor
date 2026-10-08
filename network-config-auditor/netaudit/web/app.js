"use strict";
const $ = id => document.getElementById(id);
let exports_ = null, report_ = null;
let inputRevision = 0, auditRunning = false, configSource = "输入文本";
let fileLoading = false, fileLoadId = 0, importAbort = null;
function refreshRunState() { $("run").disabled=auditRunning||fileLoading; }
function cancelConfigImport() {
  fileLoadId++;fileLoading=false;
  if(importAbort)importAbort.abort();importAbort=null;refreshRunState();
}
const resultTitles = {findings:"安全发现",architecture:"网络架构检查",intelligence:"CVE / KEV 情报",ai:"AI 解释与整改建议",inventory:"报告与配置清单",help:"使用帮助"};
const resultTabs = [...document.querySelectorAll("[data-result-tab]")];
function selectResultTab(name, focus=false) {
  if(!Object.hasOwn(resultTitles,name)) return;
  for(const tab of resultTabs) {
    const selected=tab.dataset.resultTab===name;
    tab.setAttribute("aria-selected",String(selected));tab.tabIndex=selected?0:-1;
    $(tab.getAttribute("aria-controls")).hidden=!selected;
    if(selected&&focus)tab.focus();
  }
  $("result-title").textContent=resultTitles[name];
}
for(const tab of resultTabs) {
  tab.addEventListener("click",()=>selectResultTab(tab.dataset.resultTab));
  tab.addEventListener("keydown",event=>{
    const index=resultTabs.indexOf(tab);
    let next;
    if(event.key==="ArrowRight"||event.key==="ArrowDown")next=(index+1)%resultTabs.length;
    else if(event.key==="ArrowLeft"||event.key==="ArrowUp")next=(index+resultTabs.length-1)%resultTabs.length;
    else if(event.key==="Home")next=0;
    else if(event.key==="End")next=resultTabs.length-1;
    else return;
    event.preventDefault();selectResultTab(resultTabs[next].dataset.resultTab,true);
  });
}
function allowExports(available) {
  $("exports").hidden=!available;
  document.querySelectorAll("[data-format]").forEach(button=>button.disabled=!available);
}
function updateConfigMeta() {
  const text=$("config").value,bytes=new TextEncoder().encode(text).length;
  $("config-meta").textContent=text?`${configSource} · ${configLineCount(text)} 行 · ${(bytes/1024).toFixed(1)} KiB`:"尚未导入配置";
}
function configLineCount(text) {
  if(!text)return 0;
  const lines=text.split(/\r\n|[\n\r\u0085\u2028\u2029]/);
  return lines.length-(lines[lines.length-1]===""?1:0);
}
function clearResults(message="导入配置或载入示例，开始一次本地审计。") {
  exports_=null;report_=null;allowExports(false);
  $("summary").querySelectorAll("strong").forEach(item=>item.textContent="—");
  for(const id of ["architecture","intelligence","ai-result","inventory"])$(id).hidden=true;
  $("inventory").querySelector("pre").textContent="";
  document.querySelectorAll(".panel-empty-placeholder").forEach(item=>item.hidden=false);
  $("findings").className="empty";
  $("findings").replaceChildren(node("div","⌁","empty-icon"),node("h3","等待审计"),node("p",message));
  $("result-context").textContent=message;
  renderPipeline();
}
function invalidateResults() {
  inputRevision++;
  const hadResult=Boolean(report_);
  if(hadResult||auditRunning) {
    const message=auditRunning?"输入已更改，当前请求的结果将不保留；请完成后重新审计。":"输入已更改，请重新审计以获取对应结果。";
    clearResults(message);$("status").textContent=message;
  }
  return inputRevision;
}
const labels = {critical:"严重", high:"高", medium:"中", low:"低", info:"提示"};
function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
const domainLabels={vlan:"VLAN",stp:"STP",ospf:"OSPF",acl:"ACL",nat:"NAT",management_plane:"Management Plane / 管理平面"};
const stageLabels={parse:"配置解析器",parser:"配置解析器",architecture:"网络架构检查",security:"安全规则引擎",rules:"安全规则引擎",intelligence:"CVE / KEV 情报",ai:"AI 解释与建议",reports:"Markdown / HTML 报告",report:"Markdown / HTML 报告"};
const statusLabels={completed:"已完成",passed:"已完成",checked:"已检查",findings:"存在发现","needs-review":"需人工核对","not-observed":"未观察到配置","not-configured":"未配置","no-matches":"未匹配",matched:"已匹配",disabled:"未启用",error:"失败",failed:"失败",unavailable:"不可用",skipped:"已跳过","not-requested":"未启用","not-needed":"无需解释"};
const confidenceLabels={"cpe-version-match":"精确 CPE 版本关联，仍需核对适用条件","needs-review":"需人工核对","user-provided-candidate":"用户提供候选编号"};
const originLabels={"bundled-official-snapshot":"随包官方快照",bundled:"随包快照","user-import":"本地导入（未核实来源）","caller-provided-unverified":"用户提供（未核实来源）","official-download":"官方地址下载"};
const statusText=value=>statusLabels[value]||value||"—";
const valueText=value=>value==null?"—":typeof value==="object"?JSON.stringify(value):String(value);
function field(parent,label,value){const p=node("p");p.append(node("strong",label+"："),document.createTextNode(valueText(value)));parent.append(p);}
function sourceLink(value){
  const text=String(value||"未提供来源");
  try{const url=new URL(text);if(url.protocol==="https:"&&!url.username&&!url.password){const link=node("a",text);link.href=url.href;link.target="_blank";link.rel="noreferrer noopener";return link;}}
  catch(e){/* Untrusted source strings remain literal text. */}
  return node("span",text);
}
function renderPipeline(items,running=false){
  const root=$("pipeline");root.replaceChildren();
  const stages=items&&items.length?items:Object.entries(stageLabels).filter(([key])=>["parse","architecture","rules","intelligence","ai","reports"].includes(key)).map(([stage])=>({stage,status:running?"waiting":"",detail:""}));
  for(const item of stages){const step=node("li");step.append(node("strong",stageLabels[item.stage]||item.stage));if(item.status)step.append(node("span",item.status==="waiting"?"等待结果":statusText(item.status)));if(item.detail)step.append(node("small",item.detail));root.append(step);}
}
function renderArchitecture(){
  const domains=report_.architecture&&report_.architecture.domains||[];$("architecture").hidden=!domains.length;$("domains").replaceChildren();
  for(const item of domains){const card=node("article",undefined,"domain-card");card.append(node("h3",domainLabels[item.domain]||item.domain),node("span",statusText(item.status),"badge"));field(card,"已观察配置",item.observed);field(card,"覆盖范围",item.coverage);if(item.finding_ids&&item.finding_ids.length)field(card,"相关规则",item.finding_ids.join("、"));$("domains").append(card);}
}
function renderIntelligence(){
  const root=$("intelligence"),intel=report_.intelligence;root.replaceChildren();root.hidden=!intel;if(!intel)return;
  root.append(node("h2","CVE / KEV 情报"));field(root,"状态",statusText(intel.status));root.append(node("p",intel.message));field(root,"资产标识",intel.asset||{});
  for(const [title,key] of [["精确版本匹配","matches"],["候选项 · 不能作为已确认漏洞","candidates"]]){
    root.append(node("h3",title));const items=intel[key]||[];
    if(!items.length)root.append(node("p","无。未匹配不表示安全；仍需核对设备版本、适用条件和厂商公告。","hint"));
    for(const item of items){const card=node("article");card.append(node("h3",[item.cve_id,item.title].filter(Boolean).join(" · ")));field(card,"严重度",item.severity);field(card,"KEV 已知利用",item.known_exploited?"是":"未收录");field(card,"判断",confidenceLabels[item.confidence]||item.confidence);field(card,"匹配依据",item.match_basis);if(item.description)card.append(node("p",item.description));const source=node("p");source.append(node("strong","来源："),sourceLink(item.source_url));card.append(source);if(item.kev&&item.kev.requiredAction)field(card,"CISA 要求",item.kev.requiredAction);root.append(card);}
  }
  if(intel.sources&&intel.sources.length){const details=node("details");details.append(node("summary","情报来源与时效"));for(const source of intel.sources){const card=node("article");card.append(node("h3",source.name||source.kind),sourceLink(source.source_url));field(card,"发布日期",source.date_released);field(card,"目录版本",source.catalog_version);field(card,"来源",originLabels[source.origin]||source.origin);field(card,"SHA-256",source.sha256);field(card,"快照过期",source.stale?"是":"否");field(card,"快照年龄（天）",source.age_days);field(card,"目录条目",source.count);field(card,"许可 / 归属",source.license);details.append(card);}root.append(details);}
  if(intel.limitations&&intel.limitations.length){const list=node("ul",undefined,"limitations");for(const text of intel.limitations)list.append(node("li",text));root.append(list);}
}
function renderAI(){
  const root=$("ai-result"),ai=report_.ai;root.replaceChildren();root.hidden=!ai;if(!ai)return;
  root.append(node("h2","AI 解释与整改建议"));field(root,"状态",statusText(ai.status));if(ai.provider)field(root,"提供方",ai.provider);if(ai.model)field(root,"模型",ai.model);root.append(node("p",ai.message),node("p","模型内容仅供辅助理解，不能替代规则证据、厂商公告和变更审批。","hint"));
  for(const item of ai.items||[]){const card=node("article");card.append(node("h3",item.rule_id));field(card,"解释",item.explanation);field(card,"整改建议",item.remediation);root.append(card);}
}
async function readIntelligenceFile(id,label){
  const file=$(id).files[0];if(!file)return undefined;if(file.size>16*1024*1024)throw new Error(label+" 文件超过 16 MiB 限制");
  let value;try{value=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer()));}catch(e){throw new Error(label+" 文件必须为 UTF-8 JSON");}
  if(!value||typeof value!=="object"||Array.isArray(value))throw new Error(label+" JSON 顶层必须是对象");return value;
}
async function auditPayload(){
  const config=$("config").value;if(new TextEncoder().encode(config).length>2*1024*1024)throw new Error("配置超过 2 MiB 限制");
  const asset={},cpe=$("cpe").value.trim(),ids=$("cve-ids").value.trim();if(cpe)asset.cpe=cpe;if(ids)asset.cve_ids=[...new Set(ids.split(/[\s,，]+/).filter(Boolean))];
  const enabled=$("ai-enabled").checked,model=$("ai-model").value.trim();if(enabled&&!model)throw new Error("启用 AI 时需填写已安装的本机模型名称");
  const payload={vendor:$("vendor").value,config,asset,ai:enabled?{enabled:true,provider:"ollama",endpoint:"http://127.0.0.1:11434",model,timeout:30}:{enabled:false}};
  const [kev,nvd]=await Promise.all([readIntelligenceFile("kev-file","KEV"),readIntelligenceFile("nvd-file","NVD")]);if(kev!==undefined)payload.kev=kev;if(nvd!==undefined)payload.nvd=nvd;return payload;
}
function renderFindings() {
  const root = $("findings"); root.replaceChildren(); root.className = "";
  const items = report_.findings.filter(f => $("severity").value === "all" || f.severity === $("severity").value);
  if(!items.length) {root.className="empty";root.append(node("h3","没有符合筛选条件的发现"),node("p","请同时检查配置清单、未建模行与报告适用范围。"));return;}
  for(const f of items) {
    const card=node("article"),meta=node("div",undefined,"meta");
    meta.append(node("span",labels[f.severity],"badge "+f.severity),node("span",f.rule_id),node("span",f.confidence==="needs-review"?"需核对场景":"配置已确认"));
    if((f.occurrences||1)>1)meta.append(node("span",`已合并 ${f.occurrences} 处`));
    card.append(meta,node("h3",f.title));
    for(const [label,key] of [["配置问题","problem"],["安全风险","risk"],["修改建议","recommendation"]]) {const p=node("p");p.append(node("strong",label+"："),document.createTextNode(f[key]));card.append(p);}
    if(f.affected_objects?.length)field(card,"影响对象",f.affected_objects.join("、"));
    if(f.evidence.length) {
      const evidence=node("pre",f.evidence.map(e=>`L${e.line}: ${e.text}`).join("\n"),"evidence");
      if(f.evidence.length>8){const details=node("details");details.append(node("summary",`查看完整证据（${f.evidence.length} 行）`),evidence);card.append(details);}else card.append(evidence);
    }
    if(f.command_notes)field(card,"命令前提",f.command_notes);
    for(const [key,label] of [["verification_commands","检查与验证命令 · 只读"],["commands","建议整改命令 · 满足前提后人工执行"],["command_templates","命令模板 · 先填写参数并核对"]]) {
      if(f[key]?.length){card.append(node("p",label,"confidence"));for(const script of f[key])card.append(node("pre",script));}
    }
    root.append(card);
  }
}
$("run").addEventListener("click", async () => {
  const revision=inputRevision;auditRunning=true;
  $("run").disabled=true;$("example").disabled=true;clearResults("正在审计，请等待本地处理完成。");
  $("status").textContent="正在审计…启用 AI 时请等待本机模型完成。";renderPipeline(null,true);
  document.querySelector(".results").setAttribute("aria-busy","true");
  $("findings").replaceChildren(node("p","正在审计…"));
  try {
    const payload=await auditPayload();
    if(revision!==inputRevision)return;
    const sessionResponse=await fetch("/api/session",{cache:"no-store"});
    if(!sessionResponse.ok) throw new Error("无法建立本地会话");
    const session=await sessionResponse.json();
    if(revision!==inputRevision)return;
    const response=await fetch("/api/audit",{method:"POST",headers:{"Content-Type":"application/json","X-NetAudit-Token":session.token},body:JSON.stringify(payload)});
    if(revision!==inputRevision)return;
    const value=await response.json();if(!response.ok)throw new Error(value.error||"审计失败");
    if(revision!==inputRevision)return;
    report_=value.report;exports_=value.exports;const s=report_.summary;
    const nums=$("summary").querySelectorAll("strong");nums[0].textContent=s.severity.critical+s.severity.high;nums[1].textContent=s.severity.medium+s.severity.low;nums[2].textContent=s.unsupported_lines;
    $("status").textContent=`审计完成 · ${report_.device.vendor} · ${report_.device.hostname} · 识别 ${s.recognized_lines}/${s.relevant_lines} 行`;
    $("result-context").textContent=`当前结果 · ${report_.device.vendor} · ${report_.device.hostname} · ${s.total} 类发现`+(s.merged_count?` · 涉及 ${s.occurrences_total} 处（同类已合并）`:"");
    document.querySelectorAll(".panel-empty-placeholder").forEach(item=>item.hidden=true);
    allowExports(true);$("inventory").hidden=false;$("inventory").querySelector("pre").textContent=JSON.stringify(report_.inventory,null,2);renderPipeline(report_.pipeline);renderArchitecture();renderIntelligence();renderAI();renderFindings();
  } catch(e) {
    if(revision!==inputRevision)return;
    clearResults("审计未完成，请检查配置、厂商与可选设置后重试。");
    $("status").textContent="审计失败："+e.message;
  }
  finally {auditRunning=false;refreshRunState();$("example").disabled=false;document.querySelector(".results").setAttribute("aria-busy","false");}
});
for(const id of ["config","cpe","cve-ids","ai-model"])$(id).addEventListener("input",()=>{if(id==="config"){cancelConfigImport();configSource="手动编辑";updateConfigMeta();$("vendor-detection").textContent="配置已编辑，可手动选择厂商或在审计时自动识别。";}invalidateResults();});
$("vendor").addEventListener("change",()=>{cancelConfigImport();invalidateResults();$("vendor-detection").textContent=$("vendor").value==="auto"?"审计时按配置内容自动识别。":"已手动选择："+$("vendor").selectedOptions[0].textContent;});
$("ai-enabled").addEventListener("change",()=>{$("ai-model").disabled=!$("ai-enabled").checked;invalidateResults();});
for(const kind of ["kev","nvd"]){$("clear-"+kind).addEventListener("click",()=>{$(kind+"-file").value="";invalidateResults();});$(kind+"-file").addEventListener("change",()=>{invalidateResults();const file=$(kind+"-file").files[0];if(file&&file.size>16*1024*1024){$(kind+"-file").value="";$("status").textContent=kind.toUpperCase()+" 文件超过 16 MiB 限制，请选择较小的官方 JSON 文件。";}});}
$("severity").addEventListener("change",()=>{if(report_)renderFindings();});
async function readConfigBuffer(file) {
  let timer;
  try {
    return await Promise.race([file.arrayBuffer(),new Promise((_,reject)=>{
      timer=setTimeout(()=>reject(new Error("读取文件超时，请重新拖入或选择文件。")),10000);
    })]);
  } finally {clearTimeout(timer);}
}
async function loadConfigFile(file) {
  cancelConfigImport();const loadId=fileLoadId;
  let revision=invalidateResults(),timer=null;
  $("file").value="";
  if(file.size>2*1024*1024){$("status").textContent="文件超过 2 MiB 限制";return;}
  fileLoading=true;refreshRunState();$("status").textContent="正在读取配置文件…";
  try {
    const buffer=await readConfigBuffer(file);let text;
    try{text=new TextDecoder("utf-8",{fatal:true}).decode(buffer);}
    catch(e){throw new Error("文件必须为 UTF-8 文本。");}
    if(revision!==inputRevision)return;
    if(!text.trim())throw new Error("文件为空，请导入设备配置。");
    if(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(text))throw new Error("文件含非文本控制字符，请导入 UTF-8 配置文本。");
    if(configLineCount(text)>30000)throw new Error("配置超过 30000 行限制。");
    revision=invalidateResults();$("config").value=text;$("vendor").value="auto";
    configSource=file.name;updateConfigMeta();$("vendor-detection").textContent="正在按配置内容识别厂商…";
    $("status").textContent="文件已载入，正在识别厂商…";
    const controller=new AbortController();importAbort=controller;
    timer=setTimeout(()=>controller.abort(),5000);
    try {
      const sessionResponse=await fetch("/api/session",{cache:"no-store",signal:controller.signal});
      if(!sessionResponse.ok)throw new Error("无法建立本地会话");
      const session=await sessionResponse.json();if(revision!==inputRevision)return;
      const response=await fetch("/api/detect",{method:"POST",headers:{"Content-Type":"application/json","X-NetAudit-Token":session.token},body:JSON.stringify({config:text}),signal:controller.signal});
      const value=await response.json();if(revision!==inputRevision)return;
      if(!response.ok)throw new Error("自动识别暂不可用");
      if(value.status==="detected"&&["cisco","huawei","h3c","ruijie"].includes(value.vendor)) {
        $("vendor").value=value.vendor;
        $("vendor-detection").textContent="已自动识别："+$("vendor").selectedOptions[0].textContent+"；可手动调整。";
        $("status").textContent="文件已载入，"+$("vendor-detection").textContent+"点击开始审计。";
      } else {
        $("vendor-detection").textContent="无法可靠识别，请手动选择设备厂商。";
        $("status").textContent="文件已载入，"+$("vendor-detection").textContent;
      }
    } catch(e) {
      if(revision!==inputRevision)return;
      $("vendor-detection").textContent="自动识别暂不可用，可手动选择设备厂商。";
      $("status").textContent="文件已载入，"+$("vendor-detection").textContent;
    }
  } catch(e) {if(revision===inputRevision)$("status").textContent=e.message;}
  finally {
    if(timer!==null)clearTimeout(timer);
    if(loadId===fileLoadId){fileLoading=false;importAbort=null;refreshRunState();}
  }
}
$("file").addEventListener("change",()=>{const file=$("file").files[0];if(file)void loadConfigFile(file);});
const dropZone=$("config-drop-zone");let dragDepth=0;
const hasFiles=event=>Array.from(event.dataTransfer?.types||[]).includes("Files");
function resetDragState(){dragDepth=0;dropZone.classList.remove("drag-over");}
dropZone.addEventListener("dragenter",event=>{if(hasFiles(event)){event.preventDefault();dragDepth++;dropZone.classList.add("drag-over");}});
dropZone.addEventListener("dragover",event=>{if(hasFiles(event)){event.preventDefault();event.dataTransfer.dropEffect="copy";}});
dropZone.addEventListener("dragleave",event=>{if(hasFiles(event)){dragDepth=Math.max(0,dragDepth-1);if(!dragDepth)resetDragState();}});
dropZone.addEventListener("drop",event=>{
  if(!hasFiles(event))return;
  event.preventDefault();event.stopPropagation();resetDragState();
  const files=Array.from(event.dataTransfer.files);
  const directory=Array.from(event.dataTransfer.items||[]).some(item=>item.webkitGetAsEntry?.()?.isDirectory);
  if(directory){$("status").textContent="请拖入配置文件，不支持文件夹。";return;}
  if(files.length!==1){$("status").textContent="每次请拖入一份设备配置文件。";return;}
  void loadConfigFile(files[0]);
});
window.addEventListener("dragover",event=>{if(hasFiles(event)){event.preventDefault();if(!dropZone.contains(event.target))event.dataTransfer.dropEffect="none";}});
window.addEventListener("drop",event=>{if(hasFiles(event)){event.preventDefault();resetDragState();$("status").textContent="请将配置文件拖入左侧配置文本区域。";}});
document.querySelectorAll("[data-format]").forEach(button=>button.addEventListener("click",()=>{
  if(!exports_)return;const f=button.dataset.format;const blob=new Blob([exports_[f]],{type:{json:"application/json",md:"text/markdown",html:"text/html"}[f]+";charset=utf-8"});const url=URL.createObjectURL(blob);const a=node("a");a.href=url;a.download="network-audit."+f;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}));
$("example").addEventListener("click",()=>{cancelConfigImport();invalidateResults();$("vendor").value="cisco";$("vendor-detection").textContent="Cisco 合成示例；可导入自己的配置自动识别厂商。";$("config").value=`hostname LAB-SW
spanning-tree mode rapid-pvst
vlan 10
 name OFFICE
!
interface GigabitEthernet0/1
 switchport mode trunk
 switchport trunk allowed vlan all
 switchport trunk native vlan 1
 spanning-tree portfast trunk
 spanning-tree bpdufilter enable
 no shutdown
!
ip access-list extended WAN-IN
 permit ip any any
 deny tcp any any eq 23
!
interface GigabitEthernet0/2
 ip address 192.0.2.1 255.255.255.0
 ip access-group WAN-IN in
!
router ospf 1
 router-id 10.255.0.1
 network 10.0.0.0 0.0.0.255 area 0
!
ip http server
ip ssh authentication-retries 10
line vty 0 4
 transport input telnet ssh
 login local
 exec-timeout 0 0
!
`;configSource="Cisco 合成示例";updateConfigMeta();$("status").textContent="已载入 Cisco 合成问题示例（含 STP / OSPF），仅供演示。";});
selectResultTab("findings");allowExports(false);updateConfigMeta();
