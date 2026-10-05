import { IconAttachment } from "../icons";
import type { Attachment } from "../types";

interface AttachmentPreviewProps {
  attachment: Attachment;
}

/** Map content_type / file extension to a background colour for the icon. */
function getIconColor(attachment: Attachment): string {
  const ct = (attachment.content_type ?? "").toLowerCase();
  const ext = (attachment.filename ?? "").split(".").pop()?.toLowerCase() ?? "";

  if (ct === "application/pdf" || ext === "pdf") return "#ea4335";
  if (["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/csv"].includes(ct) || ["xlsx", "csv"].includes(ext)) return "#34a853";
  if (["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"].includes(ct) || ["doc", "docx"].includes(ext)) return "#4285f4";
  if (ct.startsWith("image/") || ["jpg", "jpeg", "png", "gif", "webp"].includes(ext)) return "#a142f4";
  return "#5f6368";
}

/** Return a short human-readable label for a MIME content type. */
function humanContentType(ct: string | undefined): string {
  if (!ct) return "Attachment";
  const map: Record<string, string> = {
    "application/pdf": "PDF",
    "application/msword": "Document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Spreadsheet",
    "text/csv": "CSV",
    "image/png": "PNG Image",
    "image/jpeg": "JPEG Image",
    "image/gif": "GIF Image",
    "application/octet-stream": "File",
  };
  if (map[ct]) return map[ct];
  if (ct.startsWith("image/")) return "Image";
  if (ct.startsWith("text/")) return "Text";
  return "Attachment";
}

/** Format file size: KB for small files, MB for >= 1024 KB. */
function formatSize(bytes: number | undefined): string {
  if (!bytes) return "";
  const kb = Math.ceil(bytes / 1024);
  if (kb >= 1024) {
    const mb = (kb / 1024).toFixed(1);
    return ` \u00b7 ${mb} MB`;
  }
  return ` \u00b7 ${kb} KB`;
}

export function AttachmentPreview({ attachment }: AttachmentPreviewProps) {
  const iconColor = getIconColor(attachment);

  return (
    <div className="gmail-attachment" aria-label={`Attachment ${attachment.filename}`}>
      <div
        className="gmail-attachment__icon"
        aria-hidden="true"
        style={{ background: iconColor, borderRadius: 4, padding: 4, display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <IconAttachment />
      </div>
      <div>
        <strong>{attachment.filename}</strong>
        <div style={{ color: "var(--color-text-muted)" }}>
          {humanContentType(attachment.content_type)}
          {formatSize(attachment.size_bytes)}
        </div>
      </div>
    </div>
  );
}
