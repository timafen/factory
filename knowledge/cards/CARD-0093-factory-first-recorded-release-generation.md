# CARD-0093 — Первое записанное поколение выпуска Factory

Implementation commit: d3873a8262288e8249e9e3dcc3ebfea86ef06326 — первый выпуск
проверяет исходную точку, записывает полный bootstrap-комплект и отказывается
от небезопасной истории до сборки или остановки служб.

## HEAD

- Status: Specified — готово к реализации по зафиксированному контракту.
- What is requested: fail-closed bootstrap первого recorded release и
  проверяемое доказательство корректности.
- Owner decision: не менять `factory-current.json`, не выполнять живой выпуск
  и не создавать поколения вручную, пока не подтверждена исходная точка.
- Implementation scope: `ops/fx-factory-release`,
  `ops/test-fx-factory-release.sh`.
- Required evidence: `bash ops/test-fx-factory-release.sh` завершается с кодом
  0, проверяет bootstrap в `previous` и отказы для `0644`, отсутствующего
  `release_id` и частичной истории.

## LOG

### 2026-08-14 — Specification

Зафиксирован контракт первого записанного поколения: только пустая история с
полным проверенным комплектом может породить bootstrap; любая неоднозначность
останавливает выпуск до мутаций. Полный план:
`knowledge/specs/factory-first-recorded-release-generation.md`.

## Следующее действие

Передать в Implement. До успешной целевой проверки и отдельного решения
владельца не запускать живой выпуск и не править metadata вручную.
