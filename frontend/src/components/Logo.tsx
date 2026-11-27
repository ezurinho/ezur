import { useId } from "react";

interface Props {
  size?: number;
  title?: string;
}

/**
 * La marca de ezur: una insignia de carbono con la E espectral.
 *
 * La placa es un octógono con facetas, no un cuadrado redondeado: los chaflanes
 * y el borde luminoso le dan el aire de una pieza mecanizada. La E ya no es un
 * hueco plano, sino tres barras inclinadas con degradado esmeralda: a 16 px la
 * inclinación se pierde, pero el trazo sigue midiendo casi 2 px y la letra se
 * lee; a 48 px se ve el detalle de las facetas.
 *
 * Usa `--accent` para el borde y el brillo, y `--logo-cut` para la sombra de la
 * placa, de modo que el color siga al tema elegido. Vector puro, sin fuente ni
 * imagen.
 */
export function Logo({ size = 30, title }: Props) {
  const uid = useId().replace(/:/g, "");
  const plateId = `ezur-plate-${uid}`;
  const edgeId = `ezur-edge-${uid}`;
  const letterId = `ezur-letter-${uid}`;
  const shadeId = `ezur-shade-${uid}`;
  const clipId = `ezur-clip-${uid}`;
  const plate = "M13 2.5h22l10.5 10.5v22L35 45.5H13L2.5 35V13z";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role={title ? "img" : "presentation"}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      data-logo="ezur"
    >
      <defs>
        <linearGradient id={plateId} x1="6" y1="3" x2="41" y2="46" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#183122" />
          <stop offset=".48" stopColor="#0b1710" />
          <stop offset="1" stopColor="#050b07" />
        </linearGradient>
        <linearGradient id={edgeId} x1="3" y1="2" x2="45" y2="46" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#d8ffe1" />
          <stop offset=".38" stopColor="var(--accent, #35ea86)" />
          <stop offset="1" stopColor="#0b7042" />
        </linearGradient>
        <linearGradient id={letterId} x1="13" y1="7" x2="37" y2="41" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#effff5" />
          <stop offset=".48" stopColor="#86ffbb" />
          <stop offset="1" stopColor="#22c46f" />
        </linearGradient>
        <linearGradient id={shadeId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity=".16" />
          <stop offset=".55" stopColor="#ffffff" stopOpacity=".02" />
          <stop offset="1" stopColor="#000000" stopOpacity=".32" />
        </linearGradient>
        <clipPath id={clipId}>
          <path d={plate} />
        </clipPath>
      </defs>

      <path d={plate} fill={`url(#${plateId})`} />
      <g clipPath={`url(#${clipId})`}>
        {/* Dos facetas opuestas: la izquierda recibe la luz, la derecha se hunde. */}
        <path d="M2.5 13 13 2.5h11v43H13L2.5 35z" fill={`url(#${shadeId})`} />
        <path d="M35 2.5 45.5 13v22L35 45.5 24 48V0z" fill="#000000" opacity=".26" />
        <path d="M2.5 35 13 45.5h22l10.5-10.5" fill="none" stroke="#000000" opacity=".24" />
      </g>
      <path d={plate} fill="none" stroke={`url(#${edgeId})`} strokeWidth="1.4" />

      {/* Una sola forma compuesta: las barras se funden sin costuras internas. */}
      <path
        fill={`url(#${letterId})`}
        d="M13.2 10.6 19 9.4v30l-5.8 1.2z M13.2 10.6 36.4 6.7l1.1 7.3-24.3 4.7z M13.2 20.9 31.2 17.6l1.1 7.3-19.1 3.8z M13.2 31.3 37.4 27.3l1.1 7.3-25.3 4.5z"
      />

      {/* Tres trazos espectrales en el borde derecho: desaparecen a 16 px,
          pero a tamaño de cabecera dan la sensación de telemetría. */}
      <g stroke="var(--accent, #35ea86)" strokeLinecap="round" opacity=".42">
        <path d="M39.5 17.5h3.1" />
        <path d="M40.2 23.5h2.4" />
        <path d="M40.9 29.5h1.7" />
      </g>
    </svg>
  );
}
