Implementation commit: будет указан этапом Implement после создания продуктового изменения; на этапе Specification такого коммита намеренно нет

# CARD-0302: обработка этапа только после успешного continuation

## HEAD

Status: Implemented
Branch: `factory/9ef315c8-044-4b5eeab2-187`
Specification: `knowledge/specs/stage-processed-after-successful-continuation.md`
Implementation commit: 2a0cd84bf94fc689915c9f412f49f4711d778498 — terminal task
помечается обработанным только после валидного ID созданного продолжения.
What changed: ранняя запись `processed` перенесена в подтверждённый handoff;
некорректный ответ и ожидания остаются повторяемыми, а остановка и дедупликация
сохраняют явный terminal outcome.
Evidence: `python3 -m unittest -v` (6 целевых AdaptivePollingTests) → OK;
`git diff --check` → OK.
Next action: Review проверяет все terminal outcomes и отсутствие регрессий.

## LOG

### 2026-08-15 — Specification

Подтверждён дефект cursor-а: `pilot.cycle()` добавляет terminal task в
`state["processed"]` до выбора worker, machine-gates и
`create_child_task()`. Основной handoff создаётся в конце ветви, а обработчик
исключения уже умеет снять отметку через `retry_terminal_task()`, что не
закрывает ранние `continue` и неполный успешный ответ.

Спецификация закрепляет перенос отметки на подтверждённый child с валидным ID,
повтор при ошибке/ожидании и сохранение request-key дедупликации. Намеренные
`CLOSE`/`DUPLICATE` выделены как terminal outcomes, которые реализация должна
явно подтвердить тестами, а не наследовать от прежней ранней отметки.

Карточка создана по пути из handoff текущей работы; чужие карточки не менялись.

Обязательная проверка уточнена до отдельного регрессионного теста: реализация
должна доказать, что исходный этап попадает в `processed` только после ответа
с валидным ID созданного продолжения.

### 2026-08-15 — Implement

Ранняя отметка `processed` удалена из terminal loop. Новый узкий helper
подтверждает handoff лишь после непустого ID child; неполный ответ возвращает
источник в retry queue. Явные outcomes остановки и найденного continuation
сохраняют cursor отдельно. Целевые проверки AdaptivePollingTests (6) и
`git diff --check` прошли.
