"use client";

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="card empty" role="alert">
      <p className="error-text">
        <strong>Couldn&apos;t load data.</strong> {error.message}
      </p>
      <p>
        The API may be waking up (free tier) or temporarily down.{" "}
        <button type="button" onClick={reset}>
          Try again
        </button>
      </p>
    </div>
  );
}
