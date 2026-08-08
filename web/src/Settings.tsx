import { AlertTriangle, ArrowDown, ArrowUp, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, APIError } from "./api";
import type { PilotSettings, PilotStage, PilotTier } from "./types";

const stages: PilotStage[] = ["Triage", "Specification", "Implement + Test", "Review", "Verify"];
const tiers: PilotTier[] = ["low", "medium", "high"];

export function Settings() {
  const query = useQuery({ queryKey: ["pilot-settings"], queryFn: api.pilotSettings, retry: false });
  if (query.isPending || !query.data) return <div className="page"><p>Loading pilot settings…</p>{query.error && <ErrorMessage error={query.error} />}</div>;
  return <SettingsEditor key={query.data.version} initial={query.data} refresh={() => void query.refetch()} />;
}

function SettingsEditor({initial,refresh}:{initial:Awaited<ReturnType<typeof api.pilotSettings>>;refresh:()=>void}) {
  const [settings, setSettings] = useState<PilotSettings>(() => structuredClone(initial.settings));
  const [version, setVersion] = useState(initial.version);
  const [warnings, setWarnings] = useState(initial.warnings);
  const [saved, setSaved] = useState(false);
  const errors = useMemo(() => validate(settings), [settings]);
  const save = useMutation({
    mutationFn: () => api.updatePilotSettings(version, settings),
    onSuccess: (result) => { setSettings(structuredClone(result.settings)); setVersion(result.version); setWarnings(result.warnings); setSaved(true); },
  });
  const set = <K extends keyof PilotSettings>(key: K, value: PilotSettings[K]) => { setSaved(false); setSettings({ ...settings, [key]: value }); };
  const stageWorkers = (stage: PilotStage) => settings.stages.find((entry) => entry.workflow === stage)!.workers;
  const setStage = (stage: PilotStage, tier: PilotTier, value: string) => set("stages", settings.stages.map((entry) => entry.workflow === stage ? { ...entry, workers: { ...entry.workers, [tier]: value } } : entry));
  const workerOptions = [...new Set([...settings.allowed_workers, ...stages.flatMap((stage) => tiers.map((tier) => stageWorkers(stage)[tier]))])].filter(Boolean).sort();
  return <div className="page settings-page">
    <div className="view-header"><div><h1>Pilot settings</h1><p>Changes apply when pilot starts its next polling cycle.</p></div><button className="button" onClick={refresh}><RefreshCw size={15}/> Refresh</button></div>
    {(warnings.length > 0) && <div className="settings-warning"><AlertTriangle size={17}/><div><strong>Saved with warnings</strong>{warnings.map((warning) => <span key={warning}>{warning}</span>)}</div></div>}
    {save.error && <ErrorMessage error={save.error} conflictAction={refresh} />}
    {saved && <p className="settings-success">Settings saved. Version {version.slice(0, 12)}.</p>}

    <SettingsSection title="Operation">
      <Check label="Pilot enabled" checked={settings.enabled} onChange={(value) => set("enabled", value)}/>
      <NumberField label="Poll interval (seconds)" value={settings.poll_seconds} onChange={(value) => set("poll_seconds", value)}/>
      <NumberField label="Stage timeout (seconds)" value={settings.timeout_seconds} onChange={(value) => set("timeout_seconds", value)}/>
      <NumberField label="Maximum stage attempts" value={settings.max_stage_attempts} onChange={(value) => set("max_stage_attempts", value)}/>
      <NumberField label="Maximum work rounds" value={settings.max_work_rounds} onChange={(value) => set("max_work_rounds", value)}/>
      <NumberField label="Maximum parallel subtasks" value={settings.max_parallel_subtasks} onChange={(value) => set("max_parallel_subtasks", value)}/>
    </SettingsSection>

    <SettingsSection title="Stage routing" wide>
      <Check label="Allow workers outside the list" checked={settings.allow_any_worker} onChange={(value) => set("allow_any_worker", value)}/>
      <label className="field settings-full"><span>Allowed worker IDs</span><input value={settings.allowed_workers.join(", ")} onChange={(event) => set("allowed_workers", splitList(event.target.value))}/><small className="field-hint">Initialized from workers known to Factory; comma-separated and editable.</small></label>
      <div className="settings-stage-table settings-full"><div className="settings-stage-head"><span>Stage</span>{tiers.map((tier) => <span key={tier}>{tier}</span>)}</div>{stages.map((stage) => <div className="settings-stage-row" key={stage}><strong>{stage}</strong>{tiers.map((tier) => <select aria-label={`${stage} ${tier} worker`} key={tier} value={stageWorkers(stage)[tier]} onChange={(event) => setStage(stage, tier, event.target.value)}>{workerOptions.map((worker) => <option key={worker}>{worker}</option>)}</select>)}</div>)}</div>
      <label className="field settings-full"><span>Skip for low complexity</span><input value={settings.skip_stages_for_low.join(", ")} onChange={(event) => set("skip_stages_for_low", splitList(event.target.value))}/></label>
      <label className="field settings-full"><span>Stopped pipelines</span><input value={settings.stopped_pipelines.join(", ")} onChange={(event) => set("stopped_pipelines", splitList(event.target.value))}/></label>
    </SettingsSection>

    <SettingsSection title="Automation and budgets">
      <Check label="Auto merge" checked={settings.auto_merge} onChange={(value) => set("auto_merge", value)}/><Check label="Auto answer" checked={settings.auto_answer} onChange={(value) => set("auto_answer", value)}/>
      <NumberField label="Daily cap (USD)" value={settings.day_cap_usd} onChange={(value) => set("day_cap_usd", value)}/>
      {tiers.map((tier) => <NumberField key={`factor-${tier}`} label={`${tier} complexity factor`} value={settings.complexity_factor[tier]} onChange={(value) => set("complexity_factor", {...settings.complexity_factor, [tier]:value})}/>) }
      {tiers.map((tier) => <NumberField key={`cap-${tier}`} label={`${tier} work cap (USD)`} value={settings.work_cap_usd[tier]} onChange={(value) => set("work_cap_usd", {...settings.work_cap_usd, [tier]:value})}/>) }
      {stages.map((stage) => <NumberField key={stage} label={`${stage} base (USD)`} value={settings.stage_base_usd[stage]} onChange={(value) => set("stage_base_usd", {...settings.stage_base_usd, [stage]:value})}/>) }
      <TextField label="Staging deploy command" value={settings.deploy_staging_cmd} onChange={(value) => set("deploy_staging_cmd", value)}/>
    </SettingsSection>

    <SettingsSection title="Notifications and owner links">
      <TextField label="ntfy server" value={settings.ntfy_server} onChange={(value) => set("ntfy_server", value)}/><TextField label="ntfy topic" value={settings.ntfy_topic} onChange={(value) => set("ntfy_topic", value)}/><TextField label="Owner ntfy topic" value={settings.ntfy_owner_topic} onChange={(value) => set("ntfy_owner_topic", value)}/><TextField label="Owner chat URL" value={settings.owner_chat_url} onChange={(value) => set("owner_chat_url", value)}/><TextField label="Owner UI URL" value={settings.owner_ui_url} onChange={(value) => set("owner_ui_url", value)}/>
    </SettingsSection>

    <SettingsSection title="Brain chain" wide>
      <div className="settings-full brain-list">{settings.brain_chain.map((brain, index) => <div className="brain-row" key={index}><TextField label="CLI" value={brain.cli} onChange={(value) => updateBrain(index,"cli",value)}/><TextField label="Model" value={brain.model} onChange={(value) => updateBrain(index,"model",value)}/><TextField label="Provider" value={brain.provider} onChange={(value) => updateBrain(index,"provider",value)}/><TextField label="Note" value={brain.note ?? ""} onChange={(value) => updateBrain(index,"note",value)}/><div className="brain-actions"><button aria-label="Move up" disabled={index===0} onClick={() => moveBrain(index,-1)}><ArrowUp size={15}/></button><button aria-label="Move down" disabled={index===settings.brain_chain.length-1} onClick={() => moveBrain(index,1)}><ArrowDown size={15}/></button><button aria-label="Remove brain" disabled={settings.brain_chain.length===1} onClick={() => set("brain_chain",settings.brain_chain.filter((_,i)=>i!==index))}><Trash2 size={15}/></button></div></div>)}</div>
      <button className="button settings-full" onClick={() => set("brain_chain", [...settings.brain_chain,{cli:"",model:"",provider:"",note:""}])}><Plus size={15}/> Add brain</button>
    </SettingsSection>
    <SettingsSection title="Configuration note"><label className="field settings-full"><span>Configuration note</span><textarea value={settings._note ?? ""} onChange={(event)=>set("_note",event.target.value)} rows={3}/></label></SettingsSection>
    {errors.length > 0 && <div className="settings-errors">{errors.map((error) => <span key={error}>{error}</span>)}</div>}
    <div className="settings-save"><button className="button button-primary" disabled={errors.length>0 || save.isPending} onClick={() => save.mutate()}><Save size={16}/>{save.isPending ? "Saving…" : "Save settings"}</button></div>
  </div>;

  function updateBrain(index:number,key:"cli"|"model"|"provider"|"note",value:string) { const next=settings!.brain_chain.map((entry,i)=>i===index?{...entry,[key]:value}:entry); set("brain_chain",next); }
  function moveBrain(index:number,delta:number) { const next=[...settings!.brain_chain]; [next[index],next[index+delta]]=[next[index+delta],next[index]]; set("brain_chain",next); }
}

