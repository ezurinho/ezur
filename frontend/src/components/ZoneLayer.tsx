import { ZONE_KINDS, type Zone } from "../types";

interface Props {
  zones: Zone[];
}

/**
 * Renders zones by kind only. A kind the contract does not define is skipped,
 * never guessed: the backend is the authority on what a zone means.
 */
export function ZoneLayer({ zones }: Props) {
  const known = zones.filter((zone) => ZONE_KINDS.includes(zone.kind as never));
  return (
    <div className="zone-layer">
      {known.map((zone) => (
        <div
          key={zone.id}
          className={`zone zone-${zone.kind}${zone.active ? "" : " zone-inactive"}`}
          data-zone
          data-kind={zone.kind}
          data-active={zone.active}
          title={zone.label ?? undefined}
        >
          {zone.label ? <span className="zone-label">{zone.label}</span> : null}
        </div>
      ))}
    </div>
  );
}
