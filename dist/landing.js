'use strict';
let landingProduct = 'P2';
let landingFeature = 'records';
let pendingLandingSection = null;

const pathwayContent = {
 P1: { title:'先从日常生活，找回稳定的起点。', desc:'把当前情况、基本活动感受和恢复目标记录下来，明确需要先确认的问题。', points:['了解个人恢复路线与活动范围','留下承重、步行和日常活动的观察记录','根据反馈，由人工确认后续服务路径'], label:'基础复训', status:'产品分层设计', action:'查看筛查与档案', target:'profile' },
 P2: { title:'把运动能力，拆成可以观察的变化。', desc:'从小腿提踵这一具体场景开始，连接动作视频、训练感受和次日反应，让人工复核有据可依。', points:['同一次训练关联 T0–T3 四时点反馈','视频关键点、候选轨迹与质量提示','人工复核后，形成可回看的模块记录'], label:'运动能力重建', status:'本版已展开 · 小腿提踵能力', action:'体验小腿提踵观察', target:'motion' },
 P3: { title:'围绕你的运动目标，持续记录与复盘。', desc:'将个人目标、阶段变化和反馈放回更长的恢复路径中，作为后续陪跑服务的设计方向。', points:['面向个体运动目标设计后续路径','持续积累训练与阶段反馈','专项服务内容与交付方式待进一步验证'], label:'重返运动陪跑', status:'产品分层设计', action:'了解三层产品', target:'profile' }
};

let calfSource = 'overlay';
function featureScreenshot(name,label,route,portrait=false) {
 return `<a class="real-screen-link ${portrait?'portrait':''}" href="#${route}" aria-label="打开${label}"><img src="./assets/screens/${name}.png?v=20261028-real" alt="${label}的实际功能页面，内置示例数据" loading="lazy"><span>实际功能截图 · 打开${label} ↗</span></a>`;
}
function calfMedia() {
 const overlay=calfSource==='overlay';
 return `<div class="real-video-preview"><div class="real-preview-topline"><strong>小腿运动 · 视频观察</strong><span>本机分析</span></div><div class="calf-source-tabs" role="group" aria-label="切换视频画面"><button data-action="calf-source" data-source="source" aria-pressed="${!overlay}">原视频</button><button data-action="calf-source" data-source="overlay" aria-pressed="${overlay}">MMPose 骨架叠加</button></div><video id="calf-demo-video" controls playsinline preload="metadata" ${overlay?'poster="./assets/calf/poster.jpg"':''} src="./assets/calf/${overlay?'overlay':'source'}.mp4"></video><div class="real-result-note"><span class="result-dot"></span><div><strong>观察质量不足，保留原视频供人工复核</strong><small>本次不生成次数 · 有效观察帧 22.1%</small></div></div><p class="media-credit">公开视频测试素材：Explosive Calf Raise，Capt. Matthew Holfinger / USMC，<a href="https://www.dvidshub.net/video/636502/explosive-calf-raise" target="_blank" rel="noopener">DVIDS 来源 ↗</a>。用于算法观察测试，未作为康复教学或用户案例。<a href="./assets/calf/SOURCE-LICENSE.txt" target="_blank" rel="noopener">来源与使用说明</a></p><p class="media-credit">The appearance of U.S. Department of War (DoW) visual information does not imply or constitute DoW endorsement.</p></div>`;
}
function heroProductPreview() {
 return `<div class="hero-preview real-hero"><div id="calf-media">${calfMedia()}</div></div>`;
}
function renderPathwayPanel() {
 const d=pathwayContent[landingProduct];
 return `<div class="pathway-copy real-pathway-copy"><span class="section-kicker">${landingProduct} · ${d.label}</span><span class="pathway-status">${d.status}</span><h3>${d.title}</h3><p>${d.desc}</p><ul>${d.points.map(t=>`<li>${icon('check')}<span>${t}</span></li>`).join('')}</ul>${pageLink(d.target,d.action,'')}<small>${landingProduct==='P2'?'本版可实际上传视频、查看轨迹与人工复核；真人标准提踵计数仍待合适录像验证。':'当前展示服务分层，尚未实现该层全部课程与交付。'}</small></div>`;
}
function renderFeatureShowcase() {
 const definitions={records:['四时点反馈','同一次训练的 T0–T3','在下面展开完整记录，或切到填写表单。保存内容会进入本机档案。'],motion:['小腿提踵观察','上传、分析、查看与复核','接入本机 MMPose / RTMPose。可选择自己的视频，历史结果保留来源。'],review:['人工复核','把观察与感受放在一起看','可以切换单次记录与阶段复核，填写依据并保存。'],report:['阶段报告','把当前档案整理成完整记录','直接读取本机档案，支持查看、导出与打印。']};
 const [label,title,desc]=definitions[landingFeature];
 const renderers={records:renderRecords,motion:renderMotion,review:renderReview,report:renderReport};
 const content=renderers[landingFeature]().replace(/<h1>/g,'<h3>').replace(/<\/h1>/g,'</h3>');
 return `<div class="live-feature-intro"><div><span class="section-kicker">${label}</span><h3>${title}</h3><p>${desc}</p></div>${pageLink(landingFeature,'打开完整工作台','secondary small')}</div><div class="live-workspace">${content}</div>`;
}

