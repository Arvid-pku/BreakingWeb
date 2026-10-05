import { DocsSidebar } from "@/components/docs/DocsSidebar";
import { TableOfContents } from "@/components/docs/TableOfContents";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-center pt-[80px] pb-24 px-6">
      {/* Left sidebar */}
      <aside className="hidden lg:block w-[200px] shrink-0 sticky top-[80px] self-start max-h-[calc(100vh-100px)] overflow-y-auto pr-6">
        <DocsSidebar />
      </aside>

      {/* Content */}
      <main data-docs-content className="min-w-0 max-w-[720px] w-full px-6">
        {children}
      </main>

      {/* Right sidebar — TOC */}
      <aside className="hidden xl:block w-[180px] shrink-0 sticky top-[80px] self-start max-h-[calc(100vh-100px)] overflow-y-auto pl-6">
        <TableOfContents />
      </aside>
    </div>
  );
}
