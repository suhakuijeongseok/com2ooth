const state={players:[],pitcher:null,phase:"idle",pitch:null,startedAt:0,duration:0,frame:0,spriteTimer:0,spritePose:0,sequenceStartedAt:0,effectTimers:[],hits:0,misses:0,streak:0,best:0,targetX:0,targetY:0,releaseX:0,releaseY:0,ballX:0,ballY:0,ballScale:.38,trail:[]};
const $=id=>document.getElementById(id);
const ui={select:$("selectScreen"),game:$("gameScreen"),stage:$("gameStage"),pitcher:$("pitcherFigure"),grid:$("pitcherGrid"),name:$("pitcherName"),season:$("seasonLabel"),ball:$("ball"),trail:$("ballTrail"),bat:$("bat"),action:$("actionButton"),status:$("status"),last:$("lastPitch"),arsenal:$("arsenal"),hits:$("hitCount"),misses:$("missCount"),best:$("bestScore"),needle:$("timingNeedle"),burst:$("contactBurst"),result:$("resultFlash")};
const setAction=label=>{ui.action.querySelector("b").textContent=label};
const movements={
  "4seam":{x:0,y:-7,onset:.38},
  "2seam":{x:-42,y:14,onset:.25},
  cutt:{x:34,y:5,onset:.34},
  slid:{x:78,y:28,onset:.22},
  curv:{x:-18,y:62,onset:.18},
  chan:{x:-45,y:36,onset:.24},
  fork:{x:6,y:70,onset:.32},
  splt:{x:5,y:66,onset:.32},
  sinker:{x:-52,y:44,onset:.22},
  other:{x:0,y:12,onset:.3}
};
const underhandMovements={
  "4seam":{x:-10,y:55,onset:.18},
  "2seam":{x:-18,y:64,onset:.16},
  cutt:{x:34,y:-18,onset:.24},
  slid:{x:58,y:-36,onset:.2},
  curv:{x:28,y:-20,onset:.18},
  chan:{x:-22,y:58,onset:.2},
  fork:{x:0,y:78,onset:.25},
  splt:{x:0,y:74,onset:.25},
  sinker:{x:-14,y:70,onset:.15},
  other:{x:0,y:38,onset:.2}
};
const MOUND_TO_PLATE_METERS=18.44;
const GAMEPLAY_FLIGHT_TIME_SCALE=1.22;
const VELOCITY_REFERENCE_KMH=145;
const VELOCITY_DIFFERENCE_EXPONENT=.65;
const MIN_FLIGHT_TIME_MS=500;
const MAX_FLIGHT_TIME_MS=850;
const HORIZONTAL_BREAK_SCALE=1.2;
const VERTICAL_BREAK_PERCENT_SCALE=.105;
const WINDUP_DURATION_MS=1050;
const FOLLOW_THROUGH_DURATION_MS=500;
const CONTACT_PROGRESS=.91;
const PERFECT_WINDOW_MS=50;
const HIT_WINDOW_MS=115;
const BATTED_BALL_DURATION_MS=420;
const RESULT_DISPLAY_MS=850;
function flightDurationForVelocity(velocityKmh){const velocity=Math.max(80,Number(velocityKmh)||135),physical=MOUND_TO_PLATE_METERS/(velocity/3.6)*1000,emphasis=Math.pow(VELOCITY_REFERENCE_KMH/velocity,VELOCITY_DIFFERENCE_EXPONENT);return Math.min(MAX_FLIGHT_TIME_MS,Math.max(MIN_FLIGHT_TIME_MS,physical*GAMEPLAY_FLIGHT_TIME_SCALE*emphasis))}
function movementForPitch(code,profile){const table=profile?.form==="under"?underhandMovements:movements;return table[code]||table.other}
function preloadSprite(src){const image=new Image();image.src=src;return image.decode?image.decode().catch(()=>{}):Promise.resolve()}
const waitForPaint=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
const spriteReady={over:preloadSprite("assets/pitcher-right-overhand-30-normalized.png"),under:preloadSprite("assets/pitcher-right-underhand-normalized.png")};
const pitcherProfiles={
  "16108":{hand:"left",form:"over"},"13167":{hand:"right",form:"over"},"16568":{hand:"right",form:"over"},
  "14616":{hand:"left",form:"over"},"14156":{hand:"right",form:"over"},"11126":{hand:"right",form:"over"},
  "14816":{hand:"right",form:"under"},"14108":{hand:"right",form:"over"},"14106":{hand:"left",form:"over"},
  "11489":{hand:"right",form:"over"},"10783":{hand:"right",form:"over"},"11411":{hand:"left",form:"over"}
};
function getPitcherProfile(player){return pitcherProfiles[String(player.player_id)]||{hand:player.throw_hand||"right",form:player.pitching_form||"over"}}
function profileLabel(profile){const hand=profile.hand==="left"?"좌완":"우완";const form=profile.form==="under"?"언더핸드":profile.form==="sidearm"?"사이드암":"오버핸드";return `${hand} ${form}`}
function clearTrail(){state.trail=[];ui.trail.classList.add("hidden");[...ui.trail.children].forEach(dot=>dot.style.opacity=0)}
function updateTrail(x,y,scale){state.trail.unshift({x,y,scale});state.trail.length=Math.min(6,ui.trail.children.length);ui.trail.classList.remove("hidden");[...ui.trail.children].forEach((dot,index)=>{const point=state.trail[index];if(!point){dot.style.opacity=0;return}dot.style.left=`calc(50% + ${point.x}px)`;dot.style.top=`${point.y}%`;dot.style.transform=`translate(-50%,-50%) scale(${point.scale})`;dot.style.opacity=Math.max(0,.24-index*.04)})}
const spriteLayouts={
  over:{columns:6,rows:5,count:30,releaseIndex:20,releaseAnchor:{x:.385,y:.33},windupDuration:WINDUP_DURATION_MS,followDuration:FOLLOW_THROUGH_DURATION_MS},
  under:{columns:4,rows:3,count:12,releaseIndex:7,releaseAnchor:{x:.72,y:.78},windupDuration:850,followDuration:420},
  sidearm:{columns:4,rows:3,count:12,releaseIndex:7,releaseAnchor:{x:.8,y:.52},windupDuration:850,followDuration:420}
};
function getSpriteLayout(){return spriteLayouts[state.profile?.form]||spriteLayouts.over}
function setPitcherFrame(index){const layout=getSpriteLayout(),frame=Math.max(0,Math.min(layout.count-1,index)),column=frame%layout.columns,row=Math.floor(frame/layout.columns),x=column*100/(layout.columns-1),y=row*100/(layout.rows-1);ui.pitcher.style.setProperty("--sprite-x",`${x}%`);ui.pitcher.style.setProperty("--sprite-y",`${y}%`);ui.pitcher.style.setProperty("--sprite-columns",layout.columns);ui.pitcher.style.setProperty("--sprite-rows",layout.rows)}
function scheduleEffect(callback,delay){const timer=setTimeout(()=>{state.effectTimers=state.effectTimers.filter(id=>id!==timer);callback()},delay);state.effectTimers.push(timer);return timer}
function cancelPitchPlayback(){cancelAnimationFrame(state.frame);cancelAnimationFrame(state.spriteTimer);state.effectTimers.forEach(clearTimeout);state.effectTimers=[];ui.bat.classList.remove("swinging");ui.burst.classList.add("hidden");ui.stage.classList.remove("pitch-flight","camera-hit","batted-ball-flight")}
function finishBallVisuals(){ui.ball.classList.add("hidden");clearTrail();ui.ball.style.transform="";ui.ball.style.filter=""}
function measureReleasePoint(){const layout=getSpriteLayout(),stageRect=ui.stage.getBoundingClientRect(),pitcherRect=ui.pitcher.getBoundingClientRect(),anchorX=state.profile?.hand==="left"?1-layout.releaseAnchor.x:layout.releaseAnchor.x;return{x:pitcherRect.left-stageRect.left+pitcherRect.width*anchorX,y:pitcherRect.top-stageRect.top+pitcherRect.height*layout.releaseAnchor.y,stageWidth:stageRect.width,stageHeight:stageRect.height}}
function playPitcherSequence(now){if(state.phase!=="windup"&&state.phase!=="pitching")return;const layout=getSpriteLayout(),elapsed=now-state.sequenceStartedAt,totalDuration=layout.windupDuration+layout.followDuration;let targetPose;if(elapsed<layout.windupDuration){targetPose=Math.min(layout.releaseIndex,Math.floor(elapsed/layout.windupDuration*(layout.releaseIndex+1)))}else{const followProgress=Math.min(1,(elapsed-layout.windupDuration)/layout.followDuration);targetPose=layout.releaseIndex+Math.min(layout.count-1-layout.releaseIndex,Math.floor(followProgress*(layout.count-layout.releaseIndex)))}state.spritePose=Math.min(targetPose,state.spritePose+1);setPitcherFrame(state.spritePose);if(state.phase==="windup"&&elapsed>=layout.windupDuration&&state.spritePose===layout.releaseIndex)releasePitchFromHand(now);if(elapsed<totalDuration||state.spritePose<layout.count-1)state.spriteTimer=requestAnimationFrame(playPitcherSequence)}

