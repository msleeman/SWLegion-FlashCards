"""
Patches build_swlegion_v4.py HTML_TEMPLATE with all custom features, then regenerates HTML.
"""
import subprocess, sys, os

SCRIPT = r"C:\Users\marti\AI\SWLegion-FlashCards\build_swlegion_v4.py"

with open(SCRIPT, 'r', encoding='utf-8') as f:
    src = f.read()

errors = []

def patch(old, new, label):
    global src
    if old in src:
        src = src.replace(old, new, 1)
        print(f"  ✓ {label}")
    else:
        errors.append(f"  ✗ NOT FOUND: {label}")
        print(f"  ✗ NOT FOUND: {label}")

# ────────────────────────────────────────────────────────────────
# CSS PATCHES
# ────────────────────────────────────────────────────────────────

# 1. Image – top-anchored, no overlays, full opacity
patch(
    "#fs-img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.45;transition:opacity .4s}\n#fs-img.dim{opacity:.25}\n#fs-scan{position:absolute;inset:0;pointer-events:none;\n  background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.08) 2px,rgba(0,0,0,.08) 4px);z-index:1}\n#fs-top-grad{position:absolute;top:0;left:0;right:0;height:200px;\n  background:linear-gradient(rgba(0,0,0,.85),transparent);pointer-events:none;z-index:2}\n#fs-bot-grad{position:absolute;bottom:0;left:0;right:0;height:60%;\n  background:linear-gradient(transparent,rgba(0,0,0,.95));pointer-events:none;z-index:2}",
    "#fs-img{position:absolute;top:68px;left:50%;transform:translateX(-50%);width:auto;height:calc(100% - 68px);max-width:100%;object-fit:contain;object-position:top center;opacity:1;transition:opacity .4s}\n#fs-scan{display:none}\n#fs-top-grad{display:none}\n#fs-bot-grad{display:none}",
    "CSS: image positioning"
)

# 2. #fs-bottom – scrollable with gradient
patch(
    "#fs-bottom{position:absolute;bottom:0;left:0;right:0;padding:0 20px 24px;z-index:10}",
    "#fs-bottom{position:absolute;bottom:0;left:0;right:0;max-height:calc(100% - 90px);overflow-y:auto;-webkit-overflow-scrolling:touch;padding:60px 16px 16px;z-index:10;background:linear-gradient(transparent,rgba(0,0,0,.92) 30%)}\n#fs-bottom::-webkit-scrollbar{width:4px}\n#fs-bottom::-webkit-scrollbar-track{background:transparent}\n#fs-bottom::-webkit-scrollbar-thumb{background:rgba(245,197,24,.45);border-radius:2px}",
    "CSS: fs-bottom scroll"
)

# 3. back content CSS + notes + rules section
patch(
    "#fs-back-content{display:none}\n#fs-back-name{font-size:22px;font-weight:700;color:var(--gold);margin-bottom:8px}\n#fs-definition{font-size:15px;color:var(--white);line-height:1.7;max-width:660px;text-shadow:0 1px 4px rgba(0,0,0,.6)}\n#fs-source{font-size:11px;color:rgba(255,255,255,.3);margin-top:8px}\n#fs-actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}",
    "#fs-back-content{display:none}\n#fs-back-name{font-size:22px;font-weight:700;color:var(--gold);margin-bottom:6px}\n#fs-notes-col{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}\n.fs-notes-label{font-size:10px;font-weight:700;color:rgba(255,255,255,.35);text-transform:uppercase;letter-spacing:.6px}\n#fs-notes{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:8px;color:var(--white);font-size:13px;padding:8px 10px;font-family:inherit;resize:none;width:100%;min-height:80px;line-height:1.6;outline:none;box-sizing:border-box}\n#fs-notes:focus{border-color:rgba(245,197,24,.6)}\n#fs-rules-section{margin-top:2px}\n#fs-rules-header{display:flex;align-items:center;gap:8px;cursor:pointer;padding:5px 0;user-select:none;border-top:1px solid rgba(255,255,255,.08)}\n#fs-rules-preview{font-size:13px;color:rgba(255,255,255,.45);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\n#fs-rules-caret{color:var(--gold);font-size:11px;flex-shrink:0;transition:transform .2s}\n#fs-definition{display:none;font-size:14px;color:var(--white);line-height:1.7;text-shadow:0 1px 4px rgba(0,0,0,.6);padding-top:6px}\n#fs-source{font-size:11px;color:rgba(255,255,255,.3);margin-top:4px}\n#fs-actions{display:flex;gap:8px;margin-top:7px;flex-wrap:wrap}",
    "CSS: notes + rules section"
)

