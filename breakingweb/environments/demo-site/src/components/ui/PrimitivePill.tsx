export function PrimitivePill({ name }: { name: string }) {
  return (
    <span className="text-[13px] px-4 py-[7px] border border-[var(--border)] rounded-xl text-[var(--text-secondary)] hover:border-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors duration-150">
      {name}
    </span>
  );
}
