import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { Watchlist } from "../types";

export function WatchlistsPage() {
  const { api, notify } = useRobinhoodLayout();
  const location = useLocation();
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");

  const load = async () => {
    try {
      const items = await api.listWatchlists();
      setWatchlists(items);
    } catch { /* skip */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [api]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await api.createWatchlist(newName.trim());
      notify("Watchlist Created", newName.trim());
      setNewName("");
      setShowCreate(false);
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to create watchlist");
    }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-watchlists" aria-label="Watchlists">
      <div className="rh-page-header">
        <h1>Lists</h1>
        <Button variant="primary" onClick={() => setShowCreate(true)} aria-label="Create watchlist">
          + Create List
        </Button>
      </div>

      {showCreate && (
        <div className="rh-watchlists__create">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="List name"
            aria-label="New list name"
            autoFocus
          />
          <div className="rh-watchlists__create-actions">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate}>Create</Button>
          </div>
        </div>
      )}

      {watchlists.length === 0 ? (
        <div className="rh-empty">No watchlists yet. Create one to start tracking stocks.</div>
      ) : (
        <div className="rh-watchlists__grid">
          {watchlists.map((wl) => (
            <Link
              key={wl.id}
              to={preserveQueryParams(`/lists/${wl.id}`, location.search)}
              className="rh-watchlists__card"
            >
              <h3>{wl.name}</h3>
              <span className="rh-watchlists__count">{wl.symbols.length} {wl.symbols.length === 1 ? "item" : "items"}</span>
              <div className="rh-watchlists__symbols">
                {wl.symbols.slice(0, 5).join(", ")}
                {wl.symbols.length > 5 ? ` +${wl.symbols.length - 5} more` : ""}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
