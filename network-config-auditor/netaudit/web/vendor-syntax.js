/* Local visual syntax hints. This is not a command validator or vendor detector. */
"use strict";
((root, factory) => {
  const api = factory();
  if(typeof module === "object" && module.exports) module.exports = api;
  else root.NetAuditVendorSyntax = api;
})(typeof globalThis === "object" ? globalThis : this, () => {
  const MAX_CHARS = 2 * 1024 * 1024, MAX_LINES = 30000;
  const names = Object.freeze({cisco:"Cisco",huawei:"Huawei",h3c:"H3C",ruijie:"Ruijie"});
  const ALL = Object.freeze(["cisco","huawei","h3c","ruijie"]);
  const IOS = Object.freeze(["cisco","ruijie"]), VRP = Object.freeze(["huawei","h3c"]);

  // Deliberately narrower than parser.detect_vendor: IOS/RGOS and VRP/Comware
  // have shared commands. A keyword match never proves exclusive device support.
  const markers = [
    [/^version\s+\S*RGOS(?:\s|$)/i,"ruijie","RGOS 版本标记"],
    [/^(?:!\s*)?Cisco IOS(?: XE)? Software(?:\s|,|$)/i,"cisco","Cisco IOS 软件标记"],
    [/^(?:!\s*)?Cisco Nexus Operating System(?:\s|$)/i,"cisco","Cisco 软件标记"],
    [/^!Command:\s*(?:show\s+running-config|show\s+startup-config)(?:\s|$)/i,"cisco","Cisco 配置输出头标记"],
    [/^!Software Version(?:\s|$)/i,"huawei","Huawei 配置版本头标记"],
    [/^(?:Huawei )?Versatile Routing Platform Software(?:\s|,|$)/i,"huawei","Huawei VRP 软件标记"],
    [/^H3C Comware (?:Platform )?Software(?:\s|,|$)/i,"h3c","H3C Comware 软件标记"],
  ];
  const rules = [
    // Distinctive spellings already handled by the repository's parser/model.
    [/^interface\s+Vlanif\s*\d+(?:\s|$)/i,["huawei"]],
    [/^port\s+(?:trunk\s+allow-pass\s+vlan|default\s+vlan|hybrid\s+(?:tagged|untagged)\s+vlan)(?:\s|$)/i,["huawei"]],
    [/^vlan\s+batch(?:\s|$)/i,["huawei"]],
    [/^traffic-filter\s+(?:inbound|outbound)(?:\s|$)/i,["huawei"]],
    [/^stelnet\s+server(?:\s|$)/i,["huawei"]],
    [/^authentication-mode\s+aaa$/i,["huawei"]],
    [/^interface\s+Vlan-interface\s*\d+(?:\s|$)/i,["h3c"]],
    [/^port\s+(?:trunk\s+permit\s+vlan|access\s+vlan)(?:\s|$)/i,["h3c"]],
    [/^packet-filter\s+\S+\s+(?:inbound|outbound)(?:\s|$)/i,["h3c"]],
    [/^local-user\s+\S+\s+class\s+manage(?:\s|$)/i,["h3c"]],
    [/^acl\s+(?:basic|advanced)(?:\s|$)/i,["h3c"]],
    [/^authentication-mode\s+scheme$/i,["h3c"]],
    [/^irf\s+(?:member|domain|priority|port|auto-update|mac-address|link-delay|fabric)(?:\s|$)/i,["h3c"]],
    [/^vlan\s+range(?:\s|$)/i,["ruijie"]],
    [/^spanning-tree\s+bpdufilter\s+(?:enabled|disabled)$/i,["ruijie"]],
    // IOS / RGOS family. Do not label hostname/switchport as Cisco-exclusive.
    [/^(?:hostname|snmp-server|username|enable\s+(?:password|secret)|service\s+(?:password-encryption|tcp-keepalives-in|tcp-keepalives-out))(?:\s|$)/i,IOS],
    [/^(?:configure\s+terminal|conf\s+t|enable|end|exit)$/i,IOS],
    [/^switchport(?:\s+(?:mode|access\s+vlan|trunk\s+(?:allowed|native)\s+vlan|protected))?(?:\s|$)/i,IOS],
    [/^ip\s+(?:access-list|access-group|nat|ssh|http\s+(?:server|secure-server)|route|source-route|source\s+routing)(?:\s|$)/i,IOS],
    [/^(?:spanning-tree|router\s+ospf|line\s+vty|access-list|access-class|transport\s+input|login|exec-timeout)(?:\s|$)/i,IOS],
    [/^(?:passive-interface|router-id)(?:\s|$)/i,IOS],
    [/^(?:show\s+(?:running-config|startup-config|vlan|interfaces?|ip\s+(?:interface|route|access-lists)|access-lists)|write\s+memory|copy\s+running-config\s+startup-config)(?:\s|$)/i,IOS],
    // VRP / Comware family. Both accept sysname, undo and system-view.
    [/^(?:sysname|user-interface|snmp-agent|local-user|ip\s+route-static|ospf|info-center)(?:\s|$)/i,VRP],
    [/^(?:system-view|quit|return|save)$/i,VRP],
    [/^port\s+(?:link-type|trunk\s+pvid\s+vlan)(?:\s|$)/i,VRP],
    [/^(?:stp|protocol\s+inbound|idle-timeout|authentication-mode|http\s+(?:server|secure-server)|telnet\s+server|ssh\s+server|ip\s+https?\s+enable)(?:\s|$)/i,VRP],
    [/^(?:acl\s+(?:number\s+)?\d+|acl\s+\d+\s+(?:inbound|outbound)|rule\s+\d+|nat\s+(?:outbound|server|address-group))(?:\s|$)/i,VRP],
    [/^display\s+(?:current-configuration|saved-configuration|vlan|interface|ip\s+(?:interface|routing-table)|acl)(?:\s|$)/i,VRP],
    // Generic statements retain their candidate set even when context is used.
    [/^(?:interface|description|name|version)\s+\S/i,ALL],
    [/^vlan\s+\d+(?:\s|$)/i,ALL],
    [/^(?:shutdown|ip\s+address(?:\s+\S.*)?|ip\s+vrf\s+forwarding\s+\S.*|vrf\s+forwarding\s+\S.*)$/i,ALL],
    [/^(?:network|area)\s+\S/i,ALL],
    [/^(?:\d+\s+)?(?:permit|deny|remark)(?:\s|$)/i,IOS],
  ];
  const hints = (category, vendors, label, reason, basis="neutral") => ({category,vendors:[...vendors],label,reason,basis});

  function commandHint(text, selected) {
    let body = text, inverse = null;
    if(/^no\s+/i.test(body)) { inverse = IOS; body = body.replace(/^no\s+/i,""); }
    else if(/^undo\s+/i.test(body)) { inverse = VRP; body = body.replace(/^undo\s+/i,""); }
    let candidates = null;
    for(const [pattern, vendors] of rules) {
      if(pattern.test(body)) { candidates = vendors; break; }
    }
    if(!candidates) return hints("unknown",[],"未识别","当前高亮规则未识别此行；不代表设备不支持。");
    if(inverse) candidates = candidates.filter(vendor => inverse.includes(vendor));
    if(!candidates.length) return hints("unknown",[],"未识别","否定形式与已识别语法家族不一致，未推断厂商。");
    if(candidates.length === 1) {
      const vendor = candidates[0];
      return hints(vendor,candidates,names[vendor] + " 语法线索","匹配已建模的 " + names[vendor] + " 命令写法；颜色不代表可执行或安全。","syntax");
    }
    const family = candidates.length === 4 ? "通用" : candidates.map(vendor => names[vendor]).join(" / ");
    if(selected && candidates.includes(selected)) {
      return hints(selected,candidates,names[selected] + " 上下文·共享语法",family + " 共享语法，按当前厂商显示；不能据此独立判断厂商、可执行性或安全性。","context");
    }
    return hints("shared",candidates,family + " 共享语法","多厂商共享此写法，未据此指定单一厂商。","syntax");
  }

  function classifyLines(config, options={}) {
    if(typeof config !== "string") throw new TypeError("配置文本必须为字符串");
    if(config.length > MAX_CHARS) throw new RangeError("高亮仅处理最多 2 Mi 字符的文本");
    const lines = config.split(/\r\n|[\n\r]/);
    const physicalCount = lines.length - (lines.length > 1 && lines.at(-1) === "" ? 1 : 0);
    if(physicalCount > MAX_LINES) throw new RangeError("高亮仅处理最多 30000 行");
    const selected = options && Object.hasOwn(names,options.vendor) ? options.vendor : null;
    let banner = null;
    // Repeated commands are common in large backups. Cache metadata, never line
    // objects: text and line numbers must stay exact and independently editable.
    const cache = new Map();
    return lines.map((text,index) => {
      const command = text.trim();
      let hint;
      if(banner !== null) {
        hint = hints("comment",[],"Banner 正文","登录提示正文，不作为配置命令识别。");
        if(command.includes(banner)) banner = null;
      } else if(!command) {
        hint = hints("blank",[],"空行","");
      } else {
        // Comware uses "header login %" / "header motd %"; VRP also
        // accepts the "information" keyword. Both protect multiline bodies.
        const opening = /^(banner\s+\S+|header\s+(?:login|shell|legal|incoming|motd)(?:\s+information)?)\s+(.+)$/i.exec(command);
        if(opening) {
          const value = opening[2], delimiter = value.startsWith("^") ? value.slice(0,2) : value[0];
          const fileReference = /^header\s+\S+\s+information$/i.test(opening[1]) && /^file\s+\S/i.test(value);
          if(!fileReference && !value.slice(delimiter.length).includes(delimiter)) banner = delimiter;
          hint = hints("shared",/^banner\s/i.test(command) ? IOS : VRP,"登录提示定义","提示正文中的厂商词或指令不参与识别。","syntax");
        } else {
          for(const [pattern,vendor,reason] of markers) {
            if(pattern.test(command)) { hint = hints(vendor,[vendor],names[vendor] + " 标记",reason,"marker"); break; }
          }
          if(!hint && /^[!#]/.test(command)) hint = hints("comment",[],"注释","注释中的指令文字不参与厂商识别。");
          if(!hint) {
            hint = cache.get(command);
            if(!hint) { hint = commandHint(command,selected); cache.set(command,hint); }
          }
        }
      }
      return {lineNumber:index + 1,text,...hint,vendors:[...hint.vendors]};
    });
  }
  // Presentation only: do not replace per-line categories or infer that an
  // unrecognized command is compatible, executable, or safe. Shared syntax
  // alone cannot establish a vendor without the user's explicit context.
  function presentationForLines(lines,options={}) {
    const selected = options && Object.hasOwn(names,options.vendor) ? options.vendor : null;
    let candidates = [...ALL], recognized = 0, unknown = 0;
    const established = new Set();
    for(const line of lines) {
      if(line.category === "unknown") {unknown++;continue;}
      if(line.category === "comment" || line.category === "blank" || !line.vendors.length) continue;
      recognized++;
      candidates = candidates.filter(vendor => line.vendors.includes(vendor));
      if(line.vendors.length === 1) established.add(line.vendors[0]);
    }
    const singleVendor = !recognized ? null : selected
      ? (candidates.includes(selected) ? selected : null)
      : (candidates.length === 1 && established.has(candidates[0]) ? candidates[0] : null);
    return {suppressColors:singleVendor !== null,singleVendor,candidates,recognized,unknown};
  }
  return Object.freeze({classifyLines,presentationForLines,MAX_CHARS,MAX_LINES});
});
