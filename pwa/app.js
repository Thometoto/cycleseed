"use strict";

const STORAGE_KEY = "cycleseed-data-v1";
const MODEL = {
  threshold: 0.15,
  names: ["bias","cycle_day_scaled","temperature_delta","fertile_mucus","disturbed","menstrual","history_prior"],
  mean: {bias:0,cycle_day_scaled:.3552719480683185,temperature_delta:.07371372187559085,fertile_mucus:.15754395916052183,disturbed:.06778218944980148,menstrual:.15399886557005105,history_prior:.2631877481565513},
  scale: {bias:1,cycle_day_scaled:.2057744199576745,temperature_delta:.3018034494788466,fertile_mucus:.3436286675869987,disturbed:.2514074180490191,menstrual:.3609988569933149,history_prior:.32801218179709873},
  weights: {bias:-1.3511756107055346,cycle_day_scaled:-1.5174006801519597,temperature_delta:-1.3402325528470653,fertile_mucus:.19859140275709955,disturbed:.17805566280244606,menstrual:-.8095932230884958,history_prior:3.981606106724014}
};
const $ = id => document.getElementById(id);
const isoToday = () => new Date().toLocaleDateString("en-CA");
const dateAtNoon = iso => new Date(`${iso}T12:00:00`);
const addDays = (value, days) => { const d = typeof value === "string" ? dateAtNoon(value) : new Date(value); d.setDate(d.getDate()+days); return d; };
const iso = d => d.toLocaleDateString("en-CA");
const dayDiff = (a,b) => Math.round((dateAtNoon(a)-dateAtNoon(b))/86400000);
const mean = values => values.reduce((a,b)=>a+b,0)/values.length;
const clamp = (v,a,b) => Math.max(a,Math.min(b,v));

function emptyState(){ return {version:1,profile:null,observations:[]}; }
function load(){ try { return {...emptyState(),...JSON.parse(localStorage.getItem(STORAGE_KEY)||"null")}; } catch { return emptyState(); } }
function save(state){ localStorage.setItem(STORAGE_KEY,JSON.stringify(state)); }
let state = load();

function cycleInfo(observation){
  const sorted=[...state.observations].sort((a,b)=>a.date.localeCompare(b.date));
  let start=state.profile?.anchorDate || observation.date;
  let anchorDay=state.profile?.anchorCycleDay || 1;
  for(const item of sorted){
    if(item.date>observation.date) break;
    if(item.menstrual && (!sorted.some(x=>x.date<item.date && dayDiff(item.date,x.date)===1 && x.menstrual))){ start=item.date; anchorDay=1; }
  }
  return {start,day:anchorDay+dayDiff(observation.date,start)};
}

function currentCycle(observation){
  const info=cycleInfo(observation);
  return state.observations.filter(o=>o.date>=info.start&&o.date<=observation.date).sort((a,b)=>a.date.localeCompare(b.date)).map(o=>({...o,cycle_day:1+dayDiff(o.date,info.start)}));
}

function thermalShift(cycle){
  const clean=cycle.filter(o=>o.temperature_c!=null&&!o.disturbed);
  for(let i=6;i<clean.length-2;i++){
    const threshold=Math.max(...clean.slice(i-6,i).map(o=>o.temperature_c))+.15;
    if(clean.slice(i,i+3).every(o=>o.temperature_c>=threshold)) return clean[i].cycle_day;
  }
  return null;
}

function features(cycle,index,expected){
  const o=cycle[index], previous=cycle.slice(Math.max(0,index-6),index).filter(x=>x.temperature_c!=null&&!x.disturbed).map(x=>x.temperature_c);
  const baseline=previous.length>=3?mean(previous):o.temperature_c;
  const delta=o.temperature_c!=null&&baseline!=null&&!o.disturbed?clamp((o.temperature_c-baseline)/.4,-1,1):0;
  const mucus=["WATERY","EGG_WHITE"].includes(o.mucus_type)?1:o.mucus_type==="CREAMY"?.5:0;
  return {bias:1,cycle_day_scaled:Math.min(o.cycle_day,45)/45,temperature_delta:delta,fertile_mucus:mucus,disturbed:o.disturbed?1:0,menstrual:o.menstrual?1:0,history_prior:Math.max(0,1-Math.abs(o.cycle_day-expected)/8)};
}

