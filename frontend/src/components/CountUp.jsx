import { useEffect, useRef, useState } from "react";
import { animate } from "framer-motion";

// Spring-eased number that counts up from its previous value whenever it
// changes — the "numbers animate" beat, used for every headline metric.
export default function CountUp({ value, decimals = 0, prefix = "", suffix = "", className }) {
  const [display, setDisplay] = useState(value ?? 0);
  const prev = useRef(value ?? 0);

  useEffect(() => {
    const target = value ?? 0;
    const controls = animate(prev.current, target, {
      duration: 0.9,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(v),
    });
    prev.current = target;
    return () => controls.stop();
  }, [value]);

  const text = Number(display).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return <span className={className}>{prefix}{text}{suffix}</span>;
}
