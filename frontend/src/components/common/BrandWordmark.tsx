export const GRADEX_LOGO_SRC = "/gradex-logo.png";

type BrandWordmarkProps = {
  className?: string;
};

export function BrandWordmark({ className }: BrandWordmarkProps) {
  if (GRADEX_LOGO_SRC) {
    return <img className={className} src={GRADEX_LOGO_SRC} alt="GradeX" />;
  }

  return <span className={className}>GradeX</span>;
}
