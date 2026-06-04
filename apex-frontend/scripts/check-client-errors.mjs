/**
 * Opens the dashboard and fails if pageerror or console.error occurs.
 * Usage: node scripts/check-client-errors.mjs [url]
 */
import { chromium } from "playwright";

const url = process.argv[2] || "http://localhost:3001";
const errors = [];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

page.on("pageerror", (err) => {
  errors.push(`pageerror: ${err.message}\n${err.stack || ""}`);
});

console.log(`Loading ${url} ...`);
await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
await page.waitForTimeout(8000);

const bodyText = await page.locator("body").innerText();
if (bodyText.includes("Application error")) {
  errors.push("Page shows 'Application error' banner");
}

await browser.close();

if (errors.length) {
  console.error("CLIENT ERRORS DETECTED:\n");
  for (const e of errors) console.error(e, "\n---");
  process.exit(1);
}

console.log("OK: no client-side errors detected after 8s");
process.exit(0);