# 4. Catalog search + cat-add-row + modal edit styles
patch(
    ".cat-count{font-size:13px;color:rgba(255,255,255,.3);margin-bottom:12px}",
    ".cat-count{font-size:13px;color:rgba(255,255,255,.3);margin-bottom:12px}\n#cat-search{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:var(--rs);color:var(--white);font-size:13px;padding:8px 14px;font-family:inherit;outline:none;width:100%;margin-bottom:12px;box-sizing:border-box}\n#cat-search:focus{border-color:rgba(245,197,24,.4)}\n#cat-search::placeholder{color:rgba(255,255,255,.2)}\n#cat-add-row{display:none;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,.07)}\n#cat-add-row .add-label{font-size:11px;color:rgba(255,255,255,.35);white-space:nowrap}\n.dark-pill.extra-on{background:rgba(245,197,24,.2);border-color:var(--gold);color:var(--gold)}\n#mod-def-edit{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:var(--rs);color:var(--white);font-size:13px;padding:10px 12px;font-family:inherit;resize:vertical;width:100%;min-height:120px;line-height:1.6;outline:none;box-sizing:border-box;margin-top:8px;display:none}\n#mod-def-edit:focus{border-color:rgba(245,197,24,.5)}\n.modal-btn.pin-on{background:rgba(245,197,24,.2);border-color:var(--gold);color:var(--gold)}",
    "CSS: catalog search + extras + modal edit"
)

# ────────────────────────────────────────────────────────────────
# HTML PATCHES
# ────────────────────────────────────────────────────────────────

# 5. fs-back-content – add notes + rules
patch(
    "    <div id=\"fs-back-content\">\n      <div id=\"fs-back-name\"></div>\n      <div id=\"fs-definition\"></div>\n      <div id=\"fs-source\">Source: legion.takras.net</div>\n      <div id=\"fs-actions\"></div>\n    </div>",
    "    <div id=\"fs-back-content\">\n      <div id=\"fs-back-name\"></div>\n      <div id=\"fs-notes-col\">\n        <div class=\"fs-notes-label\">Summary / Notes</div>\n        <textarea id=\"fs-notes\" placeholder=\"Add your notes...\"></textarea>\n      </div>\n      <div id=\"fs-rules-section\">\n        <div id=\"fs-rules-header\" onclick=\"toggleRulesSection()\">\n          <span class=\"fs-notes-label\">Rules</span>\n          <span id=\"fs-rules-preview\"></span>\n          <span id=\"fs-rules-caret\">&#9660;</span>\n        </div>\n        <div id=\"fs-definition\"></div>\n      </div>\n      <div id=\"fs-source\"></div>\n      <div id=\"fs-actions\"></div>\n    </div>",
    "HTML: fs-back-content with notes + rules"
)

# 6. Add catalog search box
patch(
    "    <div class=\"cat-count\" id=\"cat-count\"></div>",
    "    <input type=\"text\" id=\"cat-search\" placeholder=\"&#128269; Search keywords...\" oninput=\"renderCatalog()\">\n    <div class=\"cat-count\" id=\"cat-count\"></div>",
    "HTML: catalog search input"
)

# 7. Add cat-add-row after the closing of cat-filters div
# Find the end of cat-filters div followed by cat-count
OLD_AFTER_FILTERS = "    </div>\n    <input type=\"text\" id=\"cat-search\""
NEW_AFTER_FILTERS = "    </div>\n    <div id=\"cat-add-row\">\n      <span class=\"add-label\">Also include:</span>\n      <button class=\"dark-pill\" id=\"cat-add-unit\" onclick=\"toggleCatExtra('unit',this)\">+ Unit</button>\n      <button class=\"dark-pill\" id=\"cat-add-weapon\" onclick=\"toggleCatExtra('weapon',this)\">+ Weapon</button>\n      <button class=\"dark-pill\" id=\"cat-add-concept\" onclick=\"toggleCatExtra('concept',this)\">+ Concept</button>\n      <button class=\"dark-pill\" id=\"cat-add-pinned\" onclick=\"toggleCatExtra('pinned',this)\">&#128204; Pinned</button>\n    </div>\n    <input type=\"text\" id=\"cat-search\""
patch(OLD_AFTER_FILTERS, NEW_AFTER_FILTERS, "HTML: cat-add-row")

