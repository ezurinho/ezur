import { useId, useState } from "react";

interface Props {
  term: string;
  text: string;
}

/**
 * A dot that explains a term in one sentence.
 *
 * The advanced UI is full of acronyms that are obvious to whoever wrote them.
 * This is the cheapest fix that does not dumb the screen down: nothing is
 * shown until someone asks, and the explanation is one hover or one Tab away.
 */
export function Info({ term, text }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span className="info" onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className="info-dot"
        aria-describedby={id}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((value) => !value)}
        data-info-term={term}
      >
        <span aria-hidden="true">i</span>
        <span className="sr-only">{`Qué es ${term}`}</span>
      </button>
      <span role="tooltip" id={id} className={open ? "info-bubble open" : "info-bubble"}>
        <b>{term}</b> {text}
      </span>
    </span>
  );
}
