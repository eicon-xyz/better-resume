import type { DimensionView } from "../../api/types";
import { buildRadar, ringPolygon } from "../../interview/radar";
import styles from "./RadarChart.module.css";

export interface RadarChartProps {
  dimensions: DimensionView[];
  title?: string;
}

/** Hand-drawn SVG radar (no chart library): stable in screenshots, zero runtime deps. */
export function RadarChart({ dimensions, title = "能力雷达" }: RadarChartProps) {
  const safe = dimensions.length >= 3 ? dimensions : padDimensions(dimensions);
  const geometry = buildRadar(safe);
  const size = geometry.center * 2;

  return (
    <figure className={styles.figure}>
      <svg
        className={styles.svg}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={title}
        data-testid="radar-chart"
      >
        {geometry.rings.map((ring) => (
          <polygon
            key={ring}
            className={styles.ring}
            points={ringPolygon(ring, { axes: safe.length })}
            data-ring={ring}
          />
        ))}

        {safe.map((dimension, index) => {
          const outer = ringPolygon(100, { axes: safe.length }).split(" ")[index];
          const [x, y] = (outer ?? "0,0").split(",");
          return (
            <line
              key={dimension.key}
              className={styles.axis}
              x1={geometry.center}
              y1={geometry.center}
              x2={Number(x)}
              y2={Number(y)}
            />
          );
        })}

        <polygon className={styles.area} points={geometry.polygon} />

        {geometry.points.map((point) => (
          <g key={point.key}>
            <circle className={styles.dot} cx={point.x} cy={point.y} r={3.5} />
            <text
              className={styles.label}
              x={labelPosition(point, geometry.center).x}
              y={labelPosition(point, geometry.center).y}
              textAnchor="middle"
            >
              {point.label} {point.score.toFixed(0)}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}

function padDimensions(dimensions: DimensionView[]): DimensionView[] {
  const defaults: DimensionView[] = [
    { key: "accuracy", label: "准确性", score: 0 },
    { key: "depth", label: "深度", score: 0 },
    { key: "coverage", label: "要点覆盖", score: 0 },
  ];
  return [...dimensions, ...defaults.slice(dimensions.length)].slice(0, Math.max(3, dimensions.length));
}

function labelPosition(
  point: { x: number; y: number },
  center: number,
): { x: number; y: number } {
  const dx = point.x - center;
  const dy = point.y - center;
  const length = Math.hypot(dx, dy) || 1;
  return { x: point.x + (dx / length) * 18, y: point.y + (dy / length) * 18 };
}
