# HW9 — вибір локального судді

Перевірено на `qwen2.5:7b` станом на 2026-11-03.
Повне калібрування: 25/30, Wilson 0.664–0.927, самоузгодженість 30/30.
Рішення — перехід з умовами, не безумовна заміна хмарного контролю.

## Матеріали

- [Рекомендація](./model-selection-recommendation.md).
- [Хмарна заява L09](./judge-trust-statement.md) і
  [локальна заява](./judge-trust-statement.local.md).
- [Конфігурація без ключів](./judge.local.env).
- [Узагальнений шаблон](./model-selection-recommendation.template.md).
- [Рядок вартості L08](./cost-model.md).
- [Звіти](./evals/reports/) і [журнал виконання](./hw9.md).

## Відтворення

Потрібні Docker Compose та Ollama на хості з установленою `qwen2.5:7b`.
Калібратор оцінює записані відповіді; агента й хмарного провайдера не викликає.
Запустіть із кореня репозиторію:

```sh
cd evals
docker compose --env-file ../judge.local.env run --rm \
  -e JUDGE_MODEL=ollama:qwen2.5:7b \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e JUDGE_FORMAT=schema -e TEMP=0 -e RUNS=5 \
  -e CALIBRATION_SINGLE_CALL=1 \
  --entrypoint python eval tools/calibrate_run.py l09_labels
```

Звіт з'явиться в `evals/reports/`. Один виклик зі схемою на повтор,
без повторних викликів для виправлення JSON. `.env` не потрібний і не включений.
Повторне калібрування на чистому клоні вихідного коміту `a930e11`
підтверджено [звітом](./evals/reports/calibration-l09_labels-20261103T183241.json);
У перенесеній структурі HW9 усі 4 тести пройшли 2026-11-03.
Повне калібрування саме з цієї структури окремо не запускали.

Тести без викликів моделі, з папки `evals`:

```sh
docker compose run --rm --entrypoint python eval -m unittest test_judge -v
```

Код релізного ранера має іншу політику розбору та повторів, ніж калібратор.
Підтвердження однакового режиму гейта — умова переходу, не виконаний факт.
Зміна тегу/дайджесту, режиму, рубрики чи промптів потребує перекалібрування.
