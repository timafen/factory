# Перенос патруля Claude в Factory Automations

Патруль конвейера выполняется существующей schedule Automation. Provisioner
принимает идентификатор уже созданной schedule Automation, сохраняет инструкции
патруля в её context и включает её только при доступных Workflow и repository.
Cron и timezone не создаются и не изменяются. Каждое scheduled или Run now
срабатывание остаётся durable Occurrence с диагностикой и связанной Task.

ГОТОВО-КОГДА: файл internal/controlplane/pipeline_patrol.go
ГОТОВО-КОГДА: файл internal/controlplane/pipeline_patrol_test.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_runtime.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_automations_test.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'