function probability(values){
  const score=MODEL.names.reduce((sum,name)=>sum+MODEL.weights[name]*(name==="bias"?1:(values[name]-MODEL.mean[name])/MODEL.scale[name]),0);
  return 1/(1+Math.exp(-clamp(score,-30,30)));
}

function analyze(observation){
  const info=cycleInfo(observation), cycle=currentCycle(observation), average=state.profile.averageCycleLength, expected=Math.max(6,average-12);
  let prob=probability(features(cycle,cycle.length-1,expected));
  const shift=thermalShift(cycle), peak=Math.max(0,...cycle.filter(o=>["WATERY","EGG_WHITE"].includes(o.mucus_type)).map(o=>o.cycle_day));
  let confidence=0; const evidence=[];
  if(shift&&info.day-shift+1>=3){ confidence+=.55; evidence.push("A sustained thermal rise was detected across 3 valid readings."); }
  if(peak&&info.day-peak>=3){ confidence+=.25; evidence.push("The last fertile-type mucus sign was observed at least 3 days ago."); }
  if(["WATERY","EGG_WHITE"].includes(observation.mucus_type)){ prob=Math.max(prob,.85); evidence.push("Fertile-type cervical mucus was observed today."); }
  if(observation.disturbed) confidence*=.65;
  confidence=Math.min(confidence,.95);
  let phase,phaseShort;
  if(observation.menstrual){ phase="MENSTRUATION_OBSERVED"; phaseShort="MENSTRUATION"; }
  else if(confidence>=.8){ phase="LUTEAL_PHASE_SUPPORTED"; phaseShort="LUTEAL"; }
  else if(state.profile.theoretical){
    const reported={MENSTRUATION:"MENSTRUATION_REPORTED",FOLLICULAR:"FOLLICULAR_PHASE_REPORTED",OVULATORY:"OVULATORY_WINDOW_REPORTED",LUTEAL:"LUTEAL_PHASE_REPORTED_UNCONFIRMED",UNKNOWN:"PHASE_UNCERTAIN"};
    phase=reported[state.profile.initialPhase]; phaseShort=state.profile.initialPhase==="OVULATORY"?"OVULATION":state.profile.initialPhase;
  } else { phase=prob>=.65?"OVULATORY_WINDOW_POSSIBLE":"FOLLICULAR_PHASE_OR_UNCERTAIN"; phaseShort=prob>=.65?"OVULATION":"FOLLICULAR"; }
  const lower=shift&&info.day-shift+1>=3?Math.max(1,shift-2):Math.max(1,expected-6), upper=shift&&info.day-shift+1>=3?shift:expected+6;
  const ovStart=addDays(info.start,lower-1), ovEnd=addDays(info.start,upper-1), current=dateAtNoon(observation.date);
  const favorable=current>=addDays(ovStart,-2)&&current<=addDays(ovEnd,1)&&prob>=.65;
  const possible=current>=addDays(ovStart,-5)&&current<=addDays(ovEnd,1)&&confidence<.8;
  return {date:observation.date,cycle_day:info.day,cycle_start:info.start,cycle_phase:phase,phase_short:phaseShort,fertility_status:prob>=MODEL.threshold||confidence<.8?"POTENTIALLY_FERTILE":"FERTILITY_NOT_CURRENTLY_DETECTED",baby_timing:favorable?"FAVORABLE":possible?"POSSIBLE":"OUTSIDE_ESTIMATED_WINDOW",model_probability:prob,confidence,ovulation_start_day:lower,ovulation_end_day:upper,evidence,theoretical:state.profile.theoretical,average};
}

