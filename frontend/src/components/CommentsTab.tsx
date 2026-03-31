// Comments Tab Component - Digital Post-it system for order comments
import React, { useState, useEffect, useCallback } from 'react';
import { commentsApi, OrderComment } from '../api/comments';
import { useAuth } from '../contexts';
import '../styles/components/CommentsTab.css';

interface CommentsTabProps {
  orderId: number;
}

/**
 * Formats a date string as a relative time (e.g., "vor 5 Minuten")
 * Falls back to absolute date for older entries
 */
const formatRelativeTime = (dateStr: string): string => {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'gerade eben';
  if (diffMin < 60) return `vor ${diffMin} ${diffMin === 1 ? 'Minute' : 'Minuten'}`;
  if (diffHour < 24) return `vor ${diffHour} ${diffHour === 1 ? 'Stunde' : 'Stunden'}`;
  if (diffDay < 7) return `vor ${diffDay} ${diffDay === 1 ? 'Tag' : 'Tagen'}`;

  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

/**
 * Generates a consistent color for a user based on their user_id
 */
const getUserColor = (userId: number): string => {
  const colors = [
    '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
    '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6',
  ];
  return colors[userId % colors.length];
};

/**
 * Extracts initials from a user name or falls back to "?"
 */
const getInitials = (name: string | null): string => {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return parts[0].substring(0, 2).toUpperCase();
};

export const CommentsTab: React.FC<CommentsTabProps> = ({ orderId }) => {
  const { user } = useAuth();
  const [comments, setComments] = useState<OrderComment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New comment state
  const [newText, setNewText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Delete confirmation state
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadComments = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await commentsApi.getForOrder(orderId);
      setComments(data);
    } catch (err) {
      console.error('Failed to load comments:', err);
      setError('Kommentare konnten nicht geladen werden');
    } finally {
      setIsLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    loadComments();
  }, [loadComments]);

  const handleAddComment = async () => {
    const trimmed = newText.trim();
    if (!trimmed || isSubmitting) return;

    try {
      setIsSubmitting(true);
      await commentsApi.create(orderId, trimmed);
      setNewText('');
      await loadComments();
    } catch (err) {
      console.error('Failed to add comment:', err);
      alert('Kommentar konnte nicht hinzugefügt werden.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl+Enter or Cmd+Enter to submit
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleAddComment();
    }
  };

  const startEditing = (comment: OrderComment) => {
    setEditingId(comment.id);
    setEditText(comment.text);
    setDeletingId(null);
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditText('');
  };

  const handleSaveEdit = async () => {
    if (editingId === null || isSavingEdit) return;
    const trimmed = editText.trim();
    if (!trimmed) return;

    try {
      setIsSavingEdit(true);
      await commentsApi.update(orderId, editingId, trimmed);
      setEditingId(null);
      setEditText('');
      await loadComments();
    } catch (err) {
      console.error('Failed to update comment:', err);
      alert('Kommentar konnte nicht aktualisiert werden.');
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleEditKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSaveEdit();
    }
    if (e.key === 'Escape') {
      cancelEditing();
    }
  };

  const handleDelete = async (commentId: number) => {
    try {
      await commentsApi.delete(orderId, commentId);
      setDeletingId(null);
      await loadComments();
    } catch (err) {
      console.error('Failed to delete comment:', err);
      alert('Kommentar konnte nicht gelöscht werden.');
    }
  };

  const isOwnComment = (comment: OrderComment): boolean => {
    return user !== null && user.id === comment.user_id;
  };

  if (isLoading) {
    return (
      <div className="comments-tab">
        <div className="comments-loading">
          <p>Kommentare werden geladen...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="comments-tab">
        <div className="comments-error">
          <p>{error}</p>
          <button className="btn-retry" onClick={loadComments}>
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="comments-tab">
      {/* Header */}
      <div className="tab-header">
        <h2>
          Kommentare
          {comments.length > 0 && (
            <span className="comment-count">({comments.length})</span>
          )}
        </h2>
      </div>

      {/* New Comment Form */}
      <div className="new-comment-form">
        <textarea
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Kommentar schreiben... (Strg+Enter zum Absenden)"
          rows={2}
          disabled={isSubmitting}
        />
        <button
          className="btn-add-comment"
          onClick={handleAddComment}
          disabled={!newText.trim() || isSubmitting}
        >
          {isSubmitting ? 'Senden...' : 'Senden'}
        </button>
      </div>

      {/* Comments List */}
      {comments.length === 0 ? (
        <div className="comments-empty">
          <div className="empty-icon">💬</div>
          <p>Noch keine Kommentare. Schreiben Sie den ersten!</p>
        </div>
      ) : (
        <div className="comments-list">
          {comments.map((comment) => (
            <div key={comment.id} className="comment-card">
              {/* Avatar */}
              <div
                className="comment-avatar"
                style={{ backgroundColor: getUserColor(comment.user_id) }}
              >
                {getInitials(comment.user_name)}
              </div>

              {/* Body */}
              <div className="comment-body">
                <div className="comment-header">
                  <span className="comment-user-name">
                    {comment.user_name || 'Unbekannt'}
                  </span>
                  <span className="comment-timestamp">
                    {formatRelativeTime(comment.created_at)}
                  </span>
                </div>

                {editingId === comment.id ? (
                  /* Edit Mode */
                  <div className="comment-edit-form">
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={handleEditKeyDown}
                      rows={3}
                      autoFocus
                    />
                    <div className="comment-edit-actions">
                      <button
                        className="btn-edit-cancel"
                        onClick={cancelEditing}
                      >
                        Abbrechen
                      </button>
                      <button
                        className="btn-edit-save"
                        onClick={handleSaveEdit}
                        disabled={!editText.trim() || isSavingEdit}
                      >
                        {isSavingEdit ? 'Speichern...' : 'Speichern'}
                      </button>
                    </div>
                  </div>
                ) : (
                  /* Display Mode */
                  <>
                    <p className="comment-text">{comment.text}</p>

                    {/* Actions (only for own comments) */}
                    {isOwnComment(comment) && (
                      <>
                        <div className="comment-actions">
                          <button
                            className="btn-comment-action"
                            onClick={() => startEditing(comment)}
                          >
                            Bearbeiten
                          </button>
                          <button
                            className="btn-comment-action delete"
                            onClick={() => setDeletingId(comment.id)}
                          >
                            Löschen
                          </button>
                        </div>

                        {/* Delete Confirmation */}
                        {deletingId === comment.id && (
                          <div className="delete-confirm">
                            <span>Kommentar wirklich löschen?</span>
                            <button
                              className="btn-confirm-delete"
                              onClick={() => handleDelete(comment.id)}
                            >
                              Ja, löschen
                            </button>
                            <button
                              className="btn-cancel-delete"
                              onClick={() => setDeletingId(null)}
                            >
                              Nein
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
