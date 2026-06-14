import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { easeOut, fadeUp, Grain, Overline } from "../common";

export const REPO_DURATION = 300;

type TreeLine = { text: string; note?: string; hi?: boolean };

const TREE: TreeLine[] = [
  { text: "my-paper/" },
  { text: "├─ AGENTS.md", note: "← the paper agent's brief", hi: true },
  { text: "├─ README.md", note: "human overview" },
  { text: "├─ LICENSE" },
  { text: "├─ paper/", note: "canonical manuscript" },
  { text: "├─ code/", note: "figure-reproduction map" },
  { text: "├─ data/", note: "datasets & provenance" },
  { text: "├─ environment/", note: "exact setup" },
  { text: "├─ supplementary/", note: "notes · know-how" },
  { text: "└─ skills/", note: "optional agent skills" },
];

const Row: React.FC<{ line: TreeLine; delay: number }> = ({ line, delay }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [delay, delay + 14], [0, 1], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const x = interpolate(frame, [delay, delay + 18], [-22, 0], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        opacity,
        transform: `translateX(${x}px)`,
        marginBottom: 21,
      }}
    >
      <span
        style={{
          fontFamily: MONO,
          fontSize: 31,
          fontWeight: line.hi ? 600 : 400,
          color: line.hi ? C.amber : C.cream,
          whiteSpace: "pre",
        }}
      >
        {line.text}
      </span>
      {line.note ? (
        <span
          style={{
            fontFamily: MONO,
            fontSize: 23,
            color: line.hi ? C.amber : C.creamDim,
            marginLeft: 28,
            opacity: line.hi ? 0.95 : 0.75,
          }}
        >
          {line.note}
        </span>
      ) : null}
    </div>
  );
};

export const Repo: React.FC = () => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [REPO_DURATION - 16, REPO_DURATION], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.night }}>
      <AbsoluteFill
        style={{
          flexDirection: "row",
          alignItems: "center",
          padding: "0 130px",
          gap: 90,
          opacity: exit,
        }}
      >
        {/* left column */}
        <div style={{ width: 740 }}>
          <div style={fadeUp(frame, 4, 26, 18)}>
            <Overline color={C.amber}>The publication object</Overline>
          </div>
          <div style={{ height: 42 }} />
          <div
            style={{
              fontFamily: SERIF,
              fontWeight: 900,
              fontSize: 88,
              lineHeight: 1.08,
              color: C.cream,
              letterSpacing: "-0.01em",
              ...fadeUp(frame, 12),
            }}
          >
            The repository{" "}
            <em style={{ fontStyle: "italic", color: C.accent }}>is</em> the
            publication.
          </div>
          <div style={{ height: 44 }} />
          <div
            style={{
              fontFamily: SERIF,
              fontSize: 34,
              lineHeight: 1.55,
              color: C.creamDim,
              ...fadeUp(frame, 44),
            }}
          >
            Not a PDF with a code link — one versioned object carrying the
            manuscript, the materials, and an agent that knows its way around.
          </div>
          <div style={{ height: 56 }} />
          <div
            style={{
              fontFamily: MONO,
              fontSize: 26,
              color: C.green,
              ...fadeUp(frame, 225, 28, 20),
            }}
          >
            ✓ tag · commit · manifest — author-approved
          </div>
        </div>

        {/* right: terminal card */}
        <div
          style={{
            flex: 1,
            background: C.nightCard,
            border: `1px solid ${C.nightBorder}`,
            borderRadius: 18,
            boxShadow: "0 40px 90px rgba(0,0,0,0.5)",
            overflow: "hidden",
            ...fadeUp(frame, 18, 32, 50),
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "22px 30px",
              borderBottom: `1px solid ${C.nightBorder}`,
            }}
          >
            {["#E5604C", "#E2A33C", "#7FA661"].map((c) => (
              <div key={c} style={{ width: 17, height: 17, borderRadius: 9, background: c, opacity: 0.9 }} />
            ))}
            <div style={{ fontFamily: MONO, fontSize: 23, color: C.creamDim, marginLeft: 16 }}>
              my-paper — tagged v1.0.0
            </div>
          </div>
          <div style={{ padding: "40px 44px 26px" }}>
            {TREE.map((line, i) => (
              <Row key={line.text} line={line} delay={36 + i * 13} />
            ))}
          </div>
        </div>
      </AbsoluteFill>
      <Grain opacity={0.05} blend="screen" />
    </AbsoluteFill>
  );
};