function render(result){
  $("result").style.display=$("chartSection").style.display=$("calendarSection").style.display="block";
  const fields=[["Cycle day",`Day ${result.cycle_day}`],["Estimated phase",result.cycle_phase],["Fertility",result.fertility_status],["Pregnancy timing",result.baby_timing]];
  $("metrics").innerHTML=fields.map(([a,b])=>`<div class="metric">${a}<strong>${b}</strong></div>`).join("");
  $("explanation").textContent=result.evidence.length?result.evidence.join(" "):result.theoretical?"This phase is based on the approximate starting information and remains theoretical.":"More observations are needed to support the current phase.";
  drawChart(result); drawCalendar(result);
}

function phaseForDay(day,result){ if(day<=5)return"MENSTRUATION";if(day<result.ovulation_start_day)return"FOLLICULAR";if(day<=result.ovulation_end_day)return"OVULATION";return"LUTEAL"; }
function drawChart(result){
  const c=$("chart"),ctx=c.getContext("2d"),ratio=devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;c.width=w*ratio;c.height=h*ratio;ctx.scale(ratio,ratio);
  const pad={l:44,r:14,t:18,b:35},pw=w-pad.l-pad.r,ph=h-pad.t-pad.b,max=result.average,x=d=>pad.l+(d-1)/(max-1)*pw;
  const colors={MENSTRUATION:"#f2aaa2",FOLLICULAR:"#efb4d3",OVULATION:"#f5dfa0",LUTEAL:"#add6ea"},bands=[[1,5,"MENSTRUATION"],[6,result.ovulation_start_day-1,"FOLLICULAR"],[result.ovulation_start_day,result.ovulation_end_day,"OVULATION"],[result.ovulation_end_day+1,max,"LUTEAL"]];
  ctx.clearRect(0,0,w,h);bands.forEach(([a,b,p])=>{if(a>b)return;ctx.fillStyle=colors[p];ctx.globalAlpha=.75;ctx.fillRect(x(a),pad.t,Math.max(2,x(Math.min(max,b+1))-x(a)),ph)});ctx.globalAlpha=1;
  const cycle=currentCycle(state.observations.find(o=>o.date===result.date)),points=cycle.filter(o=>o.temperature_c!=null),temps=points.map(o=>o.temperature_c),lo=temps.length?Math.floor((Math.min(...temps)-.15)*10)/10:36,hi=temps.length?Math.ceil((Math.max(...temps)+.15)*10)/10:37.2,y=t=>pad.t+(hi-t)/(hi-lo||1)*ph;
  ctx.strokeStyle="#fff9";ctx.lineWidth=1;for(let t=lo;t<=hi+.001;t+=.2){ctx.beginPath();ctx.moveTo(pad.l,y(t));ctx.lineTo(w-pad.r,y(t));ctx.stroke();ctx.fillStyle="#62706a";ctx.font="11px sans-serif";ctx.fillText(t.toFixed(1),3,y(t)+4)}
  ctx.beginPath();ctx.strokeStyle="#24322c";ctx.lineWidth=3;points.forEach((p,i)=>i?ctx.lineTo(x(p.cycle_day),y(p.temperature_c)):ctx.moveTo(x(p.cycle_day),y(p.temperature_c)));ctx.stroke();
  points.forEach(p=>{ctx.beginPath();ctx.fillStyle=p.disturbed?"#9a3f37":"#24322c";ctx.arc(x(p.cycle_day),y(p.temperature_c),4,0,Math.PI*2);ctx.fill()});
  ctx.setLineDash([5,4]);ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x(result.cycle_day),pad.t);ctx.lineTo(x(result.cycle_day),pad.t+ph);ctx.stroke();ctx.setLineDash([]);ctx.font="12px sans-serif";ctx.fillText(`Today · D${result.cycle_day}`,Math.min(w-100,x(result.cycle_day)+5),pad.t+14);ctx.fillText("D1",pad.l,pad.t+ph+22);ctx.fillText(`D${max}`,w-pad.r-25,pad.t+ph+22);
}