function releasePitchFromHand(releaseTime=performance.now()){if(state.phase!=="windup")return;setPitcherFrame(getSpriteLayout().releaseIndex);const point=measureReleasePoint();state.releaseX=point.x-point.stageWidth/2;state.releaseY=point.y/point.stageHeight*100;state.ballX=state.releaseX;state.ballY=state.releaseY;state.ballScale=.38;state.phase="pitching";state.startedAt=releaseTime;clearTrail();ui.ball.style.left=`calc(50% + ${state.releaseX}px)`;ui.ball.style.top=`${state.releaseY}%`;ui.ball.style.transform="scale(.38) rotate(0deg)";ui.ball.style.filter="blur(0)";void ui.ball.offsetWidth;ui.ball.classList.remove("hidden");ui.stage.classList.add("pitch-flight");setAction("스윙!");ui.status.textContent="공을 끝까지 보세요";ui.last.textContent="구종은 타격 후 공개됩니다";state.frame=requestAnimationFrame(animatePitchFromHand)}
function animatePitchFromHand(now){if(state.phase!=="pitching")return;const raw=Math.min(1,(now-state.startedAt)/state.duration),depth=raw*raw*(3-2*raw),profile=state.profile||getPitcherProfile(state.pitcher),handMirror=profile.hand==="left"?-1:1,move=movementForPitch(state.pitch.statiz_code,profile),breakProgress=Math.max(0,(raw-move.onset)/(1-move.onset)),brk=breakProgress*breakProgress*(3-2*breakProgress),breakX=move.x*HORIZONTAL_BREAK_SCALE*handMirror,x=state.releaseX*(1-depth)+state.targetX*depth+breakX*brk,y=state.releaseY+(63+state.targetY-state.releaseY)*depth-2.1*Math.sin(Math.PI*raw)+move.y*brk*VERTICAL_BREAK_PERCENT_SCALE,scale=.38+Math.pow(raw,2.15)*3.05;state.ballX=x;state.ballY=y;state.ballScale=scale;ui.ball.style.left=`calc(50% + ${x}px)`;ui.ball.style.top=`${y}%`;ui.ball.style.transform=`scale(${scale}) rotate(${handMirror*raw*1080}deg)`;ui.ball.style.filter=`blur(${raw>.97?(raw-.97)*2:0}px)`;updateTrail(x,y,Math.max(.28,scale*.72));ui.needle.style.left=`${Math.min(99,raw*100)}%`;if(raw>=1)resolveMiss("루킹");else state.frame=requestAnimationFrame(animatePitchFromHand)}

