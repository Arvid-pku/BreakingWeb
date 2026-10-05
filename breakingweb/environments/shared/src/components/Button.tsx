import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

import { classNames } from "../utils/format";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

export function Button({
  variant = "secondary",
  className,
  type = "button",
  children,
  ...props
}: PropsWithChildren<ButtonProps>) {
  return (
    <button
      type={type}
      className={classNames("wab-button", `wab-button--${variant}`, className)}
      {...props}
    >
      {children}
    </button>
  );
}
