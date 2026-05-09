import { motion } from "framer-motion";
import {
  STATION_NAMES,
  STATION_ORDER,
  type EmployeeAtSlot,
  type HourSlot,
  type StationKey,
} from "../lib/types";
import { StationZone } from "./StationZone";

interface RestaurantMapProps {
  hour: HourSlot | null;
  selectedStation: StationKey | "ALL";
  onSelectStation: (s: StationKey | "ALL") => void;
  onEmployeeClick: (e: EmployeeAtSlot) => void;
  highlightedEmployeeId?: number | null;
}

const TABS: { key: StationKey | "ALL"; label: string }[] = [
  { key: "ALL", label: "Все станции" },
  { key: "K", label: STATION_NAMES.K },
  { key: "C", label: STATION_NAMES.C },
  { key: "BVR", label: STATION_NAMES.BVR },
  { key: "FF", label: STATION_NAMES.FF },
  { key: "TS", label: STATION_NAMES.TS },
];

export function RestaurantMap({
  hour,
  selectedStation,
  onSelectStation,
  onEmployeeClick,
  highlightedEmployeeId,
}: RestaurantMapProps) {
  const stations = hour?.stations ?? [];
  const byKey = new Map(stations.map((s) => [String(s.station_key), s]));

  const stationFor = (k: StationKey) =>
    byKey.get(k) ?? {
      station_key: k,
      station_name: STATION_NAMES[k],
      required: 0,
      assigned: 0,
      employees: [],
    };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex flex-wrap gap-2">
          {TABS.map((t) => {
            const active = selectedStation === t.key;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => onSelectStation(t.key)}
                className={`chip-tab ${
                  active
                    ? "bg-brand-forest text-white border-brand-forest shadow"
                    : "bg-white text-graphite-700 border-graphite-200 hover:bg-graphite-50"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {selectedStation === "ALL" ? (
        <div className="grid grid-cols-12 gap-4">
          <motion.div layout className="col-span-12 lg:col-span-3">
            <StationZone
              station={stationFor("K")}
              onEmployeeClick={onEmployeeClick}
              highlightedEmployeeId={highlightedEmployeeId}
            />
          </motion.div>
          <motion.div
            layout
            className="col-span-12 lg:col-span-6 grid grid-cols-1 lg:grid-cols-2 gap-4"
          >
            <div className="lg:col-span-2">
              <StationZone
                station={stationFor("C")}
                onEmployeeClick={onEmployeeClick}
                highlightedEmployeeId={highlightedEmployeeId}
              />
            </div>
            <StationZone
              station={stationFor("BVR")}
              onEmployeeClick={onEmployeeClick}
              highlightedEmployeeId={highlightedEmployeeId}
            />
            <StationZone
              station={stationFor("FF")}
              onEmployeeClick={onEmployeeClick}
              highlightedEmployeeId={highlightedEmployeeId}
            />
          </motion.div>
          <motion.div layout className="col-span-12 lg:col-span-3">
            <StationZone
              station={stationFor("TS")}
              onEmployeeClick={onEmployeeClick}
              highlightedEmployeeId={highlightedEmployeeId}
            />
          </motion.div>
        </div>
      ) : (
        <motion.div layout>
          <StationZone
            big
            station={stationFor(selectedStation)}
            onEmployeeClick={onEmployeeClick}
            highlightedEmployeeId={highlightedEmployeeId}
          />
        </motion.div>
      )}

      {STATION_ORDER.length === 0 && null}
    </div>
  );
}
