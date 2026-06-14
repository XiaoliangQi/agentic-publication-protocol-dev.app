import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { C, MONO } from "../theme";
import { Cursor, Grain, typedChars } from "../common";

export const FLIP_DURATION = 110;

const PROMPT_TEXT = "what if you could ask the paper itself?";

export const Flip: React.FC = () => {
  const frame = useCurrentFrame();
  const radius = interpolate(frame, [0, 38], [0, 1500], {
    easing: Easing.bezier(0.7, 0, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const typed = typedChars(frame, 42, PROMPT_TEXT, 0.85);

  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <Grain />
      <AbsoluteFill
        style={{
          background: C.night,
          clipPath: `circle(${radius}px at 50% 50%)`,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <div
          style={{
            fontFamily: MONO,
            fontSize: 46,
            fontWeight: 500,
            color: C.cream,
            display: "flex",
            alignItems: "center",
          }}
        >
          <span style={{ color: C.amber, marginRight: 24 }}>❯</span>
          <span>{typed}</span>
          <Cursor />
        </div>
        <Grain opacity={0.05} blend="screen" />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
