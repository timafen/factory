# CARD-0098 — Общий предел worker-слотов по мощности машины

Implementation commit: 7140b35eeca338079ca28d38b831816943630d4f — `Claim` ограничивает суммарные active lease числом CPU машины

- Status: Implemented and verified.
- Scope: общий бюджет для всех worker одного control plane равен `runtime.NumCPU()`.
- Evidence: именованный regression, `go test ./...`, `go build ./...` и `git diff --check` прошли на кандидатской ветке.
- Review note: CARD-0094 описывает настраиваемый `host_max_concurrent`; это расхождение сохранено как сознательное решение текущей работы.

## Реализация

В атомарном `Claim` считаются непросроченные `preparing` и `running` attempts
всех worker. На машине с 8 CPU первые восемь claim проходят, девятый остаётся
пустым; terminal transition и истечение lease освобождают бюджет.

## Передача

Следующий этап — review и вливание существующей реализации после проверки
целевого regression и diff только по файлам этой работы.
