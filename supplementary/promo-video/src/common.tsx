import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { C, MONO } from "./theme";

export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.45, 0, 0.55, 1);

const clamp = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

export const fade = (frame: number, start: number, dur = 25): number =>
  interpolate(frame, [start, start + dur], [0, 1], { easing: easeOut, ...clamp });

export const fadeUp = (
  frame: number,
  start: number,
  dur = 32,
  dist = 44,
): React.CSSProperties => ({
  opacity: fade(frame, start, dur),
  transform: `translateY(${interpolate(frame, [start, start + dur], [dist, 0], {
    easing: easeOut,
    ...clamp,
  })}px)`,
});

export const typedChars = (
  frame: number,
  start: number,
  text: string,
  charsPerFrame = 1,
): string => {
  const n = Math.max(0, Math.min(text.length, Math.floor((frame - start) * charsPerFrame)));
  return text.slice(0, n);
};

const NOISE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="220" height="220" filter="url(#n)"/></svg>`;
const NOISE_URL = `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(NOISE_SVG)}")`;

export const Grain: React.FC<{
  opacity?: number;
  blend?: React.CSSProperties["mixBlendMode"];
}> = ({ opacity = 0.07, blend = "multiply" }) => (
  <AbsoluteFill
    style={{
      backgroundImage: NOISE_URL,
      backgroundRepeat: "repeat",
      opacity,
      mixBlendMode: blend,
      pointerEvents: "none",
    }}
  />
);

export const Cursor: React.FC<{
  color?: string;
  width?: number;
  height?: number;
  marginLeft?: number;
}> = ({ color = C.amber, width = 22, height = 46, marginLeft = 10 }) => {
  const frame = useCurrentFrame();
  const visible = frame % 26 < 15;
  return (
    <span
      style={{
        display: "inline-block",
        width,
        height,
        marginLeft,
        background: color,
        opacity: visible ? 1 : 0,
        verticalAlign: "-0.08em",
      }}
    />
  );
};

export const Overline: React.FC<{
  color?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ color = C.inkSoft, children, style }) => (
  <div
    style={{
      fontFamily: MONO,
      fontSize: 25,
      fontWeight: 500,
      letterSpacing: "0.34em",
      textTransform: "uppercase",
      color,
      ...style,
    }}
  >
    {children}
  </div>
);
