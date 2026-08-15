import { AlertTriangle, ArrowDown, ArrowUp, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, APIError } from "./api";
import type { PilotNotificationGroup, PilotSettings, PilotTier } from "./types";

const tiers: PilotTier[] = ["low", "medium", "high"];
const tierNames: Record<PilotTier, string> = { low: "низкая", medium: "средняя", high: "высокая" };
const notificationGroups: Array<{key:PilotNotificationGroup;label:string;hint:string;defaultEnabled:boolean}> = [
  {key:"questions",label:"Вопросы ко мне",hint:"Присылать уведомление, когда пилоту нужен ваш ответ.",defaultEnabled:true},
  {key:"stuck",label:"Работа встала",hint:"Присылать уведомление, если задача остановилась и требует вмешательства.",defaultEnabled:true},
  {key:"money",label:"Деньги и лимиты",hint:"Присылать уведомление о расходах и приближении к лимитам.",defaultEnabled:true},
  {key:"done",label:"Завершения и запуски задач",hint:"Присылать уведомление о завершении и запуске задач.",defaultEnabled:true},
  {key:"escalate",label:"Исполнитель повышен",hint:"Присылать уведомление, когда после двух провалов этап уходит модели уровнем выше (это дороже).",defaultEnabled:true},
  {key:"routine",label:"Рабочая рутина",hint:"Присылать уведомление о рутинных шагах пилота.",defaultEnabled:false},
];

function withNotificationDefaults(settings:PilotSettings):PilotSettings {
  return {...settings,notify_groups:Object.fromEntries(notificationGroups.map((group)=>[group.key,settings.notify_groups?.[group.key]??group.defaultEnabled]))};
}

export function Settings() {
  const query = useQuery({ queryKey: ["pilot-settings"], queryFn: api.pilotSettings, retry: false });
  if (query.isPending || !query.data) return <div className="page"><p>Загружаем настройки…</p>{query.error && <ErrorMessage error={query.error} />}</div>;
  return <SettingsEditor key={query.data.version} initial={query.data} refresh={() => void query.refetch()} />;
}

