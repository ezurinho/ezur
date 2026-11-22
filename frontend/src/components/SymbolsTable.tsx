import type { Instrument, Quote } from "../types";
import { formatValue } from "../utils";

interface Props {
  instruments: Instrument[];
  quotes: Record<string, Quote>;
}

export function SymbolsTable({ instruments, quotes }: Props) {
  if (instruments.length === 0) {
    return <p className="empty">Sin instrumentos configurados</p>;
  }
  return (
    <table className="symbols-table">
      <thead>
        <tr>
          <th>Instrumento</th>
          <th>Rol</th>
          <th>Último</th>
          <th>Var.</th>
        </tr>
      </thead>
      <tbody>
        {instruments.map((instrument) => {
          const quote = quotes[instrument.symbol];
          const change = quote?.change_pct ?? null;
          const tone = change === null ? "neutral" : change >= 0 ? "good" : "bad";
          return (
            <tr key={instrument.symbol} data-symbol={instrument.symbol}>
              <td>{instrument.symbol}</td>
              <td>{instrument.role}</td>
              <td>
                {formatValue(quote?.last ?? null, "price", instrument.decimals)}{" "}
                <small>{instrument.currency}</small>
              </td>
              <td className={`tone-${tone}`}>
                {formatValue(change, "pct", instrument.decimals)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
