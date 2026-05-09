import { CalendarX } from "lucide-react";

interface EmptyStateProps {
  onReset: () => void;
}

export function EmptyState({ onReset }: EmptyStateProps) {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6">
      <div className="card max-w-xl w-full p-8 text-center">
        <div className="mx-auto h-14 w-14 rounded-2xl bg-brand-orange-soft text-brand-orange-deep flex items-center justify-center mb-4">
          <CalendarX className="h-6 w-6" />
        </div>
        <h2 className="text-xl font-semibold text-graphite-900 mb-2">
          Расписание для этой недели пока недоступно
        </h2>
        <p className="text-graphite-500">
          Строгий режим не нашёл валидное расписание для текущих данных.
          Попробуйте загрузить другую неделю или обновить входные данные.
        </p>
        <div className="mt-6">
          <button type="button" onClick={onReset} className="btn-ghost">
            Вернуться на главный экран
          </button>
        </div>
      </div>
    </div>
  );
}
