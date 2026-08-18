/**
 * Shared data shapes for the office pipeline (#147).
 *
 * The segment union and the lectionary day are the contract flowing through
 * web/render.js — the SPA, both CLIs, the QA validators and the unit suite
 * all consume them. Nothing states this contract today; these typedefs are
 * written once and referenced from the code that walks the shapes, so a
 * shape confusion fails at the call site instead of surfacing as a runtime
 * `undefined` (#141: a psalm in `psalm_sets` is a bare citation *or* an
 * object; `_shared` values are sometimes a list-wrapped field and sometimes
 * the block itself).
 */

/** A leaf segment: one said/sung line with a role. */
export interface TextSegment {
  type: 'leader' | 'response' | 'rubric' | 'label';
  text: string;
}

/** One group within an alternatives choice. */
export interface AltGroup {
  label: string;
  segments: Segment[];
}

/** A choice between alternative groups (canticle, affirmation, doxology…). */
export interface AlternativesSegment {
  type: 'alternatives';
  groups: AltGroup[];
}

/** A reference into the `_shared` block, resolved at render time. */
export interface SharedSegment {
  type: 'shared';
  key: string;
}

/** The segment union: everything walkSegments / renderSegments can meet. */
export type Segment = TextSegment | AlternativesSegment | SharedSegment;

/** A section value: a segment list, a single alternatives block, or a shared ref. */
export type SectionValue = Segment[] | AlternativesSegment | SharedSegment;

/** A psalm appointment: a bare citation, or an object with optional/omit marks. */
export type PsalmEntry =
  | string
  | { citation: string; optional?: boolean; omit?: Array<{ citation: string }> };

/** A lesson appointment: a bare citation or an optional-marked object. */
export type LessonEntry = string | { citation: string; optional: boolean };

/** One office (morning or evening) of a lectionary day. */
export interface LectionaryOffice {
  psalms?: PsalmEntry[];
  psalm_sets?: PsalmEntry[][];
  collect?: string;
  lessons?: LessonEntry[];
  lessons_pick?: string;
  rubric?: string;
  label?: string;
  alternate?: LectionaryOffice;
  title?: string;
  note?: string;
  colour?: string;
  rank?: string;
  year_note?: string;
  // Alternate offices carry `optional` — whether the alternate is offered at
  // all (ADR 0018); app.js reads it on the active office (app.js:982).
  optional?: boolean;
}

/** One note on a day or office (pastoral note, O Antiphon, sourcing…). */
export interface DayNote {
  type: string;
  text: string;
}

/** A day-level commemoration (secondary observance) shown alongside the day. */
export interface Commemoration {
  name: string;
  rank?: string;
  colour?: string;
}

/** A lectionary day entry (one date in data/lectionary/YYYY-MM.json). */
export interface LectionaryDay {
  date: string;
  name: string;
  rank: string;
  colour: string;
  eucharist?: string;
  morning: LectionaryOffice;
  evening: LectionaryOffice;
  observances?: string[];
  notes?: DayNote[];
  commemorations?: Commemoration[];
  commemoration_join?: string;
  collect_inline?: { name: string; text: string };
}