async function loadPlayers(){try{const response=await fetch("../output/pitchers.json",{cache:"no-store"});if(!response.ok)throw new Error(`데이터 응답 오류 (${response.status})`);const data=await response.json();state.players=data.players.filter(p=>usable(p).length);renderPitchers()}catch(error){ui.grid.innerHTML=`<div class="error">선수 데이터를 읽지 못했습니다.<br><small>${error.message}<br>run_game.ps1로 실행해 주세요.</small></div>`}}
const usable=player=>player.pitches.filter(p=>Number(p.ratio)>0&&p.pitch_type!=="기타");
function weightedAverage(pitches){const valid=pitches.filter(p=>Number(p.velocity_kmh)),total=valid.reduce((s,p)=>s+p.ratio,0)||1;return valid.reduce((s,p)=>s+p.velocity_kmh*p.ratio,0)/total}
function renderPitchers(){ui.grid.innerHTML="";state.players.forEach((player,index)=>{const pitches=usable(player),profile=getPitcherProfile(player),primary=[...pitches].sort((a,b)=>b.ratio-a.ratio)[0],card=document.createElement("button");card.className="pitcher-card";card.innerHTML=`<span class="card-number">${String(index+1).padStart(2,"0")}</span><span class="player-silhouette"></span><div class="card-content"><span class="primary-pitch">ACE · ${primary.pitch_type} ${(primary.ratio*100).toFixed(1)}%</span><h2>${player.name}</h2><div class="meta">${profileLabel(profile)} · ${pitches.length}구종 · ${weightedAverage(pitches).toFixed(1)} km/h</div></div>`;card.onclick=()=>selectPitcher(player);ui.grid.append(card)})}
function selectPitcher(player){cancelPitchPlayback();const profile=getPitcherProfile(player),lowArm=profile.form==="under"?2:profile.form==="sidearm"?1:0,hand=profile.hand==="left"?1:-1;Object.assign(state,{pitcher:player,profile,phase:"idle",hits:0,misses:0,streak:0,best:0});ui.pitcher.classList.remove("left-handed","sidearm","underhand","sprite-pitcher");if(profile.form==="over"||profile.form==="under")ui.pitcher.classList.add("sprite-pitcher");if(profile.hand==="left")ui.pitcher.classList.add("left-handed");if(profile.form==="sidearm")ui.pitcher.classList.add("sidearm");if(profile.form==="under")ui.pitcher.classList.add("underhand");ui.stage.style.setProperty("--release-x",`${hand*(lowArm?25:12)}px`);ui.stage.style.setProperty("--release-y",`${50.5+lowArm*2.4}%`);ui.select.classList.add("hidden");ui.game.classList.remove("hidden");ui.name.textContent=player.name;ui.season.textContent=`${player.season} SEASON · ${profileLabel(profile)}`;ui.arsenal.innerHTML=usable(player).sort((a,b)=>b.ratio-a.ratio).map(p=>`<span class="pitch-chip"><b>${p.pitch_type}</b> ${(p.ratio*100).toFixed(1)}% · ${p.velocity_kmh?p.velocity_kmh.toFixed(1):"-"}</span>`).join("");resetRound("준비되면 투구를 시작하세요");updateScore()}
function weightedPitch(){const pitches=usable(state.pitcher),total=pitches.reduce((s,p)=>s+p.ratio,0);let draw=Math.random()*total;for(const pitch of pitches){draw-=pitch.ratio;if(draw<=0)return pitch}return pitches.at(-1)}
async function beginPitch(){if(state.phase!=="idle")return;state.phase="loading";await (spriteReady[state.profile?.form]||Promise.resolve());await waitForPaint();if(state.phase!=="loading")return;cancelPitchPlayback();state.pitch=weightedPitch();state.duration=flightDurationForVelocity(state.pitch.velocity_kmh);state.phase="windup";state.spritePose=0;state.sequenceStartedAt=performance.now();ui.result.classList.add("hidden");ui.ball.classList.add("hidden");ui.pitcher.classList.remove("windup");void ui.pitcher.offsetWidth;ui.pitcher.classList.add("windup");setPitcherFrame(0);setAction("준비");ui.status.textContent="투수 와인드업";ui.last.textContent="손에서 공이 떠나는 순간을 보세요";state.spriteTimer=requestAnimationFrame(playPitcherSequence)}
function swing(){if(state.phase!=="pitching")return;const elapsed=performance.now()-state.startedAt,progress=Math.min(1,elapsed/state.duration),errorMs=elapsed-state.duration*CONTACT_PROGRESS,absoluteErrorMs=Math.abs(errorMs);cancelAnimationFrame(state.frame);ui.bat.classList.add("swinging");scheduleEffect(()=>ui.bat.classList.remove("swinging"),260);if(absoluteErrorMs<=PERFECT_WINDOW_MS)resolveHit("PERFECT!","result-perfect",3);else if(absoluteErrorMs<=HIT_WINDOW_MS)resolveHit(errorMs<0?"조금 빨랐지만 안타!":"조금 늦었지만 안타!","result-hit",1);else resolveMiss(progress<CONTACT_PROGRESS?"너무 빨랐습니다":"너무 늦었습니다")}
function animateBattedBall(done){state.phase="contact";clearTrail();ui.stage.classList.remove("pitch-flight");ui.stage.classList.add("camera-hit","batted-ball-flight");ui.burst.style.left=`calc(50% + ${state.ballX}px)`;ui.burst.style.top=`${state.ballY}%`;ui.burst.classList.remove("hidden");ui.burst.style.animation="none";void ui.burst.offsetWidth;ui.burst.style.animation="";const startX=state.ballX,startY=state.ballY,startScale=state.ballScale,startedAt=performance.now();function fly(now){if(state.phase!=="contact")return;const progress=Math.min(1,(now-startedAt)/BATTED_BALL_DURATION_MS),ease=1-Math.pow(1-progress,3),x=startX*(1-ease)+(startX<0?90:-90)*ease,y=startY*(1-ease)+24*ease-18*Math.sin(Math.PI*progress),scale=startScale*(1-ease)+.34*ease;ui.ball.style.left=`calc(50% + ${x}px)`;ui.ball.style.top=`${y}%`;ui.ball.style.transform=`scale(${scale}) rotate(${progress*900}deg)`;ui.ball.style.filter="blur(0)";if(progress<1)state.frame=requestAnimationFrame(fly);else{ui.burst.classList.add("hidden");ui.stage.classList.remove("camera-hit","batted-ball-flight");finishBallVisuals();done()}}state.frame=requestAnimationFrame(fly)}
function resolveHit(message,className,points){state.hits++;state.streak+=points;state.best=Math.max(state.best,state.streak);animateBattedBall(()=>showResult(message,className))}
function resolveMiss(message){if(state.phase==="pitching"){state.phase="resolved";cancelAnimationFrame(state.frame)}state.misses++;state.streak=0;showResult(message,"result-miss")}
function showResult(message,className){state.phase="resolved";ui.stage.classList.remove("pitch-flight");finishBallVisuals();ui.status.className=`status ${className}`;ui.status.textContent=message;const detail=`${state.pitch.pitch_type} · ${state.pitch.velocity_kmh?state.pitch.velocity_kmh.toFixed(1):"-"} km/h · 구사율 ${(state.pitch.ratio*100).toFixed(1)}%`;ui.last.textContent=detail;ui.result.className=`result-flash ${className}`;ui.result.querySelector("strong").textContent=message;ui.result.querySelector("span").textContent=detail;setAction("다음 투구");updateScore();scheduleEffect(()=>ui.result.classList.add("hidden"),RESULT_DISPLAY_MS)}
function resetRound(message="다음 공을 준비하세요"){cancelPitchPlayback();setPitcherFrame(0);state.phase="idle";state.targetX=(Math.random()-.5)*70;state.targetY=(Math.random()-.5)*5.5;ui.pitcher.classList.remove("windup");ui.result.classList.add("hidden");ui.ball.classList.add("hidden");clearTrail();ui.ball.style.transform="";ui.ball.style.filter="";ui.needle.style.left="0%";ui.status.className="status";ui.status.textContent=message;ui.last.textContent="SPACE 또는 버튼을 누르세요";setAction("투구 시작")}
function updateScore(){ui.hits.textContent=state.hits;ui.misses.textContent=state.misses;ui.best.textContent=state.best}
function handleAction(){if(state.phase==="idle"){state.targetX=(Math.random()-.5)*70;state.targetY=(Math.random()-.5)*5.5;beginPitch()}else if(state.phase==="pitching")swing();else if(state.phase==="resolved")resetRound()}
ui.action.onclick=handleAction;$("backButton").onclick=()=>{resetRound();ui.game.classList.add("hidden");ui.select.classList.remove("hidden")};window.addEventListener("keydown",event=>{if(event.code==="Space"&&!ui.game.classList.contains("hidden")){event.preventDefault();handleAction()}});loadPlayers();
