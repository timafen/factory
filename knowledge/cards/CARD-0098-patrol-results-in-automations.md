# CARD-0098: находки патрулей в Automations

Implementation commit: e43462307fcd7c25003eecfe693fd21a9dfe8ba7 — базовый код Work и Automations до реализации этого этапа

## Контекст

Патрульные задачи сейчас попадают в общий API задач и поэтому отображаются в Work как обычная работа. Детали Automation уже содержат occurrence, состояние, diagnostic и связанную задачу, но это поведение нужно закрепить спецификацией и регрессиями.

## Объём

Исключить только `workClassPatrol` из всех списков Work с корректной пагинацией; сохранить остальные типы задач. В Runs Automation detail явно показывать finding/diagnostic, конечное состояние и связанную задачу, если она существует, включая reload и pagination.

## Проверка

Целевая проверка: `cd web && npm test -- --run src/Work.test.ts src/Automations.test.tsx`.
