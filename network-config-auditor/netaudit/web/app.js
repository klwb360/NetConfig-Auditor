"use strict";
const $ = id => document.getElementById(id);
let exports_ = null, report_ = null;
const labels = {critical:"严重", high:"高", medium:"中", low:"低", info:"提示"};
function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
function renderFindings() {
  const root = $("findings"); root.replaceChildren(); root.className = "";
  const items = report_.findings.filter(f => $("severity").value === "all" || f.severity === $("severity").value);
  if(!items.length) {root.className="empty";root.append(node("h3","没有符合筛选条件的发现"),node("p","请同时检查配置清单、未建模行与报告适用范围。"));return;}
  for(const f of items) {
    const card=node("article"),meta=node("div",undefined,"meta");
    meta.append(node("span",labels[f.severity],"badge "+f.severity),node("span",f.rule_id),node("span",f.confidence==="needs-review"?"需核对场景":"配置已确认"));
    card.append(meta,node("h3",f.title));
    for(const [label,key] of [["配置问题","problem"],["安全风险","risk"],["修改建议","recommendation"]]) {const p=node("p");p.append(node("strong",label+"："),document.createTextNode(f[key]));card.append(p);}
    if(f.evidence.length) card.append(node("pre",f.evidence.map(e=>`L${e.line}: ${e.text}`).join("\n"),"evidence"));
    if(f.commands.length) {card.append(node("p","建议命令 · 需核对平台版本与管理回退", "confidence"),node("pre",f.commands.join("\n")));}
    root.append(card);
  }
}
$("run").addEventListener("click", async () => {
  $("run").disabled=true;$("status").textContent="正在审计…";exports_=null;report_=null;
  $("exports").hidden=true;$("inventory").hidden=true;
  $("summary").querySelectorAll("strong").forEach(n=>n.textContent="—");
  $("findings").replaceChildren(node("p","正在审计…"));
  try {
    const sessionResponse=await fetch("/api/session",{cache:"no-store"});
    if(!sessionResponse.ok) throw new Error("无法建立本地会话");
    const session=await sessionResponse.json();
    const response=await fetch("/api/audit",{method:"POST",headers:{"Content-Type":"application/json","X-NetAudit-Token":session.token},body:JSON.stringify({vendor:$("vendor").value,config:$("config").value})});
    const value=await response.json();if(!response.ok)throw new Error(value.error||"审计失败");
    report_=value.report;exports_=value.exports;const s=report_.summary;
    const nums=$("summary").querySelectorAll("strong");nums[0].textContent=s.severity.critical+s.severity.high;nums[1].textContent=s.severity.medium+s.severity.low;nums[2].textContent=s.unsupported_lines;
    $("status").textContent=`审计完成 · ${report_.device.vendor} · ${report_.device.hostname} · 识别 ${s.recognized_lines}/${s.relevant_lines} 行`;
    $("exports").hidden=false;$("inventory").hidden=false;$("inventory").querySelector("pre").textContent=JSON.stringify(report_.inventory,null,2);renderFindings();
  } catch(e) {$("status").textContent="审计失败："+e.message;$("findings").replaceChildren(node("p","请检查配置与厂商选项后重试。"));}
  finally {$("run").disabled=false;}
});
$("severity").addEventListener("change",()=>{if(report_)renderFindings();});
$("file").addEventListener("change", async () => {
  const file=$("file").files[0];if(!file)return;
  if(file.size>2*1024*1024){$("status").textContent="文件超过 2 MiB 限制";return;}
  try {$("config").value=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());$("status").textContent="文件已载入，点击开始审计。";}
  catch(e){$("status").textContent="文件必须为 UTF-8 文本。";}
});
document.querySelectorAll("[data-format]").forEach(button=>button.addEventListener("click",()=>{
  if(!exports_)return;const f=button.dataset.format;const blob=new Blob([exports_[f]],{type:{json:"application/json",md:"text/markdown",html:"text/html"}[f]+";charset=utf-8"});const url=URL.createObjectURL(blob);const a=node("a");a.href=url;a.download="network-audit."+f;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}));
$("example").addEventListener("click",()=>{$("vendor").value="cisco";$("config").value=`hostname LAB-SW
vlan 10
 name OFFICE
!
interface GigabitEthernet0/1
 switchport mode trunk
 switchport trunk allowed vlan all
 switchport trunk native vlan 1
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
ip http server
ip ssh authentication-retries 10
line vty 0 4
 transport input telnet ssh
 login local
 exec-timeout 0 0
!
`;$("status").textContent="已载入 Cisco 演示配置。";});
