Implementation commit: 99701704b37e8740db3fdbe38c0193917570da5c — исходная реализация worker и lifecycle-теста, для которого специфицировано устранение SA4000

# CARD-0119: staticcheck для attempt lifecycle

Статус: specification

Проблема: обязательный `just staticcheck` падает на самосравнении в
`internal/worker/attempt_lifecycle_test.go:31`, хотя это старый тест вне
предыдущего diff.

Решение: в отдельном implementation commit исправить только assertion
стабильности задержки, сохранив проверку детерминированности lease-renewal.
После него карточку закрыть документационным commit.

Проверки: целевой `go test ./internal/worker -run 'TestLeaseRenewal'` и
`just staticcheck`. `just test-browser` требует разрешённого Chromium и в
текущем контейнере заблокирован политикой; это отдельная инфраструктурная
находка, не критерий приёмки этого исправления.

Связанный документ: `knowledge/specs/staticcheck-attempt-lifecycle.md`.
