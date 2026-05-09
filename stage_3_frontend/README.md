# Точка запятая — Симулятор расписания смен (frontend)

Интерактивный симулятор для демонстрации расписания смен ресторана:
схема ресторана, динамика сотрудников по часам, индикация покрытия,
техническая сводка и метрики качества.

## Запуск

```bash
npm install
npm run dev
```

Откройте `http://localhost:5173`.

## Где данные

Frontend читает JSON из `public/data/`:

- `public/data/timeline.json`
- `public/data/validation_report.json`
- `public/data/employee_summary.json`

Если файлов нет — используются mock-данные из `src/data/`.

Чтобы подключить реальное расписание из Python-пайплайна, положите
сгенерированные JSON в `public/data/` с теми же именами.
