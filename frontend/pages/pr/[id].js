import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import Link from "next/link";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const SEVERITY_STYLES = {
  critical: {
    card: "bg-red-50 border-red-200",
    badge: "bg-red-100 text-red-700 ring-1 ring-red-200",
    dot: "bg-red-500",
    label: "text-red-700",
  },
  warning: {
    card: "bg-amber-50 border-amber-200",
    badge: "bg-amber-100 text-amber-700 ring-1 ring-amber-200",
    dot: "bg-amber-400",
    label: "text-amber-700",
  },
  info: {
    card: "bg-emerald-50 border-emerald-200",
    badge: "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200",
    dot: "bg-emerald-500",
    label: "text-emerald-700",
  },
};

const SEVERITY_ORDER = ["critical", "warning", "info"];

function CommentCard({ comment }) {
  const sev = SEVERITY_STYLES[comment.severity] || SEVERITY_STYLES.info;
  return (
    <div className={`rounded-xl border p-4 ${sev.card}`}>
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="text-xs font-mono text-gray-600 truncate">
          {comment.path}
          <span className="text-gray-400"> :{comment.line}</span>
        </span>
        <span className={`shrink-0 text-[11px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide ${sev.badge}`}>
          {comment.severity}
        </span>
      </div>
      <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
        {comment.body}
      </p>
    </div>
  );
}

function SeverityBar({ comments }) {
  const counts = comments.reduce((acc, c) => {
    acc[c.severity || "info"] = (acc[c.severity || "info"] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="flex flex-wrap gap-3">
      {SEVERITY_ORDER.map((sev) => {
        const s = SEVERITY_STYLES[sev];
        return (
          <div key={sev} className={`flex items-center gap-2 px-4 py-2 rounded-xl border ${s.card}`}>
            <div className={`w-2 h-2 rounded-full ${s.dot}`} />
            <span className={`text-2xl font-bold ${s.label}`}>{counts[sev] || 0}</span>
            <span className={`text-sm font-medium capitalize ${s.label} opacity-70`}>{sev}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function PRDetail() {
  const router = useRouter();
  const { id } = router.query;

  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!id) return;
    fetch(`${BACKEND_URL}/reviews/${id}`)
      .then((res) => {
        if (res.status === 404) throw new Error("not_found");
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setReview(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [id]);

  const sorted = review?.comments
    ? [...review.comments].sort(
        (a, b) =>
          SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
      )
    : [];

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      {/* Header */}
      <header className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-4">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Dashboard
          </Link>
          {review && (
            <>
              <span className="text-gray-200">/</span>
              <span className="text-sm text-gray-500 truncate max-w-xs">{review.title}</span>
            </>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-5">
        {loading && (
          <div className="flex flex-col items-center justify-center py-32 gap-3">
            <div className="w-8 h-8 border-[3px] border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-gray-400">Loading review…</p>
          </div>
        )}

        {error === "not_found" && (
          <div className="flex flex-col items-center justify-center py-32 gap-3 text-center">
            <p className="text-base font-semibold text-gray-700">Review not found</p>
            <Link href="/" className="text-sm text-indigo-600 hover:underline">
              Return to dashboard
            </Link>
          </div>
        )}

        {error && error !== "not_found" && (
          <div className="bg-red-50 border border-red-100 rounded-xl p-5 text-sm text-red-600">
            Failed to load review: {error}
          </div>
        )}

        {!loading && !error && review && (
          <>
            {/* PR metadata card */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-mono text-gray-400 mb-1">
                    {review.repo}{" "}
                    <span className="text-gray-300">#{review.pr_number}</span>
                  </p>
                  <h1 className="text-xl font-bold text-gray-900 leading-snug">
                    {review.title}
                  </h1>
                  <div className="flex items-center gap-2 mt-2">
                    <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-500 uppercase">
                      {review.author?.[0]}
                    </div>
                    <span className="text-sm text-gray-500">@{review.author}</span>
                  </div>
                </div>
                <a
                  href={review.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                  </svg>
                  View on GitHub
                </a>
              </div>
            </div>

            {/* Summary */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                Review Summary
              </p>
              <p className="text-gray-700 leading-relaxed">{review.summary}</p>
            </div>

            {/* Severity breakdown */}
            {sorted.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
                  Severity Breakdown
                </p>
                <SeverityBar comments={sorted} />
              </div>
            )}

            {/* Inline comments */}
            {sorted.length > 0 ? (
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                  Inline Comments ({sorted.length})
                </p>
                <div className="space-y-3">
                  {sorted.map((comment) => (
                    <CommentCard key={comment.id} comment={comment} />
                  ))}
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-10 text-center text-gray-400 text-sm">
                No inline comments were posted for this review.
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
