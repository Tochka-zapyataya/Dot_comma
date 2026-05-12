function hash32(input: number | string): number {
  const str = String(input);
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

const SKIN_TONES = ["#f6cfa3", "#e7b48a", "#cf9670", "#a86d4a", "#6e4326"];

const HAIR_COLORS = [
  "#1f2937",
  "#3f3530",
  "#6b4423",
  "#a16f3a",
  "#d49a4f",
  "#7a1f1f",
  "#5c3a8c",
];

/** Зелёная форма в фирменных тонах сети. */
export const BRAND_UNIFORM = {
  green: "#004A32",
  greenDeep: "#003428",
  /** Светлее основы — воротник / козырёк. */
  trim: "#0d6b4c",
  black: "#1a1a1a",
} as const;

/** Знак на форме: кружок + «фри» (как в официальном логотипе). */
export const BRAND_LOGO = {
  patty: "#f04e23",
  fries: "#ff8200",
} as const;

export interface AvatarLook {
  skin: string;
  hair: string;
  hairStyle: 0 | 1 | 2;
}

export function avatarLook(employeeId: number | string): AvatarLook {
  const h1 = hash32(`skin:${employeeId}`);
  const h5 = hash32(`style:${employeeId}`);

  return {
    skin: SKIN_TONES[h1 % SKIN_TONES.length],
    hair: HAIR_COLORS[hash32(`hair:${employeeId}`) % HAIR_COLORS.length],
    hairStyle: (h5 % 3) as 0 | 1 | 2,
  };
}
