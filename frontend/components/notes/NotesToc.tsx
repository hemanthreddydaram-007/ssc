import type { NoteSectionOut } from "@/lib/api/notes";

interface NotesTocProps {
  sections: readonly NoteSectionOut[];
  hasRecap: boolean;
}

export function NotesToc({ sections, hasRecap }: NotesTocProps) {
  if (sections.length === 0 && !hasRecap) {
    return null;
  }

  return (
    <nav
      aria-label="Table of contents"
      className="rounded-lg border bg-card p-4 shadow-sm print:hidden"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Contents
      </h2>
      <ul className="mt-2.5 space-y-1.5 text-sm">
        {sections.map((section, idx) => (
          <li key={section.key}>
            <a
              href={`#section-${section.key}`}
              className="block rounded px-2 py-1 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {idx + 1}. {section.title}
            </a>
          </li>
        ))}
        {hasRecap ? (
          <li>
            <a
              href="#section-one-minute-recap"
              className="block rounded px-2 py-1 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              1-Minute Recap
            </a>
          </li>
        ) : null}
      </ul>
    </nav>
  );
}
