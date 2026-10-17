export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (typeof options.body === "string")
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      headers,
      signal: options.signal ?? AbortSignal.timeout(60_000),
    });
  } catch (error) {
    if (
      error instanceof DOMException &&
      ["TimeoutError", "AbortError"].includes(error.name)
    ) {
      throw new Error(
        "The request timed out. Reload the bill before retrying a save or approval; it may already have completed.",
      );
    }
    throw new Error(
      "Cannot reach the local workspace. Check that the server is running; your unsaved entries are still on this page.",
    );
  }
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
export const money = (
  value: string | number | null | undefined,
  currency = "INR",
) =>
  value == null || value === ""
    ? "—"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency,
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
export const moment = (value: string) =>
  new Date(value).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
