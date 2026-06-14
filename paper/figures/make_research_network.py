import random

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch


random.seed(17)


def add_arrow(ax, start, end, color, lw=1.15, alpha=0.75, rad=0.0):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=8.5,
        linewidth=lw,
        color=color,
        alpha=alpha,
        shrinkA=8,
        shrinkB=8,
        connectionstyle=f"arc3,rad={rad}",
        zorder=2,
    )
    ax.add_patch(arrow)


def make_nodes(counts_by_range, y_range):
    xs = []
    for n, x_range in counts_by_range:
        x_min, x_max = x_range
        bin_width = (x_max - x_min) / n
        xs.extend(
            x_min + (i + random.uniform(0.12, 0.88)) * bin_width
            for i in range(n)
        )
    xs = sorted(xs)
    nodes = []
    for x in xs:
        y = random.uniform(*y_range)
        nodes.append((x, y))
    return nodes


def edge_probability(source, target, span):
    midpoint = 0.5 * (source[0] + target[0])
    if target[0] < 0:
        base = 0.16
        length_bonus = 0.035 * smoothstep(span, 0.8, 1.8)
        span_penalty = 0.32
    elif source[0] > 0:
        base = 0.185
        length_bonus = 0.145 * smoothstep(span, 1.25, 3.6)
        span_penalty = 0.10
    else:
        regime = smoothstep(midpoint, -1.0, 1.0)
        base = 0.12 + 0.10 * regime
        length_bonus = 0.05 * regime * smoothstep(span, 1.25, 3.0)
        span_penalty = 0.22

    return max(0.0, base + length_bonus - span_penalty * (span / 4.2))


def make_edges(nodes, max_span=None):
    edges = []
    for i, source in enumerate(nodes):
        for j in range(i + 1, len(nodes)):
            target = nodes[j]
            span = target[0] - source[0]
            if max_span is not None and span > max_span:
                continue
            probability = edge_probability(source, target, span)
            if random.random() < probability:
                edges.append((source, target))
    return edges


def smoothstep(value, low, high):
    value = max(0.0, min(1.0, (value - low) / (high - low)))
    return value * value * (3.0 - 2.0 * value)


nodes = make_nodes(
    [
        (48, (-6.2, 0.0)),
        (82, (0.0, 6.2)),
    ],
    (-3.55, 3.55),
)
edges = make_edges(nodes, max_span=4.2)
left_nodes = [node for node in nodes if node[0] < 0]
right_nodes = [node for node in nodes if node[0] > 0]

fig, ax = plt.subplots(figsize=(12.0, 9.0), constrained_layout=True)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

ax.axvspan(-6.55, 0, color="#f2f4f7", zorder=0)
ax.axvspan(0, 6.55, color="#eef7f4", zorder=0)
ax.axvline(0, color="#5d6470", linewidth=1.1, linestyle=(0, (4, 4)), zorder=1)

for source, target in edges:
    midpoint = 0.5 * (source[0] + target[0])
    if midpoint < -0.25:
        add_arrow(ax, source, target, color="#6e7785", lw=1.0, alpha=0.52)
    elif midpoint > 0.25:
        add_arrow(ax, source, target, color="#2f6f73", lw=1.0, alpha=0.57)
    else:
        add_arrow(ax, source, target, color="#8a6f2a", lw=1.05, alpha=0.62)

lx, ly = zip(*left_nodes)
rx, ry = zip(*right_nodes)
ax.scatter(lx, ly, s=185, facecolor="#ffffff", edgecolor="#3f4651", linewidth=1.35, zorder=3)
ax.scatter(rx, ry, s=185, facecolor="#ffffff", edgecolor="#0f6b69", linewidth=1.35, zorder=3)

ax.text(-3.25, 4.05, "before agentification", ha="center", va="center", fontsize=12, color="#353b45")
ax.text(3.25, 4.05, "after agentification", ha="center", va="center", fontsize=12, color="#164f4d")

time_arrow = FancyArrowPatch(
    (-6.35, -4.35),
    (6.35, -4.35),
    arrowstyle="-|>",
    mutation_scale=13,
    linewidth=1.4,
    color="#2f3540",
    zorder=4,
)
ax.add_patch(time_arrow)
ax.text(5.6, -4.18, "time", ha="center", va="bottom", fontsize=11, color="#2f3540")

ax.set_xlim(-6.55, 6.55)
ax.set_ylim(-4.65, 4.35)
ax.set_xticks([])
ax.set_yticks([])
for spine in ax.spines.values():
    spine.set_visible(False)

output_base = "research_network"
fig.savefig(f"{output_base}.png", dpi=300)
fig.savefig(f"{output_base}.pdf")
fig.savefig(f"{output_base}.svg")
