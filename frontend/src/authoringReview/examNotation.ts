/** Exam-facing typography only. Canonical math and evidence hashes stay intact. */
export function examMath(source: string): string {
  // Iranian exam papers use [x] for the integer-part/floor operation.
  // Also handles \left\lfloor ... \right\rfloor without parsing its contents.
  return source.replace(/\\lfloor\b/g, "[").replace(/\\rfloor\b/g, "]");
}

export function examOption(source: string): string {
  // Never alter prose or turn a word such as "fog" into a guessed operation.
  // Composition is already encoded explicitly as \circ in the stored math.
  return source.replace(/\$([^$]+)\$/g, (_, math: string) => `$${examMath(math)}$`);
}
