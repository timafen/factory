Implementation commit: b28bc152cd9968148365b057055907e7319e65ef — отдельная read-only страница `/solutions` со всей историей вопросов.

# CARD-0121 — Страница «Решения» со всеми вопросами

## HEAD

- Status: Implemented — awaiting Review.
- Branch: `factory/1ff8d702-32b-eaa842a1-d1e`.
- Implementation commit: b28bc152cd9968148365b057055907e7319e65ef — отдельная read-only страница `/solutions` со всей историей вопросов.
- What changed: пункт «Решения» открывает отдельный список всех вопросов и сохранённых ответов; действия владельца остались только в очереди «Нужен ответ».
- Evidence: 3 целевых Vitest-файла — 66 passed; typecheck, lint и production build — passed.
- Next action: провести Review нового снимка на свежей базе `main`.

## LOG

### 2026-08-13 — Implement

На свежий `main` перенесены маршрут `/solutions`, пункт меню и read-only история вопросов всех статусов. Целевые тесты подтвердили отдельную навигацию, отображение открытых, отвеченных, решённых, устаревших и неизвестных статусов, а также отсутствие кнопок ответа и мутаций; typecheck, lint и production build завершились успешно.
