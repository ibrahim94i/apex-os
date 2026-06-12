/** Display-price layer helpers — MetaTrader primary, Binance secondary. */

export function displayPriceHint(source: string | null | undefined): string {
  if (source === "metatrader") return "MetaTrader · للعرض فقط";
  if (source === "twelvedata") return "TwelveData · fallback";
  if (source?.startsWith("binance")) return "Binance XAUUSDT · للعرض فقط";
  return "APEX · للعرض فقط";
}

export function shouldApplyDisplayPriceUpdate(
  currentSource: string | null | undefined,
  incomingSource: string | null | undefined,
): boolean {
  if (incomingSource === "metatrader") return true;
  if (currentSource === "metatrader" && incomingSource?.startsWith("binance")) {
    return false;
  }
  return true;
}
