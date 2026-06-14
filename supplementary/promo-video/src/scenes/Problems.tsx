import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { fade, fadeUp, Grain, Overline } from "../common";

export const PROBLEMS_DURATION = 250;

const Stamp: React.FC<{
  text: string;
  top: number;
  left: number;
  rotate: number;
  delay: number;
}> = ({ text, top, left, rotate, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const spr = spring({
    frame: frame - delay,
    fps,
    config: { damping: 16, stiffness: 220, mass: 0.7 },
  });
  const scale = interpolate(spr, [0, 1], [2.1, 1]);
  const opacity = interpolate(frame, [delay, delay + 5], [0, 0.94], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        top,
        left,
        transform: `rotate(${rotate}deg) scale(${scale})`,
        opacity,
        fontFamily: MONO,
        fontWeight: 600,
        fontSize: 36,
        letterSpacing: "0.16em",
        color: C.accent,
        border: `5px double ${C.accent}`,
        padding: "16px 30px",
        whiteSpace: "nowrap",
        background: "rgba(243, 237, 222, 0.82)",
      }}
    >
      {text}
    </div>
  );
};

const SkeletonLine: React.FC<{ width: string }> = ({ width }) => (
  <div style={{ height: 11, borderRadius: 6, background: C.paperDeep, width, marginBottom: 15 }} />
);

const PAGE_LINE_WIDTHS = [
  "100%", "97%", "99%", "93%", "100%", "96%", "60%",
  "100%", "98%", "94%", "100%", "91%", "97%", "44%",
];

export const Problems: React.FC = () => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [PROBLEMS_DURATION - 16, PROBLEMS_DURATION], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <AbsoluteFill style={{ flexDirection: "row", padding: "110px 130px", opacity: exit }}>
        {/* left column */}
        <div style={{ width: 760, paddingTop: 70 }}>
          <div style={fadeUp(frame, 6, 28, 20)}>
            <Overline>The problem</Overline>
          </div>
          <div style={{ height: 46 }} />
          <div
            style={{
              fontFamily: SERIF,
              fontWeight: 900,
              fontSize: 92,
              lineHeight: 1.06,
              color: C.ink,
              letterSpacing: "-0.01em",
              ...fadeUp(frame, 10),
            }}
          >
            Frozen at the moment of publication.
          </div>
          <div style={{ height: 80 }} />
          <div style={fadeUp(frame, 178)}>
            <span style={{ fontFamily: SERIF, fontWeight: 900, fontSize: 120, color: C.accent }}>
              26%
            </span>
            <div
              style={{
                fontFamily: MONO,
                fontSize: 26,
                lineHeight: 1.6,
                color: C.inkSoft,
                maxWidth: 640,
                marginTop: 12,
              }}
            >
              of sampled <em>Science</em> papers had main findings that could be
              reproduced — Stodden et al., PNAS 2018
            </div>
          </div>
        </div>

        {/* right: manuscript page with stamps */}
        <div style={{ flex: 1, position: "relative" }}>
          <div
            style={{
              position: "absolute",
              right: 60,
              top: 10,
              width: 620,
              padding: "60px 56px",
              background: "#FAF5E9",
              border: `1px solid ${C.line}`,
              boxShadow: "0 30px 70px rgba(28, 24, 18, 0.22)",
              transform: "rotate(1.6deg)",
              ...fadeUp(frame, 6, 30, 60),
            }}
          >
            <div
              style={{
                fontFamily: SERIF,
                fontWeight: 600,
                fontSize: 30,
                textAlign: "center",
                color: C.ink,
                lineHeight: 1.3,
              }}
            >
              On the Dynamics of a Promising Result
            </div>
            <div
              style={{
                fontFamily: SERIF,
                fontStyle: "italic",
                fontSize: 22,
                textAlign: "center",
                color: C.inkSoft,
                marginTop: 14,
                marginBottom: 44,
              }}
            >
              A. Author, B. Author, and C. Author
            </div>
            {PAGE_LINE_WIDTHS.slice(0, 7).map((w, i) => (
              <SkeletonLine key={`a-${i}`} width={w} />
            ))}
            <div
              style={{
                height: 170,
                border: `1px solid ${C.line}`,
                borderRadius: 4,
                margin: "20px 0 30px",
                background: C.paper,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: MONO,
                fontSize: 20,
                color: C.inkSoft,
              }}
            >
              Fig. 1 — (data not included)
            </div>
            {PAGE_LINE_WIDTHS.slice(7).map((w, i) => (
              <SkeletonLine key={`b-${i}`} width={w} />
            ))}
          </div>

          <Stamp text="STATIC" top={70} left={120} rotate={-8} delay={32} />
          <Stamp text="CAN'T BE UPDATED" top={290} left={230} rotate={5} delay={78} />
          <Stamp text="HARD TO REPRODUCE" top={520} left={90} rotate={-4} delay={124} />
          <Stamp text="KNOW-HOW LOST" top={730} left={280} rotate={7} delay={170} />
        </div>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 6,
          background: C.accent,
          opacity: 0.5 * fade(frame, 178, 20) * exit,
        }}
      />
      <Grain />
    </AbsoluteFill>
  );
};
