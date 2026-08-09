# CARD-0043 — Блок продукта на обзоре для каждого проекта

## HEAD

- Status: Implemented — целевые проверки и сборка зелёные.
- Branch: `factory/485cc076-09a-d2c70818-ea0`.
- Head commit: `3f1618d`.
- Specification: `knowledge/specs/overview-project-products.md`.
- What changed: снимок и «Обзор» показывают каждый включённый проект в порядке
  каталога; `trade` и `factory` — единственные фиксированные read-only провайдеры.
- Evidence: 68 Python + 18 UI tests + `PilotConfig` Go tests → PASS;
  production web build → PASS; три живых read-only источника → available/healthy.
- One next action: провести этап Verify и опубликовать результат на staging.

## LOG

### 2026-08-09 — Specification

Владелец подтвердил источник правды: проекты — только включённые зарегистрированные
репозитории в порядке API; сведения о релизах и стендах поставляет явный серверный
провайдер проекта. Для торговой системы остаётся существующий провайдер, для
Фабрики используются `fx factory release-info` и `fx factory health`; проекты без
провайдера остаются видимыми с честным состоянием отсутствующих сведений.

### 2026-08-09 — Implement

Снимок переведён с одного `release` на упорядоченный массив `projects`, настройки
ограничены типами `trade` и `factory` без команд из UI. Ошибка источника не
объявляется отказом стенда. Прошли 68 Python-тестов, 18 UI-тестов, целевые
Go-тесты и production-сборка; живые staging, prod и factory прочитаны успешно.