function SettingsSection({title,children,wide=false}:{title:string;children:ReactNode;wide?:boolean}) { return <section className={`panel settings-section ${wide?"settings-wide":""}`}><h2>{title}</h2><div className="settings-grid">{children}</div></section>; }
function Check({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}) { return <label className="settings-check"><input type="checkbox" checked={checked} onChange={(event)=>onChange(event.target.checked)}/><span>{label}</span></label>; }
function TextField({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}) { return <label className="field"><span>{label}</span><input value={value} onChange={(event)=>onChange(event.target.value)}/></label>; }
function NumberField({label,value,onChange}:{label:string;value:number;onChange:(value:number)=>void}) { return <label className="field"><span>{label}</span><input type="number" step="any" value={value} onChange={(event)=>onChange(Number(event.target.value))}/></label>; }
function splitList(value:string) { return value.split(",").map((item)=>item.trim()).filter(Boolean); }
function validate(settings:PilotSettings) { const errors:string[]=[]; const numbers=[settings.poll_seconds,settings.timeout_seconds,settings.max_stage_attempts,settings.max_work_rounds,settings.max_parallel_subtasks,settings.day_cap_usd,...Object.values(settings.stage_base_usd),...Object.values(settings.complexity_factor),...Object.values(settings.work_cap_usd)]; if(numbers.some((value)=>!Number.isFinite(value)||value<=0)) errors.push("All durations, limits, factors, and budgets must be positive."); for(const [label,value] of [["ntfy server",settings.ntfy_server],["owner chat",settings.owner_chat_url],["owner UI",settings.owner_ui_url]]) { try { const url=new URL(value); if(!["http:","https:"].includes(url.protocol)) throw new Error(); } catch { errors.push(`${label} must be a valid http(s) URL.`); } } if(settings.brain_chain.some((entry)=>!entry.cli.trim()||!entry.model.trim()||!entry.provider.trim())) errors.push("Every brain-chain row needs CLI, model, and provider."); if(!settings.allow_any_worker && settings.stages.some((stage)=>tiers.some((tier)=>!settings.allowed_workers.includes(stage.workers[tier])))) errors.push("Every routed worker must be in the allowed list while unrestricted workers are disabled."); return errors; }
function ErrorMessage({error,conflictAction}:{error:unknown;conflictAction?:()=>void}) { const conflict=error instanceof APIError&&error.status===409; return <div className="settings-errors"><span>{error instanceof Error?error.message:"Unable to load settings."}</span>{conflict&&conflictAction&&<button className="button" onClick={conflictAction}>Refresh latest settings</button>}</div>; }
