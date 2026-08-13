# CARD-0097 — CPU-изоляция панели, мозга и тяжёлых прогонов

Implementation commit: 74b39f3d0643bfa5cd2e9b03bce729f003e2a0f0 — сформирована проверяемая техническая спецификация CPU-политики и стендовой проверки.

## HEAD

- Status: Specification ready for implementation.
- Specification: `knowledge/specs/cpu-isolation-panel-brain-and-heavy-runs.md`.
- Owner impact: панель Factory и мозг получают предсказуемый приоритет, пока
  workers и release Gate выполняют тяжёлую работу.
- What is defined: четыре соседних slice, утверждённые веса/квоты/nice,
  вычисление квот из online CPU, атомарная доставка/откат и публичное SLO
  dashboard.
- Evidence: спецификация ссылается на фактические `ops/systemd/`,
  `ops/fx-factory-release` и существующий `FACTORY_WORKER_SERVICES`; обязательная
  будущая проверка — `bash ops/test-install-cpu-isolation.sh`.
- One next action: реализовать файлы из списка «ГОТОВО-КОГДА» и провести
  минутный SLO-прогон на staging.

## LOG

### 2026-08-12 — Specification

Владелец утвердил точную политику: panel `CPUWeight=10000` без quota и
`Nice=-5`; brain `CPUWeight=3000`, `CPUQuota=100%`, `Nice=0`; workers —
`CPUWeight=300`, общая quota `N*50%`, `Nice=10`; Gate — `CPUWeight=100`,
общая quota `N*25%`, `Nice=15`. N — число logical CPU. Контракт требует
60 запросов за минуту к публичному dashboard при параллельной тяжёлой нагрузке
workers и Gate: все 200, p95 полного времени не более секунды.

Прошлая triage-ветка `factory/29a78228-1ba-eeb77305-4bb` отсутствовала в
origin на момент Specification. Выводы восстановлены из утверждённого ответа
владельца и свежего `main`; чужая ветка не checkout’илась и не была заменена
локальным предположением.
