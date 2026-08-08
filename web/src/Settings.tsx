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
  if (query.isPending || !query.data) return <div className="page"><p>Загрузка настроек пилота…</p>{query.error && <ErrorMessage error={query.error} />}</div>;
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
  const setStage = (stage: PilotStage, tier: PilotTier, value: string) => set("stages", { ...settings.stages, [stage]: { ...settings.stages[stage], [tier]: value } });
  const workerOptions = [...new Set([...settings.allowed_workers, ...stages.flatMap((stage) => tiers.map((tier) => settings.stages[stage][tier]))])].filter(Boolean).sort();
  return <div className="page settings-page">
    <div className="view-header"><div><h1>Настройки</h1><p>Изменения применятся в начале следующего цикла работы пилота.</p></div><button className="button" onClick={refresh}><RefreshCw size={15}/> Обновить</button></div>
    {(warnings.length > 0) && <div className="settings-warning"><AlertTriangle size={17}/><div><strong>Сохранено с предупреждениями</strong>{warnings.map((warning) => <span key={warning}>{warning}</span>)}</div></div>}
    {save.error && <ErrorMessage error={save.error} conflictAction={refresh} />}
    {saved && <p className="settings-success">Настройки сохранены. Версия {version.slice(0, 12)}.</p>}

    <SettingsSection title="Работа пилота">
      <Check label="Пилот включён" description="Разрешает пилоту автоматически обрабатывать новые задачи." checked={settings.enabled} onChange={(value) => set("enabled", value)}/>
      <NumberField label="Интервал проверки, секунд" description="Как часто пилот проверяет, не появилась ли новая работа." value={settings.poll_seconds} onChange={(value) => set("poll_seconds", value)}/>
      <NumberField label="Лимит времени этапа, секунд" description="Сколько максимум может выполняться один этап до остановки." value={settings.timeout_seconds} onChange={(value) => set("timeout_seconds", value)}/>
      <NumberField label="Максимум попыток этапа" description="Сколько раз можно повторить этап после неудачи." value={settings.max_stage_attempts} onChange={(value) => set("max_stage_attempts", value)}/>
      <NumberField label="Параллельных подзадач" description="Сколько подзадач пилот может выполнять одновременно." value={settings.max_parallel_subtasks} onChange={(value) => set("max_parallel_subtasks", value)}/>
    </SettingsSection>

    <SettingsSection title="Маршрутизация этапов" wide>
      <Check label="Разрешить исполнителей вне списка" description="Позволяет назначать этапы исполнителям, которых нет в списке разрешённых." checked={settings.allow_any_worker} onChange={(value) => set("allow_any_worker", value)}/>
      <label className="field settings-full"><span>Идентификаторы разрешённых исполнителей</span><input value={settings.allowed_workers.join(", ")} onChange={(event) => set("allowed_workers", splitList(event.target.value))}/><small className="field-hint">Worker ID, которым можно назначать этапы; перечисляются через запятую и не переводятся.</small></label>
      <div className="settings-stage-table settings-full"><div className="settings-stage-caption"><strong>Исполнитель для каждого этапа и сложности</strong><small className="field-hint">Выберите worker ID отдельно для каждого сочетания этапа и уровня сложности.</small></div><div className="settings-stage-head"><span>Этап</span>{tiers.map((tier) => <span key={tier}>{tier}</span>)}</div>{stages.map((stage) => <div className="settings-stage-row" key={stage}><strong>{stage}</strong>{tiers.map((tier) => <select aria-label={`Исполнитель: ${stage}, ${tier}`} key={tier} value={settings.stages[stage][tier]} onChange={(event) => setStage(stage, tier, event.target.value)}>{workerOptions.map((worker) => <option key={worker}>{worker}</option>)}</select>)}</div>)}</div>
      <label className="field settings-full"><span>Этапы, пропускаемые для низкой сложности</span><input value={settings.skip_stages_for_low.join(", ")} onChange={(event) => set("skip_stages_for_low", splitList(event.target.value))}/><small className="field-hint">Технические названия этапов через запятую, которые не запускаются для уровня low.</small></label>
      <label className="field settings-full"><span>Остановленные конвейеры</span><input value={settings.stopped_pipelines.join(", ")} onChange={(event) => set("stopped_pipelines", splitList(event.target.value))}/><small className="field-hint">Идентификаторы конвейеров через запятую, для которых обработка временно остановлена.</small></label>
    </SettingsSection>

    <SettingsSection title="Автоматизация и бюджеты">
      <Check label="Автоматически сливать изменения" description="Разрешает слияние успешно проверенных изменений без участия владельца." checked={settings.auto_merge} onChange={(value) => set("auto_merge", value)}/><Check label="Автоматически отвечать" description="Разрешает пилоту самостоятельно отправлять итоговый ответ после выполнения." checked={settings.auto_answer} onChange={(value) => set("auto_answer", value)}/>
      <NumberField label="Дневной лимит, USD" description="Максимальная суммарная стоимость работы пилота за сутки." value={settings.day_cap_usd} onChange={(value) => set("day_cap_usd", value)}/>
      {tiers.map((tier) => <NumberField key={`factor-${tier}`} label={`Коэффициент сложности ${tier}`} description={`Множитель оценки стоимости для технического уровня ${tier}.`} value={settings.complexity_factor[tier]} onChange={(value) => set("complexity_factor", {...settings.complexity_factor, [tier]:value})}/>) }
      {tiers.map((tier) => <NumberField key={`cap-${tier}`} label={`Лимит задачи ${tier}, USD`} description={`Максимальная стоимость одной задачи уровня ${tier}.`} value={settings.work_cap_usd[tier]} onChange={(value) => set("work_cap_usd", {...settings.work_cap_usd, [tier]:value})}/>) }
      {stages.map((stage) => <NumberField key={stage} label={`Базовая стоимость ${stage}, USD`} description={`Базовая оценка стоимости технического этапа ${stage}.`} value={settings.stage_base_usd[stage]} onChange={(value) => set("stage_base_usd", {...settings.stage_base_usd, [stage]:value})}/>) }
      <TextField label="Команда развёртывания на стенде" description="Команда, которую пилот выполняет для публикации результата на staging-стенде." value={settings.deploy_staging_cmd} onChange={(value) => set("deploy_staging_cmd", value)}/>
    </SettingsSection>

    <SettingsSection title="Уведомления и модели" wide>
      <TextField label="Адрес сервера ntfy" description="HTTP(S)-адрес сервера ntfy для отправки уведомлений." value={settings.ntfy_server} onChange={(value) => set("ntfy_server", value)}/><TextField label="Тема ntfy" description="Техническое имя общей темы уведомлений пилота." value={settings.ntfy_topic} onChange={(value) => set("ntfy_topic", value)}/><TextField label="Тема ntfy владельца" description="Техническое имя темы для личных уведомлений владельца." value={settings.ntfy_owner_topic} onChange={(value) => set("ntfy_owner_topic", value)}/><TextField label="Ссылка на чат владельца" description="HTTP(S)-ссылка, по которой пилот направляет владельца в чат." value={settings.owner_chat_url} onChange={(value) => set("owner_chat_url", value)}/><TextField label="Ссылка на интерфейс владельца" description="HTTP(S)-ссылка на интерфейс, доступный владельцу." value={settings.owner_ui_url} onChange={(value) => set("owner_ui_url", value)}/>
      <div className="settings-full settings-subsection"><strong>Цепочка моделей</strong><small className="field-hint">Модели пробуются сверху вниз; технические имена сохраняются без перевода.</small></div>
      <div className="settings-full brain-list">{settings.brain_chain.map((brain, index) => <div className="brain-row" key={index}><TextField label="Команда CLI" description="Техническое имя запускаемой CLI-команды." value={brain.cli} onChange={(value) => updateBrain(index,"cli",value)}/><TextField label="Модель" description="Технический идентификатор модели." value={brain.model} onChange={(value) => updateBrain(index,"model",value)}/><TextField label="Провайдер" description="Технический идентификатор поставщика модели." value={brain.provider} onChange={(value) => updateBrain(index,"provider",value)}/><TextField label="Примечание к модели" description="Необязательное пояснение о назначении этой модели." value={brain.note ?? ""} onChange={(value) => updateBrain(index,"note",value)}/><div className="brain-actions"><button aria-label="Переместить выше" disabled={index===0} onClick={() => moveBrain(index,-1)}><ArrowUp size={15}/></button><button aria-label="Переместить ниже" disabled={index===settings.brain_chain.length-1} onClick={() => moveBrain(index,1)}><ArrowDown size={15}/></button><button aria-label="Удалить модель" disabled={settings.brain_chain.length===1} onClick={() => set("brain_chain",settings.brain_chain.filter((_,i)=>i!==index))}><Trash2 size={15}/></button></div></div>)}</div>
      <button className="button settings-full" onClick={() => set("brain_chain", [...settings.brain_chain,{cli:"",model:"",provider:"",note:""}])}><Plus size={15}/> Добавить модель</button>
      <label className="field settings-full"><span>Примечание к конфигурации</span><textarea value={settings._note ?? ""} onChange={(event)=>set("_note",event.target.value)} rows={3}/><small className="field-hint">Свободный комментарий владельца о назначении или последних изменениях настроек.</small></label>
    </SettingsSection>
    {errors.length > 0 && <div className="settings-errors">{errors.map((error) => <span key={error}>{error}</span>)}</div>}
    <div className="settings-save"><button className="button button-primary" disabled={errors.length>0 || save.isPending} onClick={() => save.mutate()}><Save size={16}/>{save.isPending ? "Сохранение…" : "Сохранить настройки"}</button></div>
  </div>;

  function updateBrain(index:number,key:"cli"|"model"|"provider"|"note",value:string) { const next=settings!.brain_chain.map((entry,i)=>i===index?{...entry,[key]:value}:entry); set("brain_chain",next); }
  function moveBrain(index:number,delta:number) { const next=[...settings!.brain_chain]; [next[index],next[index+delta]]=[next[index+delta],next[index]]; set("brain_chain",next); }
}

