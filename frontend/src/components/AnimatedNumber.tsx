import { useCountUp } from "../motion";

interface Props {
  value: number;
  format?: (value: number) => string;
  className?: string;
}

const plain = (value: number) =>
  value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** A number that moves toward its value instead of teleporting. */
export function AnimatedNumber({ value, format = plain, className }: Props) {
  const display = useCountUp(value);
  return <span className={className}>{format(display)}</span>;
}
