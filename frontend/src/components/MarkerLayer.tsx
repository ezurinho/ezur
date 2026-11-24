import { MARKER_KINDS, type Marker } from "../types";

const MARKER_WORD: Record<string, string> = {
  entry: "entrada",
  exit: "salida",
  phase: "fase",
  note: "nota",
  warning: "aviso",
};

interface Props {
  markers: Marker[];
}

export function MarkerLayer({ markers }: Props) {
  const known = markers.filter((marker) =>
    MARKER_KINDS.includes(marker.kind as never),
  );
  return (
    <ul className="marker-layer">
      {known.map((marker) => (
        <li
          key={marker.id}
          className={`marker marker-${marker.kind}`}
          data-marker
          data-kind={marker.kind}
        >
          {marker.label ? <span>{marker.label}</span> : <span>{MARKER_WORD[marker.kind] ?? marker.kind}</span>}
        </li>
      ))}
    </ul>
  );
}
