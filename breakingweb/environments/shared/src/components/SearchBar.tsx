import type { FormEvent } from "react";

import { classNames } from "../utils/format";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
}

export function SearchBar({
  value,
  onChange,
  onSubmit,
  placeholder = "Search",
  ariaLabel = "Search",
  className,
}: SearchBarProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit?.();
  };

  return (
    <form className={classNames("wab-searchbar", className)} role="search" onSubmit={handleSubmit}>
      <span aria-hidden="true">⌕</span>
      <input
        className="wab-searchbar__input"
        aria-label={ariaLabel}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
      <button type="submit" className="wab-searchbar__submit" aria-label="Run search">
        Search
      </button>
    </form>
  );
}
