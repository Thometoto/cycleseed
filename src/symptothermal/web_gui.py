from __future__ import annotations

import json
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .schema import DailyObservation, read_observations, upsert_observation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = PROJECT_ROOT / "data" / "personal.csv"
PROFILE_FILE = PROJECT_ROOT / "data" / "profile.json"
MODEL_FILE = PROJECT_ROOT / "models" / "base_model.json"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_FILE = OUTPUT_DIR / "today.json"


@dataclass
class EntryValues:
    observation_date: str
    temperature: Optional[float]
    mucus_type: str
    disturbed: bool
    pms: Optional[bool]
    menstrual: bool
    menstrual_flow: str
    spotting: bool = False


def save_daily_observation(values: EntryValues, path: Path = DATA_FILE) -> DailyObservation:
    existing = read_observations(path)
    menstruation_started = values.menstrual and (not existing or not existing[-1].menstrual)
    if not existing or menstruation_started:
        previous_number = max(
            [int(item.cycle_id.rsplit("-", 1)[-1]) for item in existing if item.cycle_id.startswith("personal-")],
            default=0,
        )
        cycle_id = f"personal-{previous_number + 1:04d}"
    else:
        cycle_id = existing[-1].cycle_id
    observation = DailyObservation(
        date=values.observation_date,
        temperature_c=values.temperature,
        mucus_type=values.mucus_type,
        disturbed=values.disturbed,
        pms=values.pms,
        menstrual=values.menstrual,
        menstrual_flow=values.menstrual_flow if values.menstrual else "NONE",
        spotting=values.spotting and not values.menstrual,
        cycle_id=cycle_id,
    )
    observation.validate()
    upsert_observation(path, observation)
    return observation