# 8. Modal – add pin + edit buttons + textarea
patch(
    "      <div class=\"modal-acts\">\n        <button class=\"modal-btn\" id=\"mod-lrnd\"  onclick=\"modToggleLearned()\"></button>\n        <button class=\"modal-btn\" id=\"mod-photo\" onclick=\"modBadPhoto()\">Bad photo</button>\n        <button class=\"modal-btn cls\"             onclick=\"closeMod()\">Close</button>\n      </div>\n    </div>\n  </div>\n</div>",
    "      <div class=\"modal-acts\">\n        <button class=\"modal-btn\" id=\"mod-lrnd\"  onclick=\"modToggleLearned()\"></button>\n        <button class=\"modal-btn\" id=\"mod-pin\"   onclick=\"modTogglePin()\">&#128204; Pin</button>\n        <button class=\"modal-btn\" id=\"mod-edit\"  onclick=\"modToggleEditDef()\">Edit Rules</button>\n        <button class=\"modal-btn\" id=\"mod-photo\" onclick=\"modBadPhoto()\">Bad photo</button>\n        <button class=\"modal-btn cls\"             onclick=\"closeMod()\">Close</button>\n      </div>\n      <textarea id=\"mod-def-edit\" placeholder=\"Edit the rules text...\"></textarea>\n      <div id=\"mod-def-edit-acts\" style=\"display:none;gap:8px;flex-wrap:wrap;margin-top:6px\">\n        <button class=\"modal-btn\" onclick=\"modSaveDef()\">Save</button>\n        <button class=\"modal-btn\" onclick=\"modResetDef()\">Reset to Original</button>\n      </div>\n    </div>\n  </div>\n</div>",
    "HTML: modal pin + edit buttons"
)

# ────────────────────────────────────────────────────────────────
# JS PATCHES
# ────────────────────────────────────────────────────────────────

# 9. ST init – add notes, customDef, pinned
patch(
    "CARDS.forEach(c => { ST[c.name]={idx:0,learned:false,flagged:false,busy:false}; });",
    "CARDS.forEach(c => { ST[c.name]={idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',pinned:false}; });",
    "JS: ST init with notes/customDef/pinned"
)

# 10. s() helper
patch(
    "function s(n){ return ST[n]||{idx:0,learned:false,flagged:false,busy:false}; }",
    "function s(n){ return ST[n]||{idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',pinned:false}; }",
    "JS: s() helper"
)

# 11. saveState – include notes/customDef/pinned
patch(
    "  Object.keys(ST).forEach(n=>{ const{idx,learned,flagged}=ST[n]; out[n]={idx,learned,flagged}; });\n  localStorage.setItem('swlegion_v1',JSON.stringify(out));\n  scheduleSync();",
    "  Object.keys(ST).forEach(n=>{ const{idx,learned,flagged,notes,customDef,pinned}=ST[n]; out[n]={idx,learned,flagged,notes:notes||'',customDef:customDef||'',pinned:!!pinned}; });\n  localStorage.setItem('swlegion_v1',JSON.stringify(out));\n  scheduleSync();",
    "JS: saveState with notes/customDef/pinned"
)

# 12. syncToCloud – include notes/customDef/pinned
patch(
    "    const out={};\n    Object.keys(ST).forEach(n=>{ const{idx,learned,flagged}=ST[n]; out[n]={idx,learned,flagged}; });",
    "    const out={};\n    Object.keys(ST).forEach(n=>{ const{idx,learned,flagged,notes,customDef,pinned}=ST[n]; out[n]={idx,learned,flagged,notes:notes||'',customDef:customDef||'',pinned:!!pinned}; });",
    "JS: syncToCloud with notes/customDef/pinned"
)

# 13. Variables after typeFilter/activeListId/catListId
patch(
    "let typeFilter='all';\nlet activeListId=null; // flashcard/quiz list filter\nlet catListId=null;    // catalog list filter",
    "let typeFilter='all';\nlet activeListId=null; // flashcard/quiz list filter\nlet catListId=null;    // catalog list filter (null=inherit, ''=explicit none, id=specific)\nconst catExtras=new Set(); // extra types to include when list filter active",
    "JS: catExtras variable"
)

