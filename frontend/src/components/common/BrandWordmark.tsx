// Transparent, trimmed copy of public/gradex-logo.png (that file has an opaque cream background).
export const GRADEX_LOGO_SRC = "/gradex-logo-transparent.png";

type BrandWordmarkProps = {
  className?: string;
};

export function BrandWordmark({ className }: BrandWordmarkProps) {
  if (GRADEX_LOGO_SRC) {
    // The class goes on a wrapper: the stylesheet sizes the logo as `.tg-brand-name img` /
    // `.brand-word img` (and hides the old icon tile via :has(... img)). With the class on the <img>
    // itself none of those rules matched and the logo rendered at its full 412x315 size.
    return (
      <span className={className}>
        <img src={GRADEX_LOGO_SRC} alt="GradeX" />
      </span>
    );
  }

  return <span className={className}>GradeX</span>;
}
