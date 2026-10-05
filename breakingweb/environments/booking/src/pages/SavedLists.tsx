import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { SavedList } from "../types";
import { useBookingLayout } from "../context";

export default function SavedLists() {
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();
  const { listId: deepLinkListId } = useParams<{ listId?: string }>();

  const [lists, setLists] = useState<SavedList[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(deepLinkListId ?? null);
  const [newListName, setNewListName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listSavedLists();
      setLists(data.lists);
    } catch {
      notify("Error", "Failed to load saved lists.");
    } finally {
      setLoading(false);
    }
  }, [api, sessionId, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreateList = async () => {
    const name = newListName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await api.createSavedList(name);
      setLists((prev) => [...prev, created]);
      setNewListName("");
      notify("List created", `"${created.name}" has been created.`);
    } catch {
      notify("Error", "Failed to create list.");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteList = async (listId: string, listName: string) => {
    try {
      await api.deleteSavedList(listId);
      setLists((prev) => prev.filter((l) => l.id !== listId));
      if (expandedId === listId) setExpandedId(null);
      notify("List deleted", `"${listName}" has been removed.`);
    } catch {
      notify("Error", "Failed to delete list.");
    }
  };

  const handleRemoveProperty = async (listId: string, propertyId: string) => {
    try {
      const updated = await api.removeFromSavedList(listId, propertyId);
      setLists((prev) =>
        prev.map((l) => (l.id === listId ? updated : l))
      );
      notify("Removed", "Property removed from list.");
    } catch {
      notify("Error", "Failed to remove property.");
    }
  };

  if (loading) {
    return <div className="bk-loading">Loading saved lists...</div>;
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 className="bk-section-title" style={{ marginBottom: 0 }}>
          My Saved Lists
        </h1>
      </div>

      {/* Create new list */}
      <div
        className="bk-card"
        style={{ padding: 16, marginBottom: 24, display: "flex", gap: 12, alignItems: "center" }}
      >
        <input
          type="text"
          className="bk-input"
          style={{ flex: 1 }}
          placeholder="New list name..."
          value={newListName}
          onChange={(e) => setNewListName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleCreateList();
          }}
          aria-label="New list name"
        />
        <button
          className="bk-btn bk-btn--primary"
          onClick={handleCreateList}
          disabled={creating || !newListName.trim()}
        >
          {creating ? "Creating..." : "Create List"}
        </button>
      </div>

      {lists.length === 0 ? (
        <div className="bk-empty">
          <h3>No saved lists yet</h3>
          <p>Create a list to start saving your favorite properties.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {lists.map((list) => {
            const isExpanded = expandedId === list.id;
            const previews = list.property_previews ?? [];
            const propertyCount = list.property_ids.length;

            return (
              <div key={list.id} className="bk-card" style={{ overflow: "visible" }}>
                {/* List header */}
                <div
                  className="bk-saved-list-header"
                  style={{
                    padding: 16,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    cursor: "pointer",
                    background: isExpanded ? "var(--bk-gray-50)" : undefined,
                    transition: "background 120ms ease",
                  }}
                  onClick={() => setExpandedId(isExpanded ? null : list.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setExpandedId(isExpanded ? null : list.id);
                    }
                  }}
                  aria-expanded={isExpanded}
                  aria-label={`${list.name}, ${propertyCount} properties`}
                >
                  <div>
                    <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
                      {list.name}
                    </h3>
                    <span style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                      {propertyCount} propert{propertyCount !== 1 ? "ies" : "y"} saved
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button
                      className="bk-btn bk-btn--danger bk-btn--sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteList(list.id, list.name);
                      }}
                      aria-label={`Delete list ${list.name}`}
                    >
                      Delete
                    </button>
                    <span style={{ fontSize: 18, color: "var(--bk-gray-300)" }}>
                      {isExpanded ? "\u25B2" : "\u25BC"}
                    </span>
                  </div>
                </div>

                {/* Expanded property cards */}
                {isExpanded && (
                  <div
                    style={{
                      borderTop: "1px solid var(--bk-border)",
                      padding: 16,
                    }}
                  >
                    {propertyCount === 0 ? (
                      <p style={{ color: "var(--bk-gray-600)", fontSize: 13, textAlign: "center", padding: 16 }}>
                        No properties in this list yet. Browse properties and save them here.
                      </p>
                    ) : previews.length > 0 ? (
                      <div className="bk-grid bk-grid--3">
                        {previews.map((prop) => (
                          <div
                            key={prop.id}
                            className="bk-card"
                            style={{ position: "relative" }}
                          >
                            <div className="bk-card-image" style={{ minHeight: 120 }}>
                              {prop.images && prop.images.length > 0 ? (
                                <img
                                  src={prop.images[0]}
                                  alt={prop.name}
                                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                  onError={(e) => {
                                    (e.target as HTMLImageElement).style.display = "none";
                                  }}
                                />
                              ) : (
                                <span>{prop.name.charAt(0)}</span>
                              )}
                            </div>
                            <div style={{ padding: 12 }}>
                              <Link
                                to={preserveQueryParams(
                                  `/property/${prop.id}`,
                                  location.search
                                )}
                                style={{ fontWeight: 600, fontSize: 14 }}
                              >
                                {prop.name}
                              </Link>
                              <p style={{ fontSize: 12, color: "var(--bk-gray-600)", marginTop: 2 }}>
                                {prop.city}
                              </p>
                              <button
                                className="bk-btn bk-btn--ghost bk-btn--sm"
                                style={{ marginTop: 8, color: "var(--bk-red)" }}
                                onClick={() =>
                                  void handleRemoveProperty(list.id, prop.id)
                                }
                                aria-label={`Remove ${prop.name} from list`}
                              >
                                Remove
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      /* Fallback: show property IDs if previews not available */
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {list.property_ids.map((pid) => (
                          <div
                            key={pid}
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              padding: "8px 12px",
                              background: "var(--bk-gray-50)",
                              borderRadius: "var(--bk-radius)",
                            }}
                          >
                            <Link
                              to={preserveQueryParams(
                                `/property/${pid}`,
                                location.search
                              )}
                              style={{ fontSize: 13 }}
                            >
                              Property {pid}
                            </Link>
                            <button
                              className="bk-btn bk-btn--ghost bk-btn--sm"
                              style={{ color: "var(--bk-red)" }}
                              onClick={() =>
                                void handleRemoveProperty(list.id, pid)
                              }
                              aria-label={`Remove property ${pid} from list`}
                            >
                              Remove
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