# 14. filteredCards – append pinned
patch(
    """function filteredCards(){
  let cards=CARDS;
  // Apply list filter first
  if(activeListId){
    const lst=getListById(activeListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      cards=cards.filter(c=>kwSet.has(c.name.toLowerCase()));
    }
  }
  if(typeFilter==='weapon')    return cards.filter(c=>c.type==='weapon');
  if(typeFilter==='unit')      return cards.filter(c=>c.type==='unit');
  if(typeFilter==='noconcept') return cards.filter(c=>c.type!=='concept');
  return cards;
}""",
    """function filteredCards(){
  let cards=CARDS;
  if(activeListId){
    const lst=getListById(activeListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      const baseCards=CARDS.filter(c=>kwSet.has(c.name.toLowerCase()));
      const extraCards=CARDS.filter(c=>catExtras.has(c.type));
      const pinnedCards=CARDS.filter(c=>s(c.name).pinned);
      cards=[...new Set([...baseCards,...extraCards,...pinnedCards])];
    }
  }
  const pinnedAll=CARDS.filter(c=>s(c.name).pinned);
  if(typeFilter==='weapon'){const f=cards.filter(c=>c.type==='weapon');return[...new Set([...f,...pinnedAll])];}
  if(typeFilter==='unit'){const f=cards.filter(c=>c.type==='unit');return[...new Set([...f,...pinnedAll])];}
  if(typeFilter==='noconcept'){const f=cards.filter(c=>c.type!=='concept');return[...new Set([...f,...pinnedAll])];}
  return [...new Set([...cards,...pinnedAll])];
}""",
    "JS: filteredCards with pinned"
)

# 15. setListFilter + clearListFilter – savePrefs
patch(
    "function setListFilter(listId){\n  activeListId=listId||null;\n  updateListPillLabel();",
    "function setListFilter(listId){\n  activeListId=listId||null;\n  savePrefs();\n  updateListPillLabel();",
    "JS: setListFilter savePrefs"
)
patch(
    "function clearListFilter(){\n  activeListId=null;\n  updateListPillLabel();",
    "function clearListFilter(){\n  activeListId=null;\n  savePrefs();\n  updateListPillLabel();",
    "JS: clearListFilter savePrefs"
)

# 16. setCatList – three-state + savePrefs + updateCatAddRow + toggleCatExtra
patch(
    """function setCatList(listId){
  catListId=listId||null;
  updateCatListPillLabel();
  renderCatalog();
}""",
    """function setCatList(listId){
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
}""",
    "JS: setCatList + updateCatAddRow + toggleCatExtra"
)

# 17. updateCatListPillLabel – three-state
patch(
    """function updateCatListPillLabel(){
  const pill=document.getElementById('cat-pill-list'); if(!pill) return;
  if(catListId){
    const lst=getListById(catListId);
    pill.innerHTML=(lst?escHtml(lst.name):'List')+' &#9660;';
    pill.classList.add('active');
  } else {
    pill.innerHTML='List: None &#9660;';
    pill.classList.remove('active');
  }
}""",
    """function updateCatListPillLabel(){
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
}""",
    "JS: updateCatListPillLabel three-state"
)

