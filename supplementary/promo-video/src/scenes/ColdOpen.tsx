import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { fadeUp, Grain, Overline } from "../common";

export const COLD_OPEN_DURATION = 165;

const headline: React.CSSProperties = {
  fontFamily: SERIF,
  fontWeight: 600,
  fontSize: 104,
  lineHeight: 1.1,
  color: C.ink,
  letterSpacing: "-0.01em",
};

export const ColdOpen: React.FC = () => {
  const frame = useCurrentFrame();
  const exit = interpolate(
    frame,
    [COLD_OPEN_DURATION - 16, COLD_OPEN_DURATION],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ background: C.paper }}>
      {/* ledger margin rules */}
      <div style={{ position: "absolute", left: 150, top: 0, bottom: 0, width: 3, background: C.accent, opacity: 0.55 }} />
      <div style={{ position: "absolute", left: 168, top: 0, bottom: 0, width: 1, background: C.line }} />

      <AbsoluteFill style={{ justifyContent: "center", paddingLeft: 270, paddingRight: 160, opacity: exit }}>
        <div style={fadeUp(frame, 6, 24, 20)}>
          <Overline>The scientific paper · est. 1665</Overline>
        </div>
        <div style={{ height: 56 }} />
        <div style={{ ...headline, ...fadeUp(frame, 20) }}>A paper tells you</div>
        <div style={{ ...headline, ...fadeUp(frame, 30) }}>
          <em style={{ fontStyle: "italic", fontWeight: 900 }}>what</em> was discovered.
        </div>
        <div style={{ height: 44 }} />
        <div style={{ ...headline, color: C.accent, ...fadeUp(frame, 66) }}>
          It rarely tells you <em style={{ fontStyle: "italic", fontWeight: 900 }}>how</em>.
        </div>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          right: 90,
          bottom: 64,
          fontFamily: MONO,
          fontSize: 24,
          color: C.inkSoft,
          opacity: exit,
          ...fadeUp(frame, 96, 26, 16),
        }}
      >
        p. 1 of ∞
      </div>
      <Grain />
    </AbsoluteFill>
  );
};
