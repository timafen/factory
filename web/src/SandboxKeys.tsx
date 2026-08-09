import { KeyRound, Loader2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api";
import type { EbayConsent } from "./types";

const terminal = new Set(["authorized", "failed", "expired"]);

export function SandboxKeys() {
  const [consent, setConsent] = useState<EbayConsent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [manual, setManual] = useState(false);

  useEffect(() => {
    if (!consent || terminal.has(consent.status)) return;
    const timer = window.setInterval(() => {
      void api.ebaySellerConsentStatus(consent.operation_id).then(setConsent).catch(() => {
        setError("Не удалось проверить согласие. Попробуйте обновить состояние.");
      });
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [consent]);

  const start = async () => {
    setBusy(true); setError("");
    try { setConsent(await api.startEbaySellerConsent()); }
    catch { setError("Не удалось начать согласие eBay. Повторите попытку."); }
    finally { setBusy(false); }
  };
  const refresh = async () => {
    if (!consent) return;
    try { setConsent(await api.ebaySellerConsentStatus(consent.operation_id)); }
    catch { setError("Не удалось проверить согласие. Попробуйте ещё раз."); }
  };
  const openConsent = () => { if (consent?.consent_url) window.open(consent.consent_url, "_blank", "noopener,noreferrer"); };

  const pending = consent?.status === "pending";
  return <div>
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}><KeyRound size={20} color="#e0cf9f" /><h1 style={{ margin: 0, fontSize: 22 }}>Ключи песочницы</h1></div>
    <p style={{ color: "var(--text-muted, #8a94a6)", maxWidth: 720 }}>Подключите тестового продавца eBay. После согласия eBay сам вернёт вас на защищённый адрес, а ключи сохранит торговая система.</p>
    <section className="panel" style={{ maxWidth: 720 }}>
      <strong>Продавец eBay</strong>
      {!consent && <p>Ключи ещё не получены.</p>}
      {pending && <p role="status">Ожидаем согласия eBay. Откройте eBay и подтвердите доступ — состояние обновится само.</p>}
      {consent?.status === "authorized" && <p role="status" style={{ color: "#7ee2a8" }}>Ключи получены, продавец привязан.</p>}
      {(consent?.status === "failed" || consent?.status === "expired") && <p role="alert">{consent.message || "Согласие не завершено. Начните заново."}</p>}
      {error && <p role="alert">{error}</p>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {pending && <button className="button button-primary" onClick={openConsent}>Открыть eBay</button>}
        {pending && <button className="button" onClick={() => void refresh()}><RefreshCw size={15} /> Обновить</button>}
        {!pending && <button className="button button-primary" disabled={busy} onClick={() => void start()}>{busy ? <Loader2 className="spin" size={15} /> : "Получить ключи продавца"}</button>}
      </div>
      <button className="link-button" style={{ marginTop: 14 }} onClick={() => setManual(!manual)}>Если не сработало автоматически</button>
      {manual && <p style={{ fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>Ничего не копируйте: обновите состояние после возврата eBay или начните согласие заново.</p>}
    </section>
  </div>;
}
