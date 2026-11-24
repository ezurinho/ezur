import { useId } from "react";

interface Props {
  size?: number;
  title?: string;
}

/**
 * La marca de ezur: la E tallada en una placa redondeada.
 *
 * Una sola idea y tres formas —placa, E, nada más—: la E es la letra y también
 * tres barras de un gráfico. Las barras miden 6,5 de 48 con huecos de 3,25, así
 * que a 16 px siguen midiendo más de 2 px y el hueco no se cierra: el criterio
 * de las guías de marca es que por debajo de eso la marca se vuelve un borrón.
 *
 * La placa usa `--accent`, o sea el color que el operador haya elegido en el
 * selector de temas; las barras se recortan con el color del fondo
 * (`--logo-cut`), de modo que la letra se lee como un hueco y no como un trazo
 * encima. Vector puro: sin fuente, sin imagen, sin dependencia.
 */
export function Logo({ size = 30, title }: Props) {
  const shineId = `ezur-shine-${useId().replace(/:/g, "")}`;
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
        {/* Luz de arriba y sombra abajo: da volumen sin depender de un color fijo. */}
        <linearGradient id={shineId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity=".26" />
          <stop offset=".52" stopColor="#ffffff" stopOpacity=".03" />
          <stop offset="1" stopColor="#000000" stopOpacity=".22" />
        </linearGradient>
      </defs>
      <rect x="1.5" y="1.5" width="45" height="45" rx="12" fill="var(--accent, #37e0d0)" />
      <rect
        x="1.5"
        y="1.5"
        width="45"
        height="45"
        rx="12"
        fill={`url(#${shineId})`}
      />
      <g fill="var(--logo-cut, #070b11)">
        <rect x="13" y="11" width="6.5" height="26" />
        <rect x="13" y="11" width="21" height="6.5" />
        <rect x="13" y="20.75" width="17" height="6.5" />
        <rect x="13" y="30.5" width="23" height="6.5" />
      </g>
      <rect
        x="1.5"
        y="1.5"
        width="45"
        height="45"
        rx="12"
        fill="none"
        stroke="#ffffff"
        strokeOpacity=".16"
      />
    </svg>
  );
}
