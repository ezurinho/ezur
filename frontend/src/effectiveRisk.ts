/**
 * Texto único para explicar la diferencia entre riesgo configurado y efectivo.
 *
 * La reducción por promoción no se guarda en `config.json`: la pantalla enseña
 * el valor configurado y el motor usa otro. Sin esta frase, el formulario
 * parece decir que arriesga el 1 % cuando en realidad arriesga el 0,25 %.
 */
function asNumber(value: number | string): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  // `Number("")` es 0: un campo vacío no es «riesgo cero», es un dato que
  // todavía no se puede comparar. Sin esto, la nota inventaría un 0 %.
  const text = value.trim();
  if (text === "") return null;
  const parsed = Number(text.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function shown(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function effectiveRiskNote(
  configured: number | string,
  effective: number | null | undefined,
): string | null {
  const configuredValue = asNumber(configured);
  const effectiveValue =
    effective === null || effective === undefined ? null : asNumber(effective);
  if (configuredValue === null || effectiveValue === null) return null;
  if (Math.abs(configuredValue - effectiveValue) <= 0.001) return null;
  return (
    `La promoción no está aprobada: el motor usa ${shown(effectiveValue)} % efectivo, ` +
    `no el ${shown(configuredValue)} % configurado.`
  );
}
