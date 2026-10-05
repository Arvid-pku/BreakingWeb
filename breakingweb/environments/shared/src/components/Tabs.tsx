interface TabItem {
  label: string;
  value: string;
}

interface TabsProps {
  label: string;
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
}

export function Tabs({ label, items, value, onChange }: TabsProps) {
  return (
    <div className="wab-tabs" role="tablist" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          className="wab-tabs__trigger"
          data-active={item.value === value}
          aria-selected={item.value === value}
          aria-label={item.label}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