function currentWorkspace() {
 const p=profile(),rs=records(),missing=rs.filter(r=>!r.t3).length,pending=rs.filter(r=>r.reviewStatus!=='reviewed').length,stage=latestStage();
 if(!p)return `<section class="landing-section current-workspace" id="current-workspace"><div class="landing-container">${empty('从第一份档案开始','先记录当前情况，再由人工确认参与范围。','<button class="button" data-action="new-profile">建立我的档案</button>')}</div></section>`;
 return `<section class="landing-section current-workspace" id="current-workspace"><div class="landing-container"><div class="workspace-title"><div><span class="section-kicker">YOUR RECOVERY WORKSPACE</span><h2>回到你的<span class="highlight">恢复记录。</span></h2><p>${esc(p.name)} · ${esc(p.product)} ${esc(products[p.product])}${p.isDemo?' · 模拟示例档案':''}</p></div>${pageLink('profile','查看 / 切换档案','secondary')}</div><div class="stats-row" aria-label="当前档案统计"><div class="stat"><div class="stat-title">训练记录</div><div class="stat-value">${rs.length}<span>次</span></div><div class="stat-sub">每次训练关联四个时点</div></div><div class="stat"><div class="stat-title">待补次日反馈</div><div class="stat-value">${missing}<span>条</span></div><div class="stat-sub">缺项持续保留为待办</div></div><div class="stat"><div class="stat-title">待人工复核</div><div class="stat-value">${pending}<span>条</span></div><div class="stat-sub">信息更新后重新复核</div></div><div class="stat"><div class="stat-title">当前阶段意见</div><div class="stat-value stage-value">${esc(stage?decisionName(stage.decision):'等待复核')}</div><div class="stat-sub">由人工提交与确认</div></div></div><div class="workspace-lower"><div class="workspace-latest"><h3>最近的训练</h3>${rs.slice(0,2).map(r=>`<div class="record-row"><div><strong>${esc(r.date)} · 小腿提踵</strong><p>${sideName(r.side)}观察 · ${r.t3?'四个时点已记录':'等待次日反馈'}</p></div><button class="button secondary small" data-action="review-record" data-id="${esc(r.id)}">查看记录 ↗</button></div>`).join('')||'<p class="muted">还没有训练记录，可以从今天开始。</p>'}</div><div class="workspace-next"><span>${icon('arrow')}</span><h3>接下来，可以做什么？</h3><p>${!currentIntake()?'先确认档案与参与范围。':missing?'补齐次日反应，再进行人工复核。':pending?'把视频观察与训练感受一起复核。':'查看阶段报告，保留待确认的下一步。'}</p>${pageLink(!currentIntake()?'profile':missing?'records':pending?'review':'report','前往查看','secondary')}</div></div></div></section>`;
}

