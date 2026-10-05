interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  const pages = Array.from({ length: totalPages }, (_, index) => index + 1);

  return (
    <nav className="wab-pagination" aria-label="Pagination">
      {pages.map((item) => (
        <button
          key={item}
          type="button"
          className="wab-pagination__button"
          aria-current={item === page ? "page" : undefined}
          aria-label={`Go to page ${item}`}
          onClick={() => onPageChange(item)}
        >
          {item}
        </button>
      ))}
    </nav>
  );
}
