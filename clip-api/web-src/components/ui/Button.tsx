import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";

// The one button. Primary: white with black text (one per view). Secondary: the quieter action beside it.
// Ghost: no surface until hovered. Its classes are `.btn` in app/styles.css; the corner follows the theme
// (a pill on the public site, a rounded rectangle in the app).
export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANT: Record<ButtonVariant, string> = { primary: "primary", secondary: "ghost", ghost: "quiet" };
const SIZE: Record<ButtonSize, string> = { sm: "small", md: "", lg: "btn-lg" };

export const buttonClass = (variant: ButtonVariant = "primary", size: ButtonSize = "md", extra = "") =>
  ["btn", VARIANT[variant], SIZE[size], extra].filter(Boolean).join(" ");

type Shared = { variant?: ButtonVariant; size?: ButtonSize; className?: string };
type AsButton = Shared & ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined };
type AsLink = Shared & AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

export function Button(props: AsButton | AsLink) {
  const { variant, size, className, ...rest } = props;
  const cls = buttonClass(variant, size, className);
  if (rest.href !== undefined) return <Link {...(rest as AsLink)} href={rest.href} className={cls} />;
  return <button type="button" {...(rest as AsButton)} className={cls} />;
}
