const CARDS = /*CARD_JSON*/;
const ST = {};
function dispName(n){ return n.replace(/\[\]/g,'').trim(); }
CARDS.forEach(c => { ST[c.name]={idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',customSummary:'',pinned:false}; });

function loadState(){
  try{
    const saved=JSON.parse(localStorage.getItem('swlegion_v1')||'{}');
    Object.keys(saved).forEach(n=>{ if(ST[n]) Object.assign(ST[n],saved[n]); });
  }catch(e){}
}
function saveState(){
  const out={};
  Object.keys(ST).forEach(n=>{ const{idx,learned,flagged,notes,customDef,pinned}=ST[n]; out[n]={idx,learned,flagged,notes:notes||'',customDef:customDef||'',pinned:!!pinned}; });
  localStorage.setItem('swlegion_v1',JSON.stringify(out));
  scheduleSync();
}
function s(n){ return ST[n]||{idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',pinned:false}; }
function ci(c){ const st=s(c.name); return (c.imgs&&c.imgs[st.idx])||(c.imgs&&c.imgs[0])||''; }
function ic(c){ return (c.imgs&&c.imgs.length)||0; }

let _st=null;
function setStatus(msg,cls,ms){
  const el=document.getElementById('fs-status');
  el.textContent=msg; el.className='show '+(cls||'ok');
  clearTimeout(_st); if(ms) _st=setTimeout(()=>{el.textContent='';el.className='';},ms);
}
function clrStatus(){ clearTimeout(_st); const el=document.getElementById('fs-status'); el.textContent='';el.className=''; }

function showScreen(id){
  document.querySelectorAll('.screen').forEach(el=>el.classList.remove('on'));
  document.getElementById(id).classList.add('on');
  if(id==='catalog-screen') renderCatalog();
  if(id==='lists-screen'){ renderSavedLists(); }
}

let typeFilter='all';
let activeListId=null; // flashcard/quiz list filter
let catListId=null;    // catalog list filter (null=inherit, ''=explicit none, id=specific)
const catExtras=new Set(); // extra types union-included when a list filter is active

function setTypeFilter(t){
  typeFilter=t;
  ['all','unit','weapon','concept'].forEach(x=>{
    const el=document.getElementById('pill-'+x); if(el) el.classList.remove('active');
  });
  const activeId = t==='noconcept'?'pill-concept':'pill-'+t;
  const activeEl=document.getElementById(activeId); if(activeEl) activeEl.classList.add('active');
  clrStatus(); initDeck(); render();
}
function filteredCards(){
  let cards=CARDS;
  if(activeListId){
    const lst=getListById(activeListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      const base=CARDS.filter(c=>kwSet.has(c.name.toLowerCase()));
      const extras=CARDS.filter(c=>catExtras.has(c.type));
      const pinned=CARDS.filter(c=>s(c.name).pinned);
      cards=[...new Set([...base,...extras,...pinned])];
    }
  }
  const pinnedAll=CARDS.filter(c=>s(c.name).pinned);
  if(typeFilter==='weapon'){const f=cards.filter(c=>c.type==='weapon');return[...new Set([...f,...pinnedAll])];}
  if(typeFilter==='unit'){const f=cards.filter(c=>c.type==='unit');return[...new Set([...f,...pinnedAll])];}
  if(typeFilter==='noconcept'){const f=cards.filter(c=>c.type!=='concept');return[...new Set([...f,...pinnedAll])];}
  return [...new Set([...cards,...pinnedAll])];
}
function setListFilter(listId){
  activeListId=listId||null;
  savePrefs();
  updateListPillLabel();
  updateCatListPillLabel();
  renderListFilterBadges();
  clrStatus(); initDeck(); render();
}
function clearListFilter(){
  activeListId=null;
  savePrefs();
  updateListPillLabel();
  updateCatListPillLabel();
  renderListFilterBadges();
  clrStatus(); initDeck(); render();
}
function updateListPillLabel(){
  const pill=document.getElementById('pill-list'); if(!pill) return;
  if(activeListId){
    const lst=getListById(activeListId);
    pill.innerHTML=(lst?escHtml(lst.name):'List')+' &#9660;';
    pill.classList.add('active');
  } else {
    pill.innerHTML='List: None &#9660;';
    pill.classList.remove('active');
  }
}
function updateCatListPillLabel(){
  const pill=document.getElementById('cat-pill-list'); if(!pill) return;
  if(catListId===null){
    if(activeListId){
      const lst=getListById(activeListId);
      pill.innerHTML='('+escHtml(lst?lst.name:'?')+') &#9660;';
      pill.classList.add('active');
    } else { pill.innerHTML='List: None &#9660;'; pill.classList.remove('active'); }
  } else if(catListId===''){
    pill.innerHTML='List: None &#9660;'; pill.classList.remove('active');
  } else {
    const lst=getListById(catListId);
    pill.innerHTML=(lst?escHtml(lst.name):'List')+' &#9660;';
    pill.classList.add('active');
  }
}
function toggleListDropdown(){
  const dd=document.getElementById('list-dropdown');
  if(dd.classList.contains('open')){ dd.classList.remove('open'); return; }
  // Build items
  const lists=loadLists();
  let html=`<div class="list-dd-item none-item${!activeListId?' active':''}" onclick="setListFilter(null);document.getElementById('list-dropdown').classList.remove('open')">None</div>`;
  lists.forEach(l=>{
    const active=activeListId===l.id;
    html+=`<div class="list-dd-item${active?' active':''}" onclick="setListFilter('${l.id}');document.getElementById('list-dropdown').classList.remove('open')">${escHtml(l.name)}</div>`;
  });
  if(!lists.length) html+=`<div class="list-dd-item none-item">No lists saved</div>`;
  dd.innerHTML=html;
  dd.classList.add('open');
  // Close on outside click
  setTimeout(()=>{ document.addEventListener('click', function _c(e){ if(!document.getElementById('list-dropdown-wrap').contains(e.target)){ dd.classList.remove('open'); document.removeEventListener('click',_c); } }); },0);
}
function toggleCatListDropdown(){
  const dd=document.getElementById('cat-list-dropdown');
  if(dd.classList.contains('open')){ dd.classList.remove('open'); return; }
  const lists=loadLists();
  let html=`<div class="list-dd-item none-item${catListId===''||(catListId===null&&!activeListId)?' active':''}" onclick="setCatList('');document.getElementById('cat-list-dropdown').classList.remove('open')">None</div>`;
  lists.forEach(l=>{
    const active=catListId===l.id;
    html+=`<div class="list-dd-item${active?' active':''}" onclick="setCatList('${l.id}');document.getElementById('cat-list-dropdown').classList.remove('open')">${escHtml(l.name)}</div>`;
  });
  if(!lists.length) html+=`<div class="list-dd-item none-item">No lists saved</div>`;
  dd.innerHTML=html;
  dd.classList.add('open');
  setTimeout(()=>{ document.addEventListener('click', function _c(e){ if(!document.getElementById('cat-list-dropdown-wrap').contains(e.target)){ dd.classList.remove('open'); document.removeEventListener('click',_c); } }); },0);
}
function setCatList(listId){
  catListId=(listId===undefined)?null:listId;
  savePrefs();
  updateCatListPillLabel();
  updateCatAddRow();
  renderCatalog();
}
function updateCatAddRow(){
  const effectiveId=catListId===null?activeListId:catListId;
  const row=document.getElementById('cat-add-row');
  if(row) row.style.display=effectiveId?'flex':'none';
}
function toggleCatExtra(type,btn){
  if(catExtras.has(type)){ catExtras.delete(type); btn.classList.remove('extra-on'); }
  else { catExtras.add(type); btn.classList.add('extra-on'); }
  renderCatalog();
}
function renderListFilterBadges(){
  document.querySelectorAll('.list-card').forEach(el=>{
    el.classList.toggle('active-filter', el.dataset.listId===activeListId);
  });
  document.querySelectorAll('.list-btn-filter').forEach(el=>{
    el.classList.toggle('on', el.dataset.listId===activeListId);
    el.textContent=el.dataset.listId===activeListId?'Filtering':'Filter';
  });
}

let deck=[],cur=0,mode='learn',revealed=false,answered=false,sc=0,sw=0,_quizChoices=[];
let _stDeck=[],_stCur=0,_stSc=0,_stSw=0,_stQ=null,_stAnswered=false;
function activeDeck(){ return filteredCards().filter(c=>!s(c.name).learned); }
function shuffle(a){ for(let i=a.length-1;i>0;i--){const j=0|Math.random()*(i+1);[a[i],a[j]]=[a[j],a[i]];} return a; }
function initDeck(){ deck=[...activeDeck()]; shuffle(deck); cur=0; }

function render(){
  if(mode==='stats'){ renderStatCard(); return; }
  document.getElementById('fs-stats-cover').style.display='none';
  const alive=activeDeck();
  const alldone=document.getElementById('fs-alldone');
  if(!alive.length){ alldone.classList.add('on'); return; }
  alldone.classList.remove('on');
  while(deck[cur]&&s(deck[cur].name).learned&&cur<deck.length) cur++;
  if(!deck[cur]||s(deck[cur].name).learned) initDeck();
  const c=deck[cur];
  revealed=false; answered=false;
  const qr=document.getElementById('fs-qres'); qr.className=''; qr.textContent='';
  document.getElementById('fs-opts').className='';
  document.getElementById('fs-pfill').style.width=Math.round(((cur+1)/deck.length)*100)+'%';
  document.getElementById('fs-ctr').textContent=(cur+1)+'/'+deck.length;
  document.getElementById('fs-prev').disabled=cur===0;
  document.getElementById('fs-next').disabled=cur===deck.length-1;
  const img=document.getElementById('fs-img');
  const src=ci(c);
  if(src){ img.src=src; img.style.display='block'; }
  else   { img.style.display='none'; }
  showFront(c); renderActions(c);
}

function typeBadgeHTML(type){
  const labels={unit:'Unit Keyword',weapon:'Weapon Keyword',upgrade:'Upgrade',concept:'Concept'};
  return `<span class="type-badge type-${type}">${labels[type]||type}</span>`;
}
function fitImg(){
  const img=document.getElementById('fs-img');
  const bot=document.getElementById('fs-bottom');
  if(!img||!bot) return;
  requestAnimationFrame(()=>{
    const botH=bot.getBoundingClientRect().height;
    const clearH=Math.max(0,botH-60); // 60px = gradient top-padding, overlap is intentional
    img.style.height=`calc(100% - 68px - ${clearH}px)`;
  });
}
function showFront(c){
  document.getElementById('fs-front-content').style.display='block';
  document.getElementById('fs-back-content').style.display='none';
  document.getElementById('fs-keyword-name').textContent=dispName(c.name);
  document.getElementById('fs-keyword-subtext').innerHTML=typeBadgeHTML(c.type);
  document.getElementById('fs-tap-hint').style.display=mode==='learn'?'block':'none';
  document.getElementById('fs-img').classList.remove('dim');
  if(mode==='quiz') renderOpts(c);
  fitImg();
}
let _rulesOpen=false;
function toggleRulesSection(){
  _rulesOpen=!_rulesOpen;
  const defEl=document.getElementById('fs-definition');
  const caretEl=document.getElementById('fs-rules-caret');
  if(defEl) defEl.style.display=_rulesOpen?'block':'none';
  if(caretEl) caretEl.style.transform=_rulesOpen?'rotate(180deg)':'';
}
function autoSummary(def){
  if(!def) return '';
  if(def.length<=700) return def;
  let t=def.slice(0,700);
  const last=Math.max(t.lastIndexOf(' '),t.lastIndexOf('.'),t.lastIndexOf(','));
  if(last>400) t=t.slice(0,last);
  return t+'\u2026';
}
async function badSummary(){
  const c=deck[cur]; if(!c) return;
  const st=s(c.name);
  const def=(st.customDef||c.definition||'').trim();
  if(!def){ setStatus('No definition to summarise','err',2000); return; }
  setStatus('Generating AI summary\u2026','work');
  try {
    const resp=await fetch(SUPA_URL+'/functions/v1/summarize',{
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+SUPA_KEY},
      body:JSON.stringify({definition:def,name:c.name})
    });
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    const {summary,error}=await resp.json();
    if(error) throw new Error(error);
    st.notes=summary; saveState();
    const el=document.getElementById('fs-notes');
    if(el){ el.value=summary; el.oninput=()=>{ st.notes=el.value; saveState(); }; }
    setStatus('AI summary ready','ok',2000);
  } catch(e){
    setStatus('AI unavailable — '+e.message,'err',3000);
  }
}
function cardSource(c){ const st=s(c.name); return st.customDef ? 'Admin' : (c.credit||'legion.takras.net'); }
function showBack(c){
  document.getElementById('fs-front-content').style.display='none';
  document.getElementById('fs-back-content').style.display='block';
  document.getElementById('fs-back-name').innerHTML=dispName(c.name)+' '+typeBadgeHTML(c.type);
  const st=s(c.name);
  const def=st.customDef||c.definition||'';
  // Notes / Summary
  const notesEl=document.getElementById('fs-notes');
  if(notesEl){
    notesEl.value=(st.notes!==undefined&&st.notes!=='')?st.notes:(c.summary||autoSummary(def));
    const isOwner=(_currentUser?.email==='martinjsleeman@gmail.com');
    notesEl.readOnly=!isOwner;
    notesEl.style.opacity=isOwner?'1':'0.85';
    if(isOwner) notesEl.oninput=()=>{ st.notes=notesEl.value; saveState(); };
  }
  // Rules section (collapsed by default)
  _rulesOpen=false;
  const defEl=document.getElementById('fs-definition');
  const caretEl=document.getElementById('fs-rules-caret');
  const previewEl=document.getElementById('fs-rules-preview');
  if(defEl){ defEl.style.display='none'; defEl.textContent=def; }
  if(caretEl) caretEl.style.transform='';
  if(previewEl){
    const first=(def.match(/^[^.!?]+[.!?]/)||[''])[0].trim();
    previewEl.textContent=first||def.slice(0,80);
  }
  // Source
  const srcEl=document.getElementById('fs-source');
  if(srcEl) srcEl.textContent=cardSource(c);
  const unitsEl=document.getElementById('fs-units');
  if(unitsEl) unitsEl.textContent=c.units?'Units: '+c.units:'';
  // Reset feedback area
  const fba=document.getElementById('fs-feedback-area');
  if(fba) fba.style.display='none';
  const fbi=document.getElementById('fs-feedback-input');
  if(fbi) fbi.value='';
  // Owner feedback display
  renderOwnerFeedbackEl(c.name, 'fs-owner-feedback');
  fitImg();
}
function renderActions(c){
  const st=s(c.name);
  const sn=c.name.replace(/'/g,"\\'");
  document.getElementById('fs-actions').innerHTML=
    `<button class="fs-btn${st.learned?' learned':''}" onclick="toggleLearned('${sn}')">${st.learned?'Learned':'Mark as learned'}</button>`+
    `<button class="fs-btn" onclick="toggleFsFeedback()">Feedback</button>`;
}
function handleTap(){
  if(mode==='stats') return;
  if(mode==='quiz'&&!answered) return;
  if(!revealed){ revealed=true; showBack(deck[cur]); }
  else { if(cur<deck.length-1){ cur++; render(); } }
}
function go(d){
  if(mode==='stats'){ _stCur=Math.max(0,Math.min(_stDeck.length-1,_stCur+d)); renderStatCard(); return; }
  cur=Math.max(0,Math.min(deck.length-1,cur+d)); render();
}
function setMode(m){
  mode=m;
  document.getElementById('pill-learn').classList.toggle('active',m==='learn');
  document.getElementById('pill-quiz').classList.toggle('active',m==='quiz');
  document.getElementById('pill-stats').classList.toggle('active',m==='stats');
  document.getElementById('fs-quiz-stats').style.display=m==='quiz'?'flex':'none';
  document.getElementById('fs-stats-score').style.display=m==='stats'?'flex':'none';
  document.getElementById('fs-stats-cover').style.display=m==='stats'?'block':'none';
  if(m==='quiz'){sc=0;sw=0;['sc','sw'].forEach(id=>document.getElementById(id).textContent=0);}
  clrStatus();
  if(m==='stats'){ initStatsDeck(); renderStatCard(); }
  else { document.getElementById('fs-stats-cover').style.display='none'; initDeck(); render(); }
}
function renderOpts(c){
  const pool=filteredCards().filter(x=>x.name!==c.name); shuffle(pool);
  _quizChoices=[{card:c,correct:true},...pool.slice(0,3).map(x=>({card:x,correct:false}))];
  shuffle(_quizChoices);
  const el=document.getElementById('fs-opts'); el.className='on';
  el.innerHTML=_quizChoices.map((ch,i)=>{
    const escaped=ch.card.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const raw=s(ch.card.name).notes||ch.card.definition||'';
    const def=raw.replace(new RegExp('\\b'+escaped+'\\b','gi'),'the keyword')
                  .replace(/\bthe keyword keyword\b/gi,'the keyword');
    const display=def.length>220?def.slice(0,def.lastIndexOf(' ',220))+'…':def;
    return `<button class="fs-opt" onclick="pick(this,${i})">${display}</button>`;
  }).join('');
  document.getElementById('fs-tap-hint').style.display='none';
}
function pick(btn,idx){
  if(answered)return; answered=true;
  const ok=_quizChoices[idx].correct;
  document.querySelectorAll('.fs-opt').forEach((b,i)=>{
    b.disabled=true;
    if(_quizChoices[i].correct) b.classList.add('correct');
    else if(b===btn&&!ok) b.classList.add('wrong');
  });
  if(ok){sc++;}else{sw++;}
  document.getElementById('sc').textContent=sc;
  document.getElementById('sw').textContent=sw;
  const qr=document.getElementById('fs-qres');
  const correctName=_quizChoices.find(ch=>ch.correct).card.name;
  qr.textContent=ok?'Correct!':'Nope — the answer was "'+correctName+'"';
  qr.className='on '+(ok?'ok':'no');
  revealed=true;
  const total=sc+sw;
  if(cur<deck.length-1){
    setTimeout(()=>{cur++;render();},2200);
  } else {
    const pct=total>0?Math.round(sc/total*100):0;
    let msg;
    if(pct===100) msg=`Perfect score! ${sc}/${total} — you're a Legion master!`;
    else if(pct>=80) msg=`Excellent! ${sc}/${total} — nearly perfect!`;
    else if(pct>=60) msg=`Great effort! ${sc}/${total} — you're getting there!`;
    else if(pct>=40) msg=`Good start! ${sc}/${total} — keep practicing!`;
    else msg=`${sc}/${total} — keep studying, you've got this!`;
    setTimeout(()=>{qr.textContent=msg; qr.className='on ok';},2200);
  }
}
function initStatsDeck(){
  _stDeck=Object.keys(UNIT_STATS).filter(k=>UNIT_DB[k]);
  shuffle(_stDeck);
  _stCur=0; _stSc=0; _stSw=0;
  document.getElementById('ss').textContent=0;
  document.getElementById('se').textContent=0;
}

function makeStatQuestion(code){
  const st=UNIT_STATS[code];
  // All questions must produce exactly 4 options.
  // Movement: only 1/2/3 exist in-game; "4" is always a wrong distractor.
  // Attack Surge: "Block" is a defense-surge result — good distractor to test knowledge.
  // Defense Die removed: only 2 real values (Red/White), can't make a fair 4-choice question.
  const qs=[
    {key:'sp', label:'Movement?', ans:String(st.sp),
      opts:()=>shuffle(['1','2','3','4'])},
    {key:'w',  label:'Total Wounds?', ans:String(st.w),
      opts:()=>{
        const pool=[...new Set(Object.values(UNIT_STATS).map(u=>u.w))];
        shuffle(pool);
        const wrong=pool.filter(v=>v!==st.w).slice(0,3);
        return shuffle([st.w,...wrong]).map(String);
      }},
    {key:'cg', label:'Courage?', ans:st.cg===null?'Fearless':String(st.cg),
      opts:()=>shuffle(['1','2','3','Fearless'])},
    {key:'as', label:'Attack Surge?',
      ans:st.as==='h'?'Hit':st.as==='c'?'Critical':'None',
      opts:()=>shuffle(['Hit','Critical','None','Block'])},
  ];
  const q=qs[Math.floor(Math.random()*qs.length)];
  const opts=q.opts();
  if(!opts.includes(q.ans)) opts[0]=q.ans;
  return {label:q.label, ans:q.ans, opts};
}

function positionStatsOverlay(){
  const img=document.getElementById('fs-img');
  const cover=document.getElementById('fs-stats-cover');
  if(!img||!cover||img.style.display==='none') return;
  const imgR=img.getBoundingClientRect();
  const bgR=document.getElementById('fs-bg').getBoundingClientRect();
  const ow=imgR.width*0.44, oh=imgR.height*0.28;
  cover.style.left=(imgR.right-bgR.left-ow)+'px';
  cover.style.top=(imgR.bottom-bgR.top-oh)+'px';
  cover.style.width=ow+'px';
  cover.style.height=oh+'px';
  cover.style.display='block';
}

function renderStatCard(){
  if(_stCur>=_stDeck.length){
    document.getElementById('fs-alldone').classList.add('on');
    return;
  }
  document.getElementById('fs-alldone').classList.remove('on');
  const code=_stDeck[_stCur];
  const unit=UNIT_DB[code];
  _stQ=makeStatQuestion(code);
  _stAnswered=false;
  // Progress
  document.getElementById('fs-pfill').style.width=Math.round((_stCur+1)/_stDeck.length*100)+'%';
  document.getElementById('fs-ctr').textContent=(_stCur+1)+'/'+_stDeck.length;
  document.getElementById('fs-prev').disabled=_stCur===0;
  document.getElementById('fs-next').disabled=true;
  // Show unit card image
  const img=document.getElementById('fs-img');
  img.src='images/'+unit.i;
  img.style.display='block';
  img.classList.remove('dim');
  // Front content: show unit name + question
  document.getElementById('fs-front-content').style.display='block';
  document.getElementById('fs-back-content').style.display='none';
  const uname=(unit.t?unit.n+' — '+unit.t:unit.n);
  document.getElementById('fs-keyword-name').textContent=uname;
  document.getElementById('fs-keyword-subtext').innerHTML='<span style="font-size:18px;color:var(--gold);font-weight:700">'+_stQ.label+'</span>';
  document.getElementById('fs-tap-hint').style.display='none';
  // Options
  const el=document.getElementById('fs-opts'); el.className='on';
  el.innerHTML=_stQ.opts.map((o,i)=>`<button class="fs-opt" onclick="pickStat(this,'${o.replace(/'/g,"\\'")}',${i})">${o}</button>`).join('');
  // Result
  const qr=document.getElementById('fs-qres'); qr.className=''; qr.textContent='';
  // Position overlay after image loads
  if(img.complete) positionStatsOverlay();
  else img.onload=positionStatsOverlay;
}

function pickStat(btn,chosen,idx){
  if(_stAnswered) return;
  _stAnswered=true;
  const ok=chosen===_stQ.ans;
  document.querySelectorAll('.fs-opt').forEach(b=>{
    b.disabled=true;
    if(b.textContent.trim()===_stQ.ans) b.classList.add('correct');
    else if(b===btn&&!ok) b.classList.add('wrong');
  });
  if(ok){_stSc++;}else{_stSw++;}
  document.getElementById('ss').textContent=_stSc;
  document.getElementById('se').textContent=_stSw;
  const qr=document.getElementById('fs-qres');
  qr.textContent=ok?'Correct!':'The answer is "'+_stQ.ans+'"';
  qr.className='on '+(ok?'ok':'no');
  const total=_stSc+_stSw;
  if(_stCur<_stDeck.length-1){
    setTimeout(()=>{_stCur++;renderStatCard();},2200);
  } else {
    const pct=total>0?Math.round(_stSc/total*100):0;
    let msg;
    if(pct===100) msg='Perfect! '+_stSc+'/'+total+' — you know every unit!';
    else if(pct>=80) msg='Excellent! '+_stSc+'/'+total+' — nearly perfect!';
    else if(pct>=60) msg='Good work! '+_stSc+'/'+total+' — getting there!';
    else msg=_stSc+'/'+total+' — keep studying those stat cards!';
    setTimeout(()=>{qr.textContent=msg; qr.className='on ok'; document.getElementById('fs-stats-cover').style.display='none';},2200);
  }
}
function toggleLearned(name){
  const wasLearned=ST[name].learned;
  ST[name].learned=!wasLearned;
  saveState();
  if(!wasLearned){
    deck.splice(cur,1);
    if(cur>=deck.length) cur=Math.max(0,deck.length-1);
  } else {
    const card=CARDS.find(c=>c.name===name);
    if(card) deck.push(card);
  }
  render();
  syncToCloud();
}
function resetLearned(){
  CARDS.forEach(c=>{ ST[c.name].learned=false; });
  saveState(); initDeck();
  document.getElementById('fs-alldone').classList.remove('on');
  render();
}
function unitImgsForKeyword(c){
  const kw=c.name, base=kw.replace(/\s+\d+$/,'');
  return Object.values(UNIT_DB)
    .filter(u=>u.k&&u.k.some(k=>k===kw||k===base||k.startsWith(base+' ')))
    .map(u=>'images/'+u.i);
}
const KEYWORD_FALLBACK=[
  ['Compulsory Move',    'AT-ST.webp'],
  ['Cumbersome',         'AT-ST.webp'],
  ['Plodding',           'Imperial Dark Troopers.webp'],
  ['Unstoppable',        'Imperial Dark Troopers.webp'],
  ['Unconcerned',        'Imperial Dark Troopers.webp'],
  ['Climbing Vehicle',   'AT-RT Reb.webp'],
  ['Expert Climber',     'AT-RT Reb.webp'],
  ['Fixed Front',        'AAT Battle Tank.webp'],
  ['Barrage',            'AAT Battle Tank.webp'],
  ['Hover Air',          'LAAT Patrol Transport E.webp'],
  ['Hover Ground',       'AAT Battle Tank.webp'],
  ['Transport',          'TX-225 GAVw Occupier Tank.webp'],
  ['Weak Point',         'AT-ST.webp'],
  ['Command Vehicle',    'Jedi Knight Mounted Jedi General.webp'],
  ['Mobile',             'TSMEU-6 Wheel Bikes.webp'],
  ['Wheel Mode',         'Droidekas.webp'],
  ['Ion',                'AT-ST.webp'],
  ['Immune: Melee',      'T-47 Airspeeder.webp'],
  ['Immune: Blast',      'T-47 Airspeeder.webp'],
  ['Immune: Range',      'T-47 Airspeeder.webp'],
  ['Immune: Pierce',     'Obi-Wan Kenobi.webp'],
  ['Immune:',            'Darth Vader Dark Lord of the Sith.webp'],
  ['Soresu Mastery',     'Obi-Wan Kenobi.webp'],
  ['Makashi Mastery',    'Count Dooku.webp'],
  ['Ataru Mastery',      'Ki-Adi-Mundi.webp'],
  ['Djem So Mastery',    'Anakin Skywalker.webp'],
  ['Juyo Mastery',       'Maul Impatient Apprentice.webp'],
  ["Jar'Kai Mastery",    'Asajj Ventress.webp'],
  ['Vaapad Mastery',     'Mace Windu.webp'],
  ['Shien Mastery',      'Ahsoka Tano Padawan Commander.webp'],
  ['Master of the Force','Obi-Wan Kenobi.webp'],
  ['Deflect',            'Obi-Wan Kenobi.webp'],
  ['Pierce',             'Luke Skywalker Jedi Knight.webp'],
  ['Melee',              'Luke Skywalker Jedi Knight.webp'],
  ['Impact',             'General Grievous Sinister Cyborg.webp'],
  ['Blast',              'AAT Battle Tank.webp'],
  ['Programmed',         'Droidekas.webp'],
  ['Override',           'Command and Control Droid.webp'],
  ['Speeder',            '74-Z Speeder Bikes.webp'],
  ['Strafe',             'T-47 Airspeeder.webp'],
  ['Attack Run',         'Raddaugh Gnasp Fluttercraft Attack Craft.webp'],
  ['Scout',              'Rebel Commandos.webp'],
  ['Infiltrate',         'Jyn Erso.webp'],
  ['Incognito',          'K-2SO.webp'],
  ['Inconspicuous',      'R2-D2 Hero of a Thousand Devices.webp'],
  ['Inconspicious',      'R2-D2 Hero of a Thousand Devices.webp'],
  ['Shielded',           'Droidekas.webp'],
  ['Generator',          'Droidekas.webp'],
  ['Bounty',             'Boba Fett Infamous Bounty Hunter.webp'],
  ['Suppressive',        'Stormtroopers.webp'],
  ['Demoralize',         'Stormtroopers.webp'],
  ['Jump',               'Sabine Wren.webp'],
  ['Repair',             'R2-D2 Hero of a Thousand Devices.webp'],
  ['Enrage',             'Chewbacca Walking Carpet.webp'],
  ['Scale',              'Chewbacca Walking Carpet.webp'],
  ['Indomitable',        'Wookiee Warriors Freedom Fighters.webp'],
  ['Guardian',           'Obi-Wan Kenobi.webp'],
  ['Inspire',            'Leia Organa.webp'],
  ['Bolster',            'T-Series Tactical Droid.webp'],
  ['Observe',            'Imperial Probe Droid.webp'],
  ['Entourage',          'Darth Vader Dark Lord of the Sith.webp'],
  ['Charge',             'Luke Skywalker Hero of the Rebellion.webp'],
];
const EXTRA_IMGS = {
  'Anti-Materiel X':                ['images/AT-ST.webp'],
  'Anti-Personnel X':               ['images/Wicket.webp','images/Ewok Skirmishers.webp'],
  'Upgrading and Downgrading Dice': ['images/Grand Admiral Thrawn.webp'],
  'Cumbersome':                     ['images/AT-ST.webp'],
  'Beam X':                         ['images/Iden Versio.webp'],
};
function fallbackImg(name){
  const lower=name.toLowerCase();
  for(const [pat,img] of KEYWORD_FALLBACK){
    if(lower.startsWith(pat.toLowerCase())) return 'images/'+img;
  }
  return null;
}
function applyPermImgs(){
  CARDS.forEach(c=>{
    const base=c.name.replace(/\s+\d+$/,'');
    // Named overrides (exact match or base name match)
    const named=EXTRA_IMGS[c.name]||EXTRA_IMGS[base];
    if(named){ if(!c.imgs)c.imgs=[]; named.forEach(p=>{if(!c.imgs.includes(p))c.imgs.push(p);}); }
    // KEYWORD_FALLBACK for any card still without images
    if(!c.imgs||!c.imgs.length){
      const fb=fallbackImg(c.name);
      if(fb){ if(!c.imgs)c.imgs=[]; c.imgs.push(fb); }
    }
  });
}

let _allFeedback = {}; // card_name -> [{user_identifier, feedback, created_at}]
let catFilter='all';
function setCF(v,btn){
  catFilter=v;
  document.querySelectorAll('#cat-filters .dark-pill').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active'); renderCatalog();
}
function renderCatalog(){
  let list=[...CARDS];
  // Apply list filter (catListId===null inherits activeListId)
  const effectiveCatListId=catListId===null?activeListId:catListId;
  if(effectiveCatListId){
    const lst=getListById(effectiveCatListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      const extras=CARDS.filter(c=>catExtras.has(c.type));
      const pinnedExtra=CARDS.filter(c=>catExtras.has('pinned')&&s(c.name).pinned);
      list=[...new Set([...CARDS.filter(c=>kwSet.has(c.name.toLowerCase())),...extras,...pinnedExtra])];
    }
  }
  if(catFilter==='learned')    list=list.filter(c=>s(c.name).learned);
  if(catFilter==='unlearned')  list=list.filter(c=>!s(c.name).learned);
  if(catFilter==='unit')       list=list.filter(c=>c.type==='unit');
  if(catFilter==='weapon')     list=list.filter(c=>c.type==='weapon');
  if(catFilter==='concept')    list=list.filter(c=>c.type==='concept');
  if(catFilter==='noconcept')  list=list.filter(c=>c.type!=='concept');
  if(catFilter==='feedback')   list=list.filter(c=>(_allFeedback[c.name]||[]).some(r=>!r.handled));
  // Search filter
  const q=(document.getElementById('cat-search')?.value||'').toLowerCase().trim();
  if(q) list=list.filter(c=>c.name.toLowerCase().includes(q)||(c.definition||'').toLowerCase().includes(q));
  list.sort((a,b)=>a.name.localeCompare(b.name));
  document.getElementById('cat-count').textContent=`${list.length} keyword${list.length!==1?'s':''}`;
  const g=document.getElementById('cat-grid');
  if(!list.length){ g.innerHTML='<p class="empty-msg">Nothing here.</p>'; return; }
  g.innerHTML=list.map(c=>{
    const st=s(c.name), src=ci(c);
    const sn=c.name.replace(/'/g,"\\'");
    const def=st.customDef||c.definition||'';
    const preview=def.length>90?def.slice(0,90).replace(/\s\S*$/,'')+'\u2026':def;
    const dn=dispName(c.name);
    const th=src
      ?`<img class="cat-thumb" src="${src}" alt="${dn}" loading="lazy"
             onerror="this.outerHTML='<div class=cat-thumb-ph>${dn[0]}</div>'">`
      :`<div class="cat-thumb-ph">${dn[0]}</div>`;
    return `<div class="cat-card${st.learned?' lrnd':''}" onclick="openMod('${sn}')">
      ${th}
      ${st.learned?'<span class="cat-badge badge-learned">Learned</span>':''}${st.pinned?'<span class="cat-badge" style="background:rgba(245,197,24,.9);color:#000;top:6px;left:6px">&#128204;</span>':''}
      <div class="cat-lbl">
        <div class="cat-name">${dn}</div>
        <div class="cat-type">${c.type}</div>
        <div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:3px;line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${escHtml(preview)}</div>
      </div>
    </div>`;
  }).join('');
}

let mcard=null;
function openMod(name){
  mcard=CARDS.find(c=>c.name===name);
  renderMod(); document.getElementById('modal-bg').classList.add('on');
}
function renderMod(){
  const c=mcard, st=s(c.name), src=ci(c);
  const stEl=document.getElementById('mod-st');
  if(stEl){ stEl.textContent=''; stEl.className='modal-status'; }
  const picker=document.getElementById('mod-list-picker');
  if(picker) picker.style.display='none';
  document.getElementById('mod-img').innerHTML=src
    ?`<img class="modal-photo" src="${src}" alt="${c.name}"
           onerror="this.outerHTML='<div class=modal-photo-ph>No image</div>'">`
    :`<div class="modal-photo-ph">No image</div>`;
  document.getElementById('mod-name').textContent=dispName(c.name);
  document.getElementById('mod-type').innerHTML=typeBadgeHTML(c.type);
  const defText=st.customDef||c.definition;
  const modSum=document.getElementById('mod-summary');
  if(modSum){
    let summary=st.customSummary||c.summary||'';
    if(!summary){
      const firstSent=(defText||'').split(/(?<=\.)\s/)[0]||'';
      summary=firstSent.length>20&&(defText||'').length>firstSent.length+30?firstSent:'';
    }
    modSum.textContent=summary;
    modSum.style.display=summary?'':'none';
    modSum.style.borderColor=st.customSummary?'rgba(245,197,24,.3)':'';
  }
  const sumTA=document.getElementById('mod-summary-edit');
  const sumActs=document.getElementById('mod-summary-edit-acts');
  if(sumTA) sumTA.style.display='none';
  if(sumActs) sumActs.style.display='none';
  document.getElementById('mod-def').textContent=defText;
  document.getElementById('mod-def').style.borderColor=st.customDef?'rgba(245,197,24,.3)':'';
  const modSrc=document.getElementById('mod-src');
  if(modSrc) modSrc.textContent='Source: '+cardSource(c);
  const modArtCredit=document.getElementById('mod-art-credit');
  if(modArtCredit){
    const ac=c.art_credit||'';
    modArtCredit.textContent=ac?'Image: '+ac:'';
    modArtCredit.style.display=ac?'':'none';
  }
  const modUnits=document.getElementById('mod-units');
  if(modUnits){
    modUnits.textContent=c.units?'Units: '+c.units:'';
    modUnits.style.display=c.units?'':'none';
  }
  const ml=document.getElementById('mod-lrnd');
  ml.textContent=st.learned?'Learned \u2014 reset':'Mark as learned';
  ml.className='modal-btn'+(st.learned?' lrnd':'');
  const mp=document.getElementById('mod-pin');
  if(mp){ mp.innerHTML=st.pinned?'&#128204; Pinned':'&#128204; Pin'; mp.className='modal-btn'+(st.pinned?' pin-on':''); }
  const editTA=document.getElementById('mod-def-edit');
  const editActs=document.getElementById('mod-def-edit-acts');
  if(editTA){ editTA.style.display='none'; document.getElementById('mod-def').style.display='block'; }
  if(editActs) editActs.style.display='none';
  // Reset feedback area
  const mfa=document.getElementById('mod-feedback-area');
  const mfi=document.getElementById('mod-feedback-input');
  if(mfa) mfa.style.display='none';
  if(mfi) mfi.value='';
  // Owner feedback display
  renderOwnerFeedbackEl(c.name, 'mod-owner-feedback');
}
function modTogglePin(){
  const st=s(mcard.name); st.pinned=!st.pinned;
  saveState(); renderMod(); renderCatalog();
}
function modToggleEditDef(){
  const editTA=document.getElementById('mod-def-edit');
  const editActs=document.getElementById('mod-def-edit-acts');
  const defEl=document.getElementById('mod-def');
  if(!editTA) return;
  const isOpen=editTA.style.display!=='none';
  if(isOpen){
    editTA.style.display='none';
    if(editActs) editActs.style.display='none';
    defEl.style.display='block';
  } else {
    editTA.value=s(mcard.name).customDef||mcard.definition;
    editTA.style.display='block';
    if(editActs) editActs.style.display='flex';
    defEl.style.display='none';
    editTA.focus();
  }
}
function modSaveDef(){
  const val=document.getElementById('mod-def-edit').value.trim();
  s(mcard.name).customDef=val||'';
  saveState();
  document.getElementById('mod-def').textContent=val||mcard.definition;
  document.getElementById('mod-def').style.borderColor=val?'rgba(245,197,24,.3)':'';
  document.getElementById('mod-def-edit').style.display='none';
  document.getElementById('mod-def-edit-acts').style.display='none';
  document.getElementById('mod-def').style.display='block';
  const modSrc=document.getElementById('mod-src');
  if(modSrc) modSrc.textContent='Source: '+cardSource(mcard);
}
function modResetDef(){
  s(mcard.name).customDef='';
  saveState();
  document.getElementById('mod-def-edit').value=mcard.definition;
  document.getElementById('mod-def').textContent=mcard.definition;
  document.getElementById('mod-def').style.borderColor='';
  const modSrc=document.getElementById('mod-src');
  if(modSrc) modSrc.textContent='Source: '+cardSource(mcard);
}
function modToggleEditSummary(){
  const sumTA=document.getElementById('mod-summary-edit');
  const sumActs=document.getElementById('mod-summary-edit-acts');
  const sumEl=document.getElementById('mod-summary');
  if(!sumTA) return;
  const isOpen=sumTA.style.display!=='none';
  if(isOpen){
    sumTA.style.display='none';
    if(sumActs) sumActs.style.display='none';
  } else {
    sumTA.value=s(mcard.name).customSummary||mcard.summary||'';
    sumTA.style.display='block';
    if(sumActs) sumActs.style.display='flex';
    sumTA.focus();
  }
}
function modSaveSummary(){
  const val=document.getElementById('mod-summary-edit').value.trim();
  s(mcard.name).customSummary=val;
  saveState();
  const modSum=document.getElementById('mod-summary');
  if(modSum){ modSum.textContent=val||mcard.summary||''; modSum.style.display=(val||mcard.summary)?'':'none'; modSum.style.borderColor=val?'rgba(245,197,24,.3)':''; }
  document.getElementById('mod-summary-edit').style.display='none';
  document.getElementById('mod-summary-edit-acts').style.display='none';
}
function modResetSummary(){
  s(mcard.name).customSummary='';
  saveState();
  document.getElementById('mod-summary-edit').value=mcard.summary||'';
  const modSum=document.getElementById('mod-summary');
  if(modSum){ modSum.textContent=mcard.summary||''; modSum.style.display=mcard.summary?'':'none'; modSum.style.borderColor=''; }
}
function modToggleLearned(){ toggleLearned(mcard.name); renderMod(); renderCatalog(); }
function modToggleFeedback(){
  const area=document.getElementById('mod-feedback-area');
  if(!area) return;
  area.style.display=area.style.display==='none'?'block':'none';
  if(area.style.display==='block') document.getElementById('mod-feedback-input')?.focus();
}
async function submitModFeedback(){
  const text=(document.getElementById('mod-feedback-input')?.value||'').trim();
  if(!text){ alert('Please enter some feedback.'); return; }
  const el=document.getElementById('mod-st');
  if(el){ el.textContent='Submitting\u2026'; el.className='modal-status work'; }
  const ok=await submitFeedback(mcard.name, text);
  if(ok){
    document.getElementById('mod-feedback-input').value='';
    document.getElementById('mod-feedback-area').style.display='none';
    if(el){ el.textContent='Feedback submitted \u2014 thank you!'; el.className='modal-status ok'; }
  } else {
    if(el){ el.textContent='Failed to submit feedback.'; el.className='modal-status err'; }
  }
}
function toggleFsFeedback(){
  const area=document.getElementById('fs-feedback-area');
  if(!area) return;
  area.style.display=area.style.display==='none'?'block':'none';
  if(area.style.display==='block') document.getElementById('fs-feedback-input')?.focus();
}
async function submitFsFeedback(){
  const text=(document.getElementById('fs-feedback-input')?.value||'').trim();
  if(!text){ setStatus('Please enter some feedback.','err',2000); return; }
  setStatus('Submitting\u2026','work');
  const ok=await submitFeedback(deck[cur].name, text);
  if(ok){
    document.getElementById('fs-feedback-input').value='';
    document.getElementById('fs-feedback-area').style.display='none';
    setStatus('Feedback submitted \u2014 thank you!','ok',3000);
  } else {
    setStatus('Failed to submit feedback.','err',3000);
  }
}
async function submitFeedback(cardName, text){
  if(!_supa) return false;
  try{
    const userIdentifier=_currentUser?.email||'guest';
    const{error}=await _supa.from('card_feedback').insert({card_name:cardName,user_identifier:userIdentifier,feedback:text});
    if(error) throw error;
    return true;
  }catch(e){ console.warn('submitFeedback failed:',e.message); return false; }
}
async function modRegenSummary(){
  if(!mcard) return;
  const c=mcard, st=s(c.name);
  const def=(st.customDef||c.definition||'').trim();
  const el=document.getElementById('mod-st');
  if(!def){ if(el){ el.textContent='No definition to summarise'; el.className='modal-status err'; } return; }
  if(el){ el.textContent='Generating AI summary\u2026'; el.className='modal-status work'; }
  try{
    const resp=await fetch(SUPA_URL+'/functions/v1/summarize',{
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+SUPA_KEY},
      body:JSON.stringify({definition:def,name:c.name})
    });
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    const{summary,error}=await resp.json();
    if(error) throw new Error(error);
    st.customSummary=summary; saveState();
    const modSum=document.getElementById('mod-summary');
    if(modSum){ modSum.textContent=summary; modSum.style.display=''; modSum.style.borderColor='rgba(245,197,24,.3)'; }
    if(el){ el.textContent='AI summary updated'; el.className='modal-status ok'; }
  }catch(e){
    if(el){ el.textContent='AI unavailable \u2014 '+e.message; el.className='modal-status err'; }
  }
}
async function loadOwnerFeedback(){
  if(!_supa||!_currentUser) return;
  try{
    const{data,error}=await _supa.from('card_feedback').select('id,card_name,user_identifier,feedback,created_at,handled').order('created_at',{ascending:false});
    if(error) throw error;
    _allFeedback={};
    (data||[]).forEach(r=>{
      if(!_allFeedback[r.card_name]) _allFeedback[r.card_name]=[];
      _allFeedback[r.card_name].push(r);
    });
    const fbPill=document.getElementById('cat-pill-feedback');
    if(fbPill) fbPill.style.display='';
  }catch(e){ console.warn('loadOwnerFeedback failed:',e.message); }
}
async function markFeedbackHandled(id, cardName){
  if(!_supa) return;
  try{
    const{error}=await _supa.from('card_feedback').update({handled:true}).eq('id',id);
    if(error) throw error;
    // Update local state
    const entries=_allFeedback[cardName]||[];
    const entry=entries.find(r=>r.id===id);
    if(entry) entry.handled=true;
    renderOwnerFeedbackEl(cardName,'mod-owner-feedback');
    renderOwnerFeedbackEl(cardName,'fs-owner-feedback');
    renderCatalog(); // refresh feedback filter
  }catch(e){ console.warn('markFeedbackHandled failed:',e.message); }
}
function renderOwnerFeedbackEl(cardName, elId){
  const el=document.getElementById(elId);
  if(!el) return;
  const isOwner=(_currentUser?.email==='martinjsleeman@gmail.com');
  const entries=_allFeedback[cardName]||[];
  if(!isOwner||!entries.length){ el.style.display='none'; return; }
  el.style.display='block';
  const sn=cardName.replace(/'/g,"\\'");
  el.innerHTML='<div style="font-size:10px;font-weight:700;color:rgba(245,197,24,.6);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Feedback</div>'+
    entries.map(r=>{
      const dt=new Date(r.created_at).toLocaleDateString();
      const dim=r.handled?'opacity:.4;':'';
      const btn=r.handled
        ?`<span style="font-size:10px;color:rgba(255,255,255,.3)">\u2713 Handled</span>`
        :`<button onclick="markFeedbackHandled('${r.id}','${sn}')" style="font-size:10px;padding:2px 7px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:4px;color:rgba(255,255,255,.6);cursor:pointer;font-family:inherit">\u2713 Mark handled</button>`;
      return `<div style="${dim}margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,.07)"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px"><span style="color:rgba(245,197,24,.7);font-size:11px">${escHtml(r.user_identifier)} &bull; ${dt}</span>${btn}</div>${escHtml(r.feedback)}</div>`;
    }).join('');
}
function closeMod(e){
  if(e&&!e.target.classList.contains('modal-bg')&&e.target.id!=='modal-bg') return;
  const picker=document.getElementById('mod-list-picker');
  if(picker) picker.style.display='none';
  document.getElementById('modal-bg').classList.remove('on'); mcard=null;
}
function modShowAddToList(){
  const picker=document.getElementById('mod-list-picker');
  if(!picker) return;
  if(picker.style.display!=='none'){ picker.style.display='none'; return; }
  const lists=loadLists();
  const stEl=document.getElementById('mod-st');
  if(!lists.length){
    stEl.textContent='No lists saved yet \u2014 go to Lists to create one.';
    stEl.className='modal-status err'; return;
  }
  const kwName=mcard.name;
  picker.innerHTML=lists.map(l=>{
    const has=(l.keywords||[]).some(k=>k.toLowerCase()===kwName.toLowerCase());
    const id=l.id.replace(/'/g,"\\'");
    return `<div class="list-dd-item${has?' active':''}" onclick="modAddToList('${id}')">`+
      `${escHtml(l.name)}`+
      (has?' <span style="color:var(--G);font-size:11px">&#10003; already in list</span>':'')+
      `</div>`;
  }).join('');
  picker.style.display='block';
}
function modAddToList(listId){
  const lists=loadLists();
  const list=lists.find(l=>l.id===listId);
  if(!list||!mcard) return;
  const kwName=mcard.name;
  const stEl=document.getElementById('mod-st');
  const picker=document.getElementById('mod-list-picker');
  const idx=(list.keywords||[]).findIndex(k=>k.toLowerCase()===kwName.toLowerCase());
  if(idx===-1){
    if(!list.keywords) list.keywords=[];
    list.keywords.push(kwName);
    list.keywords.sort();
    saveLists(lists);
    stEl.textContent=`"${dispName(kwName)}" added to "${list.name}"`;
    stEl.className='modal-status ok';
  } else {
    stEl.textContent=`Already in "${list.name}"`;
    stEl.className='modal-status work';
  }
  if(picker) picker.style.display='none';
}

// ─── UNIT DATABASE (from LegionHQ2) ──────────────────────────────────────────
/*UNIT_DB_JSON*/

// ─── TABLETOP ADMIRAL UNIT LOOKUP (hex id → name) ────────────────────────────
/*TTA_DB_JS*/

const UNIT_STATS={
  "at":{"sp":2,"w":20,"cg":null,"dd":"r","ds":false,"as":"c"},
  "au":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "av":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "ay":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "az":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "ba":{"sp":2,"w":5, "cg":1,   "dd":"w","ds":false,"as":null},
  "bd":{"sp":2,"w":8, "cg":2,   "dd":"w","ds":false,"as":null},
  "be":{"sp":1,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "bg":{"sp":1,"w":11,"cg":3,   "dd":"r","ds":false,"as":null},
  "bf":{"sp":3,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "bh":{"sp":2,"w":10,"cg":3,   "dd":"r","ds":false,"as":null},
  "fn":{"sp":2,"w":8, "cg":null,"dd":"r","ds":false,"as":"c"},
  "kg":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "nm":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "on":{"sp":2,"w":10,"cg":3,   "dd":"r","ds":false,"as":null},
  "tm":{"sp":1,"w":8, "cg":3,   "dd":"r","ds":false,"as":null},
  "we":{"sp":1,"w":11,"cg":3,   "dd":"r","ds":false,"as":null},
  "wl":{"sp":2,"w":5, "cg":null,"dd":"r","ds":false,"as":"c"},
  "wm":{"sp":2,"w":5, "cg":null,"dd":"r","ds":false,"as":"c"},
  "ui":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "Ff":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "Fg":{"sp":2,"w":4, "cg":3,   "dd":"w","ds":false,"as":null},
  "hf":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":true, "as":null},
  "xh":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "xz":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "sr":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "ab":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "ac":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":"h"},
  "ad":{"sp":2,"w":6, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "ae":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "af":{"sp":2,"w":8, "cg":null,"dd":"r","ds":false,"as":"c"},
  "ag":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "ah":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "ai":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "aj":{"sp":2,"w":8, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "ak":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "an":{"sp":1,"w":4, "cg":2,   "dd":"w","ds":false,"as":null},
  "ao":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "ap":{"sp":3,"w":9, "cg":3,   "dd":"r","ds":false,"as":null},
  "aq":{"sp":3,"w":8, "cg":3,   "dd":"r","ds":false,"as":null},
  "fm":{"sp":2,"w":6, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "gv":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "he":{"sp":3,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "jg":{"sp":2,"w":4, "cg":3,   "dd":"w","ds":false,"as":null},
  "kf":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "lv":{"sp":2,"w":6, "cg":3,   "dd":"w","ds":false,"as":null},
  "nl":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":"h"},
  "om":{"sp":3,"w":9, "cg":3,   "dd":"r","ds":false,"as":null},
  "vd":{"sp":2,"w":6, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "Fb":{"sp":2,"w":6, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "Fc":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":"h"},
  "ve":{"sp":2,"w":4, "cg":2,   "dd":"w","ds":false,"as":null},
  "vk":{"sp":2,"w":4, "cg":1,   "dd":"w","ds":false,"as":null},
  "vu":{"sp":2,"w":3, "cg":1,   "dd":"w","ds":false,"as":null},
  "vv":{"sp":2,"w":3, "cg":3,   "dd":"w","ds":false,"as":null},
  "wd":{"sp":2,"w":4, "cg":2,   "dd":"w","ds":false,"as":null},
  "pl":{"sp":2,"w":8, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "gw":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "na":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "Fp":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "Gs":{"sp":2,"w":5, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "Gu":{"sp":2,"w":5, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "Gw":{"sp":2,"w":5, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "fy":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "fz":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "gb":{"sp":2,"w":10,"cg":3,   "dd":"r","ds":false,"as":null},
  "ic":{"sp":3,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "jh":{"sp":2,"w":4, "cg":3,   "dd":"w","ds":false,"as":null},
  "kw":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "kz":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "mb":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "ns":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "oo":{"sp":2,"w":10,"cg":3,   "dd":"r","ds":false,"as":null},
  "ol":{"sp":2,"w":5, "cg":null,"dd":"r","ds":false,"as":"c"},
  "ue":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "xi":{"sp":2,"w":6, "cg":3,   "dd":"w","ds":false,"as":null},
  "xj":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "xp":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "ph":{"sp":2,"w":8, "cg":null,"dd":"r","ds":false,"as":"c"},
  "pg":{"sp":2,"w":8, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "pm":{"sp":2,"w":8, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "po":{"sp":2,"w":8, "cg":null,"dd":"r","ds":false,"as":"c"},
  "qs":{"sp":2,"w":9, "cg":3,   "dd":"r","ds":false,"as":null},
  "qh":{"sp":3,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "fx":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "ga":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "gc":{"sp":2,"w":10,"cg":3,   "dd":"r","ds":false,"as":null},
  "gx":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "ia":{"sp":2,"w":11,"cg":null,"dd":"r","ds":false,"as":"c"},
  "ie":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "la":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "mc":{"sp":3,"w":5, "cg":1,   "dd":"w","ds":false,"as":null},
  "nb":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "px":{"sp":2,"w":6, "cg":2,   "dd":"r","ds":false,"as":"c"},
  "pz":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "qa":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "qk":{"sp":2,"w":6, "cg":2,   "dd":"r","ds":false,"as":null},
  "qt":{"sp":2,"w":10,"cg":3,   "dd":"r","ds":false,"as":null},
  "ut":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "wn":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "wo":{"sp":3,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "wp":{"sp":3,"w":5, "cg":1,   "dd":"w","ds":false,"as":null},
  "ya":{"sp":2,"w":6, "cg":2,   "dd":"r","ds":false,"as":null},
  "aw":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "ax":{"sp":2,"w":8, "cg":null,"dd":"r","ds":false,"as":null},
  "Bj":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "Fe":{"sp":3,"w":8, "cg":3,   "dd":"r","ds":false,"as":null},
  "Hb":{"sp":2,"w":8, "cg":null,"dd":"r","ds":false,"as":"c"},
  "Hc":{"sp":2,"w":8, "cg":null,"dd":"r","ds":false,"as":"c"},
  "Hr":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "Hw":{"sp":2,"w":6, "cg":3,   "dd":"r","ds":false,"as":null},
  "Hz":{"sp":2,"w":6, "cg":3,   "dd":"r","ds":false,"as":null},
  "Hy":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "kx":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "mk":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "qy":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "qz":{"sp":2,"w":6, "cg":1,   "dd":"w","ds":false,"as":null},
  "ra":{"sp":2,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "rb":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
  "rc":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "rd":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "sm":{"sp":3,"w":9, "cg":3,   "dd":"r","ds":false,"as":null},
  "sq":{"sp":3,"w":5, "cg":2,   "dd":"w","ds":false,"as":null},
  "ti":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "tj":{"sp":2,"w":5, "cg":null,"dd":"r","ds":false,"as":"c"},
  "tk":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":null},
  "tl":{"sp":2,"w":6, "cg":null,"dd":"r","ds":false,"as":"c"},
  "vj":{"sp":1,"w":12,"cg":null,"dd":"r","ds":false,"as":"c"},
  "Ef":{"sp":3,"w":11,"cg":null,"dd":"r","ds":false,"as":"c"},
  "xd":{"sp":2,"w":6, "cg":2,   "dd":"r","ds":false,"as":"c"},
  "xe":{"sp":2,"w":10,"cg":3,   "dd":"r","ds":false,"as":null},
  "Bc":{"sp":2,"w":5, "cg":3,   "dd":"r","ds":false,"as":"c"},
  "Hq":{"sp":2,"w":4, "cg":1,   "dd":"w","ds":false,"as":null},
  "nr":{"sp":2,"w":5, "cg":3,   "dd":"w","ds":false,"as":null},
  "nk":{"sp":2,"w":3, "cg":2,   "dd":"w","ds":false,"as":null},
  "Fd":{"sp":2,"w":6, "cg":2,   "dd":"w","ds":false,"as":null},
};

// ─── ARMY LIST PARSING ───────────────────────────────────────────────────────
function parseUnitCode(code){
  // Format: {count}{2-char-unit-id}{upgrade-tokens...}
  // upgrade token: '0' = empty slot, otherwise 2 chars = upgrade ID
  let i=0;
  const count=parseInt(code[i++])||1;
  const unitId=code.slice(i,i+2); i+=2;
  const upgrades=[];
  while(i<code.length){
    if(code[i]==='0'){ upgrades.push(null); i++; }
    else{ upgrades.push(code.slice(i,i+2)); i+=2; }
  }
  return {count,unitId,upgrades};
}

function parseLegionHQUrl(url){
  // URL format: https://legionhq2.com/list/{faction}/{points}:{codes}
  // codes = comma-separated unit codes and card IDs
  try{
    const m=url.match(/legionhq2\.com\/list\/([^/]+)\/([^/?#]+)/);
    if(!m) return null;
    const faction=m[1];
    const hashPart=m[2];
    const colonIdx=hashPart.indexOf(':');
    if(colonIdx<0) return null;
    const points=parseInt(hashPart.slice(0,colonIdx))||0;
    const codes=hashPart.slice(colonIdx+1).split(',');
    return {faction,points,codes};
  }catch(e){ return null; }
}

function getUnitFromCode(code){
  const unit=UNIT_DB[code];
  if(unit) return unit; // direct card reference (command/battle card)
  return null;
}

// Normalize keyword base name (strip trailing numbers)
function kwBase(kw){
  return kw.replace(/\s+\d+(\s+.*)?$/,'').replace(/\s*:\s*.+$/,function(m){
    // keep colon for keywords that are defined with subtypes like "Immune: Pierce"
    return m;
  }).trim();
}

function decodeArmy(url){
  const parsed=parseLegionHQUrl(url);
  if(!parsed) return null;
  const {faction,points,codes}=parsed;
  const units=[];
  const allKeywords=new Set();

  for(const code of codes){
    // Check if it's a direct card ID (command/battle - 2 chars, no count prefix)
    if(UNIT_DB[code]){
      // standalone card - skip (command cards, battle cards)
      continue;
    }
    // Try to parse as unit code
    if(code.length<3) continue;
    const firstChar=code[0];
    if(!/[0-9]/.test(firstChar)) continue; // must start with count digit
    const {count,unitId,upgrades}=parseUnitCode(code);
    const unit=UNIT_DB[unitId];
    if(!unit) continue;
    units.push({count,unit,unitId,upgrades});
    // Collect keywords
    (unit.k||[]).forEach(kw=>{
      const base=kw.replace(/\s+\d+(\s+.*)?$/,'').trim();
      allKeywords.add(base);
    });
  }

  return {faction,points,units,keywords:[...allKeywords].sort()};
}

// ─── TABLETOP ADMIRAL URL PARSER ─────────────────────────────────────────────
// URL format: https://tabletopadmiral.com/listbuilder/{Faction}/{hash}
// hash: {version_prefix}-{_hexId_upg1,upg2,..._hexId_upg1,...}-{suffix}
function parseTtaUrl(url){
  try{
    const m=url.match(/tabletopadmiral\.com\/listbuilder\/([^/]+)\/([^/?#]+)/);
    if(!m) return null;
    const factionRaw=m[1];
    const hash=m[2];
    // Strip version prefix like "N-"
    const rest=hash.replace(/^[A-Za-z]+-?/,'');
    // Extract all _hexid_ unit codes
    const hexIds=[...rest.matchAll(/_([0-9a-f]+)_/gi)].map(x=>x[1].toLowerCase());
    // Count occurrences per unit
    const counts={};
    hexIds.forEach(id=>counts[id]=(counts[id]||0)+1);
    const units=[];
    const allKeywords=new Set();
    for(const [hexId,count] of Object.entries(counts)){
      const tta=TTA_UNITS[hexId];
      if(!tta) continue;
      // Find matching unit in UNIT_DB by name
      let dbUnit=null;
      for(const u of Object.values(UNIT_DB)){
        if(u.n===tta.n){dbUnit=u;break;}
      }
      const displayUnit=dbUnit||{n:tta.n,t:'',k:[],i:''};
      units.push({count,unit:displayUnit,hexId});
      if(dbUnit){
        (dbUnit.k||[]).forEach(kw=>{
          allKeywords.add(kw.replace(/\s+\d+(\s+.*)?$/,'').trim());
        });
      }
    }
    // Faction name mapping
    const fLow=factionRaw.toLowerCase().replace(/\s/g,'');
    const fMap={'empire':'empire','rebel':'rebels','galacticrepublic':'republic',
                'separatistalliance':'separatist','mercenary':'mercenary'};
    const faction=fMap[fLow]||fLow;
    return{faction,points:0,units,keywords:[...allKeywords].sort(),source:'tta'};
  }catch(e){return null;}
}

// ─── LIST PERSISTENCE ─────────────────────────────────────────────────────────
function loadLists(){
  try{ return JSON.parse(localStorage.getItem('swlegion_lists')||'[]'); }
  catch(e){ return []; }
}
function saveLists(lists){
  localStorage.setItem('swlegion_lists',JSON.stringify(lists));
  scheduleSync();
}
function getListById(id){
  return loadLists().find(l=>l.id===id)||null;
}

// ─── LISTS SCREEN ─────────────────────────────────────────────────────────────
let _parsedArmy=null;

function parseListUrl(){
  const url=document.getElementById('list-url-input').value.trim();
  if(!url){ showListStatus('Please enter a LegionHQ2 or Tabletop Admiral URL','err'); return; }
  if(url.includes('legionhq2.com')){
    _parsedArmy=decodeArmy(url);
  } else if(url.includes('tabletopadmiral.com')){
    _parsedArmy=parseTtaUrl(url);
  } else {
    showListStatus('Supports LegionHQ2 (legionhq2.com) and Tabletop Admiral (tabletopadmiral.com)','err');
    return;
  }
  if(!_parsedArmy){
    showListStatus('Could not parse URL — check that it includes the list hash.','err'); return;
  }
  renderParseResult(_parsedArmy, url);
}

function renderParseResult(army, url){
  const panel=document.getElementById('list-parse-result');
  panel.style.display='block';

  // Faction badge
  const fb=document.getElementById('list-parse-faction-badge');
  fb.textContent=army.faction.toUpperCase();
  fb.className='faction-badge faction-'+army.faction.toLowerCase();
  document.getElementById('list-parse-points').textContent=army.points?army.points+' pts':(army.source==='tta'?'Tabletop Admiral':'');
  document.getElementById('list-parse-unit-count').textContent=army.units.length+' unit types';

  // Units
  const unitsEl=document.getElementById('list-parse-units');
  unitsEl.innerHTML=army.units.map(({count,unit,unitId})=>{
    const kws=(unit.k||[]).map(k=>k.replace(/\s+\d+(\s+.*)?$/,'').trim()).slice(0,3).join(', ');
    const title=unit.t?` <em style="color:rgba(255,255,255,.4);font-size:11px">${unit.t}</em>`:'';
    return `<div class="list-unit-row">
      <span class="list-unit-count">${count}x</span>
      <div><div class="list-unit-name">${unit.n}${title}</div>
      ${kws?`<div class="list-unit-kws">${kws}${(unit.k||[]).length>3?'...':''}</div>`:''}
      </div></div>`;
  }).join('');

  // Keywords
  document.getElementById('list-kw-count').textContent=army.keywords.length;
  const tagsEl=document.getElementById('list-kw-tags');
  tagsEl.innerHTML=army.keywords.map(kw=>`<span class="kw-tag">${escHtml(kw)}</span>`).join('');

  // Pre-fill list name
  const fCap=army.faction.charAt(0).toUpperCase()+army.faction.slice(1);
  const defaultName=army.points?fCap+' '+army.points+'pts':fCap+' List';
  document.getElementById('list-name-input').value=defaultName;
  document.getElementById('list-save-status').textContent='';
}

function saveList(){
  if(!_parsedArmy){ showListStatus('Parse a URL first','err'); return; }
  const name=document.getElementById('list-name-input').value.trim();
  if(!name){ showListStatus('Enter a list name','err'); return; }
  const url=document.getElementById('list-url-input').value.trim();

  const lists=loadLists();
  const id='lst_'+Date.now();
  lists.push({
    id, name,
    faction:_parsedArmy.faction,
    points:_parsedArmy.points,
    keywords:_parsedArmy.keywords,
    armyUrl:url,
    createdAt:new Date().toISOString()
  });
  saveLists(lists);
  showListStatus('List saved!','ok');
  _parsedArmy=null;
  document.getElementById('list-url-input').value='';
  document.getElementById('list-parse-result').style.display='none';
  renderSavedLists();
  updateListPillLabel();
}

function showListStatus(msg,cls){
  const el=document.getElementById('list-save-status');
  el.textContent=msg;
  el.style.color=cls==='err'?'#f08080':'#6effc4';
}

function renderSavedLists(){
  const lists=loadLists();
  const el=document.getElementById('lists-container');
  if(!lists.length){
    el.innerHTML='<div class="lists-empty">No lists saved yet. Import one above.</div>';
    return;
  }
  el.innerHTML=lists.map(lst=>{
    const isActive=activeListId===lst.id;
    return `<div class="list-card${isActive?' active-filter':''}" data-list-id="${lst.id}" onclick="openListModal('${lst.id}')">
      <div class="list-card-info">
        <div class="list-card-name">${escHtml(lst.name)}</div>
        <div class="list-card-meta">
          <span class="faction-badge faction-${lst.faction||''}" style="font-size:10px;padding:2px 8px">${(lst.faction||'').toUpperCase()}</span>
          &nbsp;${lst.points||0} pts &nbsp;&#183;&nbsp; ${lst.keywords.length} keywords
        </div>
      </div>
      <div class="list-card-actions" onclick="event.stopPropagation()">
        <button class="list-btn-filter${isActive?' on':''}" data-list-id="${lst.id}"
          onclick="toggleListFilter('${lst.id}')">${isActive?'Filtering':'Filter'}</button>
        <button class="list-btn-edit" onclick="openListModal('${lst.id}')">Edit</button>
      </div>
    </div>`;
  }).join('');
}

function toggleListFilter(listId){
  if(activeListId===listId){
    setListFilter(null);
  } else {
    setListFilter(listId);
    showScreen('flashcard-screen');
  }
}

// kept for compatibility - just refreshes pill labels
function updateListSelectDropdown(){ updateListPillLabel(); updateCatListPillLabel(); }

// ─── LIST MODAL ───────────────────────────────────────────────────────────────
let _lmListId=null;
let _lmEditKws=[];

function openListModal(listId){
  _lmListId=listId;
  const lst=getListById(listId);
  if(!lst) return;
  _lmEditKws=[...lst.keywords];
  document.getElementById('lm-name').textContent=lst.name;
  document.getElementById('lm-meta').innerHTML=
    `<span class="faction-badge faction-${lst.faction||''}" style="font-size:10px;padding:2px 7px">${(lst.faction||'').toUpperCase()}</span>`+
    ` &nbsp;${lst.points||0} pts &nbsp;&#183;&nbsp; ${lst.keywords.length} keywords`;

  // KW tab
  document.getElementById('lm-kw-tags').innerHTML=
    lst.keywords.map(kw=>`<span class="kw-tag">${escHtml(kw)}</span>`).join('');

  setLmTab('kw');
  document.getElementById('list-modal-bg').classList.add('on');
}

function closeListModal(e){
  if(e&&e.target.id!=='list-modal-bg') return;
  document.getElementById('list-modal-bg').classList.remove('on');
  _lmListId=null;
}

function setLmTab(tab){
  document.getElementById('lm-tab-kw').classList.toggle('active',tab==='kw');
  document.getElementById('lm-tab-edit').classList.toggle('active',tab==='edit');
  document.getElementById('lm-tab-kw-panel').style.display=tab==='kw'?'block':'none';
  document.getElementById('lm-tab-edit-panel').style.display=tab==='edit'?'block':'none';
  if(tab==='edit') renderLmEditTags();
}

function renderLmEditTags(){
  const el=document.getElementById('lm-edit-tags');
  el.innerHTML=_lmEditKws.map((kw,i)=>
    `<span class="kw-tag removable" onclick="lmRemoveKw(${i})" title="Remove">${escHtml(kw)} &#215;</span>`
  ).join('');
  // Populate datalist
  const dl=document.getElementById('kw-datalist');
  const existing=new Set(_lmEditKws.map(k=>k.toLowerCase()));
  dl.innerHTML=CARDS.map(c=>c.name).filter(n=>!existing.has(n.toLowerCase()))
    .map(n=>`<option value="${escHtml(n)}">`).join('');
}

function lmRemoveKw(idx){
  _lmEditKws.splice(idx,1);
  renderLmEditTags();
}

function lmAddKeyword(){
  const inp=document.getElementById('lm-add-kw-input');
  const val=inp.value.trim();
  if(!val) return;
  if(!_lmEditKws.map(k=>k.toLowerCase()).includes(val.toLowerCase())){
    _lmEditKws.push(val);
    renderLmEditTags();
  }
  inp.value='';
}

function lmSaveEdit(){
  const lists=loadLists();
  const idx=lists.findIndex(l=>l.id===_lmListId);
  if(idx<0) return;
  lists[idx].keywords=[..._lmEditKws];
  saveLists(lists);
  // Refresh view
  openListModal(_lmListId);
  setLmTab('kw');
  renderSavedLists();
  updateListPillLabel();
  // Update active filter if needed
  if(activeListId===_lmListId){ clrStatus(); initDeck(); render(); }
  document.getElementById('lm-edit-status').textContent='Saved!';
  document.getElementById('lm-edit-status').style.color='#6effc4';
}

function lmDeleteList(){
  if(!confirm('Delete this list?')) return;
  let lists=loadLists();
  lists=lists.filter(l=>l.id!==_lmListId);
  saveLists(lists);
  if(activeListId===_lmListId) setListFilter(null);
  document.getElementById('list-modal-bg').classList.remove('on');
  renderSavedLists();
  updateListPillLabel();
}

function escHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ─── PRINT LIST KEYWORDS ─────────────────────────────────────────────────────
function printListKeywords(listId){
  const list=getListById(listId);
  if(!list||!list.keywords||!list.keywords.length){
    alert('No keywords in this list to print.'); return;
  }
  const sorted=[...list.keywords].sort((a,b)=>a.localeCompare(b));

  // Build a name-normalised lookup of cards
  function normKw(name){
    return name.replace(/\[\]/g,'').replace(/\s+X$/,'').replace(/:\s*.+$/,'').trim().toLowerCase();
  }
  const cardByNorm={};
  CARDS.forEach(c=>{ cardByNorm[normKw(c.name)]=c; });

  const rows=sorted.map(kw=>{
    const card=cardByNorm[kw.toLowerCase()]||cardByNorm[normKw(kw)];
    const def=card?(card.summary||card.definition||''):'';
    const type=card?((card.type||'').charAt(0).toUpperCase()+(card.type||'').slice(1)):'';
    const short=def.length>350?def.slice(0,350).replace(/\s\S+$/,'')+'…':def;
    return `<tr>
      <td class="pk-kw"><strong>${escHtml(dispName(kw))}</strong>${type?`<br><span class="pk-type">${escHtml(type)}</span>`:''}
      </td><td class="pk-def">${escHtml(short)}</td></tr>`;
  }).join('');

  const faction=(list.faction||'').toUpperCase();
  const pts=list.points?` · ${list.points} pts`:'';
  const src=list.source==='tta'?' · Tabletop Admiral':'';

  const pane=document.getElementById('print-keywords');
  pane.innerHTML=`
    <div class="pk-header">
      <h1>${escHtml(list.name)}</h1>
      <p class="pk-meta">${faction}${pts}${src} · ${sorted.length} keywords · Alphabetical</p>
    </div>
    <table class="pk-table"><tbody>${rows}</tbody></table>
    <p class="pk-footer">SW Legion Keywords App — ${new Date().toLocaleDateString()}</p>`;
  window.print();
}

// ─── SUPABASE AUTH & CLOUD SYNC ───────────────────────────────────────────────
const SUPA_URL = 'https://ddpretixfmrvkhyllcbm.supabase.co';
const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRkcHJldGl4Zm1ydmtoeWxsY2JtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU0NDA5NTUsImV4cCI6MjA5MTAxNjk1NX0.VFSG5ybkTu2pUW4Yjw9GN8r4Vl1CQt59w4tXlJ-hwoU';
let _supa = null, _currentUser = null, _syncTimer = null, _isGuest = false;
let _authReady = false; // tracks whether initAuth completed

function _timeout(ms, label){
  return new Promise((_,rej)=>setTimeout(()=>rej(new Error(label+' timed out after '+ms+'ms')),ms));
}

function initSupabase(){
  try{
    console.log('[AUTH] Creating Supabase client...');
    _supa = supabase.createClient(SUPA_URL, SUPA_KEY);
    console.log('[AUTH] Supabase client created OK');
  }catch(e){
    console.error('[AUTH] Supabase init FAILED:', e);
  }
}

async function initAuth(){
  console.log('[AUTH] initAuth starting...');
  initSupabase();
  if(!_supa){ console.warn('[AUTH] No client, going guest'); guestMode(); return; }

  // Register auth state listener
  _supa.auth.onAuthStateChange(async (event, session)=>{
    console.log('[AUTH] onAuthStateChange:', event, session?.user?.email||'no user');
    if(event==='SIGNED_IN' && session){
      _currentUser = session.user; _isGuest = false;
      console.log('[AUTH] SIGNED_IN — loading cloud state...');
      await loadCloudState();
      hideAuthScreen();
      startApp();
    } else if(event==='SIGNED_OUT'){
      _currentUser = null;
      console.log('[AUTH] SIGNED_OUT');
    }
  });

  // Check for existing session (with timeout so it never blocks forever)
  try{
    console.log('[AUTH] Calling getSession...');
    const t0 = Date.now();
    const { data, error } = await Promise.race([
      _supa.auth.getSession(),
      _timeout(5000, 'getSession')
    ]);
    console.log('[AUTH] getSession completed in', Date.now()-t0, 'ms',
      data?.session ? 'HAS SESSION ('+data.session.user.email+')' : 'no session',
      error || '');
    if(data?.session){
      _currentUser = data.session.user; _isGuest = false;
      await loadCloudState();
      hideAuthScreen();
      startApp();
    }
  }catch(e){
    console.warn('[AUTH] getSession failed:', e.message);
  }
  _authReady = true;
  console.log('[AUTH] initAuth complete, _authReady=true');
  // Always ensure auth screen is visible if no user
  if(!_currentUser) showAuthScreen();
}

function savePrefs(){
  try{ localStorage.setItem('swlegion_prefs',JSON.stringify({activeListId:activeListId,catListId:catListId})); }catch(e){}
}
function loadPrefs(){
  try{
    const p=JSON.parse(localStorage.getItem('swlegion_prefs')||'{}');
    if(p.activeListId!==undefined) activeListId=p.activeListId;
    if(p.catListId!==undefined) catListId=p.catListId;
  }catch(e){}
}
function startApp(){
  console.log('[AUTH] startApp, user:', _currentUser?.email||'guest');
  loadState();
  loadPrefs();
  updateListPillLabel();
  updateCatListPillLabel();
  updateCatAddRow();
  updateAccountUI();
  applyPermImgs();
  const aiBtn=document.getElementById('fs-ai-summary-btn');
  if(aiBtn) aiBtn.style.display=(_currentUser?.email==='martinjsleeman@gmail.com')?'':'none';
  setMode('learn');
}

async function loadCloudState(){
  if(!_supa || !_currentUser) return;
  try{
    console.log('[AUTH] loadCloudState for', _currentUser.id);
    const t0 = Date.now();
    const { data, error } = await Promise.race([
      _supa.from('user_state').select('card_states,army_lists').eq('user_id', _currentUser.id).maybeSingle(),
      _timeout(5000, 'loadCloudState')
    ]);
    console.log('[AUTH] loadCloudState completed in', Date.now()-t0, 'ms',
      data ? 'got data' : 'no data', error || '');
    // Always clear stale cache first — even if there's no cloud row yet, a new
    // user must never inherit lists or card states from whoever logged in before them
    localStorage.removeItem('swlegion_lists');
    if(data){
      if(data.card_states && Object.keys(data.card_states).length){
        let merged = data.card_states;
        try{
          const local=JSON.parse(localStorage.getItem('swlegion_v1')||'{}');
          if(Object.keys(local).length){
            merged={...data.card_states};
            Object.keys(local).forEach(k=>{ if(local[k]?.learned && merged[k]) merged[k]={...merged[k],learned:true}; });
          }
        }catch(e){}
        localStorage.setItem('swlegion_v1', JSON.stringify(merged));
      }
      if(data.army_lists && data.army_lists.length)
        localStorage.setItem('swlegion_lists', JSON.stringify(data.army_lists));
    }
  }catch(e){ console.warn('[AUTH] Cloud load failed:', e.message); }
}

async function syncToCloud(){
  if(!_supa || !_currentUser || _isGuest) return;
  try{
    const out={};
    Object.keys(ST).forEach(n=>{ const{idx,learned,flagged,notes,customDef,pinned}=ST[n]; out[n]={idx,learned,flagged,notes:notes||'',customDef:customDef||'',pinned:!!pinned}; });
    console.log('[AUTH] syncToCloud starting...');
    const t0 = Date.now();
    const { error } = await Promise.race([
      _supa.from('user_state').upsert({
        user_id: _currentUser.id,
        card_states: out,
        army_lists: loadLists(),
        updated_at: new Date().toISOString()
      }, { onConflict: 'user_id' }),
      _timeout(5000, 'syncToCloud')
    ]);
    console.log('[AUTH] syncToCloud completed in', Date.now()-t0, 'ms', error || 'OK');
  }catch(e){ console.warn('[AUTH] Cloud sync failed:', e.message); }
}

function scheduleSync(){
  if(!_currentUser || _isGuest) return;
  clearTimeout(_syncTimer);
  _syncTimer = setTimeout(syncToCloud, 2000);
}

// Auth screen visibility
function showAuthScreen(){
  document.getElementById('auth-screen').classList.remove('hidden');
}
function hideAuthScreen(){
  document.getElementById('auth-screen').classList.add('hidden');
}
function showAuthFromApp(){
  closeAcctDropdown();
  showAuthScreen();
}

// Auth mode tabs
let _authMode = 'login';
function setAuthMode(m){
  _authMode = m;
  document.getElementById('auth-tab-login').classList.toggle('active', m==='login');
  document.getElementById('auth-tab-signup').classList.toggle('active', m==='signup');
  document.getElementById('auth-submit').textContent = m==='login'?'Sign In':'Create Account';
  document.getElementById('auth-status').textContent = '';
  document.getElementById('auth-status').className = 'auth-status';
}
function setAuthStatus(msg, cls){
  const el = document.getElementById('auth-status');
  el.textContent = msg;
  el.className = 'auth-status ' + (cls||'');
}

// Sign in / sign up
async function authSubmit(){
  if(!_supa){ console.warn('[AUTH] No client in authSubmit'); guestMode(); return; }
  const email = document.getElementById('auth-email').value.trim();
  const pwd   = document.getElementById('auth-pwd').value;
  if(!email){ setAuthStatus('Enter your email','err'); return; }
  if(!pwd)  { setAuthStatus('Enter your password','err'); return; }
  console.log('[AUTH] authSubmit:', _authMode, email, '_authReady='+_authReady);
  const btn = document.getElementById('auth-submit');
  btn.disabled = true;
  try{
    if(_authMode === 'login'){
      setAuthStatus('Signing in…','work');
      console.log('[AUTH] calling signInWithPassword...');
      const t0 = Date.now();
      const result = await Promise.race([
        _supa.auth.signInWithPassword({ email, password: pwd }),
        _timeout(10000, 'signInWithPassword')
      ]);
      const ms = Date.now()-t0;
      console.log('[AUTH] signInWithPassword completed in', ms, 'ms');
      console.log('[AUTH] result:', JSON.stringify({error:result.error?.message, user:result.data?.user?.email}));
      btn.disabled = false;
      if(result.error){
        const msg = result.error.message.includes('Email not confirmed')
          ? 'Email not confirmed — check your inbox (or disable confirmation in Supabase dashboard)'
          : result.error.message;
        setAuthStatus(msg,'err');
      }
      // success handled by onAuthStateChange
    } else {
      if(pwd.length < 6){ btn.disabled=false; setAuthStatus('Password must be at least 6 characters','err'); return; }
      setAuthStatus('Creating account…','work');
      console.log('[AUTH] calling signUp...');
      const t0 = Date.now();
      const result = await Promise.race([
        _supa.auth.signUp({ email, password: pwd }),
        _timeout(10000, 'signUp')
      ]);
      const ms = Date.now()-t0;
      console.log('[AUTH] signUp completed in', ms, 'ms');
      console.log('[AUTH] result:', JSON.stringify({error:result.error?.message, user:result.data?.user?.email, confirmed:result.data?.user?.confirmed_at}));
      btn.disabled = false;
      if(result.error){
        setAuthStatus(result.error.message,'err');
      } else if(result.data?.user && !result.data.user.confirmed_at){
        setAuthStatus('Account created! Check your email to confirm, then sign in.','ok');
      } else {
        setAuthStatus('Signed up and logged in!','ok');
      }
    }
  }catch(e){
    btn.disabled = false;
    console.error('[AUTH] authSubmit error:', e);
    setAuthStatus(e.message||'Connection error — try again','err');
  }
}

async function authSignOut(){
  closeAcctDropdown();
  // Flush any pending sync first
  clearTimeout(_syncTimer);
  await syncToCloud();
  if(_supa) await _supa.auth.signOut();
  _currentUser = null; _isGuest = false;
  // Clear local cache
  localStorage.removeItem('swlegion_v1');
  localStorage.removeItem('swlegion_lists');
  // Reset in-memory state
  CARDS.forEach(c=>{ ST[c.name]={idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',pinned:false}; });
  // Reset auth form
  document.getElementById('auth-email').value = '';
  document.getElementById('auth-pwd').value = '';
  setAuthStatus('','');
  showAuthScreen();
}

function guestMode(){
  _isGuest = true; _currentUser = null;
  // Guests never see another user's data — wipe any cached state from a previous login
  localStorage.removeItem('swlegion_lists');
  localStorage.removeItem('swlegion_v1');
  hideAuthScreen();
  startApp();
}

// Account button dropdown
function toggleAcctDropdown(){
  const dd = document.getElementById('acct-dropdown');
  if(dd.classList.contains('open')){ closeAcctDropdown(); return; }
  dd.classList.add('open');
  setTimeout(()=>{ document.addEventListener('click', function _c(e){
    if(!document.getElementById('acct-dropdown-wrap').contains(e.target)){
      closeAcctDropdown(); document.removeEventListener('click',_c);
    }
  }); },0);
}
function closeAcctDropdown(){
  document.getElementById('acct-dropdown').classList.remove('open');
}
function updateAccountUI(){
  const btn   = document.getElementById('acct-btn');
  const label = document.getElementById('acct-email-label');
  const siItem = document.getElementById('acct-signin-item');
  const soItem = document.getElementById('acct-signout-item');
  const gLabel = document.getElementById('acct-guest-label');
  if(!btn) return;
  const loggedIn = !!_currentUser;
  const isOwner = (_currentUser?.email === 'martinjsleeman@gmail.com');
  const notesCol = document.getElementById('fs-notes-col');
  const editRulesBtn = document.getElementById('mod-edit');
  const editSumBtn = document.getElementById('mod-edit-summary');
  const regenSumBtn = document.getElementById('mod-regen-summary');
  if(notesCol) notesCol.style.display = '';
  if(editRulesBtn) editRulesBtn.style.display = isOwner ? '' : 'none';
  if(editSumBtn) editSumBtn.style.display = isOwner ? '' : 'none';
  if(regenSumBtn) regenSumBtn.style.display = isOwner ? '' : 'none';
  if(isOwner) loadOwnerFeedback();
  if(loggedIn){
    const email = _currentUser.email || '';
    const short = email.split('@')[0].substring(0,10);
    btn.textContent   = '\u{1F464} ' + short;
    label.textContent = email;
    siItem.style.display = 'none';
    soItem.style.display = 'block';
    gLabel.style.display = 'none';
  } else {
    btn.textContent   = '\u{1F464}';
    label.textContent = 'Guest mode';
    siItem.style.display = 'block';
    soItem.style.display = 'none';
    gLabel.style.display = 'block';
  }
}

// Boot
initAuth();
