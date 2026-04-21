import { useEffect, useState } from "react";
import Link from "next/link";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const SEVERITY_STYLES = {
  critical: {
    badge: "bg-red-100 text-red-700 ring-1 ring-red-200",
    dot: "bg-red-500",
  },
  warning: {
    badge: "bg-amber-100 text-amber-700 ring-1 ring-amber-200",
    dot: "bg-amber-400",
  },
  info: {
    badge: "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200",
    dot: "bg-emerald-500",
  },
};

function timeAgo(dateStr) {
  const diff = Math.floor((Date.now() - new Date(dateStr + "Z")) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function ReviewCard({ review }) {
  const sev = SEVERITY_STYLES[review.severity] || SEVERITY_STYLES.info;

  return (
    <div className="group bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md hover:border-gray-200 transition-all duration-200 flex flex-col overflow-hidden h-full">
      {/* Top stripe by severity */}
      <div className={`h-1 w-full ${sev.dot}`} />

      <div className="p-5 flex flex-col gap-3 flex-1">
        {/* Repo + time */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-gray-400 truncate max-w-[70%]">
            {review.repo}{" "}
            <span className="text-gray-300">#{review.pr_number}</span>
          </span>
          <span className="text-xs text-gray-400 shrink-0" suppressHydrationWarning>
            {review.created_at ? timeAgo(review.created_at) : ""}
          </span>
        </div>

        {/* PR title */}
        <a
          href={review.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-semibold text-gray-900 leading-snug hover:text-indigo-600 transition-colors line-clamp-2"
        >
          {review.title}
        </a>

        {/* Author + severity badge */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <div className="w-5 h-5 rounded-full bg-gray-100 flex items-center justify-center text-[10px] font-bold text-gray-500 uppercase">
              {review.author?.[0]}
            </div>
            <span className="text-xs text-gray-500">@{review.author}</span>
          </div>
          <span
            className={`ml-auto text-[11px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide ${sev.badge}`}
          >
            {review.severity}
          </span>
        </div>

        {/* Summary — fixed 3-line height so all cards align at the footer */}
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-3 min-h-[4rem]">
          {review.summary}
        </p>

        {/* Footer — severity breakdown + link */}
        <div className="flex items-center justify-between pt-2 border-t border-gray-50">
          <div className="flex items-center gap-2">
            {review.critical_count > 0 && (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-red-600">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />
                {review.critical_count} critical
              </span>
            )}
            {review.warning_count > 0 && (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-amber-600">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
                {review.warning_count} warning
              </span>
            )}
            {review.info_count > 0 && (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                {review.info_count} info
              </span>
            )}
          </div>
          <Link
            href={`/pr/${review.id}`}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors"
          >
            Full review →
          </Link>
        </div>
      </div>
    </div>
  );
}

function StatPill({ label, value, color }) {
  return (
    <div className={`flex items-center gap-2 px-4 py-2 rounded-xl ${color}`}>
      <span className="text-2xl font-bold">{value}</span>
      <span className="text-sm font-medium opacity-70">{label}</span>
    </div>
  );
}

export default function Home() {
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${BACKEND_URL}/reviews`)
      .then((res) => {
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setReviews(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const counts = reviews.reduce(
    (acc, r) => {
      acc.total++;
      if (r.severity === "critical") acc.critical++;
      if (r.severity === "warning") acc.warning++;
      return acc;
    },
    { total: 0, critical: 0, warning: 0 }
  );

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      {/* Header */}
      <header className="bg-white border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </div>
            <div>
              <h1 className="text-base font-bold text-gray-900 leading-none">PR Review Agent</h1>
              <p className="text-xs text-gray-400 mt-0.5">AI-powered code reviews</p>
            </div>
          </div>

          {!loading && !error && reviews.length > 0 && (
            <div className="flex items-center gap-2">
              <StatPill label="reviews" value={counts.total} color="bg-indigo-50 text-indigo-700" />
              {counts.critical > 0 && (
                <StatPill label={`of ${counts.total} critical`} value={counts.critical} color="bg-red-50 text-red-700" />
              )}
              {counts.warning > 0 && (
                <StatPill label={`of ${counts.total} warnings`} value={counts.warning} color="bg-amber-50 text-amber-700" />
              )}
            </div>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {loading && (
          <div className="flex flex-col items-center justify-center py-32 gap-3">
            <div className="w-8 h-8 border-[3px] border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-gray-400">Loading reviews…</p>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-100 rounded-xl p-5 text-sm text-red-600 flex items-start gap-3">
            <svg className="w-4 h-4 mt-0.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span>Failed to connect to backend: {error}</span>
          </div>
        )}

        {!loading && !error && reviews.length === 0 && (
          <div className="flex flex-col items-center justify-center py-32 gap-4 text-center">
            <div className="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center">
              <svg className="w-7 h-7 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <p className="text-base font-semibold text-gray-700">No reviews yet</p>
              <p className="text-sm text-gray-400 mt-1">Open a pull request in a connected repo to trigger the first review.</p>
            </div>
          </div>
        )}

        {!loading && !error && reviews.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 items-stretch">
            {reviews.map((review) => (
              <ReviewCard key={review.id} review={review} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
