import puppeteerCore from "puppeteer-core";

const browser = await puppeteerCore.launch({
  browser: "chrome",
  channel: "chrome",
  headless: true,
  args: ["--enable-features=WebMCP", "--no-sandbox", "--disable-setuid-sandbox"],
});

const page = await browser.newPage();
await page.goto("https://documesh.selatan.org/app", { waitUntil: "networkidle0", timeout: 30000 });
await new Promise(r => setTimeout(r, 2000));

// Check document.modelContext in the PAGE context
const mcInfo = await page.evaluate(() => {
  const has = "modelContext" in document;
  const hasRegister = has && typeof document.modelContext?.registerTool === "function";
  const toolNames = document.__documeshTools ? Object.keys(document.__documeshTools) : [];
  return { has, hasRegister, toolNames, isNative: has && !document.__documeshShimUsed };
});
console.log("document.modelContext:", JSON.stringify(mcInfo));

// Check page.webmcp (Puppeteer extension)
try {
  const tools = await page.webmcp.tools();
  console.log("page.webmcp.tools():", JSON.stringify(tools?.map(t => t.name) || []));
} catch (e) {
  console.log("page.webmcp.tools() error:", e.message);
}

// Try to call a tool directly
try {
  const result = await page.webmcp.executeTool("list_vendors", {});
  console.log("executeTool list_vendors:", JSON.stringify(result).slice(0, 200));
} catch (e) {
  console.log("executeTool error:", e.message);
}

await browser.close();
