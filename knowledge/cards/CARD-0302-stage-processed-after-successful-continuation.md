Implementation commit: будет указан этапом Implement после создания продуктового изменения; на этапе Specification такого коммита намеренно нет

# CARD-0302: обработка этапа только после успешного continuation

## HEAD

Status: Specified
Branch: `factory/3f933e27-656-610e1dce-c4b`
Specification: `knowledge/specs/stage-processed-after-successful-continuation.md`
Implementation commit: ожидается в реализации; эта поставка содержит только
спецификацию и карточку по правилам этапа Specification.

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
