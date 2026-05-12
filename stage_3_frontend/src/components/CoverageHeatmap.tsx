import {
  STATION_NAMES,
  STATION_ORDER,
  type DaySlot,
  type StationKey,
} from "../lib/types";
import { statusToHex } from "../lib/coverageStatus";
import { formatHour } from "../lib/normalizeTimeline";

interface CoverageHeatmapProps {
  day: DaySlot | null;
  selectedHour: number;
  onSelectHour: (h: number) => void;
}

export function CoverageHeatmap({
  day,
  selectedHour,
  onSelectHour,
}: CoverageHeatmapProps) {
  if (!day) {
    return (
      <div className="card p-5 text-sm text-graphite-500">
        Нет данных по дню
      </div>
    );
  }

  const hours = day.hours.map((h) => h.hour);
  const byHour = new Map(day.hours.map((h) => [h.hour, h]));

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide font-semibold text-graphite-400">
            Покрытие по часам
          </div>
          <div className="text-base font-semibold text-graphite-900">
            {day.label} · {day.date}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto scrollbar-thin">
        <div
          className="grid gap-1"
          style={{
            gridTemplateColumns: `120px repeat(${hours.length}, 1fr)`,
          }}
        >
          <div />
          {hours.map((h) => (
            <button
              type="button"
              key={`hh-${h}`}
              onClick={() => onSelectHour(h)}
              className={`text-[10px] tabular-nums text-center rounded-md py-1 transition ${
                h === selectedHour
                  ? "bg-brand-forest text-white"
                  : "text-graphite-500 hover:bg-graphite-100"
              }`}
              title={formatHour(h)}
            >
              {String(h).padStart(2, "0")}
            </button>
          ))}

          {STATION_ORDER.map((stKey: StationKey) => (
            <RowFor
              key={stKey}
              stationKey={stKey}
              stationName={STATION_NAMES[stKey]}
              hours={hours}
              dayHours={byHour}
              selectedHour={selectedHour}
              onSelectHour={onSelectHour}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function RowFor({
  stationKey,
  stationName,
  hours,
  dayHours,
  selectedHour,
  onSelectHour,
}: {
  stationKey: StationKey;
  stationName: string;
  hours: number[];
  dayHours: Map<number, DaySlot["hours"][number]>;
  selectedHour: number;
  onSelectHour: (h: number) => void;
}) {
  return (
    <>
      <div className="flex items-center gap-2 pr-2">
        <span className="text-[10px] uppercase tracking-wider font-semibold text-graphite-400 w-9">
          {stationKey}
        </span>
        <span className="text-xs text-graphite-700 truncate">
          {stationName}
        </span>
      </div>
      {hours.map((h) => {
        const hourSlot = dayHours.get(h);
        const st = hourSlot?.stations.find(
          (s) => String(s.station_key) === stationKey,
        );
        const status = st?.status ?? "no_data";
        const color = statusToHex(status);
        const required = st?.required ?? 0;
        const assigned = st?.assigned ?? 0;
        const isSelected = h === selectedHour;
        return (
          <button
            type="button"
            key={`${stationKey}-${h}`}
            onClick={() => onSelectHour(h)}
            className="group relative h-7 rounded-md transition focus:outline-none"
            style={{
              background: color,
              opacity: status === "no_data" ? 0.35 : 0.9,
              outline: isSelected ? "2px solid #0F3D2A" : "none",
              outlineOffset: "1px",
            }}
            title={`${stationName} · ${formatHour(h)} · треб ${required} / назн ${assigned}`}
          >
            <span className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold text-white drop-shadow-sm">
              {assigned}
            </span>
          </button>
        );
      })}
    </>
  );
}
