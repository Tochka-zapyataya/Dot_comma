import { AnimatePresence, motion } from "framer-motion";
import { Pause, Play, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type DaySlot, type EmployeeAtSlot } from "../lib/types";
import {
  activeShiftsAt,
  dayTimeBoundsHours,
  formatHourMinute,
  shiftsForDay,
  type ActiveShift,
} from "../lib/shifts";
import { avatarLook, BRAND_LOGO, BRAND_UNIFORM } from "../lib/avatar";
import { UniformBrandMark } from "./UniformBrandMark";

interface RestaurantTopDownProps {
  day: DaySlot | null | undefined;
  externalHour: number;
  onChangeHour: (h: number) => void;
  onEmployeeClick?: (e: EmployeeAtSlot) => void;
  highlightedEmployeeId?: number | null;
}

type StationKey = "K" | "FF" | "C" | "BVR" | "TS";

interface ZoneDef {
  key: StationKey;
  label: string;
  color: string;
  /** Центр подписи по X, верх подписи по Y (чуть выше станции). */
  labelCenter: { x: number; y: number };
  /** Слоты только для зала (столы). */
  slots: { x: number; y: number }[];
  /**
   * Прямоугольник станции (как у прежнего makeGrid): слева направо от x0,
   * при заполнении ряда — следующий ряд внутри [y0, y1].
   */
  packEnvelope?: { x0: number; x1: number; y0: number; y1: number };
}

const SCENE_W = 1600;
/** Выше сцена — больше площади; нижние станции (картофель, прилавок) ниже. */
const SCENE_H = 970;

/** Вход: по центру снизу сцены; ширина двойной двери в `Door`. */
const DOOR_GRAPHIC_W = 80;
/** Отступ низа подписи от нижней границы viewBox (антиклэмп baseline). */
const DOOR_BOTTOM_PAD = 14;
/** Верх группы «вход»: двери h=14, подпись ~fontSize 14 — резервируем запас под descenders. */
const DOOR_GROUP_Y = SCENE_H - DOOR_BOTTOM_PAD - 32;
const DOOR_GROUP_X = SCENE_W / 2 - DOOR_GRAPHIC_W / 2;

/** Сдвиг линии выдачи / прилавка в сторону зала (чем меньше — тем левее, дальше от входа). */
const SERVICE_COUNTER_SHIFT_X = 165;

/** Общая линия подписей верхнего ряда станций (кухня / напитки / зал). */
const STATION_LABEL_Y_TOP = 56;
/** Общая линия подписей нижнего ряда (картофель / прилавок). */
const STATION_LABEL_Y_BOTTOM = 582;

/**
 * Бар «Напитки»: компактный блок, чуть левее; правый край до перехода в зал (x = 1100).
 */
const BAR_COUNTER_X = 618;
const BAR_COUNTER_W = 418;
const BAR_COUNTER_Y = 148;
const BAR_COUNTER_H = 128;

/**
 * Вертикальное положение стойки прилавка — ниже в расширенной нижней зоне кухни.
 */
const COUNTER_C_Y = 638;

/** Клип шире стойки, чтобы правая кромка не резалась у границы с залом. */
const SERVICE_COUNTER_CLIP = {
  x: 38 + SERVICE_COUNTER_SHIFT_X,
  y: COUNTER_C_Y - 22,
  width: 900,
  height: 188,
} as const;

const FOOD_TRAY_Y = COUNTER_C_Y + 154;

/** Якорь — центр основания фигурки (совпадает с translate -50% -100%). */
function packEmployeesInEnvelope(
  x0: number,
  x1: number,
  y0: number,
  y1: number,
  n: number,
): { x: number; y: number }[] {
  const HALF = 42;
  const padX = 12;
  const gap = 10;
  const colStep = 2 * HALF + gap;
  const innerLeft = x0 + padX + HALF;
  const innerRight = x1 - padX - HALF;
  const out: { x: number; y: number }[] = [];
  if (n <= 0 || innerLeft > innerRight) return out;

  const widthSpan = innerRight - innerLeft;
  const maxCols = Math.max(1, Math.floor(widthSpan / colStep) + 1);
  const nRows = Math.max(1, Math.ceil(n / maxCols));
  const marginY = 10;
  const top = y0 + marginY;
  const bot = y1 - marginY;
  const rowYs =
    nRows === 1
      ? [(top + bot) / 2]
      : Array.from(
          { length: nRows },
          (_, r) => top + (r * (bot - top)) / Math.max(1, nRows - 1),
        );

  for (let i = 0; i < n; i++) {
    const col = i % maxCols;
    const row = Math.floor(i / maxCols);
    let x = innerLeft + col * colStep;
    x = Math.min(Math.max(x, innerLeft), innerRight);
    const y = rowYs[Math.min(row, rowYs.length - 1)]!;
    out.push({ x, y });
  }
  return out;
}

