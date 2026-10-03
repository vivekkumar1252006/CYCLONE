// Walks the hackathon demo flow in a real browser and saves screenshots to docs/screenshots.
// Usage: node demo_flow.mjs [baseUrl]   (requires backend :8000 and frontend :5173 running)
// Uses the locally installed Microsoft Edge / Chrome (no browser download).
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const base = process.argv[2] ?? "http://localhost:5173";
const out = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots");
mkdirSync(out, { recursive: true });

let browser;
for (const channel of ["msedge", "chrome"]) {
  try { browser = await chromium.launch({ channel }); break; } catch { /* try next */ }
}
if (!browser) throw new Error("No Edge/Chrome found for Playwright");

const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const problems = [];
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) problems.push(`HTTP ${r.status()} ${r.url()}`); });

const t0 = Date.now();
const step = (s) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${s}`);

step("1. open dashboard");
await page.goto(base);
await page.waitForSelector(".priority-item", { timeout: 30000 });

step("2. select demo scenario ALPHA");
await page.selectOption("#scenario", "alpha");
await page.click("text=Load demo scenario");
await page.waitForSelector(".scenario-desc .spinner", { state: "detached", timeout: 30000 });
await page.waitForSelector(".priority-item");
await page.waitForTimeout(1500); // tiles
step("3-4. track + affected region (wind zone) visible");
await page.screenshot({ path: `${out}/01_dashboard.png` });

step("5. toggle vulnerability heatmap");
await page.hover(".leaflet-control-layers");
await page.click("label:has-text('Vulnerability heatmap') input");
await page.click("label:has-text('Wind-risk zone') input");
await page.mouse.move(800, 500);
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/02_vulnerability_heatmap.png` });

step("6-7. click highest-risk asset -> explainable risk detail");
await page.click(".priority-item >> nth=0");
await page.waitForSelector(".asset-detail");
await page.waitForTimeout(1200);
await page.screenshot({ path: `${out}/03_asset_detail.png` });
await page.locator(".side-panel").screenshot({ path: `${out}/04_asset_detail_panel.png` });

step("8. priority list + charts");
await page.click("text=Priority list");
await page.evaluate(() => window.scrollTo(0, 1100));
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/05_charts.png` });

step("9-10. full asset page: recommendations + confidence");
const firstHref = await page.evaluate(async (api) => {
  const r = await fetch(`${api}/api/risk/priority?limit=1`).then((x) => x.json());
  return `/asset/${r.items[0].asset_id}`;
}, process.argv[3] ?? "");
await page.goto(base + firstHref);
await page.waitForSelector(".rec-list");
await page.screenshot({ path: `${out}/06_asset_page.png`, fullPage: true });

step("alerts page");
await page.goto(base + "/alerts");
await page.waitForSelector(".alert-card", { timeout: 15000 });
await page.screenshot({ path: `${out}/07_alerts.png` });

step("data page");
await page.goto(base + "/data");
await page.waitForSelector("text=Infrastructure inventory");
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/08_data.png` });

step("settings + model pages");
await page.goto(base + "/settings");
await page.waitForSelector(".slider-row");
await page.screenshot({ path: `${out}/09_settings.png` });
await page.goto(base + "/model");
await page.waitForSelector("text=Important limitations");
await page.screenshot({ path: `${out}/10_model.png`, fullPage: true });

step("mobile layout");
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(base);
await page.waitForSelector(".priority-item");
await page.waitForTimeout(1000);
await page.screenshot({ path: `${out}/11_mobile.png` });

await browser.close();
step(`done - screenshots in ${out}`);
if (problems.length) {
  console.log("PROBLEMS:\n" + problems.join("\n"));
  process.exitCode = 1;
} else console.log("No console errors or failed API calls.");
