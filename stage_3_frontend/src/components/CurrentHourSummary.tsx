import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { statusBg, statusLabel } from "../lib/coverageStatus";
import {
  STATION_NAMES,
  type EmployeeAtSlot,
  type HourSlot,
  type StationKey,
} from "../lib/types";

interface CurrentHourSummaryProps {
  hour: HourSlot | null;
  onEmployeeClick: (e: EmployeeAtSlot) => void;
}

export function CurrentHourSummary({
  hour,
  onEmployeeClick,
}: CurrentHourSummaryProps) {
  if (!hour) {
    return (
      <div className="card p-5">
        <div className="text-sm text-graphite-500">Нет данных по часу</div>
      </div>
    );
  }

  return (
    <div className="card p-0 overflow-hidden">
      <div className="px-5 py-4 border-b border-graphite-100 flex items-center justify-between">
        <div>
          <div className="text-[11px] uppercase font-semibold tracking-wide text-graphite-400">
            Техническая сводка
          </div>
          <div className="text-base font-semibold text-graphite-900">
            Покрытие по станциям в текущий час
          </div>
        </div>
      </div>
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-graphite-400 bg-graphite-50">
              <th className="px-4 py-2.5 font-semibold">Станция</th>
              <th className="px-3 py-2.5 font-semibold text-right">Треб.</th>
              <th className="px-3 py-2.5 font-semibold text-right">Назн.</th>
              <th className="px-3 py-2.5 font-semibold text-right">Разница</th>
              <th className="px-3 py-2.5 font-semibold text-right">Лишние</th>
              <th className="px-3 py-2.5 font-semibold">Статус</th>
              <th className="px-3 py-2.5 font-semibold">Сотрудники</th>
              <th className="px-3 py-2.5 font-semibold">Сообщение</th>
            </tr>
          </thead>
          <tbody>
            {hour.stations.map((st) => {
              const status = st.status ?? "no_data";
              const required = st.required ?? 0;
              const assigned = st.assigned ?? 0;
              const diff = assigned - required;
              const extra = Math.max(0, diff);
              const stName =
                st.station_name ??
                STATION_NAMES[st.station_key as StationKey] ??
                String(st.station_key);
              const okMsg =
                status === "exact"
                  ? "Покрытие выполнено"
                  : status === "overstaffed_ok"
                    ? "ОК"
                    : null;
              return (
                <tr
                  key={String(st.station_key)}
                  className="border-t border-graphite-100"
                >
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-graphite-400 w-9">
                        {String(st.station_key)}
                      </span>
                      <span className="font-medium text-graphite-800">
                        {stName}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {required}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-graphite-900">
                    {assigned}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    <span
                      className={
                        diff > 0
                          ? "text-brand-orange-deep font-semibold"
                          : diff < 0
                            ? "text-brand-orange-deep font-semibold"
                            : "text-brand-forest font-semibold"
                      }
                    >
                      {diff > 0 ? `+${diff}` : diff}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {extra}
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`pill border whitespace-nowrap ${statusBg(status)}`}
                    >
                      {statusLabel(status)}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1.5">
                      {st.employees.length === 0 ? (
                        <span className="text-graphite-400">—</span>
                      ) : (
                        st.employees.map((e) => (
                          <button
                            type="button"
                            key={`${e.employee_id}-${e.shift_start}`}
                            onClick={() => onEmployeeClick(e)}
                            className="px-1.5 py-0.5 rounded-md text-[11px] font-semibold bg-graphite-100 text-graphite-700 hover:bg-graphite-200 transition"
                            title={`Смена ${e.shift_start}:00 – ${e.shift_end}:00`}
                          >
                            #{e.employee_id}
                          </button>
                        ))
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    {st.warnings && st.warnings.length > 0 ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {st.warnings.map((w, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center gap-1 text-brand-orange-deep text-xs font-medium"
                          >
                            <AlertTriangle className="h-3.5 w-3.5" />
                            {w}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-brand-forest text-xs font-medium">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {okMsg ?? "ОК"}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
