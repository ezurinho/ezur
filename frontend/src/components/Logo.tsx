import { useId } from "react";

interface Props {
  size?: number;
  title?: string;
}

/**
 * The ezur mark: an E cut out of a chamfered plate.
 *
 * Drawn as a filled plate with the letter carved as negative space, so the arms
 * open to the right edge and the shape survives 16 px. Vector only, no font, no
 * dependency. `useId` keeps the gradient id unique when React renders it twice.
 */
export function Logo({ size = 30, title }: Props) {
  const gradientId = `ezur-${useId().replace(/:/g, "")}`;
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
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7dfbea" />
          <stop offset=".55" stopColor="#37e0d0" />
          <stop offset="1" stopColor="#0f9a91" />
        </linearGradient>
        <clipPath id={`${gradientId}-plate`}>
          <path d="M6 13 13 6h29v29l-7 7H6Z" />
        </clipPath>
      </defs>
      <path d="M6 13 13 6h29v29l-7 7H6Z" fill={`url(#${gradientId})`} />
      <g clipPath={`url(#${gradientId}-plate)`} fill="var(--logo-cut, #070b11)">
        <rect x="13" y="11.2" width="28" height="5.4" />
        <rect x="13" y="21.3" width="22" height="5.4" />
        <rect x="13" y="31.4" width="28" height="5.4" />
        <rect x="13" y="11.2" width="5.8" height="25.6" />
      </g>
      <path
        d="M6 13 13 6h29v29l-7 7H6Z"
        fill="none"
        stroke="#9dfff2"
        strokeOpacity=".45"
        strokeWidth="1"
      />
    </svg>
  );
}
