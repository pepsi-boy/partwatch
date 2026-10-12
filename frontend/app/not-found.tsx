import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card empty">
      <p>That part doesn&apos;t exist (it may have been removed).</p>
      <Link href="/">Back to all parts</Link>
    </div>
  );
}
