// devAssert — fail loudly in development when a primitive is used against
// its accessibility contract (for example an icon-only button without a
// label). Production builds skip the check (Vite folds `import.meta.env.DEV`
// to false), so a missed case degrades instead of crashing the workshop.
export function devAssert(condition: unknown, message: string): asserts condition {
  if (import.meta.env.DEV && !condition) {
    throw new Error(`[src/ui] ${message}`);
  }
}

/** Join class names, skipping falsy entries. */
export function cx(...names: Array<string | false | null | undefined>): string {
  return names.filter(Boolean).join(' ');
}
