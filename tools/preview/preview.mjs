// Runs badge/apps/universe_badge in the badger.github.io simulator and saves a
// screenshot, so you can see a change before pushing it to the badge.
//
//   node tools/preview/preview.mjs                  screenshot to preview.png
//   node tools/preview/preview.mjs --press down,select --out menu.png
//   node tools/preview/preview.mjs --live           browser window, reloads on save
//   node tools/preview/preview.mjs --ota            run the real update path against
//                                                   the published Pages site
//
// The simulator page and its MicroPython runtime come from pinned commits of
// badger/home and badger/badger.github.io, cached in ~/.cache/universe-badge-sim.
// It uses an installed Chrome or Edge (set BADGE_BROWSER to a path to override).
// Exits non-zero if the app printed a traceback.
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, watch, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { chromium } from "playwright-core";

// badger/home commit whose .github/extensions/badge-simulator/web/ we serve.
const HOME_REV = "c095061d3483a2504a67a1f37ed4d7ee71edad5a";
const APP = "universe_badge";
const BUTTONS = { down: 1, up: 2, select: 4, right: 8, left: 16, home: 32, back: 8192, menu: 16384 };

const repo = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const appDir = join(repo, "badge", "apps", APP);
const cache = join(homedir(), ".cache", "universe-badge-sim");

const { values: opts } = parseArgs({
    options: {
        out: { type: "string", default: join(repo, "preview.png") },
        ms: { type: "string", default: "1500" },
        press: { type: "string", default: "" },
        scale: { type: "string", default: "3" },
        live: { type: "boolean", default: false },
        ota: { type: "boolean", default: false },
    },
});

async function cached(url, file) {
    if (existsSync(file)) return readFileSync(file);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${response.status} fetching ${url}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file + ".tmp", bytes);
    renameSync(file + ".tmp", file);
    return bytes;
}
const webBase = `https://raw.githubusercontent.com/badger/home/${HOME_REV}/.github/extensions/badge-simulator/web/`;
const webFile = (name) => cached(webBase + name, join(cache, "web", HOME_REV, name));
const buildInfo = JSON.parse(await webFile("BUILD_INFO.json"));
const runtimeBase = `https://raw.githubusercontent.com/badger/badger.github.io/${buildInfo.revision}/public/simulator/`;
const runtimeFile = (rel) => cached(runtimeBase + rel, join(cache, "runtime", buildInfo.revision, ...rel.split("/")));

function appFiles(dir = appDir, out = []) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === "__pycache__" || entry.name.startsWith(".")) continue;
        const full = join(dir, entry.name);
        if (entry.isDirectory()) appFiles(full, out);
        else out.push({ path: relative(appDir, full).split(sep).join("/"), data: readFileSync(full).toString("base64") });
    }
    if (dir === appDir && !opts.ota) out.push({ path: "PREVIEW", data: "" });
    return out;
}

// ---- server: the subset of the badger/home simulator extension's API the page uses
const log = [];
let frames = 0;
const clients = new Set();
const mime = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json",
    ".wasm": "application/wasm", ".glb": "model/gltf-binary", ".png": "image/png" };
const send = (res, status, body, type = "application/json") => {
    res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-store" });
    res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body));
};
const readBody = (req) => new Promise((done) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => { try { done(JSON.parse(Buffer.concat(chunks).toString() || "{}")); } catch { done({}); } });
});
const broadcast = (event) => { for (const c of clients) c.write(`data: ${JSON.stringify(event)}\n\n`); };

const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    try {
        if (path === "/events") {
            res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });
            res.write(": connected\n\n");
            clients.add(res);
            req.on("close", () => clients.delete(res));
            return;
        }
        if (path === "/api/state") return send(res, 200, { apps: [APP], app: APP });
        if (path === "/api/app") return send(res, 200, { app: APP, revision: Date.now(), files: appFiles() });
        if (req.method === "POST") {
            const body = await readBody(req);
            if (path === "/api/log") for (const line of body.lines ?? []) { log.push(line); console.log(line); }
            if (path === "/api/stats" && !body.paused) frames = body.frames ?? frames;
            return send(res, 200, { ok: true });
        }
        if (path.startsWith("/simulator/")) {
            const rel = path.slice("/simulator/".length);
            return send(res, 200, await runtimeFile(rel), mime[extname(rel)] ?? "application/octet-stream");
        }
        const name = path === "/" ? "index.html" : path.slice(1);
        if (!["index.html", "simulator.js", "simulator.css"].includes(name)) return send(res, 404, { error: "Not found" });
        return send(res, 200, await webFile(name), mime[extname(name)]);
    } catch (error) {
        send(res, 500, { error: String(error.message ?? error) });
    }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const url = `http://127.0.0.1:${server.address().port}/`;

async function launchBrowser(headless) {
    if (process.env.BADGE_BROWSER) return chromium.launch({ headless, executablePath: process.env.BADGE_BROWSER });
    for (const channel of ["chrome", "msedge"]) {
        try { return await chromium.launch({ headless, channel }); } catch {}
    }
    throw new Error("No Chrome or Edge found; set BADGE_BROWSER to a Chromium executable.");
}
const browser = await launchBrowser(!opts.live);
const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
await page.goto(url);

if (opts.live) {
    let timer;
    watch(appDir, { recursive: true }, () => {
        clearTimeout(timer);
        timer = setTimeout(() => { console.log("[preview] reloading"); broadcast({ type: "reload" }); }, 200);
    });
    console.log(`[preview] ${url} (close the window to stop)`);
    page.on("close", () => { browser.close(); server.close(); process.exit(0); });
} else {
    const deadline = Date.now() + 60000;
    while (frames < 2 && Date.now() < deadline) await new Promise((r) => setTimeout(r, 250));
    if (frames < 2) console.error("[preview] no frames rendered within 60 s");
    await page.waitForTimeout(Number(opts.ms));
    for (const name of opts.press.split(",").filter(Boolean)) {
        if (!(name in BUTTONS)) throw new Error(`Unknown button ${name}; use ${Object.keys(BUTTONS).join(", ")}`);
        broadcast({ type: "press", bit: BUTTONS[name], ms: 120 });
        await page.waitForTimeout(400);
    }
    const png = await page.evaluate((scale) => {
        const src = document.querySelector("[data-screen]");
        const out = document.createElement("canvas");
        out.width = src.width * scale;
        out.height = src.height * scale;
        const ctx = out.getContext("2d");
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(src, 0, 0, out.width, out.height);
        return out.toDataURL("image/png").split(",")[1];
    }, Number(opts.scale));
    writeFileSync(opts.out, Buffer.from(png, "base64"));
    console.log(`[preview] ${frames} frames; screenshot saved to ${opts.out}`);
    await browser.close();
    server.close();
    process.exit(log.some((line) => line.startsWith("Traceback")) ? 1 : 0);
}
