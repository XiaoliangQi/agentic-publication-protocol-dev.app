import React from "react";
import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { easeOut, fadeUp, Grain, Overline } from "../common";

export const NETWORK_DURATION = 240;

type Node = { x: number; y: number };

const NODES: Node[] = Array.from({ length: 40 }, (_, i) => ({
  x: 100 + random(`nx-${i}`) * 1720,
  y: 130 + random(`ny-${i}`) * 820,
}));

const dist = (a: Node, b: Node) =>
  Math.hypot(a.x - b.x, a.y - b.y);

const SHORT_LINKS: Array<[number, number]> = [];
const LONG_LINKS: Array<[number, number]> = [];
for (let i = 0; i < NODES.length; i++) {
  for (let j = i + 1; j < NODES.length; j++) {
    const d = dist(NODES[i], NODES[j]);
    if (d < 250) {
      SHORT_LINKS.push([i, j]);
    } else if (d > 520 && random(`link-${i}-${j}`) < 0.055) {
      LONG_LINKS.push([i, j]);
    }
  }
}

const SWITCH = 82; // frame where the network "wakes up"

export const Network: React.FC = () => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [NETWORK_DURATION - 16, NETWORK_DURATION], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const beforeOpacity = interpolate(frame, [SWITCH - 12, SWITCH + 6], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const afterOpacity = interpolate(frame, [SWITCH + 4, SWITCH + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.night }}>
      <svg
        width="1920"
        height="1080"
        viewBox="0 0 1920 1080"
        style={{ position: "absolute", inset: 0, opacity: exit }}
      >
        {SHORT_LINKS.map(([i, j], k) => {
          const appear = interpolate(frame, [8 + (k % 9) * 4, 26 + (k % 9) * 4], [0, 0.22], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <line
              key={`s-${k}`}
              x1={NODES[i].x}
              y1={NODES[i].y}
              x2={NODES[j].x}
              y2={NODES[j].y}
              stroke={C.creamDim}
              strokeWidth={1.5}
              opacity={appear}
            />
          );
        })}
        {LONG_LINKS.map(([i, j], k) => {
          const delay = SWITCH + 8 + k * 4;
          const draw = interpolate(frame, [delay, delay + 30], [1, 0], {
            easing: easeOut,
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const glow = interpolate(frame, [delay, delay + 14], [0, 0.55], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <line
              key={`l-${k}`}
              x1={NODES[i].x}
              y1={NODES[i].y}
              x2={NODES[j].x}
              y2={NODES[j].y}
              stroke={C.amber}
              strokeWidth={2}
              pathLength={1}
              strokeDasharray={1}
              strokeDashoffset={draw}
              opacity={glow}
            />
          );
        })}
        {NODES.map((n, i) => {
          const appear = interpolate(frame, [(i % 10) * 3, 16 + (i % 10) * 3], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const lit = interpolate(
            frame,
            [SWITCH + 10 + (i % 12) * 5, SWITCH + 30 + (i % 12) * 5],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          );
          const r = 5.5 + lit * 2.5;
          return (
            <circle
              key={`n-${i}`}
              cx={n.x}
              cy={n.y}
              r={r}
              fill={lit > 0.5 ? C.amber : C.creamDim}
              opacity={appear * (0.55 + lit * 0.45)}
            />
          );
        })}
      </svg>

      {/* labels */}
      <div style={{ position: "absolute", left: 130, top: 110, opacity: exit }}>
        <div style={fadeUp(frame, 4, 26, 18)}>
          <Overline color={C.amber}>The research network</Overline>
        </div>
        <div style={{ height: 34 }} />
        <div style={{ position: "relative", height: 180, width: 1300 }}>
          <div
            style={{
              position: "absolute",
              fontFamily: SERIF,
              fontWeight: 900,
              fontSize: 76,
              color: C.cream,
              opacity: beforeOpacity,
              ...(frame < SWITCH ? fadeUp(frame, 10) : {}),
            }}
          >
            Today: a sparse archive.
          </div>
          <div
            style={{
              position: "absolute",
              fontFamily: SERIF,
              fontWeight: 900,
              fontSize: 76,
              color: C.cream,
              opacity: afterOpacity,
            }}
          >
            With paper agents:{" "}
            <em style={{ fontStyle: "italic", color: C.amber }}>a living network.</em>
          </div>
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 130,
          bottom: 90,
          fontFamily: MONO,
          fontSize: 27,
          color: C.creamDim,
          opacity: exit,
          ...fadeUp(frame, SWITCH + 36, 28, 18),
        }}
      >
        papers that talk to each other — a phase transition in how science compounds
      </div>
      <Grain opacity={0.05} blend="screen" />
    </AbsoluteFill>
  );
};
