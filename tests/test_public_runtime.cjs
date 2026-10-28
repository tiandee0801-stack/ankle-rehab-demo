'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const {webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..');
const seed=JSON.parse(fs.readFileSync(path.join(root,'public/seed.json')));
const script=fs.readFileSync(path.join(root,'public/runtime.js'),'utf8');
function setup(saved){
 const storage=new Map(saved||[]);
 const ctx={structuredClone,Date,URL,crypto:webcrypto,location:{origin:'https://example.test'},fetch:async()=>({ok:true,json:async()=>structuredClone(seed)}),localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},window:{}};
 vm.createContext(ctx);vm.runInContext(script,ctx);return {api:ctx.window.AnklePublic.api,storage};
}
const point={pain:1,swelling:'same',note:'测试'};
const payload={profileId:'demo-profile',date:'2026-10-27',product:'P2',module:'calf-raise',side:'left',t0:point,t1:point,t2:point,t3:null,note:'自动化测试'};
test('fictional seed preserves actual missing count',async()=>{
 const {api}=setup(),s=await api('/api/state');assert.equal(s.profiles[0].isDemo,true);assert.equal(s.meta.engineAvailable,false);assert.equal(s.analyses[0].mode,'real_pose');assert.equal(s.analyses[0].result.repCount,null);
});
test('missing next-day feedback persists across reload',async()=>{
 const {api,storage}=setup();const r=await api('/api/records',{method:'POST',body:payload});assert.equal(r.t3,null);assert.equal(r.candidate.missingNextDay,true);
 assert.ok((await setup(storage).api('/api/state')).records.some(x=>x.id===r.id));
});
test('PASS requires T3 and record changes invalidate old review',async()=>{
 const {api}=setup();const r=await api('/api/records',{method:'POST',body:payload});
 await assert.rejects(api('/api/reviews',{method:'POST',body:{profileId:r.profileId,recordId:r.id,scope:'stage',decision:'PASS',comment:'测试'}}),/次日反馈/);
 const complete=await api('/api/records/'+r.id,{method:'POST',body:{t3:point}});
 await api('/api/reviews',{method:'POST',body:{profileId:r.profileId,recordId:r.id,scope:'stage',decision:'HOLD',comment:'测试保持'}});
 assert.equal((await api('/api/report?profileId=demo-profile')).summary.latestDecision,'HOLD');
 const changed=await api('/api/records/'+r.id,{method:'POST',body:{t3:{...point,pain:3}}});assert.notEqual(changed.updatedAt,complete.updatedAt);
 assert.equal((await api('/api/report?profileId=demo-profile')).summary.latestDecision,null);
});
test('new or changed profiles require intake confirmation',async()=>{
 const {api}=setup();const p=await api('/api/profiles',{method:'POST',body:{name:'测试档案',side:'left',route:'unsure',goal:'测试',product:'P2',screening:{cleared:true,redFlags:false,notes:''}}});
 assert.equal(p.intakeStatus,'pending');await assert.rejects(api('/api/records',{method:'POST',body:{...payload,profileId:p.id}}),/确认档案/);
 await api('/api/reviews',{method:'POST',body:{profileId:p.id,scope:'intake',decision:'CONFIRM',comment:'已核对',confirmIntake:true}});
 assert.ok((await api('/api/records',{method:'POST',body:{...payload,profileId:p.id}})).id);
 assert.equal((await api('/api/profiles/'+p.id,{method:'POST',body:{screening:{cleared:false,redFlags:true,notes:'待确认'}}})).intakeStatus,'pending');
 await assert.rejects(api('/api/reviews',{method:'POST',body:{profileId:p.id,scope:'intake',decision:'CONFIRM',comment:'测试'}}),/待核对/);
});
test('invalid input rolls back, online model endpoints remain unavailable',async()=>{
 const {api}=setup();const before=await api('/api/state');await assert.rejects(api('/api/records',{method:'POST',body:{...payload,t0:{...point,pain:11}}}),/0至10/);
 assert.equal((await api('/api/state')).records.length,before.records.length);
 await assert.rejects(api('/api/analyses?recordId=demo-record',{method:'POST',body:{}}),/本机版/);
});
