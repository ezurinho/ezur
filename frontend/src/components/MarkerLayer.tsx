import { MARKER_KINDS, type Marker } from "../types";

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
          {marker.label ? <span>{marker.label}</span> : null}
        </li>
      ))}
    </ul>
  );
}
