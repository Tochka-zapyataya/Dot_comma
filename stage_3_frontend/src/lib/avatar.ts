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

const SHIRT_COLORS = [
  "#F26522",
  "#D9551A",
  "#FF8B4D",
  "#0F3D2A",
  "#0E8C3A",
  "#1A5638",
  "#0a6b2c",
  "#FFE7D6",
];

const ACCESSORY_PROBABILITY = 0.45;
const ACCESSORIES = ["cap", "glasses", "earring", "none"] as const;
type Accessory = (typeof ACCESSORIES)[number];

export interface AvatarLook {
  skin: string;
  hair: string;
  shirt: string;
  accessory: Accessory;
  hairStyle: 0 | 1 | 2;
}

export function avatarLook(employeeId: number | string): AvatarLook {
  const h1 = hash32(`skin:${employeeId}`);
  const h2 = hash32(`hair:${employeeId}`);
  const h3 = hash32(`shirt:${employeeId}`);
  const h4 = hash32(`acc:${employeeId}`);
  const h5 = hash32(`style:${employeeId}`);

  const accessory: Accessory =
    (h4 % 1000) / 1000 < ACCESSORY_PROBABILITY
      ? ACCESSORIES[h4 % (ACCESSORIES.length - 1)]
      : "none";

  return {
    skin: SKIN_TONES[h1 % SKIN_TONES.length],
    hair: HAIR_COLORS[h2 % HAIR_COLORS.length],
    shirt: SHIRT_COLORS[h3 % SHIRT_COLORS.length],
    accessory,
    hairStyle: (h5 % 3) as 0 | 1 | 2,
  };
}
