import { ZONE_KINDS, type Zone } from "../types";

interface Props {
  zones: Zone[];
}

const ZONE_WORD: Record<string, string> = {
  band: "rango",
  line: "línea",
  box: "caja",
  region: "región",
};

/**
 * Renders zones by kind only. A kind the contract does not define is skipped,
 * never guessed: the backend is the authority on what a zone means.
 */
export function ZoneLayer({ zones }: Props) {
  const known = zones.filter((zone) => ZONE_KINDS.includes(zone.kind as never));
  return (
    <div className="zone-layer">
      {known.map((zone) => {
        // Una zona sin etiqueta no puede desaparecer: el contenedor no pinta
        // nada y el flex se queda con un hueco de cero píxeles.
        const label = zone.label ?? ZONE_WORD[zone.kind];
        return (
          <div
            key={zone.id}
            className={`zone zone-${zone.kind}${zone.active ? "" : " zone-inactive"}`}
            data-zone
            data-kind={zone.kind}
            data-active={zone.active}
            title={label}
          >
            <span className="zone-label">{label}</span>
          </div>
        );
      })}
    </div>
  );
}
