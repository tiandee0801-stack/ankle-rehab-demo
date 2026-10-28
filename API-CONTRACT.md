# 脚踝康复 Demo 集成约定

本机 http://127.0.0.1:8843，buildless dist/ 前端，Python 标准库 HTTP + SQLite。只绑定 loopback。无云服务、无 API Key、无实时摄像。所有时间 ISO8601。

## API

- GET /api/health → {ok:true, service:"dee-ankle-rehab", engineAvailable:true, engineBusy:false}
- GET /api/state → {profiles:[], records:[], reviews:[], analyses:[], meta:{version, engineAvailable, engineBusy}}
- POST /api/profiles JSON → 完整 profile 对象；POST /api/profiles/{id} 更新。
- POST /api/records JSON → 完整 record 对象；POST /api/records/{id} 更新（补次日记录）。
- POST /api/reviews JSON → 完整 review 对象。
- POST /api/analyses?recordId=ID&side=left|right&filename=NAME 请求体为原始视频 bytes，Content-Type application/octet-stream → {id,status:"queued",progress:0}。最长30秒、最大80MB；每次仅1个分析任务。
- GET /api/analyses/{id} → analysis 对象，轮询 progress。失败仍有 reason，可重试新任务。
- POST /api/demo-analysis JSON {recordId,side} → 给该记录关联明确标注的“模拟关键点算法样例”，不是人体模型推理；有轨迹和计数，便于无视频演示业务闭环。
- GET /api/report?profileId=ID → {profile,records,reviews,analyses,summary:{recordCount,reviewCount,pendingNextDay,pendingReview,latestDecision},generatedAt}。
- GET /media/{analysisId}/{filename} → 分析生成文件，允许Range，所有路径限定生成目录。
- GET /api/export?profileId=ID → 同 report，JSON下载。

错误统一 {error:"可展示给用户的中文信息"}，4xx/5xx。不要将后端规则摘要说成大模型生成。

## 对象

profile: {id,name,side:"left|right|both",route:"surgery|conservative|unsure",goal,product:"P1|P2|P3",screening:{cleared:boolean,redFlags:boolean,notes:string},isDemo:boolean,createdAt,updatedAt,intakeStatus:"pending|confirmed|deferred"}。示例档案 id=demo-profile。新增档案初始pending，必须人工复核，不自动给康复训练处方。

record: {id,profileId,date,product:"P2",module:"calf-raise",side:"left|right",t0:{pain:0..10,swelling:"none|same|increased",note},t1:{pain,swelling,note},t2:{pain,swelling,note},t3:null|{pain,swelling,note},note,createdAt,updatedAt,candidate:{priority:"Routine|Review|Attention",reasons:[],missingNextDay:boolean},reviewStatus:"pending|reviewed"}。规则仅需复核提示，不是医疗阈值。任意 increased 或pain较t0增加→Review，红旗沿profile→Attention；无t3始终标缺，不设GREEN。t0..t2填写必需，t3可稍后补。所有验证由服务器完成。

review: {id,profileId,recordId?,scope:"intake|record|stage",decision,stageLabel?,comment,reviewer:"Dee",confirmIntake:boolean,recordUpdatedAt,createdAt}。scope=intake用CONFIRM/DEFER，无需recordId；scope=record用ACKNOWLEDGED/NEEDS_INFO；scope=stage才用PASS/HOLD/REGRESS/STOP，阶段固定P2模块3，未填次日不能PASS。说明不能空，历史保留；记录修改或新增分析后旧复核失效，需重新审。confirmIntake或intake操作才确认档案，STOP/DEFER→deferred。阶段决定不会自动解锁训练，缺少T3或未确认可执行范围时拒绝PASS。report.latestDecision仅统计仍对应当前记录版本的stage决定。

analysis: {id,recordId,side,status:"queued|running|completed|failed",progress:0..100,mode:"real_pose|simulated_keypoints",reason?,result?,createdAt}。

result 由 engine 输出统一：{engine,mode,side,duration,fps,analyzedFrames,validFrames,coverage,repCount:null|number,tempoSeconds:null|number,quality:"usable|limited|unusable",warnings:[],series:[{t,heelLift:null|number,confidence,valid}],events:[{start,peak,end}],reviewSegments:[{start,end,reason}],overlayVideo:null|string,poster:null|string,notes:[],modelInfo:{...}}。coverage0..1、heelLift单位是足长归一化像素几何，不是厘米或医学ROM。计数是算法候选，不自动解锁阶段。前端应显眼显示mode，不能以模拟样例证明模型效果。

## 引擎文件边界

engine/analyze_video.py CLI --input PATH --output DIR --side left|right；使用现有 MMPose .venv Python 启动；写 DIR/progress.json 与 DIR/result.json，overlay.mp4（可选）、poster.jpg，stdout只写简洁日志。exit非零视失败。frame和video限制内置。引擎 agent拥有engine/及tests/test_motion.py，主agent负责server.py与持久化。

## 视觉与范围

中文、桌面优先且手机可看。产品叫“Dee · 脚踝恢复实验室”，功能工作台，不做营销落地页。文档与模拟示例来源状态明确。三产品属于同一主项目；仅P2小腿提踵有视觉分析，P1/P3为分层与档案。无疗效、付费用户、医学准确率宣称。记录数据本机保存。前端 agent只写dist/，第三agent只写docs/设计基线和测试建议，避免交叉覆盖。
