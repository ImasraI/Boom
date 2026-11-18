import type { ReactNode } from "react";

export default function PageHeading({ eyebrow, title, description, icon, actions, children, className = "" }: {
  eyebrow?: string; title: string; description?: string; icon?: ReactNode;
  actions?: ReactNode; children?: ReactNode; className?: string;
}) {
  return <header className={`boom-page-heading ${className}`}>
    <div className="boom-heading-copy">
      {eyebrow && <p className="boom-eyebrow">{eyebrow}</p>}
      <div className="boom-heading-title">{icon && <span aria-hidden="true">{icon}</span>}<h1>{title}</h1></div>
      {description && <p className="boom-page-description">{description}</p>}
      {children}
    </div>
    {actions && <div className="boom-heading-actions">{actions}</div>}
  </header>;
}
