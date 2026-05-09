import { AnimatePresence, motion } from "framer-motion";
import {
  ChefHat,
  Coffee,
  ShoppingBag,
  Sparkles,
  Users2,
} from "lucide-react";
import {
  STATION_NAMES,
  type EmployeeAtSlot,
  type StationKey,
  type StationSlot,
} from "../lib/types";
import { statusBg, statusLabel, statusToHex } from "../lib/coverageStatus";
import { EmployeeAvatar } from "./EmployeeAvatar";

interface StationZoneProps {
  station: StationSlot;
  big?: boolean;
  onEmployeeClick: (e: EmployeeAtSlot) => void;
  highlightedEmployeeId?: number | null;
}

const ICONS: Record<StationKey, React.ReactNode> = {
  K: <ChefHat className="h-4 w-4" />,
  C: <ShoppingBag className="h-4 w-4" />,
  BVR: <Coffee className="h-4 w-4" />,
  FF: <Sparkles className="h-4 w-4" />,
  TS: <Users2 className="h-4 w-4" />,
};

export function StationZone({
  station,
  big = false,
  onEmployeeClick,
  highlightedEmployeeId,
}: StationZoneProps) {
  const status = station.status ?? "no_data";
  const stationName =
    station.station_name ??
    STATION_NAMES[station.station_key as StationKey] ??
    String(station.station_key);
  const required = station.required ?? 0;
  const assigned = station.assigned ?? 0;
  const diff = assigned - required;
  const stColor = statusToHex(status);

  return (
    <motion.div
      layout
      className="card relative overflow-hidden flex flex-col"
      style={{ minHeight: big ? 360 : 200 }}
    >
      <div
        className="absolute inset-x-0 top-0 h-1.5"
        style={{ background: stColor }}
      />

      <div className="px-4 pt-4 pb-2 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-graphite-700">
            <span
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg"
              style={{ background: stColor + "1a", color: stColor }}
            >
              {ICONS[station.station_key as StationKey] ?? null}
            </span>
            <div className="flex flex-col leading-tight">
              <span className="font-semibold text-graphite-900">
                {stationName}
              </span>
              <span className="text-[10px] uppercase font-semibold tracking-wider text-graphite-400">
                {String(station.station_key)}
              </span>
            </div>
          </div>
        </div>
        <div
          className={`pill border ${statusBg(status)} whitespace-nowrap`}
          aria-label={statusLabel(status)}
        >
          {statusLabel(status)}
        </div>
      </div>

      <div className="px-4 pb-3 grid grid-cols-3 gap-2">
        <Metric label="Требуется" value={required} />
        <Metric label="Назначено" value={assigned} bold />
        <Metric
          label="Разница"
          value={diff > 0 ? `+${diff}` : `${diff}`}
          tone={
            diff === 0
              ? "neutral"
              : diff > 0 && diff <= 2
                ? "orange"
                : diff < 0 || diff > 2
                  ? "orangeDeep"
                  : "neutral"
          }
        />
      </div>

      <div
        className={`px-3 pb-4 flex flex-wrap content-start gap-3 overflow-y-auto scrollbar-thin ${
          big ? "max-h-[260px]" : "max-h-[120px]"
        }`}
      >
        <AnimatePresence initial={false}>
          {station.employees.map((emp) => (
            <motion.div
              key={`${station.station_key}-${emp.employee_id}-${emp.shift_start}`}
              layout
              initial={{ opacity: 0, y: 8, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.9 }}
              transition={{ duration: 0.25 }}
            >
              <EmployeeAvatar
                employeeId={emp.employee_id}
                size={big ? 64 : 48}
                onClick={() => onEmployeeClick(emp)}
                highlighted={highlightedEmployeeId === emp.employee_id}
                badgeColor={stColor}
              />
            </motion.div>
          ))}
        </AnimatePresence>
        {station.employees.length === 0 && (
          <div className="w-full text-center text-xs text-graphite-400 py-6">
            Нет сотрудников в этот час
          </div>
        )}
      </div>
    </motion.div>
  );
}

function Metric({
  label,
  value,
  bold = false,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  bold?: boolean;
  tone?: "neutral" | "orange" | "orangeDeep";
}) {
  const toneCls =
    tone === "orange"
      ? "text-brand-orange-deep"
      : tone === "orangeDeep"
        ? "text-brand-orange-deep"
        : "text-graphite-800";
  return (
    <div className="rounded-lg bg-graphite-50 border border-graphite-100 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-graphite-400">
        {label}
      </div>
      <div
        className={`text-base ${bold ? "font-semibold" : "font-medium"} ${toneCls}`}
      >
        {value}
      </div>
    </div>
  );
}