function SettingsEditor({initial,refresh}:{initial:Awaited<ReturnType<typeof api.pilotSettings>>;refresh:()=>void}) {
  const [settings, setSettings] = useState<PilotSettings>(() => withNotificationDefaults(structuredClone(initial.settings)));
  const [version, setVersion] = useState(initial.version);
  const [warnings, setWarnings] = useState(initial.warnings);
  const [saved, setSaved] = useState(false);
  const errors = useMemo(() => validate(settings), [settings]);
  const save = useMutation({
    mutationFn: () => api.updatePilotSettings(version, settings),
    onSuccess: (result) => { setSettings(withNotificationDefaults(structuredClone(result.settings))); setVersion(result.version); setWarnings(result.warnings); setSaved(true); },
  });
  const set = <K extends keyof PilotSettings>(key: K, value: PilotSettings[K]) => { setSaved(false); setSettings({ ...settings, [key]: value }); };
  const setStage = (stage: string, tier: PilotTier, value: string) => set("stages", settings.stages.map((row) => row.workflow === stage ? { ...row, workers: { ...row.workers, [tier]: value } } : row));
  const workerOptions = [...new Set([...settings.allowed_workers, ...settings.stages.flatMap((row) => tiers.map((tier) => row.workers[tier]))])].filter(Boolean).sort();
  return <div className="page settings-page">
    <div className="view-header"><div><h1>Настройки</h1><p>Изменения применятся в начале следующего цикла проверки.</p></div><div className="settings-header-actions"><button className="button" onClick={refresh}><RefreshCw size={15}/> Обновить</button><button className="button button-primary" disabled={errors.length>0 || save.isPending} onClick={() => save.mutate()}><Save size={16}/>{save.isPending ? "Сохраняем…" : "Сохранить настройки"}</button></div></div>
    <nav className="settings-nav" aria-label="Разделы настроек">
      <a href="#settings-pilot">Работа пилота</a><a href="#settings-routing">Маршрутизация</a><a href="#settings-budgets">Автоматизация и бюджеты</a><a href="#settings-notifications">Уведомления</a><a href="#settings-models">Модели</a><a href="#settings-sources">Источники данных</a><a href="#settings-note">Заметка</a>
    </nav>
    {(warnings.length > 0) && <div className="settings-warning"><AlertTriangle size={17}/><div><strong>Сохранено с предупреждениями</strong>{warnings.map((warning) => <span key={warning}>{warning}</span>)}</div></div>}
    {save.error && <ErrorMessage error={save.error} conflictAction={refresh} />}
    {saved && <p className="settings-success">Настройки сохранены. Версия {version.slice(0, 12)}.</p>}

    <SettingsSection id="settings-pilot" title="Работа пилота">
      <Check label="Пилот включён" hint="Разрешает пилоту находить и запускать новые задачи." checked={settings.enabled} onChange={(value) => set("enabled", value)}/>
      <NumberField label="Интервал проверки, секунд" hint="Как часто пилот проверяет очередь новых задач." value={settings.poll_seconds} onChange={(value) => set("poll_seconds", value)}/>
      <NumberField label="Тайм-аут этапа, секунд" hint="Сколько времени этап может выполняться до принудительной остановки." value={settings.timeout_seconds} onChange={(value) => set("timeout_seconds", value)}/>
      <NumberField label="Максимум попыток этапа" hint="Сколько раз можно повторить неудачный этап." value={settings.max_stage_attempts} onChange={(value) => set("max_stage_attempts", value)}/>
      <NumberField label="Максимум параллельных подзадач" hint="Сколько подзадач одного процесса можно выполнять одновременно." value={settings.max_parallel_subtasks} onChange={(value) => set("max_parallel_subtasks", value)}/>
      <NumberField label="Параллельные работы" hint="Сколько независимых работ из Плана Factory держит в конвейере одновременно." value={settings.max_parallel_works} onChange={(value) => set("max_parallel_works", value)}/>
    </SettingsSection>

    <SettingsSection id="settings-routing" title="Маршрутизация этапов" wide>
      <Check label="Разрешить исполнителей вне списка" hint="Позволяет назначать этапы исполнителям, которых нет в списке разрешённых." checked={settings.allow_any_worker} onChange={(value) => set("allow_any_worker", value)}/>
      <TextField wide label="Разрешённые ID исполнителей" hint="Введите ID через запятую; изначально список составлен из известных Factory исполнителей." value={settings.allowed_workers.join(", ")} onChange={(value) => set("allowed_workers", splitList(value))}/>
      <div className="settings-full"><p className="settings-field-title">Исполнитель для каждого этапа</p><small className="field-hint">Выберите исполнителя отдельно для каждой сложности этапа.</small><div className="settings-stage-table"><div className="settings-stage-head"><span>Этап</span>{tiers.map((tier) => <span key={tier}>{tierNames[tier]}</span>)}</div>{settings.stages.map((row) => <div className="settings-stage-row" key={row.workflow}><strong>{row.workflow}</strong>{tiers.map((tier) => <select aria-label={`${row.workflow}: ${tierNames[tier]} сложность`} key={tier} value={row.workers[tier]} onChange={(event) => setStage(row.workflow, tier, event.target.value)}>{workerOptions.map((worker) => <option key={worker}>{worker}</option>)}</select>)}</div>)}</div></div>
      <TextField wide label="Пропускать при низкой сложности" hint="Перечислите через запятую этапы, которые не нужны для простых задач." value={settings.skip_stages_for_low.join(", ")} onChange={(value) => set("skip_stages_for_low", splitList(value))}/>
      <TextField wide label="Остановленные процессы" hint="Перечислите через запятую процессы, которые пилот не должен продолжать." value={settings.stopped_pipelines.join(", ")} onChange={(value) => set("stopped_pipelines", splitList(value))}/>
    </SettingsSection>

    <SettingsSection id="settings-budgets" title="Автоматизация и бюджеты">
      <Check label="Автоматически сливать изменения" hint="Разрешает слияние успешно проверенных изменений без участия владельца." checked={settings.auto_merge} onChange={(value) => set("auto_merge", value)}/><Check label="Автоматически отвечать" hint="Разрешает пилоту самостоятельно отвечать на операционные вопросы." checked={settings.auto_answer} onChange={(value) => set("auto_answer", value)}/>
      <NumberField label="Дневной лимит, USD" hint="Максимальные суммарные расходы пилота за день." value={settings.day_cap_usd} onChange={(value) => set("day_cap_usd", value)}/>
      {tiers.map((tier) => <NumberField key={`factor-${tier}`} label={`Коэффициент сложности: ${tierNames[tier]}`} hint="Множитель базовой стоимости для задач этой сложности." value={settings.complexity_factor[tier]} onChange={(value) => set("complexity_factor", {...settings.complexity_factor, [tier]:value})}/>) }
      {tiers.map((tier) => <NumberField key={`cap-${tier}`} label={`Лимит работы (${tierNames[tier]}), USD`} hint="Максимальная стоимость одной задачи этой сложности." value={settings.work_cap_usd[tier]} onChange={(value) => set("work_cap_usd", {...settings.work_cap_usd, [tier]:value})}/>) }
      {settings.stages.map((row) => <NumberField key={row.workflow} label={`Базовая стоимость «${row.workflow}», USD`} hint="Стоимость этапа до применения коэффициента сложности." value={settings.stage_base_usd[row.workflow] ?? 0} onChange={(value) => set("stage_base_usd", {...settings.stage_base_usd, [row.workflow]:value})}/>) }
      <TextField label="Команда публикации на стенд" hint="Команда, которая публикует результат в тестовое окружение." value={settings.deploy_staging_cmd} onChange={(value) => set("deploy_staging_cmd", value)}/>
      <TextField label="Команда автовыпуска Factory" hint="Серверная allowlisted-команда, которая выпускает саму Factory после merge её репозитория." value={settings.deploy_factory_cmd} onChange={(value) => set("deploy_factory_cmd", value)}/>
    </SettingsSection>

    <SettingsSection id="settings-notifications" title="Уведомления и ссылки владельца">
      <div className="settings-full"><p className="settings-field-title">Уведомления на телефон</p><small className="field-hint">Выберите, о каких событиях присылать уведомления.</small>{notificationGroups.map((group)=><Check key={group.key} label={group.label} hint={group.hint} checked={settings.notify_groups?.[group.key]??group.defaultEnabled} onChange={(value)=>set("notify_groups",{...settings.notify_groups,[group.key]:value})}/>)}</div>
      <TextField label="Сервер ntfy" hint="Адрес сервера, через который Factory отправляет уведомления." value={settings.ntfy_server} onChange={(value) => set("ntfy_server", value)}/><TextField label="Тема ntfy" hint="Тема общих уведомлений Factory на сервере ntfy." value={settings.ntfy_topic} onChange={(value) => set("ntfy_topic", value)}/><TextField label="Тема владельца в ntfy" hint="Отдельная тема для уведомлений, требующих внимания владельца." value={settings.ntfy_owner_topic} onChange={(value) => set("ntfy_owner_topic", value)}/><TextField label="Ссылка на чат владельца" hint="Адрес чата, куда можно направить владельца для ответа." value={settings.owner_chat_url} onChange={(value) => set("owner_chat_url", value)}/><TextField label="Ссылка на интерфейс владельца" hint="Адрес интерфейса, в котором владелец управляет Factory." value={settings.owner_ui_url} onChange={(value) => set("owner_ui_url", value)}/>
    </SettingsSection>

    <SettingsSection id="settings-models" title="Цепочка моделей" wide>
      <div className="settings-full brain-list">{settings.brain_chain.map((brain, index) => <div className="brain-row" key={index}><TextField label="Команда CLI" hint="Команда для запуска этого агента." value={brain.cli} onChange={(value) => updateBrain(index,"cli",value)}/><TextField label="Модель" hint="Имя модели, передаваемое агенту." value={brain.model} onChange={(value) => updateBrain(index,"model",value)}/><TextField label="Провайдер" hint="Поставщик модели для учёта и маршрутизации." value={brain.provider} onChange={(value) => updateBrain(index,"provider",value)}/><TextField label="Примечание" hint="Необязательное пояснение о роли модели в цепочке." value={brain.note ?? ""} onChange={(value) => updateBrain(index,"note",value)}/><div className="brain-actions"><button aria-label="Поднять" disabled={index===0} onClick={() => moveBrain(index,-1)}><ArrowUp size={15}/></button><button aria-label="Опустить" disabled={index===settings.brain_chain.length-1} onClick={() => moveBrain(index,1)}><ArrowDown size={15}/></button><button aria-label="Удалить модель" disabled={settings.brain_chain.length===1} onClick={() => set("brain_chain",settings.brain_chain.filter((_,i)=>i!==index))}><Trash2 size={15}/></button></div></div>)}</div>
      <button className="button settings-full" onClick={() => set("brain_chain", [...settings.brain_chain,{cli:"",model:"",provider:"",note:""}])}><Plus size={15}/> Добавить модель</button>
    </SettingsSection>
    <SettingsSection id="settings-sources" title="Источники данных о продуктах" wide>
      <div className="settings-full brain-list">{(settings.project_providers ?? []).map((provider,index)=><div className="brain-row" key={index}><TextField label="Репозиторий продукта" hint="Точный remote identity зарегистрированного репозитория." value={provider.remote_identity} onChange={(value)=>updateProjectProvider(index,"remote_identity",value)}/><label className="field"><span>Тип источника</span><select aria-label="Тип источника" value={provider.type} onChange={(event)=>updateProjectProvider(index,"type",event.target.value as "trade"|"factory")}><option value="trade">Торговая система</option><option value="factory">Factory</option></select><small className="field-hint">Только реализованные на сервере read-only источники; команды вводить нельзя.</small></label><div className="brain-actions"><button aria-label="Удалить источник продукта" onClick={()=>set("project_providers",(settings.project_providers??[]).filter((_,i)=>i!==index))}><Trash2 size={15}/></button></div></div>)}</div>
      <button className="button settings-full" onClick={()=>set("project_providers",[...(settings.project_providers??[]),{remote_identity:"",type:"factory"}])}><Plus size={15}/> Добавить источник продукта</button>
    </SettingsSection>
    <SettingsSection id="settings-note" title="Заметка о конфигурации"><label className="field settings-full"><span>Заметка о конфигурации</span><textarea aria-label="Заметка о конфигурации" value={settings._note ?? ""} onChange={(event)=>set("_note",event.target.value)} rows={3}/><small className="field-hint">Свободный комментарий для владельца: зачем и когда менялись настройки.</small></label></SettingsSection>
    {errors.length > 0 && <div className="settings-errors">{errors.map((error) => <span key={error}>{error}</span>)}</div>}
    <div className="settings-save"><button className="button button-primary" disabled={errors.length>0 || save.isPending} onClick={() => save.mutate()}><Save size={16}/>{save.isPending ? "Сохраняем…" : "Сохранить настройки"}</button></div>
  </div>;

  function updateBrain(index:number,key:"cli"|"model"|"provider"|"note",value:string) { const next=settings!.brain_chain.map((entry,i)=>i===index?{...entry,[key]:value}:entry); set("brain_chain",next); }
  function updateProjectProvider(index:number,key:"remote_identity"|"type",value:string) { const next=(settings!.project_providers??[]).map((entry,i)=>i===index?{...entry,[key]:value}:entry) as PilotSettings["project_providers"]; set("project_providers",next); }
  function moveBrain(index:number,delta:number) { const next=[...settings!.brain_chain]; [next[index],next[index+delta]]=[next[index+delta],next[index]]; set("brain_chain",next); }
}

