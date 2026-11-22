const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const saved=JSON.parse(localStorage.getItem('daybook')||'{}');
const state={priorities:saved.priorities||[
'Open one doc and write down the titles of the last 3 papers you read, in the 9:45 AM focus block (15 min)',
'Spend 15 minutes in the Daybook To-do after the walk: mark anything stale done or delete it',
'Open the college application and list the parts still missing, in the 9:45 AM focus block (15 min)'],
checks:saved.checks||[],energy:saved.energy||0,note:saved.note||'',todos:saved.todos||[{text:'Cleaning the shoes, clothes, towel, table and seeing if I can get the old table back by measuring, cutting nail, having breakfast and then going to college',done:false,meta:'Personal · Nov 21'}],journal:saved.journal||'',back:saved.back||'',dayShape:saved.dayShape||'Long shift 11–9',tomorrowShape:saved.tomorrowShape||'Long shift 11–9',weekShapes:saved.weekShapes||['Free day, night shift','Off shift, back on tonight','Recovery day','Morning free, shift 2:30–9','Morning free, shift 2:30–9','Long shift 11–9','Long shift 11–9']};
let selectedDayOffset=0,databaseAvailable=false,localChanged=false,saveTimer;
const dateForOffset=offset=>{const date=new Date();date.setHours(12,0,0,0);date.setDate(date.getDate()+offset);return date};
const dateKey=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
function ensureDailyRecords(){
  state.daily=state.daily||{};
  const todayKey=dateKey(dateForOffset(0)),tomorrowKey=dateKey(dateForOffset(1));
  if(!state.daily[todayKey])state.daily[todayKey]={priorities:[...state.priorities],checks:[...state.checks],energy:state.energy,note:state.note,dayShape:state.dayShape};
  if(!state.daily[tomorrowKey])state.daily[tomorrowKey]={priorities:['','',''],checks:[],energy:0,note:'',dayShape:state.tomorrowShape};
}
function dailyRecord(offset=selectedDayOffset){
  const key=dateKey(dateForOffset(offset));
  if(!state.daily[key])state.daily[key]={priorities:['','',''],checks:[],energy:0,note:'',dayShape:state.dayShape};
  return state.daily[key];
}
ensureDailyRecords();
function persist(){
  localChanged=true;
  const serialized=JSON.stringify(state);
  localStorage.setItem('daybook',serialized);
  if(!databaseAvailable)return;
  clearTimeout(saveTimer);
  $('#storageStatus').textContent='Saving to SQLite…';
  saveTimer=setTimeout(async()=>{
    try{
      const response=await fetch('/api/state',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({state})});
      const result=await response.json();
      if(!response.ok)throw new Error(result.error||`HTTP ${response.status}`);
      $('#storageStatus').textContent='Saved locally to SQLite';
    }catch(error){
      databaseAvailable=false;
      $('#storageStatus').textContent=`SQLite save failed; kept in this browser only (${error.message})`;
      $('#storageStatus').classList.add('storage-error');
    }
  },250);
}
async function initializeStorage(){
  try{
    const response=await fetch('/api/state');
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const result=await response.json();
    databaseAvailable=true;
    if(result.initialized&&!localChanged){
      Object.assign(state,result.state);
      ensureDailyRecords();
      renderDailyInputs();renderTodos();
      $('#journalInput').value=state.journal;
      $('#backInput').value=state.back;
      $$('#routineGrid select').forEach((select,index)=>select.value=state.weekShapes[index]);
    }else{
      const write=await fetch('/api/state',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({state})});
      const savedState=await write.json();
      if(!write.ok)throw new Error(savedState.error||`HTTP ${write.status}`);
    }
    $('#storageStatus').textContent='Saved locally to SQLite';
    $('#storageStatus').classList.remove('storage-error');
  }catch(error){
    databaseAvailable=false;
    $('#storageStatus').textContent=`SQLite unavailable; edits are only in this browser (${error.message})`;
    $('#storageStatus').classList.add('storage-error');
  }
}
function clock(){const d=new Date();$('#clock').textContent=d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});renderSelectedDay()}
clock();setInterval(clock,30000);
function renderSelectedDay(){
  const date=dateForOffset(selectedDayOffset);
  const labels=[['yesterdaySwitch',-1],['todaySwitch',0],['tomorrowSwitch',1]];
  $('#weekday').textContent=date.toLocaleDateString([],{weekday:'long'});
  $('#dateTitle').textContent=date.toLocaleDateString([],{month:'long',day:'numeric'});
  $('#selectedDayTitle').textContent=selectedDayOffset===0?'Today':selectedDayOffset<0?'Yesterday':'Tomorrow';
  for(const [id,offset] of labels){
    const button=$(`#${id}`);
    button.textContent=offset===0?'Today':`${offset<0?'Yesterday':'Tomorrow'} · ${dateForOffset(offset).toLocaleDateString([],{weekday:'short'})}`;
    button.classList.toggle('active',offset===selectedDayOffset);
    button.setAttribute('aria-selected',String(offset===selectedDayOffset));
  }
  const daily=dailyRecord();
  $('#nowText').innerHTML=selectedDayOffset===0?'Now <strong>Short focus block</strong> until 10:30 AM':`${selectedDayOffset<0?'Yesterday’s schedule':'Tomorrow’s plan'} <strong>${escapeHtml(daily.dayShape||'No shift selected')}</strong>`;
  $('#thenText').textContent=selectedDayOffset===0?'Then Head to work at 10:30 AM':`Schedule · ${daily.dayShape||'No shift selected'}`;
  $('#timelineTrack').classList.toggle('not-today',selectedDayOffset!==0);
}
function renderDailyInputs(){
  renderSelectedDay();
  renderPriorities();renderChecks();renderEnergy();
  $('#dayNote').value=dailyRecord().note||'';
  $('#dayShape').value=dailyRecord().dayShape||'';
  $('#tomorrowShape').value=dailyRecord(1).dayShape||'';
}
function selectDay(offset){
  if(offset < -1 || offset > 1 || offset===selectedDayOffset)return;
  selectedDayOffset=offset;
  renderDailyInputs();
}
$('#timelineTrack').innerHTML=['<div class="time-block focus"></div>','<div class="time-block work"></div>','<div class="time-block sleep"></div>'].join('');
const schedule=[['8:30 AM','Wake · water, no phone'],['8:45 AM','Sadhana'],['9:15 AM','Breakfast'],['9:45 AM','Short focus block'],['10:30 AM','Head to work'],['11:00 AM','Work'],['9:00 PM','Off · dinner'],['9:45 PM','Call home · check in'],['10:30 PM','Free time'],['11:45 PM','Wind down, screens off'],['12:15 AM','Sleep']];
function renderSchedule(){ $('#scheduleList').innerHTML=schedule.map(([t,x])=>`<div class="schedule-row"><time>${t}</time><span>${x}</span></div>`).join('') }
renderSchedule();
function renderPriorities(){const tags=['Research','Work','Grad apps'];$('#priorities').innerHTML=dailyRecord().priorities.map((p,i)=>`<div class="priority"><button class="priority-number">${i+1}</button><div><input value="${p.replace(/"/g,'&quot;')}" aria-label="Priority ${i+1}"><small>${tags[i]||'Personal'}</small></div><button class="done-button" aria-label="Mark priority ${i+1} done">○</button></div>`).join('');$$('.priority input').forEach((input,i)=>input.oninput=e=>{dailyRecord().priorities[i]=e.target.value;persist()});}
renderPriorities();
const checkLabels=['Slept 7h+','Sadhana','Moved','Deep work','Family','Friends','Fun','Real rest'];
function renderChecks(){const grid=$('#checkGrid'),daily=dailyRecord();grid.innerHTML=checkLabels.map((x,i)=>`<button class="${daily.checks.includes(i)?'active':''}" data-i="${i}">${x}</button>`).join('');grid.onclick=e=>{if(e.target.dataset.i){const i=+e.target.dataset.i,daily=dailyRecord();daily.checks=daily.checks.includes(i)?daily.checks.filter(x=>x!==i):[...daily.checks,i];persist();renderChecks();$('#checkCount').textContent=`${daily.checks.length} of 8`}};$('#checkCount').textContent=`${daily.checks.length} of 8`;}
renderChecks();
const energy=$('#energyButtons');energy.onclick=e=>{if(e.target.dataset.n){dailyRecord().energy=+e.target.dataset.n;persist();renderEnergy()}};function renderEnergy(){energy.innerHTML=[1,2,3,4,5].map(n=>`<button class="${dailyRecord().energy===n?'active':''}" data-n="${n}">${n}</button>`).join('')};renderEnergy();$('#dayNote').value=dailyRecord().note||'';$('#dayNote').oninput=e=>{dailyRecord().note=e.target.value;persist()};
function renderTodos(){const count=state.todos.filter(t=>!t.done).length;$('#todoCount').textContent=count||'';$('#todoList').innerHTML=state.todos.map((t,i)=>`<div class="todo-item"><input type="checkbox" ${t.done?'checked':''} data-done="${i}"><input value="${t.text.replace(/"/g,'&quot;')}" data-text="${i}"><button data-del="${i}">Delete</button></div>`).join('');renderComing()}function renderComing(){const t=state.todos.find(t=>!t.done);$('#comingTask').innerHTML=t?`<div class="coming-task"><button data-coming="1"></button><div><div>${t.text}</div><div class="task-meta"><span class="tag">Personal</span><span class="tag">Nov 21</span></div></div></div>`:''}renderTodos();$('#todoList').onclick=e=>{const i=e.target.dataset.done;if(i!==undefined){state.todos[+i].done=e.target.checked;persist();renderTodos()}if(e.target.dataset.del!==undefined){state.todos.splice(+e.target.dataset.del,1);persist();renderTodos()}if(e.target.dataset.text!==undefined){}};$('#todoList').oninput=e=>{if(e.target.dataset.text!==undefined){state.todos[+e.target.dataset.text].text=e.target.value;persist();renderComing()}};$('#addTodo').onclick=()=>{state.todos.push({text:'New task',done:false,meta:'Personal'});persist();renderTodos()};
$('#comingTask').onclick=e=>{if(e.target.dataset.coming){const t=state.todos.find(t=>!t.done);if(t){t.done=true;persist();renderTodos()}}};$('#allTodos').onclick=()=>activateTab('todo');
function activateTab(name){$$('.section-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));$$('.tab-panel').forEach(p=>p.classList.toggle('active',p.id===name))}$$('.section-tabs button').forEach(b=>b.onclick=()=>activateTab(b.dataset.tab));
let swipeStart=null,ignoreDayClickUntil=0;
$('#yesterdaySwitch').onclick=()=>{if(Date.now()>=ignoreDayClickUntil)selectDay(-1)};
$('#todaySwitch').onclick=()=>{if(Date.now()>=ignoreDayClickUntil)selectDay(0)};
$('#tomorrowSwitch').onclick=()=>{if(Date.now()>=ignoreDayClickUntil)selectDay(1)};
const timelineSection=$('.timeline-section');
timelineSection.addEventListener('pointerdown',event=>{if(event.target.closest('select,input,textarea')&&!event.target.closest('.day-switch'))return;swipeStart={x:event.clientX,y:event.clientY}});
timelineSection.addEventListener('pointerup',event=>{if(!swipeStart)return;const deltaX=event.clientX-swipeStart.x,deltaY=event.clientY-swipeStart.y;swipeStart=null;if(Math.abs(deltaX)>40&&Math.abs(deltaX)>Math.abs(deltaY)){ignoreDayClickUntil=Date.now()+500;selectDay(selectedDayOffset+(deltaX<0?1:-1))}});
timelineSection.addEventListener('pointercancel',()=>{swipeStart=null});
$('#journalInput').value=state.journal;$('#journalInput').oninput=e=>{state.journal=e.target.value;persist()};$('#backInput').value=state.back;$('#backInput').oninput=e=>{state.back=e.target.value;persist()};
$('#closeDay').onclick=()=>{window.alert('Day closed. Your check-in and priorities are saved.')};
const days=[['Mon','Night shift','0/8'],['Tue','Night again','0/8'],['Wed','Recovery','0/8'],['Thu','2:30–9','0/8'],['Fri','2:30–9','5/8'],['Sat','11–9','0/8'],['Sun','11–9','—']];$('#weekGrid').innerHTML=days.map(d=>`<div class="week-day"><strong>${d[0]} 16</strong><span>${d[1]}</span><small>${d[2]}</small></div>`).join('');
$('#funList').innerHTML=['A long walk with music','Try a new café','Call a friend','Watch a film','Cook something easy','Make time for games'].map(x=>`<div class="fun-item">${x}</div>`).join('');
const eventList=$('#eventList'),eventStatus=$('#eventStatus'),refreshEventsButton=$('#refreshEvents');
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
function renderEventSuggestions(events){
  if(!events.length){
    eventList.innerHTML='<p class="event-empty">No upcoming dated events are saved yet. Refresh to check the regional calendars.</p>';
    return;
  }
  eventList.innerHTML=events.map(event=>{
    const url=new URL(event.url);
    if(url.protocol!=='https:'||!['www.visitcincy.com','cincinnatizoo.org'].includes(url.hostname))return '';
    return `<article class="event-card">
      <div class="event-card-heading"><span class="event-category">${escapeHtml(event.category)}</span><span class="event-date">${escapeHtml(event.date_label)}</span></div>
      <h3><a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(event.title)}</a></h3>
      ${event.venue?`<p class="event-venue">${escapeHtml(event.venue)}</p>`:''}
      <p class="event-source">Source: ${escapeHtml(event.source)}</p>
    </article>`;
  }).join('');
}
function formatRefreshTime(value){
  if(!value)return '';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'':date.toLocaleString([],{dateStyle:'medium',timeStyle:'short'});
}
function updateEventStatus(payload){
  const sources=payload.sources||[];
  const updated=sources.filter(source=>source.ok).length;
  const failed=sources.filter(source=>!source.ok);
  const refreshed=payload.lastRefreshAt||payload.lastAttemptAt;
  const time=refreshed?` Last checked ${formatRefreshTime(refreshed)}.`:'';
  if(!sources.length){
    eventStatus.textContent='Saved suggestions are shown below. The local server checks public event calendars weekly; you can also refresh now.';
  }else if(failed.length===sources.length){
    eventStatus.textContent=`Could not refresh any event source.${time} ${failed.map(source=>`${source.name}: ${source.error}`).join(' ')}`;
    eventStatus.classList.add('event-status-error');
  }else if(failed.length){
    eventStatus.textContent=`Updated ${updated} of ${sources.length} event sources.${time} Keeping saved suggestions for unavailable sources: ${failed.map(source=>`${source.name} (${source.error})`).join('; ')}.`;
    eventStatus.classList.add('event-status-error');
  }else{
    eventStatus.textContent=`${payload.events.length} upcoming events from ${updated} sources.${time}`;
    eventStatus.classList.remove('event-status-error');
  }
}
async function loadEventSuggestions(){
  try{
    const response=await fetch('/api/events');
    const payload=await response.json();
    if(!response.ok)throw new Error(payload.error||`HTTP ${response.status}`);
    renderEventSuggestions(payload.events||[]);
    updateEventStatus(payload);
  }catch(error){
    eventStatus.textContent=`Could not load saved event suggestions (${error.message}). Start the local Daybook server and retry.`;
    eventStatus.classList.add('event-status-error');
    eventList.innerHTML='';
  }
}
refreshEventsButton.onclick=async()=>{
  refreshEventsButton.disabled=true;
  eventStatus.textContent='Checking public Cincinnati and Northern Kentucky event calendars…';
  eventStatus.classList.remove('event-status-error');
  try{
    const response=await fetch('/api/events/refresh',{method:'POST'});
    const payload=await response.json();
    if(!response.ok&&!payload.sources)throw new Error(payload.error||`HTTP ${response.status}`);
    renderEventSuggestions(payload.events||[]);
    updateEventStatus(payload);
  }catch(error){
    eventStatus.textContent=`Event refresh failed (${error.message}). Previously saved suggestions have not been removed.`;
    eventStatus.classList.add('event-status-error');
  }finally{
    refreshEventsButton.disabled=false;
  }
};
loadEventSuggestions();
const shapes=['Morning free, shift 2:30–9','Shift 2:30–9, then night shift','Long shift 11–9','Free day, night shift','Off shift, back on tonight','Recovery day','Off nights, shift 2:30–9'];$('#routineGrid').innerHTML=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d,i)=>`<div class="routine-day"><strong>${d}</strong><select>${shapes.map(s=>`<option${s===state.weekShapes[i]?' selected':''}>${s}</option>`).join('')}</select></div>`).join('');
$('#dayShape').value=dailyRecord().dayShape;$('#dayShape').onchange=e=>{dailyRecord().dayShape=e.target.value;if(selectedDayOffset===1)$('#tomorrowShape').value=e.target.value;persist();renderSelectedDay()};
$('#tomorrowShape').value=dailyRecord(1).dayShape;$('#tomorrowShape').onchange=e=>{dailyRecord(1).dayShape=e.target.value;state.tomorrowShape=e.target.value;persist();if(selectedDayOffset===1){$('#dayShape').value=e.target.value;renderSelectedDay()}};
$$('#routineGrid select').forEach((select,index)=>select.onchange=e=>{state.weekShapes[index]=e.target.value;persist()});
initializeStorage();
