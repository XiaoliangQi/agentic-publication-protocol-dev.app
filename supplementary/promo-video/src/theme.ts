import { loadFont as loadFraunces } from "@remotion/google-fonts/Fraunces";
import { loadFont as loadPlexMono } from "@remotion/google-fonts/IBMPlexMono";

const fraunces = loadFraunces("normal", {
  weights: ["400", "600", "900"],
  subsets: ["latin"],
});
loadFraunces("italic", {
  weights: ["400", "600", "900"],
  subsets: ["latin"],
});
const plexMono = loadPlexMono("normal", {
  weights: ["400", "500", "600"],
  subsets: ["latin"],
});

export const SERIF = fraunces.fontFamily;
export const MONO = plexMono.fontFamily;

export const C = {
  // paper world
  paper: "#F3EDDE",
  paperDeep: "#E9E0C9",
  ink: "#1C1812",
  inkSoft: "#5A5243",
  line: "#D5C9AC",
  // shared accent — academic stamp red
  accent: "#C23B17",
  // agent world
  night: "#0F0D09",
  nightCard: "#171410",
  nightBorder: "#2C2619",
  cream: "#F0E8D4",
  creamDim: "#968D75",
  amber: "#E2A33C",
  green: "#7FA661",
} as const;