function SettingsSection({id,title,children,wide=false}:{id:string;title:string;children:ReactNode;wide?:boolean}) { return <section id={id} className={`panel settings-section ${wide?"settings-wide":""}`}><h2>{title}</h2><div className="settings-grid">{children}</div></section>; }
function Check({label,hint,checked,onChange}:{label:string;hint:string;checked:boolean;onChange:(value:boolean)=>void}) { return <label className="settings-check"><input aria-label={label} type="checkbox" checked={checked} onChange={(event)=>onChange(event.target.checked)}/><span><span className="settings-field-title">{label}</span><small className="field-hint">{hint}</small></span></label>; }
function TextField({label,hint,value,onChange,wide=false}:{label:string;hint:string;value:string;onChange:(value:string)=>void;wide?:boolean}) { return <label className={`field ${wide?"settings-full":""}`}><span>{label}</span><input aria-label={label} value={value} onChange={(event)=>onChange(event.target.value)}/><small className="field-hint">{hint}</small></label>; }
function NumberField({label,hint,value,onChange}:{label:string;hint:string;value:number;onChange:(value:number)=>void}) { return <label className="field"><span>{label}</span><input aria-label={label} type="number" step="any" value={value} onChange={(event)=>onChange(Number(event.target.value))}/><small className="field-hint">{hint}</small></label>; }
function splitList(value:string) { return value.split(",").map((item)=>item.trim()).filter(Boolean); }
function validate(settings:PilotSettings) { const errors:string[]=[]; const numbers=[settings.poll_seconds,settings.timeout_seconds,settings.max_stage_attempts,settings.max_parallel_subtasks,settings.max_parallel_works,settings.day_cap_usd,...Object.values(settings.stage_base_usd),...Object.values(settings.complexity_factor),...Object.values(settings.work_cap_usd)]; if(numbers.some((value)=>!Number.isFinite(value)||value<=0)) errors.push("Все длительности, лимиты, коэффициенты и бюджеты должны быть положительными."); for(const [label,value] of [["Сервер ntfy",settings.ntfy_server],["Ссылка на чат владельца",settings.owner_chat_url],["Ссылка на интерфейс владельца",settings.owner_ui_url]]) { try { const url=new URL(value); if(!["http:","https:"].includes(url.protocol)) throw new Error(); } catch { errors.push(`${label}: укажите корректный адрес http(s).`); } } if(settings.brain_chain.some((entry)=>!entry.cli.trim()||!entry.model.trim()||!entry.provider.trim())) errors.push("В каждой строке цепочки нужны CLI, модель и провайдер."); if(!settings.allow_any_worker && settings.stages.some((row)=>tiers.some((tier)=>!settings.allowed_workers.includes(row.workers[tier])))) errors.push("Каждый назначенный исполнитель должен быть в разрешённом списке, пока исполнители вне списка запрещены."); return errors; }
function ErrorMessage({error,conflictAction}:{error:unknown;conflictAction?:()=>void}) { const conflict=error instanceof APIError&&error.status===409; return <div className="settings-errors"><span>{error instanceof Error?error.message:"Не удалось загрузить настройки."}</span>{conflict&&conflictAction&&<button className="button" onClick={conflictAction}>Загрузить свежие настройки</button>}</div>; }
