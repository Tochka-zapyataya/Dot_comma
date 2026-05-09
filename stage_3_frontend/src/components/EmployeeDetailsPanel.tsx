import { AnimatePresence, motion } from "framer-motion";
import { Calendar, Clock, MapPin, X } from "lucide-react";
import { EmployeeAvatar } from "./EmployeeAvatar";
import {
  STATION_NAMES,
  type EmployeeAtSlot,
  type EmployeeSummaryFile,
  type StationKey,
} from "../lib/types";
import { findEmployeeShift, getEmployeeSummary } from "../lib/employee";
import { formatHour, formatRuDate } from "../lib/normalizeTimeline";

interface EmployeeDetailsPanelProps {
  employee: EmployeeAtSlot | null;
  date: string;
  hour: number;
  summary: EmployeeSummaryFile;
  onClose: () => void;
}

export function EmployeeDetailsPanel({
  employee,
  date,
  hour,
  summary,
  onClose,
}: EmployeeDetailsPanelProps) {
  return (
    <AnimatePresence>
      {employee && (
        <>
          <motion.div
            className="fixed inset-0 bg-black/30 z-40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            className="fixed top-0 right-0 z-50 h-full w-full sm:w-[420px] bg-white shadow-2xl border-l border-graphite-100 overflow-y-auto scrollbar-thin"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.25 }}
          >
            <Body
              employee={employee}
              date={date}
              hour={hour}
              summary={summary}
              onClose={onClose}
            />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Body({
  employee,
  date,
  hour,
  summary,
  onClose,
}: {
  employee: EmployeeAtSlot;
  date: string;
  hour: number;
  summary: EmployeeSummaryFile;
  onClose: () => void;
}) {
  const empSummary = getEmployeeSummary(summary, employee.employee_id);
  const currentShift = findEmployeeShift(
    summary,
    employee.employee_id,
    date,
    hour,
  );
  const stName =
    employee.station_name ??
    STATION_NAMES[employee.station_key as StationKey] ??
    String(employee.station_key);

  return (
    <div>
      <div className="px-5 py-4 flex items-center justify-between border-b border-graphite-100">
        <div>
          <div className="text-[11px] uppercase tracking-wide font-semibold text-graphite-400">
            Сотрудник
          </div>
          <div className="text-lg font-semibold text-graphite-900">
            #{employee.employee_id}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="btn-icon"
          aria-label="Закрыть"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="px-5 pt-5 pb-3 flex items-center gap-4">
        <EmployeeAvatar
          employeeId={employee.employee_id}
          size={84}
          showId={false}
        />
        <div className="flex-1">
          <div className="text-[11px] uppercase tracking-wide font-semibold text-graphite-400">
            Сейчас на станции
          </div>
          <div className="text-base font-semibold text-graphite-900">
            {stName}
          </div>
          <div className="text-xs text-graphite-500 mt-0.5">
            {formatRuDate(date)} · {formatHour(hour)}
          </div>
        </div>
      </div>

      {currentShift ? (
        <div className="px-5 pb-3">
          <div className="rounded-xl border border-brand-forest/30 bg-brand-forest-soft p-3 grid grid-cols-3 gap-3">
            <KV
              icon={<Clock className="h-3.5 w-3.5" />}
              label="Смена"
              value={`${formatHour(currentShift.starttime)} – ${formatHour(
                currentShift.finishtime,
              )}`}
            />
            <KV
              icon={<Clock className="h-3.5 w-3.5" />}
              label="Длительность"
              value={`${currentShift.duration} ч`}
            />
            <KV
              icon={<MapPin className="h-3.5 w-3.5" />}
              label="Станция"
              value={String(currentShift.station_key)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <PriorityChip
              label="station_priority"
              value={currentShift.station_priority ?? null}
            />
            <PriorityChip
              label="shift_priority"
              value={currentShift.shift_priority ?? null}
            />
          </div>
        </div>
      ) : (
        <div className="px-5 pb-4">
          <div className="rounded-xl border border-graphite-200 bg-graphite-50 p-3 text-sm text-graphite-600">
            Сейчас не на смене.
          </div>
        </div>
      )}

      <div className="px-5 py-3 border-t border-graphite-100 grid grid-cols-3 gap-3">
        <Stat label="Часы за неделю" value={empSummary?.total_hours ?? "—"} />
        <Stat label="Дней работы" value={empSummary?.working_days ?? "—"} />
        <Stat
          label="Выходных"
          value={
            empSummary?.days_off ??
            (empSummary
              ? Math.max(0, 7 - (empSummary.working_days ?? 0))
              : "—")
          }
        />
      </div>

      <div className="px-5 pb-5">
        <div className="text-[11px] uppercase tracking-wide font-semibold text-graphite-400 mb-2 mt-2 flex items-center gap-2">
          <Calendar className="h-3.5 w-3.5" />
          График на неделю
        </div>
        {empSummary && empSummary.shifts.length > 0 ? (
          <div className="rounded-xl border border-graphite-100 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-graphite-50 text-[11px] uppercase tracking-wide text-graphite-400">
                  <th className="text-left px-3 py-2 font-semibold">Дата</th>
                  <th className="text-left px-3 py-2 font-semibold">Ст.</th>
                  <th className="text-right px-3 py-2 font-semibold">
                    Начало
                  </th>
                  <th className="text-right px-3 py-2 font-semibold">
                    Конец
                  </th>
                  <th className="text-right px-3 py-2 font-semibold">Дл.</th>
                </tr>
              </thead>
              <tbody>
                {empSummary.shifts.map((s, i) => {
                  const isCurrent = s.date === date;
                  return (
                    <tr
                      key={`${s.date}-${i}`}
                      className={`border-t border-graphite-100 ${
                        isCurrent ? "bg-brand-forest-soft" : ""
                      }`}
                    >
                      <td className="px-3 py-2 tabular-nums">
                        {formatRuDate(s.date)}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-[11px] uppercase tracking-wider font-semibold text-graphite-500">
                          {String(s.station_key)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {formatHour(s.starttime)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {formatHour(s.finishtime)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-semibold">
                        {s.duration}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-sm text-graphite-500">Смен на неделю нет.</div>
        )}
      </div>
    </div>
  );
}

function KV({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div>
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide font-semibold text-brand-forest">
        {icon}
        {label}
      </div>
      <div className="text-sm font-semibold text-graphite-900 mt-1">
        {value}
      </div>
    </div>
  );
}

function PriorityChip({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  const v = value ?? null;
  const tone =
    v == null
      ? "bg-graphite-100 text-graphite-500"
      : v === 1
        ? "bg-brand-forest text-white"
        : v === 2
          ? "bg-brand-forest-soft text-brand-forest"
          : v === 3
            ? "bg-brand-orange-soft text-brand-orange-deep"
            : "bg-brand-orange text-white";
  return (
    <div className="rounded-xl border border-graphite-100 bg-white px-3 py-2 flex items-center justify-between">
      <span className="text-[10px] uppercase tracking-wide font-semibold text-graphite-500">
        {label}
      </span>
      <span className={`pill ${tone}`}>{v ?? "—"}</span>
    </div>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-xl border border-graphite-100 bg-white px-3 py-2 text-center">
      <div className="text-[10px] uppercase tracking-wide font-semibold text-graphite-500">
        {label}
      </div>
      <div className="text-base font-semibold text-graphite-900">{value}</div>
    </div>
  );
}
