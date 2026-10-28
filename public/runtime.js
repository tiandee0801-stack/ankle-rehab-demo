'use strict';
/* GitHub Pages has no Python runtime. Persist interactive example data locally. */
(() => {
 const KEY='dee-ankle-rehab-public-v1';
 let data, versionClock=Date.now(), previewURL;
 const clone=value=>structuredClone(value);
 const now=()=>new Date(versionClock=Math.max(Date.now(),versionClock+1)).toISOString();
 const id=prefix=>prefix+'-'+crypto.randomUUID().replaceAll('-','').slice(0,16);
 const safe=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const ready=(async()=>{
  const response=await fetch('./public-seed.json');
  if(!response.ok)throw new Error('示例数据暂时无法读取，请刷新页面重试。');
  const seed=await response.json();
  try {const saved=JSON.parse(localStorage.getItem(KEY));data=saved&&['profiles','records','reviews','analyses'].every(k=>Array.isArray(saved[k]))?saved:seed;}catch{data=seed;}
 })();
 function text(value,label,max=2000,required=false){if(typeof value!=='string'||value.length>max||required&&!value.trim())throw new Error(label+'未填写或长度超出范围。');return value.trim();}
 function choice(value,list,label){if(!list.includes(value))throw new Error(label+'无效。');return value;}
 function boolean(value,label){if(typeof value!=='boolean')throw new Error(label+'需为勾选状态。');return value;}
 function get(kind,key){const value=data[kind].find(x=>x.id===key);if(!value)throw new Error('找不到这条记录，请刷新后重试。');return value;}
 function save(kind,value){const index=data[kind].findIndex(x=>x.id===value.id);if(index<0)data[kind].push(value);else data[kind][index]=value;return value;}
 function candidate(p,r){
  const reasons=[];let priority='Routine';const flag=message=>{reasons.push(message);if(priority!=='Attention')priority='Review';};
  if(p.screening.redFlags){priority='Attention';reasons.push('筛查中存在需要优先人工确认的信息。');}
  if(!p.screening.cleared)flag('尚未确认可执行范围，请先人工核对。');
  if(p.intakeStatus!=='confirmed')flag('档案尚未经过人工确认。');
  for(const [key,label] of [['t1','训练中'],['t2','训练后'],['t3','次日']])if(r[key]&&(r[key].pain>r.t0.pain||r[key].swelling==='increased'))flag(label+'反馈有增加，需人工复核。');
  if(!r.t3)flag('次日反馈待补齐；当前记录不代表完整训练反应。');
  if(!reasons.length)reasons.push('四时点已记录，仍需人工判断阶段。');
  return {priority,reasons,missingNextDay:!r.t3};
 }
 function phase(value,label){if(!value||typeof value.pain!=='number'||!Number.isFinite(value.pain)||value.pain<0||value.pain>10)throw new Error(label+'自评需为0至10的数字。');return {pain:value.pain,swelling:choice(value.swelling,['none','same','increased'],label+'肿胀变化'),note:text(value.note??'',label+'备注',1000)};}
 function profile(body,old){
  const b={...old,...body},s=b.screening;if(!s)throw new Error('请填写筛查信息。');
  const obj={id:old?.id||id('profile'),name:text(b.name,'称呼',40,true),side:choice(b.side,['left','right','both'],'关注侧'),route:choice(b.route,['surgery','conservative','unsure'],'恢复路线'),goal:text(b.goal,'目标',500,true),product:choice(b.product,['P1','P2','P3'],'服务层级'),screening:{cleared:boolean(s.cleared,'活动范围'),redFlags:boolean(s.redFlags,'优先确认信息'),notes:text(s.notes??'','筛查备注')},isDemo:old?.isDemo||false,createdAt:old?.createdAt||now(),updatedAt:now(),intakeStatus:'pending'};
  const same=old&&['side','route','product','screening'].every(k=>JSON.stringify(old[k])===JSON.stringify(obj[k]));
  if(same)obj.intakeStatus=old.intakeStatus;
  if(old&&!same)for(const r of data.records.filter(r=>r.profileId===old.id)){r.updatedAt=now();r.reviewStatus='pending';}
  return save('profiles',obj);
 }
 function record(body,old){
  const b={...old,...body},p=get('profiles',b.profileId);
  if(p.product!=='P2'||b.product&&b.product!=='P2'||b.module&&b.module!=='calf-raise')throw new Error('当前展开的是P2小腿提踵模块。');
  if(!old&&p.intakeStatus!=='confirmed')throw new Error('请先人工确认档案与参与范围。');
  if(old&&old.profileId!==b.profileId)throw new Error('不能更换已有训练记录的档案。');
  const date=text(b.date,'日期',10,true);if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||Number.isNaN(Date.parse(date))||new Date(date).toISOString().slice(0,10)!==date)throw new Error('请填写有效日期。');
  const obj={id:old?.id||id('record'),profileId:p.id,date,product:'P2',module:'calf-raise',side:choice(b.side,['left','right'],'观察侧'),t0:phase(b.t0,'T0'),t1:phase(b.t1,'T1'),t2:phase(b.t2,'T2'),t3:b.t3==null?null:phase(b.t3,'T3'),note:text(b.note??'','训练备注'),createdAt:old?.createdAt||now(),updatedAt:now(),reviewStatus:'pending'};
  obj.candidate=candidate(p,obj);return save('records',obj);
 }
 function review(body){
  const p=get('profiles',body.profileId),r=body.recordId?get('records',body.recordId):null;
  if(r&&r.profileId!==p.id)throw new Error('训练记录与档案不匹配。');
  const scope=choice(body.scope,['intake','record','stage'],'复核类型'),decision=choice(body.decision,{intake:['CONFIRM','DEFER'],record:['ACKNOWLEDGED','NEEDS_INFO'],stage:['PASS','HOLD','REGRESS','STOP']}[scope],'人工决定');
  if(scope!=='intake'&&!r)throw new Error('请选定作为复核依据的训练记录。');
  if(scope==='stage'&&decision==='PASS'&&!r.t3)throw new Error('请先补齐次日反馈，再保存阶段通过意见。');
  if(['CONFIRM','PASS'].includes(decision)&&(p.screening.redFlags||!p.screening.cleared))throw new Error('筛查信息尚有待核对事项，请先确认可执行范围。');
  if(decision==='PASS'&&p.intakeStatus!=='confirmed'&&!body.confirmIntake)throw new Error('请先人工确认档案。');
  if(body.confirmIntake&&(p.screening.redFlags||!p.screening.cleared)&&!['STOP','DEFER'].includes(decision))throw new Error('请先更新档案或记录暂缓处理。');
  const comment=text(body.comment,'复核依据',3000,true);
  if(body.confirmIntake||scope==='intake'||decision==='STOP'){
   p.intakeStatus=['STOP','DEFER'].includes(decision)?'deferred':'confirmed';p.updatedAt=now();
   if(p.intakeStatus==='deferred')for(const item of data.records.filter(x=>x.profileId===p.id)){item.updatedAt=now();item.reviewStatus='pending';}
  }
  if(r&&scope!=='intake'){r.reviewStatus=decision==='NEEDS_INFO'?'pending':'reviewed';r.candidate=candidate(p,r);}
  return save('reviews',{id:id('review'),profileId:p.id,recordId:r?.id||null,scope,decision,stageLabel:scope==='stage'?'P2 · 模块3 · 小腿提踵能力':null,comment,reviewer:'Dee',confirmIntake:!!body.confirmIntake,recordUpdatedAt:r?.updatedAt||null,createdAt:now()});
 }
 function snapshot(){for(const r of data.records)r.candidate=candidate(get('profiles',r.profileId),r);return clone({...data,meta:{version:'0.1.0-public',engineAvailable:false,engineBusy:false,storage:'browser'}});}
 function report(profileId){
  const s=snapshot(),p=get('profiles',profileId),rs=s.records.filter(r=>r.profileId===p.id),rv=s.reviews.filter(r=>r.profileId===p.id),aa=s.analyses.filter(a=>rs.some(r=>r.id===a.recordId));
  const last=rv.slice().reverse().find(v=>v.scope==='stage'&&(v.decision!=='PASS'||p.intakeStatus==='confirmed')&&rs.some(r=>r.id===v.recordId&&r.updatedAt===v.recordUpdatedAt)&&!rs.some(r=>r.createdAt>v.createdAt));
  return clone({profile:p,records:rs,reviews:rv,analyses:aa,summary:{recordCount:rs.length,reviewCount:rv.length,pendingNextDay:rs.filter(r=>!r.t3).length,pendingReview:rs.filter(r=>r.reviewStatus!=='reviewed').length,latestDecision:last?.decision||null},generatedAt:now(),notice:'浏览器本地交互演示，未运行云端模型。'});
 }
 async function api(path,options={}){
  await ready;const url=new URL(path,location.origin),method=options.method||'GET',body=typeof options.body==='string'?JSON.parse(options.body):options.body||{};
  if(method==='GET'){
   if(url.pathname==='/api/state')return snapshot();
   if(['/api/report','/api/export'].includes(url.pathname))return report(url.searchParams.get('profileId'));
   if(url.pathname.startsWith('/api/analyses/'))return clone(get('analyses',url.pathname.split('/').pop()));
   if(url.pathname==='/api/health')return {ok:true,engineAvailable:false,engineBusy:false};
  }
  if(method==='POST'){
   const before=clone(data);try{
    let result;
    if(url.pathname==='/api/profiles')result=profile(body);
    else if(url.pathname.startsWith('/api/profiles/'))result=profile(body,get('profiles',decodeURIComponent(url.pathname.split('/').pop())));
    else if(url.pathname==='/api/records')result=record(body);
    else if(url.pathname.startsWith('/api/records/'))result=record(body,get('records',decodeURIComponent(url.pathname.split('/').pop())));
    else if(url.pathname==='/api/reviews')result=review(body);
    else throw new Error('在线演示保留预先计算的视频结果；新的模型识别需运行本机版。');
    try{localStorage.setItem(KEY,JSON.stringify(data));}catch{throw new Error('浏览器未能保存记录，请允许本地存储后重试。');}
    return clone(result);
   }catch(error){data=before;throw error;}
  }
  throw new Error('这个操作需要本机版服务。');
 }
 function applyUI(){
  document.querySelectorAll('[data-action="upload-video"]').forEach(b=>b.innerHTML='预览所选视频');
  document.querySelectorAll('[data-action="simulate-analysis"]').forEach(b=>{b.disabled=true;b.title='在线演示不运行算法自检，请使用本机版。';});
  const panel=document.querySelector('.upload-panel');
  if(panel&&!panel.querySelector('.public-runtime-note')){const note=document.createElement('div');note.className='notice public-runtime-note';note.textContent='在线版可以预览本地视频。新的视频不会上传，姿态识别需运行仓库中的Python本机版。';panel.prepend(note);}
 }
 function previewVideo(){
  const f=document.querySelector('#video-file')?.files[0],error=document.querySelector('#upload-error');
  if(!f){error.textContent='请先选择一段本地视频。';return;}
  if(f.size>80*1024*1024){error.textContent='视频超过80MB，请缩短后重试。';return;}
  error.textContent='';if(previewURL)URL.revokeObjectURL(previewURL);previewURL=URL.createObjectURL(f);
  document.querySelector('#analysis-content').innerHTML=`<section class="panel"><h2>所选视频预览</h2><p class="notice">视频仅在当前浏览器播放。未上传、未运行模型，不生成识别次数。</p><video controls playsinline preload="metadata" style="width:100%;max-height:560px" src="${previewURL}"></video><p class="tiny muted">${safe(f.name)}</p></section>`;
 }
 function showAbout(){window.showModal('<h2 class="modal-title">Dee · 脚踝恢复实验室</h2><p class="modal-description">GitHub Pages 在线交互演示</p><div class="notice">档案、训练记录和人工意见保存于当前浏览器。页面使用虚构示例资料，所有访客的数据互不共享。</div><p>可以观看公开真人动作视频及此前在本机生成的MMPose骨架叠加结果。新的视频仅支持浏览器预览；仓库保留完整Python服务和本机模型调用代码。</p><p>预先计算的公开视频观察质量不足、次数为空；本项目尚无真实用户交付或康复效果验证。</p><p><a href="https://github.com/tiandee0801-stack/ankle-rehab-demo" target="_blank" rel="noopener">查看项目源码 ↗</a></p><div class="modal-actions"><button class="button" data-action="close-modal">了解了</button></div>');}
 window.AnklePublic={enabled:true,api,applyUI,previewVideo,showAbout};
})();