const ZONES: ZoneDef[] = [
  {
    key: "K",
    label: "Кухня",
    color: "#D9551A",
    labelCenter: { x: 255, y: STATION_LABEL_Y_TOP },
    slots: [],
    packEnvelope: { x0: 92, x1: 418, y0: 195, y1: 398 },
  },
  {
    key: "FF",
    label: "Картофель",
    color: "#FFC72C",
    labelCenter: { x: 250, y: STATION_LABEL_Y_BOTTOM },
    slots: [],
    packEnvelope: { x0: 120, x1: 380, y0: 690, y1: 850 },
  },
  {
    key: "BVR",
    label: "Напитки",
    color: "#7A4A1A",
    labelCenter: {
      x: BAR_COUNTER_X + BAR_COUNTER_W / 2,
      y: STATION_LABEL_Y_TOP,
    },
    slots: [],
    packEnvelope: {
      x0: BAR_COUNTER_X + 10,
      x1: BAR_COUNTER_X + BAR_COUNTER_W - 10,
      y0: 208,
      y1: 278,
    },
  },
  {
    key: "C",
    label: "Прилавок",
    color: "#0F3D2A",
    labelCenter: {
      x: (502 + 848) / 2 + SERVICE_COUNTER_SHIFT_X,
      y: STATION_LABEL_Y_BOTTOM,
    },
    slots: [],
    packEnvelope: {
      x0: 502 + SERVICE_COUNTER_SHIFT_X,
      x1: 848 + SERVICE_COUNTER_SHIFT_X,
      y0: COUNTER_C_Y + 52,
      y1: COUNTER_C_Y + 142,
    },
  },
  {
    key: "TS",
    label: "Зал",
    color: "#1F6EAD",
    labelCenter: { x: 1330, y: STATION_LABEL_Y_TOP },
    slots: [
      { x: 1170, y: 220 },
      { x: 1320, y: 220 },
      { x: 1470, y: 220 },
      { x: 1170, y: 400 },
      { x: 1320, y: 400 },
      { x: 1470, y: 400 },
      { x: 1170, y: 580 },
      { x: 1320, y: 580 },
      { x: 1470, y: 580 },
      { x: 1170, y: 760 },
      { x: 1320, y: 760 },
      { x: 1470, y: 760 },
    ],
  },
];

const SPEEDS = [
  { label: "1×", minPerSec: 1 },
  { label: "4×", minPerSec: 4 },
  { label: "10×", minPerSec: 10 },
  { label: "30×", minPerSec: 30 },
];

const TICK_MS = 100;

function asEmployeeAtSlot(s: ActiveShift): EmployeeAtSlot {
  return {
    employee_id: s.employee_id,
    shift_start: s.shift_start,
    shift_end: s.shift_end,
    shift_duration: s.shift_duration,
    station_key: s.station_key,
    station_name: s.station_name,
    station_priority: s.station_priority ?? null,
    shift_priority: s.shift_priority ?? null,
  };
}

