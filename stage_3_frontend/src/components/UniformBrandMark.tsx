import { BRAND_LOGO } from "../lib/avatar";

interface UniformBrandMarkProps {
  /** Масштаб маркера; при < 1 компактнее на груди. */
  scale?: number;
}

/**
 * Круг чуть ниже и левее — под первой «фри», ближе к ней; равные вертикальные шаги;
 * одинаковый fryHGap от круга до 1-й и между палочками.
 */
export function UniformBrandMark({ scale = 1 }: UniformBrandMarkProps) {
  const fryW = 1.85;
  const fryRx = fryW / 2;
  const fryAngle = -33;

  /** Ниже и левее прежнего — визуально «под» первой линией, чуть ближе слева к ней. */
  const cx = 4.75;
  const cy = 13.55;
  const r = 2.32;

  const circleBottom = cy + r;

  const fryVStep = 0.52;
  const fry1Y = circleBottom - fryVStep;
  const fry2Y = circleBottom - 2 * fryVStep;

  const fryHGap = 3.45;
  const fry1X = cx + r + fryHGap;
  const fry2X = cx + r + 2 * fryHGap;

  return (
    <g transform={`scale(${scale})`}>
      <g transform="translate(-11.5, -9.6)">
        <circle cx={cx} cy={cy} r={r} fill={BRAND_LOGO.patty} />
        <g transform={`translate(${fry1X}, ${fry1Y}) rotate(${fryAngle})`}>
          <rect
            x={-fryRx}
            y={-8.35}
            width={fryW}
            height={8.35}
            rx={fryRx}
            fill={BRAND_LOGO.fries}
          />
        </g>
        <g transform={`translate(${fry2X}, ${fry2Y}) rotate(${fryAngle})`}>
          <rect
            x={-fryRx}
            y={-9.55}
            width={fryW}
            height={9.55}
            rx={fryRx}
            fill={BRAND_LOGO.fries}
          />
        </g>
      </g>
    </g>
  );
}