function renderLanding() {
 return `<div class="landing">
<section class="landing-hero landing-container"><div class="hero-copy"><div class="hero-proof"><span>个人康复项目</span><i></i><span>分层服务设计</span><i></i><span>人工最终复核</span></div><h1>从每一次记录，<br><span class="highlight">走向更清晰的</span><br>恢复之路。</h1><p>连接你的训练感受、动作视频和人工反馈。Dee 脚踝恢复实验室，让每一步的变化都能被记录、被看见、被认真复核。</p><div class="hero-buttons"><button class="button" data-action="new-record">开始记录 ${icon('arrow')}</button><button class="button secondary" data-action="home-section" data-section="product-pathways">了解产品路径</button></div></div>${heroProductPreview()}</section>
<div class="proof-strip"><div class="landing-container"><span>一条完整的恢复记录</span><strong>${icon('profile')} 筛查建档</strong><strong>${icon('records')} 四时点反馈</strong><strong>${icon('motion')} 视频观察</strong><strong>${icon('review')} 人工复核</strong><strong>${icon('report')} 阶段记录</strong></div></div>
<section class="landing-section capabilities" id="product-capabilities"><div class="landing-container"><div class="landing-heading"><span class="section-kicker">BUILT AROUND YOUR RECOVERY</span><h2>让经验，变成<span class="highlight">可追踪的过程。</span></h2><p>记录、观察与人的判断，在同一条路径中连接。</p></div><div class="feature-grid"><article class="feature-card"><div class="feature-copy"><h3>了解你的起点</h3><p>保留恢复路线、当前目标与待确认的范围。</p><a href="#profile">查看档案 ${icon('arrow')}</a></div><div class="feature-visual profile-feature">${featureScreenshot('profile','筛查与档案','profile')}</div></article><article class="feature-card reverse"><div class="feature-copy"><h3>连接每次反馈</h3><p>从训练前到次日，信息属于同一次训练。</p><a href="#records">记录训练 ${icon('arrow')}</a></div><div class="feature-visual feedback-feature">${featureScreenshot('records','训练记录','records')}</div></article><article class="feature-card"><div class="feature-copy"><h3>看清动作变化</h3><p>把视频观察，放进完整的反馈与复核流程。</p><a href="#motion">体验提踵观察 ${icon('arrow')}</a></div><div class="feature-visual motion-feature">${featureScreenshot('upload','视频上传与分析','motion',true)}</div></article></div></div></section>
<section class="landing-section pathways" id="product-pathways"><div class="landing-container"><div class="landing-heading align-left"><span class="section-kicker">ONE PROJECT, THREE PATHWAYS</span><h2>从你的起点出发，<br>找到<span class="highlight">适合的恢复路径。</span></h2><p>三个服务层级属于同一个脚踝项目；路径根据实际情况和人工复核确认。</p></div><div class="pathway-shell"><div class="pathway-tabs" role="tablist" aria-orientation="vertical" aria-label="三层产品路径">${Object.entries(pathwayContent).map(([key,d])=>`<button role="tab" id="path-tab-${key}" aria-controls="pathway-panel" aria-selected="${key===landingProduct}" data-action="select-pathway" data-product="${key}" tabindex="${key===landingProduct?0:-1}"><span>${key}</span><div><strong>${d.label}</strong><small>${key==='P1'?'基本生活与活动起点':key==='P2'?'力量、稳定与协同':'围绕个体运动目标'}</small></div><b>↗</b></button>`).join('')}<div class="pathway-help"><strong>还不确定从哪里开始？</strong><p>先记录当前情况，再确认参与范围。</p>${pageLink('profile','建立档案','secondary small')}</div></div><div class="pathway-content" id="pathway-panel" role="tabpanel" tabindex="0" aria-labelledby="path-tab-${landingProduct}">${renderPathwayPanel()}</div></div></div></section>
<section class="landing-section how-it-works" id="how-it-works"><div class="landing-container"><div class="landing-heading"><span class="section-kicker">HOW IT WORKS</span><h2>从记录开始，<span class="highlight">把流程走通。</span></h2></div><div class="real-steps">${[['01','建立档案','填写恢复路线、目标和参与范围，进入人工确认。','profile'],['02','记录与上传','关联四时点反馈，提交视频并查看模型输出。','motion'],['03','人工复核','把记录、视频和次日反馈一起复核，保留阶段依据。','review']].map(([n,t,d,to])=>`<a class="real-step" href="#${to}"><span>STEP ${n}</span><h3>${t}</h3><p>${d}</p><strong>进入功能 ${icon('arrow')}</strong></a>`).join('')}</div></div></section>
<section class="landing-section feature-showcase" id="feature-showcase"><div class="landing-container"><div class="landing-heading"><span class="section-kicker">ONE WORKSPACE. CONNECTED INFORMATION.</span><h2>直接操作，<span class="highlight">体验完整流程。</span></h2><p>下方就是已接通本机数据的功能区，可以直接展开、填写和切换。</p></div><div class="showcase-tabs" role="tablist" aria-label="功能预览">${[['records','四时点记录'],['motion','提踵观察'],['review','人工复核'],['report','阶段报告']].map(([k,t])=>`<button role="tab" id="feature-tab-${k}" aria-controls="feature-panel" aria-selected="${k===landingFeature}" data-action="select-feature" data-feature="${k}" tabindex="${k===landingFeature?0:-1}">${icon(k)} ${t}</button>`).join('')}</div><div class="workspace-preview is-live" id="feature-panel" role="tabpanel" tabindex="0" aria-labelledby="feature-tab-${landingFeature}">${renderFeatureShowcase()}</div></div></section>
${currentWorkspace()}
<section class="landing-section landing-faq" id="frequently-asked"><div class="landing-container faq-layout"><div class="landing-heading align-left"><span class="section-kicker">A FEW THINGS TO KNOW</span><h2>关于这份<span class="highlight">恢复记录。</span></h2><p>在开始之前，把使用方式和当前能力说清楚。</p><button class="button secondary" data-action="about">了解这个项目 ${icon('arrow')}</button></div><div class="faq-list">${[['现在可以体验哪些功能？','可以建立和查看档案、填写四时点训练记录、在产品2上传提踵观察视频、记录人工复核意见，以及查看和导出阶段报告。产品1和产品3目前展示服务分层。'],['视频里的 AI 负责什么？','预训练姿态模型提取人体关键点，后处理整理图像轨迹、候选次数和质量提示。观察不足时不强行给出次数；阶段意见由人工确认。'],['为什么还有一个模拟样例？','模拟关键点用于演示计数逻辑与业务流程，页面会始终标明来源。真实视频推理已经接通，真人标准提踵计数仍需要合适录像和人工标注验证。'],['一定要当天填完全部反馈吗？','可以先保存 T0、T1、T2，再补同一次训练的次日 T3。缺失信息会保留为待办，补填或修改后重新进入待复核。'],['我的记录和视频保存在哪里？','本版在这台 Mac 上运行，记录与上传视频保存在本机。无需申请云端账号；服务关闭后，已保存的数据仍保留。'],['这个 Demo 已经向真实用户交付了吗？','目前还没有。这是依据既有产品文档搭建的功能原型，用于验证流程和展示产品思路，不代表已验证康复效果，也不提供诊断或自动训练进阶。']].map(([q,a])=>`<details><summary>${q}<span aria-hidden="true">＋</span></summary><p>${a}</p></details>`).join('')}</div></div></section>
<section class="landing-cta"><div class="landing-container"><span class="section-kicker">MAKE THE NEXT STEP CLEARER</span><h2>从一份记录开始，<br>让下一步更清楚。</h2><p>把感受、动作和反馈，放回完整的恢复过程。</p><div class="button-row"><button class="button" data-action="new-profile">建立我的档案 ${icon('arrow')}</button><button class="button secondary" data-action="demo-guide">查看演示路线</button></div></div></section>
</div>`;
}

function showLandingSection(id) {
 if(view!=='overview'){pendingLandingSection=id;navigate('overview');return;}
 document.getElementById(id)?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
}

function selectLandingTab(group,value) {
 if(group==='pathway'){
  if(!pathwayContent[value])return;
  landingProduct=value;
  document.querySelectorAll('[data-action="select-pathway"]').forEach(b=>{const yes=b.dataset.product===value;b.setAttribute('aria-selected',String(yes));b.tabIndex=yes?0:-1;});
  const p=document.getElementById('pathway-panel');p.innerHTML=renderPathwayPanel();p.setAttribute('aria-labelledby','path-tab-'+value);
 } else {
  if(!['records','motion','review','report'].includes(value))return;
  landingFeature=value;
  document.querySelectorAll('[data-action="select-feature"]').forEach(b=>{const yes=b.dataset.feature===value;b.setAttribute('aria-selected',String(yes));b.tabIndex=yes?0:-1;});
  const p=document.getElementById('feature-panel');p.innerHTML=renderFeatureShowcase();p.setAttribute('aria-labelledby','feature-tab-'+value);clearTimeout(pollTimer);bindPage();window.AnklePublic?.applyUI();afterRenderFunctional();
 }
}