function drawCalendar(result){
  const current=dateAtNoon(result.date),months=[];for(let offset=-1;offset<=1;offset++)months.push(new Date(current.getFullYear(),current.getMonth()+offset,1,12));
  $("calendar").innerHTML=months.map(first=>{const last=new Date(first.getFullYear(),first.getMonth()+1,0,12),blanks=(first.getDay()+6)%7;let cells='<span class="day"></span>'.repeat(blanks);for(let d=1;d<=last.getDate();d++){const value=new Date(first.getFullYear(),first.getMonth(),d,12),cycleDay=((dayDiff(iso(value),result.cycle_start)%result.average)+result.average)%result.average+1,phase=phaseForDay(cycleDay,result);cells+=`<span class="day ${phase} ${iso(value)===result.date?'today':''} ${value>current?'future':''}" title="${phase}, cycle day ${cycleDay}">${d}</span>`}return`<div class="month"><h3>${first.toLocaleDateString("en",{month:"long",year:"numeric"})}</h3><div class="week">${["M","T","W","T","F","S","S"].map(x=>`<span>${x}</span>`).join("")}</div><div class="days">${cells}</div></div>`}).join("");
}

function download(name,type,text){const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csv(){const fields=["date","temperature_c","mucus_type","disturbed","pms","menstrual","menstrual_flow","cycle_id","cycle_day","synthetic_label_fertile","synthetic_ovulation_day","synthetic_phase_label"];const rows=state.observations.map(o=>{const info=cycleInfo(o);return[o.date,o.temperature_c??"",o.mucus_type,o.disturbed,o.pms??"",o.menstrual,o.menstrual_flow,"personal-ipad",info.day,"","",""]});return[fields,...rows].map(r=>r.map(v=>`"${String(v).replaceAll('"','""')}"`).join(",")).join("\n");}

$("date").value=isoToday();$("setup").style.display=state.profile?"none":"block";$("flowLabel").style.display="none";
$("menstrual").addEventListener("change",()=>$("flowLabel").style.display=$("menstrual").checked?"grid":"none");
$("observationForm").addEventListener("submit",event=>{event.preventDefault();
  if(!state.profile){const day=Number($("initialDay").value),average=Number($("averageLength").value);if(day<1||day>90||average<15||average>90)return $("status").textContent="Check the first-use values.";state.profile={anchorDate:$("date").value,anchorCycleDay:day,initialPhase:$("initialPhase").value,averageCycleLength:average,theoretical:true};}
  const temp=$("temperature").value===""?null:Number($("temperature").value);if(temp!=null&&(temp<34||temp>42))return $("status").textContent="Temperature must be between 34 and 42 °C.";
  const observation={date:$("date").value,temperature_c:temp,mucus_type:$("mucus").value,disturbed:$("disturbed").checked,pms:$("pms").value==="unknown"?null:$("pms").value==="true",menstrual:$("menstrual").checked,menstrual_flow:$("menstrual").checked?$("flow").value:"NONE"};
  const previous=state.observations.filter(o=>o.date<observation.date).sort((a,b)=>a.date.localeCompare(b.date)).at(-1);
  if(observation.menstrual && previous && !previous.menstrual && state.observations.some(o=>o.menstrual)) state.profile.theoretical=false;
  state.observations=state.observations.filter(o=>o.date!==observation.date);state.observations.push(observation);state.observations.sort((a,b)=>a.date.localeCompare(b.date));save(state);$("setup").style.display="none";$("status").textContent="Observation saved on this device.";render(analyze(observation));
});
$("exportJson").addEventListener("click",()=>download(`cycleseed-backup-${isoToday()}.json`,"application/json",JSON.stringify(state,null,2)));
$("exportCsv").addEventListener("click",()=>download(`cycleseed-observations-${isoToday()}.csv`,"text/csv",csv()));
$("importJson").addEventListener("change",async event=>{try{const incoming=JSON.parse(await event.target.files[0].text());if(!incoming.profile||!Array.isArray(incoming.observations))throw Error();state=incoming;save(state);location.reload()}catch{alert("This is not a valid CycleSeed backup.")}});
if(state.observations.length) render(analyze(state.observations.at(-1)));
window.addEventListener("resize",()=>{if(state.observations.length)drawChart(analyze(state.observations.at(-1)))});
if("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js");
