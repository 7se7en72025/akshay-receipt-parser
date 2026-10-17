export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (typeof options.body === "string")
    headers.set("Content-Type", "application/json");
  const response = await fetch("/api" + path, { ...options, headers });
  if (!response.ok) {
    let message = "The request could not be completed.";
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
      else if (Array.isArray(payload.detail)) {
        message = payload.detail
          .map(
            (entry: { loc?: string[]; msg: string }) =>
              (entry.loc?.slice(1).join(" · ") || "Value") + ": " + entry.msg,
          )
          .join("; ");
      }
    } catch {
      /* Keep the useful fallback for non-JSON errors. */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const message = (error: unknown) =>
  error instanceof Error ? error.message : "Something went wrong.";
export const money = (value: string | number | null | undefined) =>
  value == null || value === ""
    ? "—"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
      }).format(Number(value));
export const day = (value: string | null | undefined) =>
  !value
    ? "—"
    : new Date(
        value.length === 10 ? value + "T12:00:00" : value,
      ).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
