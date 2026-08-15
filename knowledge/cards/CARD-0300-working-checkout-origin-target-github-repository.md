Implementation commit: 03afbb395aead09040d63be3591fb842ad47a4d3 — worker закрепляет GitHub CLI за репозиторием текущей задачи

# CARD-0300: Рабочий checkout направляет GitHub CLI в origin задачи

## HEAD

Status: Specification ready
Branch: factory/e2f11892-be9-26560007-27d
Specification: `knowledge/specs/working-checkout-origin-target-github-repository.md`
What changes: runtime получает `GH_REPO` исключительно из доверенной GitHub.com
identity claim и тем самым не позволяет `gh` выбрать `upstream`.
Evidence: существующий implementation commit содержит worker-код и целевой
сквозной тест; эта карточка фиксирует его контракт и проверку для текущей
работы.
One next action: выполнить целевой worker-тест из спецификации перед Verify.

## LOG

### 2026-08-15 — Specification

Зафиксирован контракт для наблюдаемого checkout с
`origin=timafen/factory` и `upstream=owainlewis/factory`: runtime должен
экспортировать `GH_REPO=timafen/factory` из repository identity задачи, а не
полагаться на выбор GitHub CLI по remote-ам. Для невалидных и недоверенных
identity переменная удаляется целиком.

`CARD-0300` и этот путь проверены как отсутствующие в свежем `origin/main` и
во всех опубликованных refs `origin`; существующие карточки другой работы не
изменялись.