# 18. renderCatalog – catExtras + search + preview
patch(
    """function renderCatalog(){
  let list=[...CARDS];
  // Apply catalog list filter (independent of flashcard list filter)
  if(catListId){
    const lst=getListById(catListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      list=list.filter(c=>kwSet.has(c.name.toLowerCase()));
    }
  }
  if(catFilter==='learned')    list=list.filter(c=>s(c.name).learned);
  if(catFilter==='unlearned')  list=list.filter(c=>!s(c.name).learned);
  if(catFilter==='unit')       list=list.filter(c=>c.type==='unit');
  if(catFilter==='weapon')     list=list.filter(c=>c.type==='weapon');
  if(catFilter==='concept')    list=list.filter(c=>c.type==='concept');
  if(catFilter==='noconcept')  list=list.filter(c=>c.type!=='concept');
  document.getElementById('cat-count').textContent=`${list.length} keyword${list.length!==1?'s':''}`;
  const g=document.getElementById('cat-grid');
  if(!list.length){ g.innerHTML='<p class="empty-msg">Nothing here.</p>'; return; }
  g.innerHTML=list.map(c=>{
    const st=s(c.name), src=ci(c);
    const sn=c.name.replace(/'/g,"\\\\'");
    const th=src
      ?`<img class="cat-thumb" src="${src}" alt="${c.name}" loading="lazy"
             onerror="this.outerHTML='<div class=cat-thumb-ph>${c.name[0]}</div>'">`
      :`<div class="cat-thumb-ph">${c.name[0]}</div>`;
    return `<div class="cat-card${st.learned?' lrnd':''}" onclick="openMod('${sn}')">
      ${th}
      ${st.learned?'<span class="cat-badge badge-learned">Learned</span>':''}
      <div class="cat-lbl">
        <div class="cat-name">${c.name}</div>
        <div class="cat-type">${c.type}</div>
      </div>
    </div>`;
  }).join('');
}""",
    r"""function renderCatalog(){
  let list=[...CARDS];
  const effectiveCatListId=catListId===null?activeListId:catListId;
  if(effectiveCatListId){
    const lst=getListById(effectiveCatListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      const extraCards=CARDS.filter(c=>catExtras.has(c.type));
      const pinnedExtra=CARDS.filter(c=>catExtras.has('pinned')&&s(c.name).pinned);
      list=[...new Set([...CARDS.filter(c=>kwSet.has(c.name.toLowerCase())),...extraCards,...pinnedExtra])];
    }
  }
  if(catFilter==='learned')    list=list.filter(c=>s(c.name).learned);
  if(catFilter==='unlearned')  list=list.filter(c=>!s(c.name).learned);
  if(catFilter==='unit')       list=list.filter(c=>c.type==='unit');
  if(catFilter==='weapon')     list=list.filter(c=>c.type==='weapon');
  if(catFilter==='concept')    list=list.filter(c=>c.type==='concept');
  if(catFilter==='noconcept')  list=list.filter(c=>c.type!=='concept');
  const q=(document.getElementById('cat-search')?.value||'').toLowerCase().trim();
  if(q) list=list.filter(c=>c.name.toLowerCase().includes(q)||(c.definition||'').toLowerCase().includes(q));
  document.getElementById('cat-count').textContent=`${list.length} keyword${list.length!==1?'s':''}`;
  const g=document.getElementById('cat-grid');
  if(!list.length){ g.innerHTML='<p class="empty-msg">Nothing here.</p>'; return; }
  g.innerHTML=list.map(c=>{
    const st=s(c.name), src=ci(c);
    const sn=c.name.replace(/'/g,"\\'");
    const def=st.customDef||c.definition||'';
    const preview=def.length>90?def.slice(0,90).replace(/\s\S*$/,'')+'\u2026':def;
    const th=src
      ?`<img class="cat-thumb" src="${src}" alt="${c.name}" loading="lazy"
             onerror="this.outerHTML='<div class=cat-thumb-ph>${c.name[0]}</div>'">`
      :`<div class="cat-thumb-ph">${c.name[0]}</div>`;
    return `<div class="cat-card${st.learned?' lrnd':''}" onclick="openMod('${sn}')">
      ${th}
      ${st.learned?'<span class="cat-badge badge-learned">Learned</span>':''}${st.pinned?'<span class="cat-badge" style="background:rgba(245,197,24,.9);color:#000;top:6px;left:6px">&#128204;</span>':''}
      <div class="cat-lbl">
        <div class="cat-name">${c.name}</div>
        <div class="cat-type">${c.type}</div>
        <div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:3px;line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${escHtml(preview)}</div>
      </div>
    </div>`;
  }).join('');
}""",
    "JS: renderCatalog with search + extras + preview"
)

# 19. showBack – notes + rules + source + autoSummary + cardSource
patch(
    """function showBack(c){
  document.getElementById('fs-front-content').style.display='none';
  document.getElementById('fs-back-content').style.display='block';
  document.getElementById('fs-back-name').innerHTML=c.name+' '+typeBadgeHTML(c.type);
  document.getElementById('fs-definition').textContent=c.definition;
  document.getElementById('fs-img').classList.add('dim');
}""",
    """let _rulesOpen=false;
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
function cardSource(c){
  return 'Rules PDF v2.6 / legion.takras.net';
}
function showBack(c){
  document.getElementById('fs-front-content').style.display='none';
  document.getElementById('fs-back-content').style.display='block';
  document.getElementById('fs-back-name').innerHTML=c.name+' '+typeBadgeHTML(c.type);
  const st=s(c.name);
  const def=st.customDef||c.definition||'';
  // Notes / Summary
  const notesEl=document.getElementById('fs-notes');
  if(notesEl){
    notesEl.value=st.notes!==undefined&&st.notes!==''?st.notes:autoSummary(def);
    notesEl.oninput=()=>{ st.notes=notesEl.value; saveState(); };
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
}""",
    "JS: showBack with notes + rules + source"
)

