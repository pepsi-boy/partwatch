import { api } from "@/lib/api";

/** Shown on every page while no Best Buy API key is configured. */
export async function DemoBanner() {
  const status = await api.status().catch(() => null);
  if (!status?.demo_mode) return null;
  return (
    <div className="banner" role="note">
      <strong>Demo mode:</strong> no Best Buy API key is set yet, so prices come from a mock
      provider that mimics the Best Buy Products API, and SKUs are placeholders.
    </div>
  );
}
