import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { classNames } from "../utils/format";

interface BaseFieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  className?: string;
}

interface InputFieldProps extends BaseFieldProps {
  as?: "input";
  inputProps?: InputHTMLAttributes<HTMLInputElement>;
}

interface TextareaFieldProps extends BaseFieldProps {
  as: "textarea";
  inputProps?: TextareaHTMLAttributes<HTMLTextAreaElement>;
}

interface SelectFieldProps extends BaseFieldProps {
  as: "select";
  inputProps?: SelectHTMLAttributes<HTMLSelectElement>;
  children: ReactNode;
}

type FormFieldProps = InputFieldProps | TextareaFieldProps | SelectFieldProps;

export function FormField(props: FormFieldProps) {
  const { id, label, hint, error, className } = props;

  return (
    <label htmlFor={id} className={classNames("wab-form-field", className)}>
      <span className="wab-form-field__label">{label}</span>
      {props.as === "textarea" ? (
        <textarea id={id} className="wab-textarea" aria-invalid={Boolean(error)} {...props.inputProps} />
      ) : props.as === "select" ? (
        <select id={id} className="wab-select" aria-invalid={Boolean(error)} {...props.inputProps}>
          {props.children}
        </select>
      ) : (
        <input id={id} className="wab-input" aria-invalid={Boolean(error)} {...props.inputProps} />
      )}
      {hint ? <span className="wab-form-field__hint">{hint}</span> : null}
      {error ? <span className="wab-form-field__error">{error}</span> : null}
    </label>
  );
}
