# CARD-0054 — Карточка подтверждает реализацию стабильным коммитом

- Implementation commit: `6727f746efc2e42d1c496bcd786a5a85949c1336` — Pilot и живые
  ревизии Review/Verify проверяют коммит кода до финальной записи карточки.
- What changed: требование равенства `Head commit` текущему `git HEAD` заменено
  на проверяемый коммит реализации; следующий документационный коммит больше не
  запускает ложный круг Review.

## Проверка

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Реальная реализация принимается после отдельной карточки | регрессия `test_card_commit_gate_accepts_code_commit_before_final_card_commit` | PASS |
| Старый `Head commit: git HEAD` и выдуманный/документационный SHA отклоняются | регрессии `test_card_commit_gate_rejects_*` | PASS |
| Активные Review/Verify получают новую ревизию | `TestKnowledgeCardImplementationCommitMigrationRevisesLiveReviewAndVerify` | PASS |
| Полные проверки | `python3 -m unittest pilot.test_pilot`, `go test -timeout 5m ./...`, `just build` | PASS |
