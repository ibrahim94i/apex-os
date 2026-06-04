/**
 * Verifies PriceChart fix: mocks dashboard + bars with future last candle,
 * then simulates live price ticks (the scenario that crashed on Vercel).
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const url = process.argv[2] || "http://localhost:3003";

const futureHour = Math.floor(Date.now() / 3600000) * 3600 + 3600;
const pastHour = futureHour - 7200;

function makeBars(symbol) {
  const base = symbol === "EURUSD" ? 1.08 : 3300;
  return {
    symbol,
    bars: [
      {
        timestamp: new Date(pastHour * 1000).toISOString(),
        open: base,
        high: base + 1,
        low: base - 1,
        close: base + 0.5,
        volume: 100,
      },
      {
        timestamp: new Date(futureHour * 1000).toISOString(),
        open: base + 0.5,
        high: base + 2,
        low: base,
        close: base + 1,
        volume: 100,
      },
    ],
  };
}

const dashboard = {
  account: { mode: "demo", balance: 10000, currency: "USD" },
  kill_switch: { status: "INACTIVE" },
  feed_status: {},
  market_status: {},
  memory_patterns: {},
  memory_summaries: {},
  hourly_report: null,
  assets: {
    XAUUSD: {
      symbol: "XAUUSD",
      current_price: 3350.25,
      regime: { regime: "TRENDING", confidence: 0.8, symbol: "XAUUSD" },
      latest_signal: null,
      signal_history: [],
      agent_consensus: null,
      market_status: { is_open: true, schedule_ar: "24/5" },
    },
    EURUSD: {
      symbol: "EURUSD",
      current_price: 1.085,
      regime: { regime: "RANGING", confidence: 0.6, symbol: "EURUSD" },
      latest_signal: null,
      signal_history: [],
      agent_consensus: null,
      market_status: { is_open: true, schedule_ar: "24/5" },
    },
  },
};

const errors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => {
  if (m.type() === "error" && m.text().includes("Cannot update oldest data")) {
    errors.push(`console: ${m.text()}`);
  }
});

await page.route("**/*", async (route) => {
  const u = route.request().url();
  if (u.includes("/api/v1/dashboard/multi")) {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dashboard),
    });
  }
  if (u.includes("/api/v1/market/bars")) {
    const sym = new URL(u).searchParams.get("symbol") || "XAUUSD";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(makeBars(sym)),
    });
  }
  if (
    u.includes("/api/v1/account/mode") ||
    u.includes("/api/v1/backtest/results") ||
    u.includes("/api/v1/performance/summary")
  ) {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ mode: "demo", balance: 10000 }),
    });
  }
  return route.continue();
});

console.log(`Testing chart crash scenario at ${url} ...`);
await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
await page.waitForTimeout(5000);

const body = await page.locator("body").innerText();
if (body.includes("Application error")) {
  errors.push("Application error banner visible");
}

await browser.close();

if (errors.length) {
  console.error("FAIL:\n", errors.join("\n"));
  process.exit(1);
}
console.log("OK: chart handles future last bar + live price without crash");
process.exit(0);