def _shift_month(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def build_visualization(today: dict) -> dict:
    observations = read_observations(DATA_FILE)
    profile = json.loads(PROFILE_FILE.read_text(encoding="utf-8")) if PROFILE_FILE.exists() else {}
    current_date = date.fromisoformat(today["date"])
    current_day = int(today["cycle_day"])
    cycle_start = current_date - timedelta(days=current_day - 1)
    average = int(profile.get("average_cycle_length", 30))
    phase = str(today.get("cycle_phase", ""))
    if phase == "LUTEAL_PHASE_SUPPORTED":
        ovulation_start = date.fromisoformat(today["estimated_ovulation_start"])
        ovulation_end = date.fromisoformat(today["estimated_ovulation_end"])
        ovulation_start_day = max(1, min(average, (ovulation_start - cycle_start).days + 1))
        ovulation_end_day = max(ovulation_start_day, min(average, (ovulation_end - cycle_start).days + 1))
    else:
        estimated_ovulation_day = max(6, average - 12)
        ovulation_start_day = max(1, estimated_ovulation_day - 2)
        ovulation_end_day = min(average, estimated_ovulation_day + 1)
        if "LUTEAL" in phase:
            ovulation_end_day = min(ovulation_end_day, current_day - 1)
            ovulation_start_day = min(ovulation_start_day, ovulation_end_day)
        elif "OVULATORY" in phase:
            ovulation_start_day = max(1, current_day - 2)
            ovulation_end_day = min(average, current_day + 1)
    current_cycle_id = observations[-1].cycle_id if observations else ""
    points = [
        {
            "date": observation.date,
            "day": (date.fromisoformat(observation.date) - cycle_start).days + 1,
            "temperature": observation.temperature_c,
            "disturbed": observation.disturbed,
        }
        for observation in observations
        if observation.cycle_id == current_cycle_id and observation.temperature_c is not None
    ]

    first_calendar_day = _shift_month(current_date, -1)
    next_month = _shift_month(current_date, 2)
    last_calendar_day = next_month - timedelta(days=1)
    observed_by_date = {observation.date: observation for observation in observations}
    calendar_days = []
    cursor = first_calendar_day
    while cursor <= last_calendar_day:
        relative = (cursor - cycle_start).days
        cycle_day = relative % average + 1
        observation = observed_by_date.get(cursor.isoformat())
        if observation and observation.menstrual:
            phase = "MENSTRUATION"
        elif cycle_day <= 5:
            phase = "MENSTRUATION"
        elif cycle_day < ovulation_start_day:
            phase = "FOLLICULAR"
        elif cycle_day <= ovulation_end_day:
            phase = "OVULATION"
        else:
            phase = "LUTEAL"
        calendar_days.append({
            "date": cursor.isoformat(), "day": cursor.day, "cycle_day": cycle_day,
            "phase": phase, "observed": observation is not None,
            "estimated": cursor > current_date, "today": cursor == current_date,
        })
        cursor += timedelta(days=1)
    return {
        "average_cycle_length": average, "current_cycle_day": current_day,
        "ovulation_start_day": ovulation_start_day, "ovulation_end_day": ovulation_end_day,
        "temperature_points": points, "calendar_days": calendar_days,
    }


HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CycleSeed</title>
  <style>
    :root{color-scheme:light;--ink:#25322d;--muted:#6f7b76;--line:#dce4e0;--accent:#26735d;--soft:#eef7f3;--warn:#9c3f35}
    *{box-sizing:border-box} body{margin:0;background:#f6f8f7;color:var(--ink);font:16px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    main{max-width:760px;margin:36px auto;padding:0 18px 50px}.card{background:white;border:1px solid var(--line);border-radius:18px;padding:26px;box-shadow:0 10px 35px #20382e10}
    h1{font-size:28px;margin:0 0 6px} h2{font-size:20px;margin:28px 0 14px}.sub,.hint{color:var(--muted);font-size:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 18px;margin-top:24px}
    label{display:grid;gap:6px;font-weight:600;font-size:14px} input,select{width:100%;padding:11px 12px;border:1px solid #bdc9c4;border-radius:10px;background:white;font:inherit;color:inherit}
    .check{display:flex;align-items:center;gap:9px;font-weight:500;padding-top:8px}.check input{width:auto}.wide{grid-column:1/-1}.init{margin-top:22px;padding:18px;background:var(--soft);border-radius:12px}
    button{margin-top:24px;border:0;border-radius:11px;padding:13px 18px;background:var(--accent);color:white;font:600 16px inherit;cursor:pointer;width:100%}button:disabled{opacity:.55;cursor:wait}
    #status{min-height:22px;margin:12px 0 0;color:var(--muted);font-size:14px}.result{display:none;margin-top:24px;border-top:1px solid var(--line);padding-top:20px}
    .metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metric{background:#f6f8f7;border-radius:11px;padding:13px}.metric b{display:block;margin-top:4px}.warning{color:var(--warn);font-size:13px;margin-top:22px}
    .viz{display:none;margin-top:26px}.chartWrap{border:1px solid var(--line);border-radius:14px;padding:12px;background:#fff;overflow:hidden}canvas{display:block;width:100%;height:310px}
    .legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:12px 0 18px;font-size:13px;color:var(--muted)}.legend span{display:flex;align-items:center;gap:6px}.swatch{width:12px;height:12px;border-radius:4px}
    .months{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.month{border:1px solid var(--line);border-radius:14px;padding:12px}.month h3{text-transform:capitalize;text-align:center;margin:2px 0 10px;font-size:16px}.week,.days{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}.week div{font-size:11px;color:var(--muted);text-align:center}.day{aspect-ratio:1;border-radius:7px;display:grid;place-items:center;font-size:12px;position:relative}.day.empty{background:transparent}.day.observed{font-weight:700}.day.estimated{opacity:.62}.day.today{outline:2px solid var(--ink);outline-offset:1px}
    .MENSTRUATION{background:#f8b5ad}.FOLLICULAR{background:#f3bad8}.OVULATION{background:#fae7a7}.LUTEAL{background:#b8def2}
    ul{padding-left:20px}.error{color:var(--warn)}@media(max-width:760px){.months{grid-template-columns:1fr}}@media(max-width:620px){main{margin-top:16px}.card{padding:20px}.grid,.metrics{grid-template-columns:1fr}.wide{grid-column:auto}canvas{height:270px}}
  </style>
</head>
<body><main><section class="card">
  <h1>CycleSeed</h1><div class="sub">Daily symptothermal tracking. Your data stays on this computer.</div>
  <form id="form"><div class="grid">
    <label>Date<input id="date" type="date" required></label>
    <label>Basal temperature (°C)<input id="temperature" inputmode="decimal" placeholder="36.65"></label>
    <label>Cervical mucus<select id="mucus"><option>DRY</option><option>STICKY</option><option>CREAMY</option><option>WATERY</option><option>EGG_WHITE</option></select></label>
    <label>PMS<select id="pms"><option value="unknown">Unknown</option><option value="false">No</option><option value="true">Yes</option></select></label>
    <label class="check"><input id="disturbed" type="checkbox"> Disturbed reading</label>
    <label class="check"><input id="menstrual" type="checkbox"> Menstruation today</label>
    <label class="check"><input id="spotting" type="checkbox"> Spotting today</label>
    <label id="flowLabel">Flow<select id="flow"><option value="LIGHT">Light</option><option value="MEDIUM" selected>Medium</option><option value="HEAVY">Heavy</option></select></label>
  </div>
  <div class="init" id="init"><strong>First use</strong><div class="hint">These details remain theoretical until one complete cycle has been observed.</div><div class="grid">
    <label>Approximate cycle day<input id="cycleDay" type="number" min="1" max="90" value="1"></label>
    <label>Approximate phase<select id="phase"><option>UNKNOWN</option><option>MENSTRUATION</option><option>FOLLICULAR</option><option>OVULATORY</option><option>LUTEAL</option></select></label>
    <label>Average cycle length<input id="average" type="number" min="15" max="90" value="30"></label>
  </div></div>
  <button id="submit">Save and analyze</button><div id="status"></div>
  </form>
  <section class="result" id="result"><h2>Today's result</h2><div class="metrics" id="metrics"></div><h2>Evidence</h2><ul id="evidence"></ul><h2>Warnings</h2><ul id="warnings"></ul></section>
  <section class="viz" id="viz"><h2>Cycle progress</h2><div class="hint">The solid line shows recorded temperatures. The colored bands show observed or estimated phases.</div><div class="chartWrap"><canvas id="cycleChart" aria-label="Temperature chart and cycle phases"></canvas></div>
    <div class="legend"><span><i class="swatch MENSTRUATION"></i>Menstruation</span><span><i class="swatch FOLLICULAR"></i>Follicular</span><span><i class="swatch OVULATION"></i>Ovulation</span><span><i class="swatch LUTEAL"></i>Luteal</span></div>
    <h2>Phase calendar</h2><div class="hint">Bold date: recorded observation. Faded color: future estimate.</div><div class="months" id="months"></div>
  </section>
  <div class="warning">Experimental prototype. Not validated for decisions about unprotected intercourse.</div>
</section></main>
<script>
const $=id=>document.getElementById(id), form=$('form'), status=$('status'), button=$('submit');
$('date').value=new Date().toISOString().slice(0,10);
function toggleFlow(){if($('menstrual').checked)$('spotting').checked=false;$('flowLabel').style.display=$('menstrual').checked?'grid':'none'} $('menstrual').onchange=toggleFlow;toggleFlow();
function list(id,items){$(id).innerHTML=(items?.length?items:['None']).map(x=>`<li>${escapeHtml(x)}</li>`).join('')}
function escapeHtml(x){return String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function drawChart(v){const c=$('cycleChart'),ctx=c.getContext('2d'),dpr=window.devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;c.width=w*dpr;c.height=h*dpr;ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);const pad={l:46,r:16,t:20,b:40},pw=w-pad.l-pad.r,ph=h-pad.t-pad.b,maxDay=v.average_cycle_length,colors={MENSTRUATION:'#f8b5ad',FOLLICULAR:'#f3bad8',OVULATION:'#fae7a7',LUTEAL:'#b8def2'};const x=d=>pad.l+(d-1)/Math.max(1,maxDay-1)*pw;const bands=[[1,5,'MENSTRUATION'],[6,Math.max(6,v.ovulation_start_day-1),'FOLLICULAR'],[v.ovulation_start_day,v.ovulation_end_day,'OVULATION'],[v.ovulation_end_day+1,maxDay,'LUTEAL']];bands.forEach(([a,b,p])=>{if(b<a)return;ctx.fillStyle=colors[p];ctx.globalAlpha=.72;ctx.fillRect(x(a),pad.t,Math.max(2,x(b+1)-x(a)),ph);ctx.globalAlpha=1});const temps=v.temperature_points.map(p=>p.temperature).filter(Number.isFinite),lo=temps.length?Math.floor((Math.min(...temps)-.15)*10)/10:36.0,hi=temps.length?Math.ceil((Math.max(...temps)+.15)*10)/10:37.2,y=t=>pad.t+(hi-t)/(hi-lo||1)*ph;ctx.strokeStyle='#ffffffaa';ctx.lineWidth=1;for(let t=lo;t<=hi+.001;t+=.2){ctx.beginPath();ctx.moveTo(pad.l,y(t));ctx.lineTo(w-pad.r,y(t));ctx.stroke();ctx.fillStyle='#64716c';ctx.font='11px sans-serif';ctx.fillText(t.toFixed(1),4,y(t)+4)}ctx.strokeStyle='#26312d';ctx.lineWidth=3;ctx.lineJoin='round';ctx.beginPath();let started=false;v.temperature_points.forEach(p=>{if(p.day<1||p.day>maxDay)return;started?ctx.lineTo(x(p.day),y(p.temperature)):ctx.moveTo(x(p.day),y(p.temperature));started=true});if(started)ctx.stroke();v.temperature_points.forEach(p=>{if(p.day<1||p.day>maxDay)return;ctx.beginPath();ctx.fillStyle=p.disturbed?'#a3453c':'#26312d';ctx.arc(x(p.day),y(p.temperature),4,0,Math.PI*2);ctx.fill()});ctx.setLineDash([5,4]);ctx.strokeStyle='#26312d';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x(v.current_cycle_day),pad.t);ctx.lineTo(x(v.current_cycle_day),pad.t+ph);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#26312d';ctx.font='12px sans-serif';ctx.fillText(`Today · D${v.current_cycle_day}`,Math.min(w-110,x(v.current_cycle_day)+5),pad.t+14);ctx.fillText('D1',pad.l,pad.t+ph+23);ctx.fillText(`D${maxDay}`,w-pad.r-24,pad.t+ph+23)}
function drawCalendar(v){const names=['January','February','March','April','May','June','July','August','September','October','November','December'],week=['M','T','W','T','F','S','S'],groups={};v.calendar_days.forEach(d=>{const key=d.date.slice(0,7);(groups[key]??=[]).push(d)});$('months').innerHTML=Object.entries(groups).map(([key,days])=>{const [year,month]=key.split('-').map(Number),first=new Date(`${key}-01T12:00:00`),offset=(first.getDay()+6)%7,blanks='<div class="day empty"></div>'.repeat(offset),cells=days.map(d=>`<div class="day ${d.phase} ${d.observed?'observed':''} ${d.estimated?'estimated':''} ${d.today?'today':''}" title="${d.phase} · cycle day ${d.cycle_day}">${d.day}</div>`).join('');return `<section class="month"><h3>${names[month-1]} ${year}</h3><div class="week">${week.map(x=>`<div>${x}</div>`).join('')}</div><div class="days">${blanks}${cells}</div></section>`}).join('')}
function show(payload){const r=payload.today||payload,v=payload.visualization||r.visualization;const fields=[['Cycle day',r.cycle_day],['Estimated phase',r.cycle_phase],['Fertility',r.fertility_status],['Pregnancy timing',r.baby_timing],['Theoretical estimate',r.theoretical_estimate?'YES':'NO'],['Estimated ovulation',`${r.estimated_ovulation_start} → ${r.estimated_ovulation_end}`]];$('metrics').innerHTML=fields.map(([a,b])=>`<div class="metric">${escapeHtml(a)}<b>${escapeHtml(b)}</b></div>`).join('');list('evidence',r.evidence);list('warnings',r.warnings);$('result').style.display='block';if(v){$('viz').style.display='block';drawChart(v);drawCalendar(v)}}
fetch('/api/state').then(r=>r.json()).then(s=>{ $('init').style.display=s.profile_exists?'none':'block'; if(s.today)show(s); if(!s.model_exists)status.innerHTML='<span class="error">Model not found. Run train_model.py first.</span>' });
form.onsubmit=async e=>{e.preventDefault();button.disabled=true;status.textContent='Analyzing…';const temp=$('temperature').value.trim().replace(',','.');const payload={date:$('date').value,temperature:temp===''?null:Number(temp),mucus_type:$('mucus').value,disturbed:$('disturbed').checked,pms:$('pms').value,menstrual:$('menstrual').checked,spotting:!$('menstrual').checked&&$('spotting').checked,menstrual_flow:$('menstrual').checked?$('flow').value:'NONE',initial_cycle_day:Number($('cycleDay').value),initial_phase:$('phase').value,average_cycle_length:Number($('average').value)};try{const response=await fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const body=await response.json();if(!response.ok)throw Error(body.error||'Unknown error');show(body);$('init').style.display='none';status.textContent='Observation saved and analysis complete.'}catch(err){status.innerHTML=`<span class="error">${escapeHtml(err.message)}</span>`}finally{button.disabled=false}};
window.addEventListener('resize',()=>{fetch('/api/state').then(r=>r.json()).then(s=>{if(s.visualization)drawChart(s.visualization)})});
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/state":
            today = json.loads(OUTPUT_FILE.read_text(encoding="utf-8")) if OUTPUT_FILE.exists() else None
            visualization = build_visualization(today) if today and DATA_FILE.exists() else None
            self._json({
                "model_exists": MODEL_FILE.exists(), "profile_exists": PROFILE_FILE.exists(),
                "today": today, "visualization": visualization,
            })
        else:
            self._json({"error": "Page not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/api/submit":
            self._json({"error": "Page not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not MODEL_FILE.exists():
                raise ValueError("Model not found. Run train_model.py first.")
            pms = None if payload["pms"] == "unknown" else payload["pms"] == "true"
            observation = save_daily_observation(EntryValues(
                observation_date=payload["date"], temperature=payload.get("temperature"),
                mucus_type=payload["mucus_type"], disturbed=bool(payload["disturbed"]), pms=pms,
                menstrual=bool(payload["menstrual"]), menstrual_flow=payload["menstrual_flow"],
                spotting=bool(payload.get("spotting", False)),
            ))
            if not PROFILE_FILE.exists():
                day, average = int(payload["initial_cycle_day"]), int(payload["average_cycle_length"])
                if not 1 <= day <= 90 or not 15 <= average <= 90:
                    raise ValueError("Invalid initialization values.")
                PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
                PROFILE_FILE.write_text(json.dumps({
                    "anchor_date": observation.date, "anchor_cycle_day": day,
                    "initial_phase": payload["initial_phase"], "average_cycle_length": average,
                    "theoretical_until_complete_cycle": True,
                }, indent=2), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "daily_followup.py")],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr or completed.stdout)
            today = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            self._json({"today": today, "visualization": build_visualization(today)})
        except Exception as error:
            self._json({"error": str(error)}, 400)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"CycleSeed is available at {url}")
    print("Press Ctrl+C in this terminal to stop it.")
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCycleSeed stopped.")
    finally:
        server.server_close()
