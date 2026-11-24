import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  emptyLabel?: string;
  rowKey?: (row: T, index: number) => string;
}

export function DynamicTable<T extends Record<string, unknown>>({
  rows,
  columns,
  emptyLabel = "Sin registros",
  rowKey,
}: Props<T>) {
  if (rows.length === 0) {
    return <p className="empty">{emptyLabel}</p>;
  }
  return (
    <table className="dynamic-table">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.key}>{column.header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={rowKey ? rowKey(row, index) : String(index)}>
            {columns.map((column) => (
              <td key={column.key}>
                {column.render
                  ? column.render(row)
                  : row[column.key] === undefined || row[column.key] === null
                    ? "—"
                    : String(row[column.key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