export function RestaurantTopDown({
  day,
  externalHour,
  onChangeHour,
  onEmployeeClick,
  highlightedEmployeeId,
}: RestaurantTopDownProps) {
  const { min: minHour, max: maxHour } = dayTimeBoundsHours(day);
  const minMin = minHour * 60;
  const maxMin = maxHour * 60;

  const [simActive, setSimActive] = useState(false);
  const [simMinutes, setSimMinutes] = useState<number>(externalHour * 60);
  const [speedIdx, setSpeedIdx] = useState<number>(1);
  const tickRef = useRef<number | null>(null);

  useEffect(() => {
    if (!simActive) {
      setSimMinutes(Math.min(maxMin, Math.max(minMin, externalHour * 60)));
    }
  }, [externalHour, simActive, minMin, maxMin]);

  useEffect(() => {
    if (!simActive) {
      if (tickRef.current) {
        window.clearInterval(tickRef.current);
        tickRef.current = null;
      }
      return;
    }
    const speed = SPEEDS[speedIdx].minPerSec;
    tickRef.current = window.setInterval(() => {
      setSimMinutes((m) => {
        const next = m + speed * (TICK_MS / 1000);
        if (next >= maxMin) {
          setSimActive(false);
          return maxMin;
        }
        return next;
      });
    }, TICK_MS);
    return () => {
      if (tickRef.current) {
        window.clearInterval(tickRef.current);
        tickRef.current = null;
      }
    };
  }, [simActive, speedIdx, maxMin]);

  useEffect(() => {
    if (!simActive) return;
    const wholeHour = Math.floor(simMinutes / 60);
    if (
      wholeHour !== externalHour &&
      wholeHour >= minHour &&
      wholeHour < maxHour
    ) {
      onChangeHour(wholeHour);
    }
  }, [simMinutes, simActive, externalHour, minHour, maxHour, onChangeHour]);

  const allShifts = useMemo(() => shiftsForDay(day), [day]);
  const hourFloat = simMinutes / 60;
  const active = useMemo(
    () => activeShiftsAt(allShifts, hourFloat),
    [allShifts, hourFloat],
  );

  const placements = useMemo(() => {
    const byZone = new Map<string, ActiveShift[]>();
    for (const s of active) {
      const sk = String(s.station_key).toUpperCase();
      const arr = byZone.get(sk) ?? [];
      arr.push(s);
      byZone.set(sk, arr);
    }
    const out: {
      shift: ActiveShift;
      x: number;
      y: number;
      color: string;
    }[] = [];
    for (const z of ZONES) {
      const list = (byZone.get(z.key) ?? []).sort(
        (a, b) => a.employee_id - b.employee_id,
      );
      let positions: { x: number; y: number }[];
      if (z.packEnvelope) {
        const e = z.packEnvelope;
        positions = packEmployeesInEnvelope(e.x0, e.x1, e.y0, e.y1, list.length);
      } else {
        positions = list.map((_, i) => {
          const slot = z.slots[i] ?? z.slots[z.slots.length - 1];
          return { x: slot.x, y: slot.y };
        });
      }
      list.forEach((s, i) => {
        const base = positions[i];
        if (!base) return;
        let x = base.x;
        let y = base.y;
        if (!z.packEnvelope && i >= z.slots.length && z.slots.length > 0) {
          const slot = z.slots[z.slots.length - 1];
          x = slot.x + (((s.employee_id * 37) % 60) - 30);
          y = slot.y + (((s.employee_id * 53) % 40) - 20);
        }
        out.push({
          shift: s,
          x,
          y,
          color: z.color,
        });
      });
    }
    return out;
  }, [active]);

  const togglePlay = useCallback(() => {
    setSimActive((v) => {
      const next = !v;
      if (next && simMinutes >= maxMin) setSimMinutes(minMin);
      return next;
    });
  }, [simMinutes, maxMin, minMin]);

  const reset = useCallback(() => {
    setSimActive(false);
    setSimMinutes(minMin);
    onChangeHour(minHour);
  }, [minMin, minHour, onChangeHour]);

  const onScrub = useCallback(
    (val: number) => {
      setSimActive(false);
      setSimMinutes(val);
      const wholeHour = Math.floor(val / 60);
      if (
        wholeHour !== externalHour &&
        wholeHour >= minHour &&
        wholeHour < maxHour
      ) {
        onChangeHour(wholeHour);
      }
    },
    [externalHour, minHour, maxHour, onChangeHour],
  );

  const totalActive = active.length;

  return (
    <div className="card p-4 lg:p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-graphite-400 font-semibold">
            План зала
          </div>
          <div className="flex items-baseline gap-3 mt-0.5">
            <div className="text-2xl font-semibold text-graphite-900 tabular-nums">
              {formatHourMinute(simMinutes)}
            </div>
            <div className="text-graphite-400">·</div>
            <div className="text-sm text-graphite-500">
              На смене сейчас:{" "}
              <span className="font-semibold text-brand-orange-deep">
                {totalActive}
              </span>{" "}
              сотр.
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center rounded-xl border border-graphite-200 bg-white overflow-hidden">
            {SPEEDS.map((s, i) => (
              <button
                key={s.label}
                type="button"
                onClick={() => setSpeedIdx(i)}
                className={`px-2.5 py-1.5 text-xs font-semibold transition ${
                  i === speedIdx
                    ? "bg-brand-forest text-white"
                    : "text-graphite-700 hover:bg-graphite-50"
                }`}
                title={`${s.minPerSec} мин / сек`}
              >
                {s.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={togglePlay}
            className={`btn-primary px-4 py-2 ${
              simActive ? "bg-graphite-800 hover:bg-graphite-900" : ""
            }`}
            aria-label={simActive ? "Пауза" : "Запустить симуляцию"}
          >
            {simActive ? (
              <>
                <Pause className="h-4 w-4" />
                Пауза
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Симуляция
              </>
            )}
          </button>
          <button
            type="button"
            onClick={reset}
            className="btn-icon"
            aria-label="Сбросить к открытию"
            title="Сбросить к открытию"
          >
            <RotateCcw className="h-5 w-5" />
          </button>
        </div>
      </div>

      <div>
        <input
          type="range"
          min={minMin}
          max={maxMin}
          step={5}
          value={Math.min(maxMin, Math.max(minMin, simMinutes))}
          onChange={(e) => onScrub(parseInt(e.target.value, 10))}
          className="w-full accent-brand-orange"
          aria-label="Время суток"
        />
        <div className="flex justify-between text-[10px] text-graphite-400 mt-1 select-none">
          {Array.from(
            { length: maxHour - minHour + 1 },
            (_, i) => minHour + i,
          ).map((h) => (
            <span
              key={h}
              className={`tabular-nums ${
                Math.floor(simMinutes / 60) === h
                  ? "text-brand-orange font-semibold"
                  : ""
              }`}
            >
              {String(h).padStart(2, "0")}
            </span>
          ))}
        </div>
      </div>

      <div className="relative w-full overflow-hidden rounded-2xl border border-graphite-200 shadow-inner aspect-[1600/970] bg-[#f4ead8]">
        <svg
          viewBox={`0 0 ${SCENE_W} ${SCENE_H}`}
          className="absolute inset-0 w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <FloorPlan />
          {ZONES.map((z) => (
            <ZoneLabel key={z.key} zone={z} />
          ))}
        </svg>

        <AnimatePresence initial={false}>
          {placements.map((p) => {
            const pctX = (p.x / SCENE_W) * 100;
            const pctY = (p.y / SCENE_H) * 100;
            return (
              <motion.div
                key={`${p.shift.station_key}-${p.shift.employee_id}-${p.shift.shift_start}`}
                layout
                initial={{ opacity: 0, scale: 0.5, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.5, y: -8 }}
                transition={{ type: "spring", stiffness: 320, damping: 22 }}
                className="absolute"
                style={{
                  left: `${pctX}%`,
                  top: `${pctY}%`,
                  width: "5.6%",
                  transform: "translate(-50%, -100%)",
                }}
                title={`#${p.shift.employee_id}`}
              >
                <ChibiPerson
                  employeeId={p.shift.employee_id}
                  uniformColor={p.color}
                  highlighted={highlightedEmployeeId === p.shift.employee_id}
                  onClick={
                    onEmployeeClick
                      ? () => onEmployeeClick(asEmployeeAtSlot(p.shift))
                      : undefined
                  }
                />
              </motion.div>
            );
          })}
        </AnimatePresence>

        {totalActive === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="bg-white/85 backdrop-blur px-4 py-2 rounded-xl border border-graphite-200 text-graphite-500 text-sm">
              В этот момент никого нет в зале
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ZoneLabel({ zone }: { zone: ZoneDef }) {
  const w = zone.label.length * 22 + 60;
  const { x: cx, y: cy } = zone.labelCenter;
  return (
    <g transform={`translate(${cx}, ${cy})`}>
      <g transform={`translate(${-w / 2}, 0)`}>
        <rect
          x={0}
          y={0}
          rx={18}
          ry={18}
          width={w}
          height={48}
          fill="white"
          stroke={zone.color}
          strokeWidth={2}
          opacity={0.92}
        />
        <circle cx={28} cy={24} r={10} fill={zone.color} />
        <text
          x={50}
          y={31}
          fontSize={22}
          fontWeight={700}
          fill="#1f242c"
          fontFamily="Inter, ui-sans-serif, sans-serif"
        >
          {zone.label}
        </text>
      </g>
    </g>
  );
}

/** Фартук, вытяжка и открытая полка над линией плит (топ-даун «кухня»). */
function KitchenBacksplashAndHood() {
  return (
    <g>
      <title>Кухонная линия — фартук и вытяжка</title>
      <rect
        x="56"
        y="84"
        width="416"
        height="14"
        rx="3"
        fill="#dce4ea"
        stroke="#9aa6ad"
        strokeWidth="1.2"
      />
      <path
        d="M 52 88 L 476 88 L 464 58 L 64 58 Z"
        fill="#4a5568"
        stroke="#2d3748"
        strokeWidth="1.5"
      />
      <rect x="68" y="48" width="392" height="12" rx="3" fill="#3d4756" />
      <line
        x1="88"
        y1="54"
        x2="440"
        y2="54"
        stroke="#1f242c"
        strokeWidth="1"
        opacity="0.35"
      />
      {[100, 145, 190, 235, 280, 325, 370, 415].map((vx) => (
        <line
          key={vx}
          x1={vx}
          y1="52"
          x2={vx}
          y2="62"
          stroke="#2d3748"
          strokeWidth="0.9"
          opacity="0.5"
        />
      ))}
      <rect
        x="72"
        y="76"
        width="384"
        height="8"
        rx="2"
        fill="#6b7280"
        stroke="#4b5563"
        strokeWidth="0.8"
      />
    </g>
  );
}

function FloorPlan() {
  return (
    <g>
      <defs>
        <pattern
          id="kitchenTile"
          width="40"
          height="40"
          patternUnits="userSpaceOnUse"
        >
          <rect width="40" height="40" fill="#e9eef0" />
          <path
            d="M0 40 L40 40 M40 0 L40 40"
            stroke="#c2cbd0"
            strokeWidth="1.2"
          />
        </pattern>
        <pattern
          id="hallWood"
          width="120"
          height="36"
          patternUnits="userSpaceOnUse"
        >
          <rect width="120" height="36" fill="#dcb589" />
          <path
            d="M0 36 L120 36"
            stroke="#b48a5e"
            strokeWidth="1"
          />
          <path
            d="M40 0 L40 36 M80 0 L80 36"
            stroke="#b48a5e"
            strokeWidth="0.6"
            opacity="0.6"
          />
        </pattern>
        <pattern
          id="counterStone"
          width="50"
          height="50"
          patternUnits="userSpaceOnUse"
        >
          <rect width="50" height="50" fill="#3d4855" />
          <circle cx="14" cy="14" r="0.8" fill="#5a6573" />
          <circle cx="34" cy="22" r="0.6" fill="#5a6573" />
          <circle cx="22" cy="38" r="0.7" fill="#5a6573" />
        </pattern>
        <clipPath id="serviceCounterClip">
          <rect
            x={SERVICE_COUNTER_CLIP.x}
            y={SERVICE_COUNTER_CLIP.y}
            width={SERVICE_COUNTER_CLIP.width}
            height={SERVICE_COUNTER_CLIP.height}
            rx="0"
          />
        </clipPath>
      </defs>

      <rect x="0" y="0" width={SCENE_W} height={SCENE_H} fill="#f4ead8" />

      <rect
        x="40"
        y="40"
        width="1040"
        height="525"
        rx="18"
        fill="url(#kitchenTile)"
        stroke="#9aa6ad"
        strokeWidth="2"
      />

      <rect
        x="40"
        y="572"
        width="380"
        height="370"
        rx="18"
        fill="url(#kitchenTile)"
        stroke="#9aa6ad"
        strokeWidth="2"
      />

      <rect
        x="1100"
        y="40"
        width="460"
        height="895"
        rx="18"
        fill="url(#hallWood)"
        stroke="#a07748"
        strokeWidth="2"
      />

      <KitchenBacksplashAndHood />

      <Stove x={70} y={92} />
      <Stove x={290} y={92} />
      <PrepTable x={70} y={308} w={420} h={72} />
      <FridgeRow x={70} y={428} />

      <Fryer x={80} y={670} />
      <Fryer x={210} y={670} />
      <Fryer x={80} y={800} />
      <Fryer x={210} y={800} />

      <BarCounter
        x={BAR_COUNTER_X}
        y={BAR_COUNTER_Y}
        w={BAR_COUNTER_W}
        h={BAR_COUNTER_H}
      />
      <CoffeeMachine x={BAR_COUNTER_X + 26} y={BAR_COUNTER_Y + 10} />
      <DrinkTaps x={BAR_COUNTER_X + BAR_COUNTER_W - 172} y={BAR_COUNTER_Y + 14} />
      <BarStool x={BAR_COUNTER_X + 54} y={BAR_COUNTER_Y + BAR_COUNTER_H + 34} />
      <BarStool x={BAR_COUNTER_X + 154} y={BAR_COUNTER_Y + BAR_COUNTER_H + 34} />
      <BarStool x={BAR_COUNTER_X + 258} y={BAR_COUNTER_Y + BAR_COUNTER_H + 34} />
      <BarStool x={BAR_COUNTER_X + 362} y={BAR_COUNTER_Y + BAR_COUNTER_H + 34} />

      <g clipPath="url(#serviceCounterClip)">
        <CounterC
          x={485 + SERVICE_COUNTER_SHIFT_X}
          y={COUNTER_C_Y}
          w={382}
          h={150}
        />
        <Register x={508 + SERVICE_COUNTER_SHIFT_X} y={COUNTER_C_Y + 18} />
        <Register x={625 + SERVICE_COUNTER_SHIFT_X} y={COUNTER_C_Y + 18} />
        <Register x={742 + SERVICE_COUNTER_SHIFT_X} y={COUNTER_C_Y + 18} />
      </g>

      <FoodTrayLane
        x={485 + SERVICE_COUNTER_SHIFT_X}
        y={FOOD_TRAY_Y}
        w={382}
      />

      <DiningTable x={1170} y={170} />
      <DiningTable x={1320} y={170} />
      <DiningTable x={1470} y={170} />
      <DiningTable x={1170} y={350} />
      <DiningTable x={1320} y={350} />
      <DiningTable x={1470} y={350} />
      <DiningTable x={1170} y={530} />
      <DiningTable x={1320} y={530} />
      <DiningTable x={1470} y={530} />
      <DiningTable x={1170} y={710} />
      <DiningTable x={1320} y={710} />
      <DiningTable x={1470} y={710} />

      <PlantPot x={1080} y={900} />
      <PlantPot x={1540} y={900} />
      <Door x={DOOR_GROUP_X} y={DOOR_GROUP_Y} />
    </g>
  );
}

function Stove({ x, y }: { x: number; y: number }) {
  const knobCx = [34, 66, 114, 146];
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width="180" height="180" rx="12" fill="#2c333d" />
      <rect x="6" y="6" width="168" height="168" rx="10" fill="#1f242c" />
      <rect
        x="10"
        y="10"
        width="160"
        height="36"
        rx="6"
        fill="#262d36"
        stroke="#3d4451"
        strokeWidth="1"
      />
      <rect
        x="14"
        y="150"
        width="152"
        height="20"
        rx="5"
        fill="#3d4451"
        stroke="#1f242c"
        strokeWidth="1"
      />
      {knobCx.map((cx) => (
        <circle
          key={cx}
          cx={cx}
          cy="160"
          r="5"
          fill="#c8ccd4"
          stroke="#8b939e"
          strokeWidth="0.8"
        />
      ))}
      <Burner cx={48} cy={62} />
      <Burner cx={132} cy={62} />
      <Burner cx={48} cy={126} />
      <Burner cx={132} cy={126} />
    </g>
  );
}

function Burner({ cx, cy }: { cx: number; cy: number }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r={28} fill="#0e1216" />
      <circle cx={cx} cy={cy} r={22} fill="#3a3329" />
      <circle cx={cx} cy={cy} r={18} fill="#5b3b1a" opacity="0.9" />
      <circle cx={cx} cy={cy} r={14} fill="#a8551d" opacity="0.6" />
    </g>
  );
}

function PrepTable({
  x,
  y,
  w,
  h,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
}) {
  const mid = h / 2;
  return (
    <g transform={`translate(${x}, ${y})`}>
      <title>Стол и мойка</title>
      <rect width={w} height={h} rx="8" fill="url(#counterStone)" />
      <ellipse
        cx="52"
        cy={mid}
        rx="26"
        ry="19"
        fill="#6eb8d8"
        stroke="#4a8bab"
        strokeWidth="1.2"
      />
      <ellipse
        cx="52"
        cy={mid + 2}
        rx="22"
        ry="14"
        fill="#8ecae6"
        opacity="0.85"
      />
      <path
        d={`M 52 ${10} L 52 ${mid - 22}`}
        stroke="#9aa6ad"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <ellipse
        cx="52"
        cy={10}
        rx="8"
        ry="5"
        fill="#b8c0c8"
        stroke="#7e8a91"
        strokeWidth="1"
      />
      <rect
        x={100}
        y={12}
        width={128}
        height={h - 24}
        rx="6"
        fill="#caa376"
        stroke="#a07748"
        strokeWidth="1.2"
      />
      <line
        x1="112"
        y1={mid - 6}
        x2="216"
        y2={mid + 8}
        stroke="#8b5a2b"
        strokeWidth="1.2"
        opacity="0.45"
      />
      <rect
        x={246}
        y={12}
        width={88}
        height={h - 24}
        rx="6"
        fill="#caa376"
        stroke="#a07748"
        strokeWidth="1.2"
      />
      <rect
        x={352}
        y={14}
        width="56"
        height={h - 28}
        rx="5"
        fill="#dde3e8"
        stroke="#b5bdc4"
        strokeWidth="1"
      />
      <line
        x1="380"
        y1="18"
        x2="380"
        y2={h - 18}
        stroke="#9aa6ad"
        strokeWidth="1"
      />
      <circle cx={318} cy={mid} r={14} fill="#d33" />
      <circle cx={348} cy={mid} r={14} fill="#3a8b3a" />
      <circle cx={378} cy={mid} r={14} fill="#e5b94a" />
    </g>
  );
}

function FridgeRow({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <title>Холодильники и верхние шкафы</title>
      <rect
        x="0"
        y="-34"
        width="420"
        height="30"
        rx="6"
        fill="#e8eef2"
        stroke="#b5bdc4"
        strokeWidth="1.2"
      />
      <line
        x1="140"
        y1="-32"
        x2="140"
        y2="-6"
        stroke="#9aa6ad"
        strokeWidth="1"
      />
      <line
        x1="280"
        y1="-32"
        x2="280"
        y2="-6"
        stroke="#9aa6ad"
        strokeWidth="1"
      />
      <rect
        x="6"
        y="-28"
        width="128"
        height="6"
        rx="2"
        fill="#cfd8df"
        opacity="0.9"
      />
      <rect
        x="146"
        y="-28"
        width="128"
        height="6"
        rx="2"
        fill="#cfd8df"
        opacity="0.9"
      />
      <rect
        x="286"
        y="-28"
        width="128"
        height="6"
        rx="2"
        fill="#cfd8df"
        opacity="0.9"
      />
      <rect
        width="420"
        height="90"
        rx="8"
        fill="#dde3e8"
        stroke="#b5bdc4"
        strokeWidth="1"
      />
      <rect x={6} y={6} width="135" height="78" rx="6" fill="#cfd8df" />
      <rect x={147} y={6} width="135" height="78" rx="6" fill="#cfd8df" />
      <rect x={288} y={6} width="126" height="78" rx="6" fill="#cfd8df" />
      <rect
        x={10}
        y={12}
        width="127"
        height="14"
        rx="3"
        fill="#b8c4cc"
        opacity="0.85"
      />
      <rect
        x={151}
        y={12}
        width="127"
        height="14"
        rx="3"
        fill="#b8c4cc"
        opacity="0.85"
      />
      <rect
        x={292}
        y={12}
        width="118"
        height="14"
        rx="3"
        fill="#b8c4cc"
        opacity="0.85"
      />
      <rect x={70} y={26} width="6" height="50" rx="2" fill="#7e8a91" />
      <rect x={211} y={26} width="6" height="50" rx="2" fill="#7e8a91" />
      <rect x={350} y={26} width="6" height="50" rx="2" fill="#7e8a91" />
    </g>
  );
}

function Fryer({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <title>Фритюр / картофель</title>
      {/* корпус — тёмный */}
      <rect width="120" height="112" rx="12" fill="#1f242c" />
      {/* золотистая «чаша» */}
      <rect x="10" y="12" width="100" height="70" rx="10" fill="#f2d57a" />
      {/* картофель / фри — насыщенный оранжево-коричневый */}
      <rect x="18" y="20" width="84" height="54" rx="8" fill="#b86520" />
      <rect x="22" y="24" width="76" height="46" rx="7" fill="#cc7828" />
      {/* лёгкая текстура «кусков» */}
      <rect x="28" y="30" width="18" height="12" rx="3" fill="#a85512" opacity="0.55" />
      <rect x={52} y="34" width="22" height="14" rx="3" fill="#a85512" opacity="0.45" />
      <rect x="72" y="28" width="16" height="10" rx="2" fill="#a85512" opacity="0.5" />
      {/* панель / ручка снизу */}
      <rect x="36" y="96" width="48" height="10" rx="4" fill="#9aa3ad" />
    </g>
  );
}

function BarCounter({
  x,
  y,
  w,
  h,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
}) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width={w} height={h} rx="14" fill="#5a3a1a" />
      <rect
        x={8}
        y={8}
        width={w - 16}
        height={h - 16}
        rx="10"
        fill="#7a4a1a"
      />
      <rect
        x={20}
        y={h - 24}
        width={w - 40}
        height={10}
        rx="3"
        fill="#3b2410"
      />
    </g>
  );
}

function CoffeeMachine({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width="140" height="110" rx="8" fill="#1f242c" />
      <rect x="10" y="10" width="120" height="40" rx="4" fill="#3a3329" />
      <rect x="20" y="56" width="40" height="40" rx="3" fill="#0e1216" />
      <rect x="80" y="56" width="40" height="40" rx="3" fill="#0e1216" />
      <circle cx="40" cy="76" r="6" fill="#a8551d" />
      <circle cx="100" cy="76" r="6" fill="#a8551d" />
    </g>
  );
}

function DrinkTaps({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width="160" height="90" rx="8" fill="#cfd8df" />
      <rect x="10" y="14" width="20" height="60" rx="4" fill="#7e8a91" />
      <rect x="42" y="14" width="20" height="60" rx="4" fill="#7e8a91" />
      <rect x="74" y="14" width="20" height="60" rx="4" fill="#7e8a91" />
      <rect x="106" y="14" width="20" height="60" rx="4" fill="#7e8a91" />
      <rect x="138" y="14" width="14" height="60" rx="4" fill="#7e8a91" />
    </g>
  );
}

function BarStool({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <circle cx="22" cy="22" r="22" fill="#3b2410" />
      <circle cx="22" cy="22" r="16" fill="#5a3a1a" />
      <circle cx="22" cy="22" r="10" fill="#a07748" />
    </g>
  );
}

function CounterC({
  x,
  y,
  w,
  h,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
}) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width={w} height={h} rx="14" fill="#3d4855" />
      <rect
        x={6}
        y={6}
        width={w - 12}
        height={h - 12}
        rx="10"
        fill="#5a6573"
      />
      <rect
        x={20}
        y={h - 22}
        width={w - 40}
        height={10}
        rx="3"
        fill="#262d36"
      />
    </g>
  );
}

function Register({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width="100" height="80" rx="8" fill="#1f242c" />
      <rect x="8" y="8" width="84" height="40" rx="4" fill="#3a8b3a" />
      <rect x="8" y="54" width="84" height="20" rx="3" fill="#2c333d" />
      <rect x="14" y="58" width="14" height="12" rx="2" fill="#a8551d" />
      <rect x="32" y="58" width="14" height="12" rx="2" fill="#a8551d" />
      <rect x="50" y="58" width="14" height="12" rx="2" fill="#a8551d" />
      <rect x="68" y="58" width="20" height="12" rx="2" fill="#a8551d" />
    </g>
  );
}

function FoodTrayLane({ x, y, w }: { x: number; y: number; w: number }) {
  const pad = 16;
  const colW = Math.max(72, Math.floor((w - pad * 2 - 8) / 3));
  const x1 = pad;
  const x2 = pad + colW + 4;
  const x3 = pad + (colW + 4) * 2;
  const col3W = Math.max(72, w - pad - x3);
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width={w} height="120" rx="14" fill="#cfd8df" />
      <rect
        x={x1}
        y={20}
        width={colW}
        height={80}
        rx="6"
        fill="#FFC72C"
      />
      <rect
        x={x2}
        y={20}
        width={colW}
        height={80}
        rx="6"
        fill="#F26522"
      />
      <rect
        x={x3}
        y={20}
        width={col3W}
        height={80}
        rx="6"
        fill="#0E8C3A"
      />
    </g>
  );
}

