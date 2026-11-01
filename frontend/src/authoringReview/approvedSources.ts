import { createContext } from "react";
/**
 * Approved source registry.
 *
 * Records carry opaque source ids, never URLs or filesystem paths. Only ids in
 * this map can produce an <img>; anything else renders an explicit missing-source
 * placeholder. The map is static and bundled, so model text cannot choose a
 * request destination.
 */

import pageSynthetic from "./assets/page-synthetic.svg";
import cropQ1 from "./assets/crop-q1.svg";
import cropQ5 from "./assets/crop-q5.svg";
import figureParabola from "./assets/figure-parabola.svg";
import answerKey from "./assets/answer-key.svg";
import type { ApprovedSource } from "./types";

export const APPROVED_SOURCES: Readonly<Record<string, ApprovedSource>> = {
  "src:page:synthetic": {
    id: "src:page:synthetic",
    kind: "page",
    src: pageSynthetic,
    alt: "صفحهٔ ساختگی دفترچهٔ ریاضی، بدون محتوای واقعی آزمون",
    width: 760,
    height: 520,
  },
  "src:crop:q1": {
    id: "src:crop:q1",
    kind: "crop",
    src: cropQ1,
    alt: "برش ساختگی پرسش یک",
    width: 720,
    height: 240,
  },
  "src:crop:q5": {
    id: "src:crop:q5",
    kind: "crop",
    src: cropQ5,
    alt: "برش ساختگی پرسش پنج با ارجاع به نمودار",
    width: 720,
    height: 250,
  },
  "src:figure:parabola": {
    id: "src:figure:parabola",
    kind: "figure",
    src: figureParabola,
    alt: "نمودار ساختگی سهمی",
    width: 520,
    height: 360,
  },
  "src:answer:key": {
    id: "src:answer:key",
    kind: "answer",
    src: answerKey,
    alt: "برگهٔ کلید پاسخ ساختگی",
    width: 420,
    height: 320,
  },
};

/**
 * Resolve a record's approved source id. Unknown ids, paths, URLs and
 * protocol-relative strings all resolve to null.
 */
export function resolveApprovedSource(id: string | null | undefined): ApprovedSource | null {
  if (!id) return null;
  if (!Object.prototype.hasOwnProperty.call(APPROVED_SOURCES, id)) return null;
  return APPROVED_SOURCES[id];
}

export const SourceResolverContext = createContext(resolveApprovedSource);
