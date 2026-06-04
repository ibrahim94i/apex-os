/**
 * Debug Vercel/client crash — logs page errors, console, and body snippet.
 */
import { chromium } from "playwright";

const url = process.argv[2] || "https://apex-os-xi.vercel.app";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const logs = [];
page.on("pageerror", (e) => logs.push(["pageerror", e.message, e.stack]));
page.on("console", (m) => logs.push(["console", m.type(), m.text()]));

await page.goto(url, { waitUntil: "networkidle", timeout: 90000 });
await page.waitForTimeout(10000);

const body = await page.locator("body").innerText();
console.log("=== BODY (first 800 chars) ===");
console.log(body.slice(0, 800));
console.log("\n=== RELEVANT LOGS ===");
for (const [kind, ...rest] of logs) {
  const line = rest.join(" | ");
  if (
    kind === "pageerror" ||
    line.includes("Error") ||
    line.includes("error") ||
    line.includes("exception") ||
    line.includes("Cannot")
  ) {
    console.log(`[${kind}]`, line.slice(0, 500));
  }
}

await browser.close();