# 20. renderMod – pin + customDef + edit actions
patch(
    """function renderMod(){
  const c=mcard, st=s(c.name), src=ci(c);
  document.getElementById('mod-img').innerHTML=src
    ?`<img class="modal-photo" src="${src}" alt="${c.name}"
           onerror="this.outerHTML='<div class=modal-photo-ph>No image</div>'">`
    :`<div class="modal-photo-ph">No image — use Bad Photo to fetch one</div>`;
  document.getElementById('mod-name').textContent=c.name;
  document.getElementById('mod-type').innerHTML=typeBadgeHTML(c.type);
  document.getElementById('mod-def').textContent=c.definition;
  const ml=document.getElementById('mod-lrnd');
  ml.textContent=st.learned?'Learned — reset':'Mark as learned';
  ml.className='modal-btn'+(st.learned?' lrnd':'');
  const mb=document.getElementById('mod-photo');
  mb.textContent=st.busy?'Fetching...':'Bad photo';
  mb.className='modal-btn'+(st.flagged?' flagd':'');
}""",
    r"""function renderMod(){
  const c=mcard, st=s(c.name), src=ci(c);
  document.getElementById('mod-img').innerHTML=src
    ?`<img class="modal-photo" src="${src}" alt="${c.name}"
           onerror="this.outerHTML='<div class=modal-photo-ph>No image</div>'">`
    :`<div class="modal-photo-ph">No image — use Bad Photo to fetch one</div>`;
  document.getElementById('mod-name').textContent=c.name;
  document.getElementById('mod-type').innerHTML=typeBadgeHTML(c.type);
  const defText=st.customDef||c.definition;
  document.getElementById('mod-def').textContent=defText;
  document.getElementById('mod-def').style.borderColor=st.customDef?'rgba(245,197,24,.3)':'';
  const ml=document.getElementById('mod-lrnd');
  ml.textContent=st.learned?'Learned \u2014 reset':'Mark as learned';
  ml.className='modal-btn'+(st.learned?' lrnd':'');
  const mp=document.getElementById('mod-pin');
  if(mp){ mp.innerHTML=st.pinned?'&#128204; Pinned':'&#128204; Pin'; mp.className='modal-btn'+(st.pinned?' pin-on':''); }
  const mb=document.getElementById('mod-photo');
  mb.textContent=st.busy?'Fetching...':'Bad photo';
  mb.className='modal-btn'+(st.flagged?' flagd':'');
  const editTA=document.getElementById('mod-def-edit');
  const editActs=document.getElementById('mod-def-edit-acts');
  if(editTA){ editTA.style.display='none'; document.getElementById('mod-def').style.display='block'; }
  if(editActs) editActs.style.display='none';
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
}
function modResetDef(){
  s(mcard.name).customDef='';
  saveState();
  document.getElementById('mod-def-edit').value=mcard.definition;
  document.getElementById('mod-def').textContent=mcard.definition;
  document.getElementById('mod-def').style.borderColor='';
}""",
    "JS: renderMod with pin + customDef + edit"
)

# 21. startApp – loadPrefs + savePrefs + updateCatAddRow
patch(
    """function startApp(){
  console.log('[AUTH] startApp, user:', _currentUser?.email||'guest');
  loadState();
  updateListPillLabel();
  updateCatListPillLabel();
  updateAccountUI();
  setMode('learn');
}""",
    """function savePrefs(){
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
  setMode('learn');
}""",
    "JS: startApp + savePrefs + loadPrefs"
)

# ────────────────────────────────────────────────────────────────
# WRITE + BUILD
# ────────────────────────────────────────────────────────────────

with open(SCRIPT, 'w', encoding='utf-8') as f:
    f.write(src)

print("\n=== PATCH SUMMARY ===")
if errors:
    print("FAILURES:")
    for e in errors: print(e)
else:
    print("All patches applied successfully!")

print("\nRunning build script to regenerate swlegion_flashcards.html...")
result = subprocess.run(
    [sys.executable, SCRIPT],
    cwd=os.path.dirname(SCRIPT),
    capture_output=True, text=True, timeout=120
)
out = result.stdout
if len(out) > 4000: out = out[-4000:]
print(out)
if result.stderr:
    err = result.stderr
    if len(err) > 2000: err = err[-2000:]
    print("STDERR:", err)
print("Exit code:", result.returncode)