function DiningTable({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <circle cx="30" cy="-22" r="14" fill="#7a4a1a" />
      <circle cx="30" cy="82" r="14" fill="#7a4a1a" />
      <circle cx="-22" cy="30" r="14" fill="#7a4a1a" />
      <circle cx="82" cy="30" r="14" fill="#7a4a1a" />
      <circle cx="30" cy="30" r="42" fill="#fff8ee" stroke="#a07748" strokeWidth="2" />
      <circle cx="30" cy="30" r="14" fill="#a07748" opacity="0.3" />
    </g>
  );
}

function PlantPot({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <ellipse cx="20" cy="40" rx="22" ry="6" fill="#3b2410" opacity="0.4" />
      <rect x="5" y="20" width="30" height="22" rx="4" fill="#a07748" />
      <circle cx="20" cy="14" r="14" fill="#0E8C3A" />
      <circle cx="10" cy="10" r="8" fill="#1A5638" />
      <circle cx="30" cy="10" r="8" fill="#1A5638" />
    </g>
  );
}

function Door({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect x="0" y="0" width="40" height="14" rx="3" fill="#a07748" />
      <rect x="40" y="0" width="40" height="14" rx="3" fill="#a07748" />
      <text
        x="40"
        y="28"
        fontSize="14"
        fontWeight="600"
        fill="#7a4a1a"
        textAnchor="middle"
        dominantBaseline="alphabetic"
        fontFamily="Inter, ui-sans-serif, sans-serif"
      >
        вход
      </text>
    </g>
  );
}

