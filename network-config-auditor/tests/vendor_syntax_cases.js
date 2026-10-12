"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {classifyLines,MAX_CHARS,MAX_LINES} = require("../netaudit/web/vendor-syntax.js");
let checks = 0;
function check(name,run) { run(); checks++; }
const one = (text,vendor="auto",kind="config") => classifyLines(text,{vendor,kind})[0];

check("four explicit vendor markers",() => {
  for(const [text,vendor] of [["Cisco IOS Software, Version 15.2","cisco"],["!Software Version V200R019","huawei"],["H3C Comware Software, Version 7.1","h3c"],["version S29_RGOS 11.4","ruijie"]]) {
    assert.equal(one(text).category,vendor);
    assert.equal(one(text).basis,"marker");
  }
});
check("distinctive command spellings",() => {
  for(const [text,vendor] of [["interface Vlanif10","huawei"],["port trunk allow-pass vlan 10","huawei"],["undo port default vlan","huawei"],["traffic-filter inbound acl 3000","huawei"],["interface Vlan-interface10","h3c"],["port trunk permit vlan 10","h3c"],["packet-filter 3000 inbound","h3c"],["local-user demo class manage","h3c"],["vlan range 10,20","ruijie"]]) assert.equal(one(text).category,vendor);
});
check("IOS commands never establish Cisco alone",() => {
  for(const text of ["hostname LAB","switchport mode trunk","ip access-list extended TEST","ip ssh version 2","no shutdown","configure terminal","show running-config"]) {
    assert.equal(one(text).category,"shared"); assert.deepEqual(one(text).vendors,["cisco","ruijie"]);
  }
});
check("VRP and Comware shared commands",() => {
  for(const text of ["sysname LAB","system-view","undo shutdown","user-interface vty 0 4","display current-configuration","stp enable","acl number 3000","ip route-static 0.0.0.0 0 192.0.2.1"]) {
    assert.equal(one(text).category,"shared"); assert.deepEqual(one(text).vendors,["huawei","h3c"]);
  }
});
check("compatible context colors known shared commands honestly",() => {
  const line=one("switchport mode trunk","ruijie");
  assert.equal(line.category,"ruijie"); assert.equal(line.basis,"context");
  assert.deepEqual(line.vendors,["cisco","ruijie"]); assert.match(line.label,/共享/);
  assert.equal(one("description workstation","h3c").category,"h3c");
});
check("selected vendor does not override foreign syntax",() => {
  assert.equal(one("port trunk permit vlan 20","cisco").category,"h3c");
  assert.equal(one("sysname LAB","cisco").category,"shared");
  assert.equal(one("switchport mode trunk","huawei").category,"shared");
});
check("unknown commands remain neutral with every selected vendor",() => {
  for(const vendor of ["cisco","ruijie","huawei","h3c"]) {
    for(const text of ["made-up-command Cisco","ip invented-option","arbitrary port trunk permit vlan 10","<script>alert(1)</script>"]) assert.equal(one(text,vendor).category,"unknown");
  }
});
check("auto never infers context for the entire document",() => {
  const result=classifyLines("version S29_RGOS 11.4\nhostname LAB\nport trunk allow-pass vlan 10\nport trunk permit vlan 20");
  assert.deepEqual(result.map(line=>line.category),["ruijie","shared","huawei","h3c"]);
});
check("comments and descriptions cannot impersonate commands",() => {
  for(const text of ["! port trunk permit vlan 10","# interface Vlanif10","# Cisco IOS Software, Version 15.2","! arbitrary Huawei Versatile Routing"]) assert.equal(one(text).category,"comment");
  assert.equal(one("description port trunk allow-pass vlan 10").category,"shared");
  assert.deepEqual(one("description port trunk allow-pass vlan 10").vendors,["cisco","huawei","h3c","ruijie"]);
});
check("multiline banner blocks command-like body until delimiter",() => {
  const result=classifyLines("banner motd ^C\ninterface Vlanif10\nversion S29_RGOS 11.4\n^C\nport trunk permit vlan 10");
  assert.deepEqual(result.map(line=>line.category),["shared","comment","comment","comment","h3c"]);
});
check("unterminated banner protects all remaining body",() => {
  assert.deepEqual(classifyLines("banner login %\nCisco IOS Software, Version 15\nport trunk permit vlan 10").map(line=>line.category),["shared","comment","comment"]);
});
check("one-line banner does not consume following commands",() => {
  assert.deepEqual(classifyLines("banner motd %port trunk permit vlan 10%\ninterface Vlanif10").map(line=>line.category),["shared","huawei"]);
});
check("header information body is protected",() => {
  assert.deepEqual(classifyLines("header login information %\nport trunk permit vlan 10\n%\ninterface Vlanif10").map(line=>line.category),["shared","comment","comment","huawei"]);
});
check("Huawei header file reference does not start a multiline body",() => {
  const result=classifyLines("header login information file banner.txt\nport trunk permit vlan 20\nversion S29_RGOS 11.4\ninterface Vlanif10");
  assert.deepEqual(result.map(line=>line.category),["shared","h3c","ruijie","huawei"]);
});
check("Comware header login and motd protect their multiline bodies",() => {
  for(const kind of ["login","motd"]) {
    const result=classifyLines(`header ${kind} %\nCisco IOS Software, Version 15.2\nport trunk allow-pass vlan 10\n%\nport trunk permit vlan 20`,{vendor:"h3c",kind:"commands"});
    assert.deepEqual(result.map(line=>line.category),["shared","comment","comment","comment","h3c"]);
  }
});
check("one-line Comware header ends before following commands",() => {
  assert.deepEqual(classifyLines("header login %interface Vlanif10%\nversion S29_RGOS 11.4").map(line=>line.category),["shared","ruijie"]);
});
check("unterminated Comware header keeps following command text neutral",() => {
  const text="HEADER MOTD #\r\nport trunk allow-pass vlan 10\r\nversion S29_RGOS 11.4";
  const result=classifyLines(text,{vendor:"h3c"});
  assert.deepEqual(result.map(line=>line.category),["shared","comment","comment"]);
  assert.deepEqual(result.map(line=>line.text),text.split("\r\n"));
});
check("case and indentation do not affect known syntax",() => {
  const result=one("\t  PORT TRUNK ALLOW-PASS VLAN 10  ");
  assert.equal(result.category,"huawei"); assert.equal(result.text,"\t  PORT TRUNK ALLOW-PASS VLAN 10  ");
});
check("negation does not falsely unify incompatible families",() => {
  assert.equal(one("no port trunk permit vlan 10").category,"unknown");
  assert.equal(one("undo switchport mode trunk").category,"unknown");
});
check("physical lines preserve whitespace and HTML literally",() => {
  const text=" hostname LAB\r\n\t<script>恶意示例</script>\rdescription A  \n";
  const result=classifyLines(text);
  assert.deepEqual(result.map(line=>line.text),[" hostname LAB","\t<script>恶意示例</script>","description A  ",""]);
  assert.deepEqual(result.map(line=>line.lineNumber),[1,2,3,4]);
  assert.equal(result[3].category,"blank");
});
check("command mode is a visual hint, never an execution verdict",() => {
  for(const text of ["show running-config","display current-configuration","write memory","save"]) {
    const result=one(text,"auto","commands");
    assert.equal(result.category,"shared");
    assert.ok(!Object.hasOwn(result,"safe")); assert.ok(!Object.hasOwn(result,"executable"));
  }
});
check("only explicit valid vendor names supply context",() => {
  for(const vendor of ["__proto__","constructor",[],null,"auto","CISCO"]) assert.equal(one("hostname LAB",vendor).category,"shared");
});
check("returned line candidate arrays are independent",() => {
  const result=classifyLines("hostname LAB\nhostname LAB");
  result[0].vendors.push("bogus");
  assert.deepEqual(result[1].vendors,["cisco","ruijie"]);
  assert.deepEqual(one("hostname LAB").vendors,["cisco","ruijie"]);
});
check("size limit accepts boundary and rejects excess",() => {
  assert.equal(classifyLines("x".repeat(MAX_CHARS)).length,1);
  assert.throws(()=>classifyLines("x".repeat(MAX_CHARS+1)),RangeError);
  assert.throws(()=>classifyLines(null),TypeError);
});
check("30000 physical lines accept trailing newline without off-by-one",() => {
  assert.equal(classifyLines("!\n".repeat(MAX_LINES)).length,MAX_LINES+1);
  assert.throws(()=>classifyLines("!\n".repeat(MAX_LINES+1)),RangeError);
});
check("repository synthetic examples classify without claiming safety",() => {
  for(const vendor of ["cisco","ruijie","huawei","h3c"]) {
    const text=fs.readFileSync(path.join(__dirname,"..","examples",vendor+".cfg"),"utf8");
    const result=classifyLines(text,{vendor});
    assert.ok(result.some(line=>line.category===vendor));
    assert.ok(result.every(line=>typeof line.label==="string" && !Object.hasOwn(line,"safe")));
  }
});
check("browser global needs neither DOM nor network",() => {
  const source=fs.readFileSync(path.join(__dirname,"..","netaudit","web","vendor-syntax.js"),"utf8");
  const context=vm.createContext({});vm.runInContext(source,context);
  assert.equal(context.NetAuditVendorSyntax.classifyLines("port trunk permit vlan 10")[0].category,"h3c");
});
process.stdout.write(JSON.stringify({all_passed:true,checks})+"\n");
