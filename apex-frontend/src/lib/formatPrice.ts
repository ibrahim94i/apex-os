/** Price display helpers per APEX symbol. */

const DOLLAR_PREFIX_SYMBOLS = new Set(["XAUUSD", "BTCUSDT"]);

export function priceDecimals(symbol: string): number {
  if (symbol === "EURUSD") return 5;
  if (symbol === "USDJPY") return 3;
  return 2;
}

export function pricePrefix(symbol: string): string {
  return DOLLAR_PREFIX_SYMBOLS.has(symbol) ? "$" : "";
}

export function formatAssetPrice(price: number, symbol: string): string {
  return price.toLocaleString("ar-EG", {
    minimumFractionDigits: priceDecimals(symbol),
    maximumFractionDigits: priceDecimals(symbol),
  });
}
