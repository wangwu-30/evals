import {units, sentences, align, threeWay, defaultRun, files, lines, wordDiff, quoteRange} from './core.mjs';

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = x => x == null ? '–' : Number(x).toFixed(2);
const labels = {model_timeout:'超时',model_empty:'空回答',model_no_answer:'没返回答案',model_truncated:'到长度上限被截断',infra_api:'接口失败',infra_harness:'测试框架失败',infra_not_sent:'请求没到模型'};
const cache = new Map();
let index, state, data = [], selected = [], generation = 0, repeatColumn = 0, repeatLimit = 11;
const media = matchMedia('(max-width:599px)');
const cname = c => index.cond_labels[c] || '条件';
const pathFor = (m,q,c) => state.b && state.b !== index.latest[m] ? index.history[[state.b,m,q,c].join('|')] : index.selections[[m,q,c].join('|')];
const available = r => (r?.has_text || r?.text?.trim()) && !r.fail_type.startsWith('infra_');
const avg = rs => rs.length ? rs.reduce((s,r) => s+r.len_units,0)/rs.length : null;

function readState() {
  const p = new URLSearchParams(location.search);
  const models = index.models;
  const base = index.baseline;
  let cs = (p.get('c') || [base,index.default_cond || index.presets[0]?.conds[0] || Object.keys(index.cond_labels).find(c=>c!==base)].join(',')).split(',').filter(c=>c in index.cond_labels);
  cs = [...new Set(cs)].slice(0,3);
  if (!cs.length) cs = [base];
  state = {m: models.includes(p.get('m')) ? p.get('m') : models[0], q:p.get('q')||'', c:cs,
    r:cs.map((_,i)=>(p.get('r')||'').split(',')[i]||'auto'), bad:p.get('bad')==='1', order:p.get('order')==='orig'?'orig':'diff',
    p:p.get('p')==='1', k:p.get('k')||'', b:p.get('b')||'', view:p.get('v')||'diff', against:Number(p.get('a'))||1};
  state.against = Math.min(Math.max(1,state.against),Math.max(1,cs.length-1));
}
function writeState(replace=false) {
  const p = new URLSearchParams({m:state.m,q:state.q,c:state.c.join(','),r:state.r.join(','),bad:state.bad?'1':'0',order:state.order,p:state.p?'1':'0',k:state.k});
  if(state.b)p.set('b',state.b);
  if(state.view!=='diff')p.set('v',state.view);
  if(state.against!==1)p.set('a',state.against);
  history[replace?'replaceState':'pushState'](null,'','?'+p);
}
function questionOrder() {
  const qs = Object.keys(index.tasks);
  if(state.order==='orig')return qs;
  const diff = q => {
    const base = pathFor(state.m,q,state.c[0])?.summary?.mean_len_units;
    if(base==null)return -1;
    return Math.max(0,...state.c.slice(1).map(c=>{
      const x=pathFor(state.m,q,c)?.summary?.mean_len_units;
      return x==null?0:Math.abs(x-base);
    }));
  };
  return qs.sort((a,b)=>diff(b)-diff(a));
}
function renderControls() {
  const qs = questionOrder(), pos=qs.indexOf(state.q), orig=Object.keys(index.tasks).indexOf(state.q)+1;
  $('controls').innerHTML = `<div class="bar"><label>模型 <select id="model">${index.models.map(m=>`<option value="${esc(m)}" ${m===state.m?'selected':''}>${esc(index.model_labels[m]||m)}</option>`).join('')}</select></label><div class="question"><div><button id="prev" aria-label="上一题" ${pos===0?'disabled':''}>‹</button><span class="step">第 ${pos+1} ${state.order==='diff'?'个':'题'} / 共 ${qs.length} 题</span><button id="next" aria-label="下一题" ${pos===qs.length-1?'disabled':''}>›</button><span class="sort">${state.order==='diff'?'按长度差排序，差得多的在前':'原题序'} <button id="order">${state.order==='diff'?`改回原题序（这是第 ${orig} 题）`:'改按长度差排序'}</button></span></div><select id="question" aria-label="题">${qs.map(q=>`<option value="${esc(q)}" ${q===state.q?'selected':''}>${esc(index.tasks[q].prompt.slice(0,150))}</option>`).join('')}</select><details><summary>题面原文</summary><div class="question-text">${esc(index.tasks[state.q]?.prompt)}</div></details></div><label id="bad-control" hidden><input id="bad" type="checkbox" ${state.bad?'checked':''}>只看答错的</label></div><div class="chips">${state.c.map((c,i)=>`<span class="chip ${i?'':'base'}">${esc(cname(c))}${i?`<button data-remove="${i}" aria-label="移除 ${esc(cname(c))}">✕</button>`:'<span class="tag">对照</span>'}</span>`).join('')}<button id="add" class="chip add" ${state.c.length>=3?'disabled':''}>${state.c.length>=3?'最多 3 个':'＋ 加一个条件'}</button></div>`;
  $('model').onchange = e=>{state.m=e.target.value;state.k='';update();};
  $('question').onchange = e=>{state.q=e.target.value;state.k='';update();};
  $('prev').onclick=()=>{state.q=qs[pos-1];update();};
  $('next').onclick=()=>{state.q=qs[pos+1];update();};
  $('order').onclick=()=>{state.order=state.order==='diff'?'orig':'diff';update();};
  $('bad').onchange=e=>{state.bad=e.target.checked;state.r=state.c.map(()=>'auto');update();};
  $('add').onclick=openConditions;
  const find=document.createElement('button');
  find.textContent='选题';find.onclick=openQuestion;
  $('question').insertAdjacentElement('afterend',find);
  $('controls').querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.remove);state.c.splice(i,1);state.r.splice(i,1);state.against=1;update();});
}
function openQuestion() {
  const dlg=$('conditions'),qs=questionOrder();
  dlg.innerHTML='<div class="dialog-head"><h3>题</h3><button id="close-question">关闭</button></div><input id="question-search" placeholder="查找题面" aria-label="查找题面"><div class="condition-options"></div>';
  const draw=search=>{
    dlg.querySelector('.condition-options').innerHTML=qs.filter(q=>index.tasks[q].prompt.toLowerCase().includes(search.toLowerCase())).map(q=>`<button data-question="${esc(q)}">${esc(index.tasks[q].prompt.slice(0,180))}</button>`).join('');
    dlg.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>{state.q=b.dataset.question;state.k='';dlg.close();update();});
  };
  draw('');$('question-search').oninput=e=>draw(e.target.value);$('close-question').onclick=()=>dlg.close();dlg.showModal();
}
function openConditions() {
  const dlg=$('conditions');
  dlg.innerHTML=`<div class="dialog-head"><h3>加一个条件</h3><button id="close-cond">关闭</button></div>${Object.keys(index.cond_labels).length>9?'<input id="condition-search" placeholder="查找条件" aria-label="查找条件">':''}<div class="condition-options"></div>`;
  const draw = (search='')=>{
    const groups=new Map();
    for(const c of Object.keys(index.cond_labels)){
      if(state.c.includes(c)||!cname(c).includes(search))continue;
      const family=index.conditions[c]?.family||'条件';
      if(!groups.has(family))groups.set(family,[]);
      groups.get(family).push(c);
    }
    dlg.querySelector('.condition-options').innerHTML=[...groups].map(([f,cs])=>`<h3>${esc(f)}</h3>${cs.map(c=>`<button data-cond="${esc(c)}">${esc(cname(c))}</button>`).join('')}`).join('');
    dlg.querySelectorAll('[data-cond]').forEach(b=>b.onclick=()=>{state.c.push(b.dataset.cond);state.r.push('auto');dlg.close();update();});
  };
  draw();$('close-cond').onclick=()=>dlg.close();
  if($('condition-search'))$('condition-search').oninput=e=>draw(e.target.value);
  dlg.showModal();
}
function failure(s) {
  const detail=Object.entries(s.failures).filter(([k])=>k.startsWith('model_')).map(([k,n])=>`${labels[k]} ${n}`).join('、');
  return `失败分类：模型失败 ${s.n_fail_model}（${detail?detail+'，':''}算 0 分）· 基础设施失败 ${s.n_fail_infra}（不算进平均）${s.legacy_failure?'；旧记录没写失败类型，按模型失败算':''}`;
}
function source(r) {
  return r?.text_source?`<span class="source" title="${r.text_source==='2026-10-12-box-pilot'?'这批（box-rescored）是同一批输出重新判分，没有重新调用模型':'原文取自模型、条件、次、耗时完全相同的旧记录'}">原文补自 ${esc(r.text_source)}</span>`:'';
}
function score(r) {
  if(!r)return '';
  if(r.correct!=null)return r.correct===1&&!r.fail_type?'答对':'答错';
  return r.score==null?'':`得分 ${fmt(r.score)}/${r.total}`;
}
function renderConclusion() {
  const means=data.map(d=>state.bad?avg(d.runs.filter(r=>available(r)&&r.correct===0)):d.summary.mean_len_units);
  const text=[];
  for(let i=1;i<state.c.length;i++){
    if(means[i]==null||means[0]==null)continue;
    const delta=means[i]-means[0], percent=means[0]?delta/means[0]*100:null;
    text.push(`${esc(cname(state.c[i]))} 的回答${percent!=null&&Math.abs(percent)<=5?'平均长度差不多':`平均${delta>=0?'长':'短'} ${Math.round(Math.abs(delta))} 字/词${percent==null?'':`（${delta>=0?'+':''}${Math.round(percent)}%）`}`}`);
  }
  const note=data.some(d=>d.summary.n_out<d.summary.n)?'平均只算有输出的次':data.map(d=>d.summary.n).every(n=>n===data[0].summary.n)?`各 ${data[0].summary.n} 次的平均`:'各条件有输出的次的平均';
  const incomplete=data.some(d=>d.summary.incomplete)?'（有一边数据不全）':'';
  $('conclusion').innerHTML=`<div class="verdict">${state.bad?'答错的那几次里，':''}${state.c.length===1?'再选一个条件，就能看差异':text.join('；')||'没有可比较的回答长度'}${incomplete}</div><div class="mut">${note}</div><div id="difference-count" class="mut"></div><div class="legend"><span><i class="sw add"></i>绿底：只在这边有</span>${state.c.length===2?'<span><i class="sw del"></i>红底：只在对照</span>':''}<span>无底色：两边都有一句字面相近的话</span><span>${state.r.every(r=>r==='auto')?'下面各取「长度最接近平均的一次」':'下面是已选的次'}</span></div>`;
}
function visibleText(text) {
  return esc(text).replace(/[\p{Cf}\x00-\x08\x0b-\x1f\x7f-\x9f]/gu,c=>`<span class="invisible">⟨U+${c.codePointAt(0).toString(16).toUpperCase().padStart(4,'0')}⟩</span>`);
}
function renderPrompt() {
  const added=selected.map(r=>r?.added_text||'');
  const descriptions=state.c.slice(1).map((c,i)=>{
    const r=selected[i+1],place=index.conditions[c]?.place;
    const varying=new Set(data[i+1].runs.map(r=>r.added_text)).size>1;
    const inA=data[0].runs.map(r=>r.in_tok).filter(x=>x!=null).sort((a,b)=>a-b);
    const mid=inA.length? (inA[Math.floor((inA.length-1)/2)]+inA[Math.floor(inA.length/2)])/2 : null;
    const tok=r?.in_tok!=null&&mid!=null?`（约 ${r.in_tok-mid} token）`:'';
    return added[i+1]?`${esc(cname(c))} ${varying?'每次加的话不同，见下面这次':`在题目${place==='suffix'?'后':'前'}面多了一句：${added[i+1].length<=40?'「'+visibleText(added[i+1])+'」':'见展开原文'}`}${tok}`:'这批没有保存可核对的 prompt 原文';
  });
  const blocks=state.p?state.c.slice(1).map((c,i)=>{
    if(!selected[0]?.prompt_text||!selected[i+1]?.prompt_text)return '<p class="mut">这批没有保存可核对的 prompt 原文</p>';
    return `<h3>${esc(cname(state.c[0]))} / ${esc(cname(c))}</h3>`+wordDiff(selected[0].prompt_text,selected[i+1].prompt_text).map(g=>g.kind==='same'?`<details class="pblock same"><summary>相同的 ${units(g.text)} 字/词，已折叠 ▸</summary>${visibleText(g.text)}</details>`:`<div class="pblock ${g.kind}"><span class="lab">只在 ${esc(cname(g.kind==='del'?state.c[0]:c))}</span>${visibleText(g.text)}</div>`).join('');
  }).join(''):'';
  $('prompt').innerHTML=`<b>prompt 差在哪</b><span class="mut">（发给模型的话，不是回答）</span>：${descriptions.join('；')} <button id="toggle-prompt">${state.p?'收起 ▴':'展开看 ▾'}</button>${blocks}`;
  $('toggle-prompt').onclick=()=>{state.p=!state.p;writeState();renderPrompt();};
}
function dotPlot(d,r,i) {
  const valid=d.runs.filter(available),max=Math.max(1,...valid.map(x=>x.len_units))*1.08;
  const language=valid.filter(x=>x.lang==='zh').length>=valid.length/2?'zh':'en';
  const dots=valid.map(x=>`<button class="dot ${x.rep===r?.rep?'on':''} ${x.lang!==language?'language':''} ${x.fail_type?'model':''}" style="left:${x.len_units/max*100}%" data-repeat="${i}" data-rep="${x.rep}" title="第 ${x.rep+1} 次 · ${x.len_units} 字/词" aria-label="选择第 ${x.rep+1} 次"></button>`).join('');
  const absent=d.runs.filter(x=>!available(x));
  return `<div class="strip"><div class="gutter"><small>没输出</small>${absent.map(x=>`<span class="${x.fail_type.startsWith('infra_')?'infra':''}" title="${esc(labels[x.fail_type]||'没有保存回答原文')}">${x.fail_type.startsWith('infra_')?'◌':x.fail_type?'✕':'–'}</span>`).join('')}</div>${dots}<b class="mean" style="left:${(d.summary.mean_len_units||0)/max*100}%" title="平均"></b></div><div class="legend">点＝每一次，竖线＝平均${absent.length?'，✕＝没输出的那次':''}</div>`;
}
function renderHeaders() {
  $('headers').style.setProperty('--n',state.c.length);
  $('headers').innerHTML=data.map((d,i)=>{
    const s=d.summary,r=selected[i],hasCorrect=d.runs.some(x=>x.correct!=null),badCount=d.runs.filter(x=>x.correct===0).length;
    const count=s.n_out<s.n?`有输出的 ${s.n_out}`:s.n;
    let empty='';
    if(!s.n)empty='这个条件在这道题上没有记录';
    else if(s.n_fail_infra===s.n)empty=`这个条件 ${s.n} 次都没跑到模型`;
    else if(state.bad&&hasCorrect&&!badCount)empty=`这个条件 ${s.n} 次都答对了`;
    else if(!r)empty=d.runs.every(x=>x.text_missing)?'这批记录没有保存回答原文':'这次没有回答原文（模型失败，算 0 分）';
    const single=r?`${state.bad&&badCount?`下面是答错的 ${badCount} 次里的第 ${d.runs.filter(x=>x.correct===0).findIndex(x=>x.rep===r.rep)+1} 次`:`下面是第 ${r.rep+1} 次${state.r[i]==='auto'?'（最接近平均）':''}`} · ${r.len_units} 字/词 · ${score(r)}`:'';
    return `<div class="colh"><div class="nm">${esc(cname(state.c[i]))} ${i?'':'<span class="tag">对照</span>'} ${s.incomplete?'<span class="inc">数据不全</span>':''}</div><div class="meta">${count} 次平均 ${s.mean_len_units==null?'–':Math.round(s.mean_len_units)} 字/词 · ${hasCorrect?`答对 ${s.n_correct}/${s.n_scored}`:`${s.n_scored} 次平均得分 ${fmt(s.mean_score)}`}${s.mean_out_tok==null?'':` · 平均输出 ${Math.round(s.mean_out_tok)} token`}</div><div class="meta desktop-meta mut">去掉最高最低 ${fmt(s.trimmed_score)}（参考）</div><div class="failure">${failure(s)}</div>${empty?`<div class="mut">${empty}</div>`:''}<div class="meta">${single} <button data-swap="${i}">换一次 ▾</button></div>${source(r)}${r?.fail_type?`<div class="failure">${labels[r.fail_type]}</div>`:''}${r?.added_text?`<details class="desktop-meta"><summary>本次加的话</summary>${visibleText(r.added_text)}</details>`:''}${dotPlot(d,r,i)}</div>`;
  }).join('');
  $('headers').querySelectorAll('[data-swap]').forEach(b=>b.onclick=()=>openRepeats(Number(b.dataset.swap)));
  $('headers').querySelectorAll('[data-repeat]').forEach(b=>b.onclick=()=>chooseRep(Number(b.dataset.repeat),b.dataset.rep));
}
function chooseRep(i,rep) {
  state.r[i]=String(rep);$('repeats').close();update();
}
function openRepeats(i) {
  repeatColumn=i;repeatLimit=11;renderRepeats();$('repeats').showModal();
  requestAnimationFrame(()=>$('repeats').querySelector('.repeat.on')?.scrollIntoView({block:'center'}));
}
function renderRepeats() {
  const i=repeatColumn,d=data[i],s=d.summary,def=defaultRun(d.runs,state.bad),r=selected[i];
  const rs=[...d.runs].sort((a,b)=>Number(!available(a))-Number(!available(b))||a.len_units-b.len_units||a.rep-b.rep);
  const at=Math.max(0,rs.findIndex(x=>x.rep===r?.rep)),start=Math.max(0,Math.min(at-Math.floor(repeatLimit/2),rs.length-repeatLimit));
  const shown=rs.slice(start,start+repeatLimit),max=Math.max(1,...rs.map(x=>x.len_units));
  const language=rs.filter(x=>available(x)&&x.lang==='zh').length>=s.n_out/2?'zh':'en';
  $('repeats').innerHTML=`<div class="dialog-head"><h3>${esc(cname(state.c[i]))} · ${s.n} 次回答</h3><button id="close-repeats">关闭</button></div><div class="repeat-list">${shown.map(x=>`<button class="repeat ${x.rep===r?.rep?'on':''}" data-rep="${x.rep}" ${!available(x)||(state.bad&&x.correct!==0)?'disabled':''}><span class="lenbar" style="width:${available(x)?Math.max(2,x.len_units/max*64):0}px"></span>第 ${x.rep+1} 次 · ${available(x)?`${x.len_units} 字/词 · ${score(x)}`:x.fail_type.startsWith('infra_')?'◌ 基础设施失败：不算进平均，不能选':x.text_missing?'没有保存回答原文，不能选':'✕ '+(labels[x.fail_type]||'空回答')+'：模型失败，算 0 分，没有原文可看'}${x.out_tok==null?'':` · 输出 ${x.out_tok} token`}<small>${x.rep===def?.rep?'最接近平均，默认看这次':''}${available(x)&&x.lang!==language?' · '+(x.lang==='en'?'英文':'中文')+'回答：这次没按其他几次的语言答':''}${x.fail_type==='model_truncated'?' · 被截断：模型失败，算 0 分':''}${x.legacy_failure?' · 旧记录没写失败类型，按模型失败算':''}</small>${source(x)}${x.added_text?`<small>本次加的话：${visibleText(x.added_text)}</small>`:''}</button>`).join('')}</div>${shown.length<rs.length?'<button id="more-repeats">再显示 10 条</button>':''}<p class="mut">有输出的 ${s.n_out} 次平均 ${Math.round(s.mean_len_units||0)} 字/词；${s.n_scored} 次平均得分 ${fmt(s.mean_score)}（模型失败的那次算 0 分）</p><p class="failure">${failure(s)}</p>`;
  $('close-repeats').onclick=()=>$('repeats').close();
  $('repeats').querySelectorAll('[data-rep]').forEach(b=>b.onclick=()=>chooseRep(i,b.dataset.rep));
  if($('more-repeats'))$('more-repeats').onclick=()=>{repeatLimit+=10;renderRepeats();};
}
function highlightInfo() {
  const k=state.k;
  if(!k)return null;
  const chosen=selected.findIndex(r=>r?.checks?.[k]===true);
  const i=chosen<0?0:chosen;
  const why=selected[i]?.why?.[k]||['',''];
  const quote=Array.isArray(why[1])?why[1].join(''):String(why[1]||'');
  const found=quote&&selected[i]?.text.includes(quote);
  const description=selected.map((r,j)=>`${cname(state.c[j])} ${r?.checks?.[k]?'过':'没过'}：「${r?.why?.[k]?.[0]||'这批没有保存评分理由'}」`).join('。');
  return {i,quote:found?quote:'',text:`已在原文里用黄色标出：${index.check_labels[k]||'检查'} —— ${description}${found?`，引用的是「${quote}」`:'；引语在原文里没找到原样的句子'}`};
}
function highlighted(text,i,h) {
  const range=h?.i===i?quoteRange(selected[i]?.text||'',h.quote,text):null;
  if(!range)return visibleText(text);
  return visibleText(text.slice(0,range[0]))+`<mark>${visibleText(text.slice(...range))}</mark>`+visibleText(text.slice(range[1]));
}
function cell(text,i,kind,h) {
  if(text==null)return '<div class="cell empty"></div>';
  const marked=h?.i===i&&quoteRange(selected[i]?.text||'',h.quote,text);
  return `<div class="cell ${kind} ${text.includes('```')?'code':''}">${kind==='add'||kind==='del'?`<span class="lab">只在 ${esc(cname(state.c[i]))}</span>`:''}${highlighted(text,i,h)}${marked?`<div class="callout mobile-note">${esc(h.text)} <button data-clear>取消标出</button></div>`:''}</div>`;
}
function renderRows(texts,byLine=false) {
  const h=highlightInfo(),split=byLine?lines:sentences;
  const pieces=texts.map(split);
  let rows=pieces.length===1?pieces[0].map(x=>[x]):pieces.length===2?align(...pieces):threeWay(pieces[0],pieces.slice(1));
  const renderRow=row=>{
    if(media.matches){
      if(state.view!=='diff')return '';
      const j=state.against;
      const a=row[0],b=row[j];
      if(a!=null&&b!=null){
        // Keep the scored quotation visible even if it belongs to the paired right sentence.
        return `<div class="row">${h?.i===j&&quoteRange(selected[j]?.text||'',h.quote,b)?cell(b,j,'',h):cell(a,0,'',h)}</div>`;
      }
      return `<div class="row">${a==null?'':cell(a,0,state.c.length===2?'del':'',h)}${b==null?'':cell(b,j,'add',h)}</div>`;
    }
    return `<div class="row" style="--n:${texts.length}">${row.map((s,i)=>cell(s,i,s==null?'empty':i===0?(texts.length===2&&row[1]==null?'del':''):row[0]==null?'add':'',h)).join('')}</div>`;
  };
  let html='',i=0;
  while(i<rows.length){
    let j=i;
    while(j<rows.length&&rows[j].every(s=>s!=null))j++;
    if(j-i>=4){
      const marked=h?.quote&&rows.slice(i,j).some(row=>row[h.i]!=null&&quoteRange(selected[h.i]?.text||'',h.quote,row[h.i]));
      html+=`<details class="shared" ${marked?'open':''}><summary>⋯ 两边都有的 ${j-i} ${byLine?'行':'句'}，已折叠 ▸</summary>${rows.slice(i,j).map(renderRow).join('')}</details>`;i=j;
    }else{html+=renderRow(rows[i]);i++;}
  }
  return `<div class="rows">${html}</div>`;
}
function renderAnswers() {
  const texts=selected.map(r=>r?.text||''),h=highlightInfo();
  $('highlight').innerHTML=h?`<div class="callout desktop-note">${esc(h.text)} <button data-clear>取消标出</button></div>`:'';
  if(media.matches&&state.view!=='diff'){
    const i=Math.min(Number(state.view)||0,selected.length-1),text=texts[i];
    const content=`<div class="fulltext">${highlighted(text,i,h)}</div>`;
    $('answers').innerHTML=`<div class="card">${lines(text).length>12?`<div class="clip">${highlighted(lines(text).slice(0,12).join(''),i,h)}</div><details><summary>展开全文</summary>${content}</details>`:content}</div>`;
  }else{
    const groups=texts.map(files);
    if(groups.some(Boolean)){
      const names=[...new Set(groups.flatMap(g=>Object.keys(g||{})))];
      $('answers').innerHTML=names.map(name=>`<details class="file" open><summary>${esc(name)}</summary>${renderRows(groups.map((g,i)=>g?.[name]||(name==='回答开头'&&!g?texts[i]:'')),true)}</details>`).join('');
      $('difference-count').textContent=names.map(name=>state.c.slice(1).map((c,i)=>`${name}：${cname(c)} ${lines(groups[i+1]?.[name]||'').length-lines(groups[0]?.[name]||'').length>=0?'长':'短'} ${Math.abs(lines(groups[i+1]?.[name]||'').length-lines(groups[0]?.[name]||'').length)} 行`).join('；')).join('；');
    }else{
      $('answers').innerHTML=renderRows(texts);
      $('difference-count').textContent=state.c.slice(1).map((c,i)=>{
        const rows=align(sentences(texts[0]),sentences(texts[i+1]));
        const add=rows.filter(r=>r[0]===null),del=rows.filter(r=>r[1]===null);
        return `下面这两次：${cname(c)} 多出 ${add.length} 句（${units(add.map(r=>r[1]).join(''))} 字/词），少了 ${del.length} 句（${units(del.map(r=>r[0]).join(''))} 字/词）`;
      }).join('；');
    }
  }
  $('answers').innerHTML+=selected.map((r,i)=>r?.thinking?`<details class="card"><summary>${esc(cname(state.c[i]))} · 思考过程</summary><div class="fulltext">${visibleText(r.thinking)}</div></details>`:'').join('');
  document.querySelectorAll('[data-clear]').forEach(b=>b.onclick=()=>{state.k='';writeState();renderAnswers();});
}
function renderPhone() {
  const originals=state.c.length===3?`<button data-view="${state.view==='diff'?'0':state.view}" class="${state.view!=='diff'?'on':''}">只看原文</button>`:state.c.map((c,i)=>`<button data-view="${i}" class="${state.view===String(i)?'on':''}">只看 ${esc(cname(c))}</button>`).join('');
  const extra=state.c.length===3?(state.view==='diff'?`<div>跟对照比：${state.c.slice(1).map((c,i)=>`<button data-against="${i+1}" ${state.against===i+1?'class="on"':''}>${esc(cname(c))}</button>`).join('')}</div>`:`<div>只看：${state.c.map((c,i)=>`<button data-view="${i}" class="${state.view===String(i)?'on':''}">${esc(cname(c))}</button>`).join('')}</div>`):'';
  $('phone').innerHTML=`<div class="segments"><button data-view="diff" class="${state.view==='diff'?'on':''}">看差异</button>${originals}</div>${extra}`;
  $('phone').querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{state.view=b.dataset.view;writeState();renderPhone();renderAnswers();});
  $('phone').querySelectorAll('[data-against]').forEach(b=>b.onclick=()=>{state.against=Number(b.dataset.against);writeState();renderPhone();renderAnswers();});
}
function renderChecks() {
  if(selected.some(r=>r?.correct!=null)){
    const values=selected.filter(Boolean).map(r=>r.correct);
    const note=n=>n?.startsWith('wrong:')?'答案写的是 '+n.slice(6):n?.startsWith('fields:')?n.slice(7)+' 字段不对':n?.startsWith('test_fail:')?'程序检查没过':n==='ok'||n==='pass'?'':n==='open'?'':n||'';
    $('checks').innerHTML=`<b>答对了吗：</b>${values.every(x=>x===1)?'这几次都答对了':values.every(x=>x===0)?'这几次都答错了':selected.map((r,i)=>`${esc(cname(state.c[i]))} ${r?.correct==null?'没有对错':r.correct&&!r.fail_type?'✓':'✗'} ${esc(note(r?.note))}`).join(' ｜ ')}`;
    return;
  }
  const keys=[...new Set(selected.flatMap(r=>Object.keys(r?.checks||{})))];
  const diff=keys.filter(k=>new Set(selected.map(r=>r?.checks?.[k])).size>1),same=keys.filter(k=>!diff.includes(k));
  const row=k=>{
    const passed=selected.find(r=>r?.checks?.[k])||selected[0];
    return `<div class="check-row"><b>${esc(index.check_labels[k]||'检查')}</b><div>${selected.map((r,i)=>`${esc(cname(state.c[i]))} <span class="${r?.checks?.[k]?'ok':'no'}">${r?.checks?.[k]?'✓ 过':'✗ 没过'}</span>`).join('<br>')}</div><div>${esc(passed?.why?.[k]?.[0]||'这批没有保存评分理由')}</div><button data-check="${esc(k)}">在原文里标出</button></div>`;
  };
  $('checks').innerHTML=`<b>${diff.length?`判得不一样的检查（${diff.length} 项）`:`两边每项检查结果都相同（共 ${keys.length} 项，这两次之间）`}</b>${diff.map(row).join('')}${same.length?`<details><summary>另外 ${same.length} 项结果都相同，已收起 ▸</summary>${same.map(row).join('')}</details>`:''}`;
  $('checks').querySelectorAll('[data-check]').forEach(b=>b.onclick=()=>{state.k=b.dataset.check;writeState();renderAnswers();if(media.matches)$('answers').querySelector('mark')?.scrollIntoView({block:'center',behavior:'smooth'});else $('highlight').scrollIntoView({block:'center',behavior:'smooth'});});
}
async function loadJson(path) {
  if(!cache.has(path))cache.set(path,fetch(path).then(r=>{if(!r.ok)throw Error('这组回答加载失败，请重试');return r.json();}).catch(e=>{cache.delete(path);throw e;}));
  return cache.get(path);
}
async function update(replace=false) {
  const ticket=++generation;
  if(!(state.q in index.tasks))state.q=questionOrder()[0];
  state.against=Math.min(state.against,Math.max(1,state.c.length-1));
  writeState(replace);renderControls();
  $('headers').innerHTML=state.c.map(c=>`<div class="colh">${esc(cname(c))}<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>`).join('');
  try{
    const loaded=await Promise.all(state.c.map(c=>{
      const entry=pathFor(state.m,state.q,c);
      return entry?loadJson(entry.path):Promise.resolve({summary:{n:0,n_out:0,n_fail_model:0,n_fail_infra:0,n_scored:0,failures:{}},runs:[]});
    }));
    if(ticket!==generation)return;
    data=loaded;
    const choices=data.map((d,i)=>{
      const pinned=d.runs.find(r=>String(r.rep)===state.r[i]&&available(r)&&(!state.bad||r.correct===0));
      return pinned||defaultRun(d.runs,state.bad);
    });
    selected=await Promise.all(choices.map(r=>r?.text_url?loadJson(r.text_url):r));
    if(ticket!==generation)return;
    $('bad-control').hidden=!data.some(d=>d.runs.some(r=>r.correct!=null));
    renderConclusion();renderPrompt();renderHeaders();renderPhone();renderAnswers();renderChecks();
    document.body.dataset.ready='true';
  }catch(e){if(ticket===generation){$('answers').textContent=e.message;$('conclusion').textContent='这组回答加载失败，请刷新重试';}}
}
let touchStart=null;
$('answers').addEventListener('touchstart',e=>{touchStart=[e.changedTouches[0].clientX,e.changedTouches[0].clientY];},{passive:true});
$('answers').addEventListener('touchend',e=>{
  if(!touchStart||state.view==='diff')return;
  const dx=e.changedTouches[0].clientX-touchStart[0],dy=e.changedTouches[0].clientY-touchStart[1];
  if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.5){state.view=String(Math.max(0,Math.min(state.c.length-1,Number(state.view)+(dx<0?1:-1))));writeState();renderPhone();renderAnswers();}
  touchStart=null;
},{passive:true});
media.addEventListener('change',()=>{if(index)renderAnswers();});
window.addEventListener('popstate',()=>{readState();update(true);});
try{index=await loadJson(document.body.dataset.eval+'.index.json');readState();await update(true);}
catch(e){$('conclusion').textContent='页面资料加载失败，请刷新重试';}