interface ChibiPersonProps {
  employeeId: number;
  uniformColor: string;
  highlighted?: boolean;
  onClick?: () => void;
}

function ChibiPerson({
  employeeId,
  uniformColor,
  highlighted,
  onClick,
}: ChibiPersonProps) {
  const look = avatarLook(employeeId);
  const idleDelay = (employeeId % 7) * 0.18;

  return (
    <motion.button
      type="button"
      onClick={onClick}
      className={`block w-full focus:outline-none ${
        onClick ? "cursor-pointer" : "cursor-default"
      }`}
      whileHover={onClick ? { scale: 1.08 } : undefined}
      whileTap={onClick ? { scale: 0.95 } : undefined}
      aria-label={`Сотрудник ${employeeId}`}
    >
      <motion.div
        animate={{ y: [0, -3, 0, 1, 0] }}
        transition={{
          repeat: Infinity,
          duration: 2.6,
          ease: "easeInOut",
          delay: idleDelay,
        }}
      >
        <svg viewBox="0 0 80 110" className="block w-full h-auto">
          <ellipse
            cx="40"
            cy="104"
            rx="22"
            ry="4"
            fill="rgba(20,24,32,0.30)"
          />

          <rect
            x="24"
            y="94"
            width="32"
            height="13"
            rx="5"
            fill={BRAND_UNIFORM.black}
          />
          <rect
            x="22"
            y="62"
            width="36"
            height="34"
            rx="10"
            fill={BRAND_UNIFORM.green}
            stroke={BRAND_UNIFORM.greenDeep}
            strokeWidth="0.8"
          />
          <rect
            x="28"
            y="62"
            width="24"
            height="7"
            rx="3"
            fill={BRAND_UNIFORM.trim}
          />
          <rect
            x="22"
            y="68"
            width="36"
            height="6"
            rx="3"
            fill="rgba(255,255,255,0.12)"
          />
          <g transform="translate(40, 76)">
            <UniformBrandMark scale={1.22} />
          </g>
          <rect
            x="14"
            y="68"
            width="10"
            height="22"
            rx="5"
            fill={BRAND_UNIFORM.green}
            stroke={BRAND_UNIFORM.greenDeep}
            strokeWidth="0.6"
          />
          <rect
            x="56"
            y="68"
            width="10"
            height="22"
            rx="5"
            fill={BRAND_UNIFORM.green}
            stroke={BRAND_UNIFORM.greenDeep}
            strokeWidth="0.6"
          />
          <circle cx="19" cy="92" r="6" fill={look.skin} />
          <circle cx="61" cy="92" r="6" fill={look.skin} />

          <ellipse cx="40" cy="36" rx="26" ry="26" fill={look.skin} />

          {look.hairStyle === 0 && (
            <path
              d="M16 36 C16 18, 26 8, 40 8 C54 8, 64 18, 64 36 L64 26 C64 22, 60 20, 56 20 L24 20 C20 20, 16 22, 16 26 Z"
              fill={look.hair}
            />
          )}
          {look.hairStyle === 1 && (
            <path
              d="M16 38 C16 18, 26 8, 40 8 C54 8, 64 18, 64 38 C58 28, 52 24, 40 24 C28 24, 22 28, 16 38 Z"
              fill={look.hair}
            />
          )}
          {look.hairStyle === 2 && (
            <path
              d="M18 36 C18 18, 28 10, 40 10 C52 10, 62 18, 62 36 L58 30 L54 36 L50 30 L46 36 L42 30 L38 36 L34 30 L30 36 L26 30 L22 36 Z"
              fill={look.hair}
            />
          )}

          <ellipse cx="32" cy="38" rx="2" ry="2.6" fill="#1f242c" />
          <ellipse cx="48" cy="38" rx="2" ry="2.6" fill="#1f242c" />
          <path
            d="M34 46 Q40 50 46 46"
            stroke="#1f242c"
            strokeWidth="1.6"
            strokeLinecap="round"
            fill="none"
          />

          <g>
            <path
              d="M14 21.85 C14 7.1 26 2.55 40 2.2 C54 2.55 66 7.1 66 21.85 Z"
              fill={BRAND_UNIFORM.green}
              stroke={BRAND_UNIFORM.greenDeep}
              strokeWidth="0.75"
            />
            <path
              d="M14 21.5 L66 21.5 L64.8 25.65 L15.2 25.65 Z"
              fill={BRAND_LOGO.fries}
              stroke="#e07000"
              strokeWidth="0.45"
            />
            <circle cx="40" cy="3.3" r="1.85" fill={BRAND_LOGO.fries} />
          </g>
          {highlighted && (
            <circle
              cx="40"
              cy="36"
              r="30"
              fill="none"
              stroke={BRAND_LOGO.fries}
              strokeWidth="3"
            />
          )}
        </svg>
      </motion.div>
      <div
        className="mx-auto mt-0.5 px-1.5 py-[1px] rounded-md text-[9px] font-bold text-white shadow"
        style={{ background: uniformColor, width: "fit-content" }}
      >
        #{employeeId}
      </div>
    </motion.button>
  );
}
