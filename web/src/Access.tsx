import { Check, Copy, Gauge, KeyRound, Loader2, Lock, Power, PowerOff, ShieldAlert, ShieldCheck, Terminal } from "lucide-react";
import { useEffect, useState } from "react";
import { SpeakButton } from "./Speak";

type Limit = { state?: string; resets_at?: string; detected_at?: string; evidence?: string; manual_off?: boolean };

type Scope = {
  key: string; title: string; description: string;
  enabled: boolean; ui_toggleable: boolean; updated_at?: string; note?: string;
  grant_command?: string; revoke_command?: string;
  grant_command_alt?: string; revoke_command_alt?: string;
};

/** Рубильники доступа фабрики к серверу. Верхний потолок: что здесь выключено,
 *  того не получит ни один агент, что бы он себе ни напридумывал. */
export function AccessView() {
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [busy, setBusy] = useState<string>("");
  const [err, setErr] = useState("");
  const [shown, setShown] = useState<string>("");
  const [limits, setLimits] = useState<Record<string, Limit>>({});
  const [copied, setCopied] = useState("");

  const load = async () => {
    try {
      const r = await fetch("/api/v1/access");
      if (!r.ok) throw new Error(`access ${r.status}`);
      setScopes(((await r.json()) as { scopes?: Scope[] }).scopes ?? []);
      setErr("");
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => { void load(); }, []);

  useEffect(() => {
    let alive = true;
    const pull = async () => {
      try {
        const r = await fetch("/api/v1/limits");
        if (!r.ok) return;
        const d = (await r.json()) as { limits?: Record<string, Limit> };
        if (alive) setLimits(d.limits ?? {});
      } catch { /* ignore */ }
    };
    void pull();
    const h = window.setInterval(() => void pull(), 30000);
    return () => { alive = false; window.clearInterval(h); };
  }, []);

  const toggleProvider = async (p: string, currentlyOff: boolean) => {
    setBusy(`prov:${p}`);
    try {
      await fetch(`/api/v1/limits/${p}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: currentlyOff }),
      });
      const r = await fetch("/api/v1/limits");
      if (r.ok) setLimits(((await r.json()) as { limits?: Record<string, Limit> }).limits ?? {});
    } finally {
      setBusy("");
    }
  };

  const toggle = async (s: Scope) => {
    setBusy(s.key);
    try {
      const r = await fetch(`/api/v1/access/${s.key}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !s.enabled }),
      });
      if (!r.ok) setErr((await r.json())?.error?.message ?? `не удалось (${r.status})`);
      await load();
    } finally {
      setBusy("");
    }
  };

  const spoken =
    "Доступы фабрики. " +
    scopes.map((s) => `${s.title}: ${s.enabled ? "включён" : "выключен"}`).join(". ");

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
        <KeyRound size={20} color="#e0cf9f" />
        <h1 style={{ margin: 0, fontSize: 22 }}>Доступы</h1>
        <SpeakButton text={spoken} label="Вслух" />
      </div>
      <p style={{ margin: "0 0 18px", color: "var(--text-muted, #8a94a6)", fontSize: 14, maxWidth: 760 }}>
        Это потолок для всей фабрики. Что здесь выключено — того не получит ни один агент.
        Отдельная задача может попросить доступ, но выше этого потолка не поднимется.
      </p>

      {err && (
        <div className="panel" style={{ borderColor: "#5a2b2b", marginBottom: 14 }}>
          <ShieldAlert size={14} color="#ffb4b4" /> {err}
        </div>
      )}

      <section className="panel" style={{ marginBottom: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Gauge size={16} color="#8ec5ff" />
          <strong>Лимиты подписок</strong>
        </div>
        {["claude", "codex"].map((p) => {
          const l = limits[p] ?? {};
          const off = !!l.manual_off;
          const blocked = l.state === "exhausted" || l.state === "throttled";
          const label = off ? "выключен вручную" : blocked ? "лимит исчерпан" : "свободна";
          const bad = off || blocked;
          return (
            <div key={p} style={{ display: "flex", gap: 10, alignItems: "center", padding: "7px 0", flexWrap: "wrap" }}>
              <span style={{ minWidth: 74, fontWeight: 600 }}>{p === "claude" ? "Claude" : "Codex"}</span>
              <span style={{
                fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
                background: bad ? "#3b1d1d" : "#16341f",
                color: bad ? "#ffb4b4" : "#7ee2a8",
              }}>{label}</span>
              {blocked && !off && (
                <span style={{ fontSize: 12.5, color: "var(--text-muted, #8a94a6)" }}>
                  {l.resets_at ? `восстановится ${l.resets_at}` : "проверю снова через час"}
                </span>
              )}
              <span style={{ flex: 1 }} />
              <button
                className="button"
                style={{ fontSize: 12, padding: "2px 12px", minWidth: 104 }}
                disabled={busy === `prov:${p}`}
                onClick={() => void toggleProvider(p, off)}
              >
                {busy === `prov:${p}` ? <Loader2 size={13} className="spin" />
                  : off ? <><Power size={13} /> Включить</> : <><PowerOff size={13} /> Выключить</>}
              </button>
            </div>
          );
        })}
        <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--text-muted, #8a94a6)" }}>
          Когда подписка упирается в лимит, пилот перестаёт отдавать ей работу и переводит
          задачи на второго провайдера. Если заняты оба — ждёт и не жжёт попытки впустую.
          Кнопкой можно выключить провайдера и вручную: тогда он не получит работу вообще,
          пока не включишь обратно.
        </p>
      </section>

      {scopes.map((s) => (
        <section key={s.key} className="panel" style={{
          marginBottom: 12,
          borderColor: s.enabled ? "#2f5741" : "var(--border, #262c38)",
        }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
            {s.enabled ? <ShieldCheck size={18} color="#7ee2a8" /> : <Lock size={18} color="#8a94a6" />}
            <div style={{ flex: 1, minWidth: 240 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <strong style={{ fontSize: 15 }}>{s.title}</strong>
                <span style={{
                  fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
                  background: s.enabled ? "#16341f" : "#22262f",
                  color: s.enabled ? "#7ee2a8" : "#8a94a6",
                }}>
                  {s.enabled ? "открыт" : "закрыт"}
                </span>
              </div>
              <p style={{ margin: "6px 0 0", fontSize: 13, lineHeight: 1.5, color: "var(--text-muted, #8a94a6)" }}>
                {s.description}
              </p>
              {s.updated_at && (
                <p style={{ margin: "4px 0 0", fontSize: 12, color: "#4d5a6b" }}>
                  изменено: {new Date(s.updated_at).toLocaleString("ru-RU")}
                </p>
              )}
            </div>
            <button
              className="button"
              disabled={busy === s.key}
              onClick={() => (s.ui_toggleable ? void toggle(s) : setShown(shown === s.key ? "" : s.key))}
              title={s.ui_toggleable ? "" : "Показать команду для сервера"}
              style={{ minWidth: 148, borderColor: s.enabled ? "#2f5741" : undefined }}
            >
              {busy === s.key ? <Loader2 size={14} className="spin" />
                : s.ui_toggleable ? (s.enabled ? "Закрыть" : "Открыть")
                : (shown === s.key ? "Скрыть команду" : <><Terminal size={13} /> Как включить</>)}
            </button>
          </div>

          {!s.ui_toggleable && shown === s.key && (
            <div style={{ marginTop: 12, borderTop: "1px solid var(--border, #262c38)", paddingTop: 12 }}>
              <p style={{ margin: "0 0 8px", fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>
                Этот доступ намеренно нельзя открыть отсюда: сервер Factory и агенты работают
                под одним пользователем, поэтому веб-кнопку смог бы нажать и агент. Открывается
                только руками на сервере, от root:
              </p>
              {[
                { label: "включить — с твоего компьютера (ключ root уже там есть)", cmd: s.grant_command ?? "" },
                { label: "включить — с любой машины, где ты заходишь под собой", cmd: s.grant_command_alt ?? "" },
                { label: "выключить обратно", cmd: s.revoke_command ?? "" },
                { label: "выключить обратно — под своим пользователем", cmd: s.revoke_command_alt ?? "" },
              ].filter((x) => x.cmd).map((x) => (
                <div key={x.label} style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, color: "#4d5a6b", marginBottom: 3 }}>{x.label}:</div>
                  <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
                    <code
                      style={{
                        flex: 1, background: "var(--surface-2, #0f131a)", padding: "8px 10px",
                        borderRadius: 6, fontSize: 12.5, wordBreak: "break-all",
                        border: "1px solid var(--border, #262c38)",
                      }}
                    >{x.cmd}</code>
                    <button
                      className="button"
                      style={{ fontSize: 12, padding: "2px 10px", whiteSpace: "nowrap" }}
                      onClick={() => {
                        void navigator.clipboard?.writeText(x.cmd);
                        setCopied(x.cmd);
                        window.setTimeout(() => setCopied(""), 2000);
                      }}
                    >
                      {copied === x.cmd ? <><Check size={13} /> скопировано</> : <><Copy size={13} /> копировать</>}
                    </button>
                  </div>
                </div>
              ))}
              <p style={{ margin: "8px 0 0", fontSize: 12, color: "#4d5a6b" }}>
                Действует сразу, перезапускать ничего не нужно. Изменение попадёт в журнал
                и пришлёт тебе пуш — чтобы такое никогда не прошло незаметно.
                Посмотреть текущее состояние: <code>ssh root@212.28.186.194 'fx-policy list'</code>
              </p>
            </div>
          )}
        </section>
      ))}

      <p style={{ marginTop: 18, fontSize: 12.5, lineHeight: 1.6, color: "var(--text-muted, #8a94a6)", maxWidth: 760 }}>
        Как это работает на сервере: агент не получает прав напрямую. Всё идёт через
        одну команду-посредника, которая принадлежит root и которую агент не может
        переписать. У неё фиксированный список операций — посмотреть статус, почитать
        логи, перезапустить сервисы staging, накатить миграции, собрать статику.
        Каждый вызов пишется в журнал с указанием, какая задача его сделала.
      </p>
    </div>
  );
}