function SettingsSection({title,children,wide=false}:{title:string;children:ReactNode;wide?:boolean}) { return <section className={`panel settings-section ${wide?"settings-wide":""}`}><h2>{title}</h2><div className="settings-grid">{children}</div></section>; }
function Check({label,description,checked,onChange}:{label:string;description:string;checked:boolean;onChange:(value:boolean)=>void}) { return <label className="settings-check"><input type="checkbox" checked={checked} onChange={(event)=>onChange(event.target.checked)}/><span><strong>{label}</strong><small className="field-hint">{description}</small></span></label>; }
function TextField({label,description,value,onChange}:{label:string;description:string;value:string;onChange:(value:string)=>void}) { return <label className="field"><span>{label}</span><input value={value} onChange={(event)=>onChange(event.target.value)}/><small className="field-hint">{description}</small></label>; }
function NumberField({label,description,value,onChange}:{label:string;description:string;value:number;onChange:(value:number)=>void}) { return <label className="field"><span>{label}</span><input type="number" step="any" value={value} onChange={(event)=>onChange(Number(event.target.value))}/><small className="field-hint">{description}</small></label>; }
function splitList(value:string) { return value.split(",").map((item)=>item.trim()).filter(Boolean); }
function validate(settings:PilotSettings) { const errors:string[]=[]; const numbers=[settings.poll_seconds,settings.timeout_seconds,settings.max_stage_attempts,settings.max_parallel_subtasks,settings.day_cap_usd,...Object.values(settings.stage_base_usd),...Object.values(settings.complexity_factor),...Object.values(settings.work_cap_usd)]; if(numbers.some((value)=>!Number.isFinite(value)||value<=0)) errors.push("All durations, limits, factors, and budgets must be positive."); for(const [label,value] of [["ntfy server",settings.ntfy_server],["owner chat",settings.owner_chat_url],["owner UI",settings.owner_ui_url]]) { try { const url=new URL(value); if(!["http:","https:"].includes(url.protocol)) throw new Error(); } catch { errors.push(`${label} must be a valid http(s) URL.`); } } if(settings.brain_chain.some((entry)=>!entry.cli.trim()||!entry.model.trim()||!entry.provider.trim())) errors.push("Every brain-chain row needs CLI, model, and provider."); if(!settings.allow_any_worker && stages.some((stage)=>tiers.some((tier)=>!settings.allowed_workers.includes(settings.stages[stage][tier])))) errors.push("Every routed worker must be in the allowed list while unrestricted workers are disabled."); return errors; }
function ErrorMessage({error,conflictAction}:{error:unknown;conflictAction?:()=>void}) { const conflict=error instanceof APIError&&error.status===409; return <div className="settings-errors"><span>{error instanceof Error?error.message:"Unable to load settings."}</span>{conflict&&conflictAction&&<button className="button" onClick={conflictAction}>Refresh latest settings</button>}</div>; }
