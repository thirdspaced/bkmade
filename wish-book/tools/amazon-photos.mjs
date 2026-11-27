// Fills wish-book/photos.json with live Amazon image links and tagged product links for every toy slot.
// Run by .github/workflows/wish-book-photos.yml twice a day. Needs Node 20+. No packages to install.
//
// Reads   wish-book/asins.json   { "n101": { "name": "Tickle Me Elmo Giggle Max", "asin": "" }, ... }
//         "asin" may be an ASIN (B0XXXXXXXX) or a full Amazon product link. Leave it "" to let the script
//         search by name and take the first result. Check those, since a search can pick the wrong product.
// Writes  wish-book/photos.json  { "updated": "...", "items": { "n101": { "img", "link", "title", "asin" } } }
//
// Secrets (GitHub repo settings, Secrets and variables, Actions):
//   AMAZON_CREDENTIAL_ID, AMAZON_CREDENTIAL_SECRET   from Associates Central, Tools, Creators API
//   AMAZON_PARTNER_TAG                               your Associates tag, like yourname-20
// Optional: AMAZON_MARKETPLACE (default www.amazon.com), AMAZON_TOKEN_URL (default is the North America endpoint)

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const ASINS = path.join(here, "..", "asins.json");
const OUT = path.join(here, "..", "photos.json");

const ID = process.env.AMAZON_CREDENTIAL_ID;
const SECRET = process.env.AMAZON_CREDENTIAL_SECRET;
const TAG = process.env.AMAZON_PARTNER_TAG;
const MARKET = process.env.AMAZON_MARKETPLACE || "www.amazon.com";
const TOKEN_URL = process.env.AMAZON_TOKEN_URL || "https://api.amazon.com/auth/o2/token";
const API = "https://creatorsapi.amazon/catalog/v1";
const RESOURCES = ["images.primary.large", "images.primary.medium", "itemInfo.title"];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function asinOf(value) {
  if (!value) return "";
  const v = String(value).trim();
  const m = v.match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})/i) || v.match(/^([A-Z0-9]{10})$/i);
  return m ? m[1].toUpperCase() : "";
}

export function pick(item) {
  if (!item) return null;
  const p = (item.images && item.images.primary) || {};
  const img = (p.large && p.large.url) || (p.medium && p.medium.url) || (p.small && p.small.url) || "";
  const link = item.detailPageURL || "";
  if (!/^https:\/\//.test(img) || !/^https:\/\//.test(link)) return null;
  const title = (item.itemInfo && item.itemInfo.title && item.itemInfo.title.displayValue) || "";
  return { img, link, title, asin: item.asin || "" };
}

async function token() {
  const r = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_type: "client_credentials", client_id: ID, client_secret: SECRET, scope: "creatorsapi::default" }),
  });
  if (!r.ok) throw new Error("Amazon would not issue a token (HTTP " + r.status + "). Check the credential ID and secret.");
  return (await r.json()).access_token;
}

async function call(op, tok, body) {
  const r = await fetch(API + "/" + op, {
    method: "POST",
    headers: { Authorization: "Bearer " + tok, "Content-Type": "application/json", "x-marketplace": MARKET },
    body: JSON.stringify({ marketplace: MARKET, partnerTag: TAG, resources: RESOURCES, ...body }),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(op + " failed (HTTP " + r.status + "): " + text.slice(0, 300));
  return JSON.parse(text);
}

export async function build(slots, api) {
  const items = {};
  const byAsin = {};
  for (const [slot, v] of Object.entries(slots)) {
    const a = asinOf(v && v.asin);
    if (a) (byAsin[a] = byAsin[a] || []).push(slot);
  }
  const asins = Object.keys(byAsin);
  for (let i = 0; i < asins.length; i += 10) {
    const res = await api("getItems", { itemIds: asins.slice(i, i + 10), itemIdType: "ASIN" });
    for (const it of (res.itemsResult && res.itemsResult.items) || []) {
      const got = pick(it);
      if (got) for (const slot of byAsin[it.asin] || []) items[slot] = got;
    }
    await sleep(1100);
  }
  // No ASIN given: search by name and take the first hit.
  for (const [slot, v] of Object.entries(slots)) {
    if (items[slot] || asinOf(v && v.asin) || !(v && v.name)) continue;
    try {
      const res = await api("searchItems", { keywords: v.name, itemCount: 1 });
      const got = pick(((res.searchResult && res.searchResult.items) || [])[0]);
      if (got) items[slot] = { ...got, searched: true };
      else console.log("No result for " + slot + " (" + v.name + ")");
    } catch (e) {
      console.log("Search failed for " + slot + " (" + v.name + "): " + e.message);
    }
    await sleep(1100);
  }
  return items;
}

async function main() {
  if (!ID || !SECRET || !TAG) {
    console.log("Amazon secrets are not set, so photos.json was left alone. See the notes at the top of this file.");
    return;
  }
  const slots = JSON.parse(await readFile(ASINS, "utf8"));
  const tok = await token();
  const items = await build(slots, (op, body) => call(op, tok, body));
  const n = Object.keys(items).length;
  if (!n) throw new Error("Amazon returned nothing usable, so photos.json was left alone.");
  await writeFile(OUT, JSON.stringify({ updated: new Date().toISOString(), items }, null, 1) + "\n");
  const searched = Object.entries(items).filter(([, v]) => v.searched).map(([k, v]) => k + " = " + v.title);
  console.log("Wrote " + n + " of " + Object.keys(slots).length + " slots.");
  if (searched.length) console.log("Found by name search, please check these:\n  " + searched.join("\n  "));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => { console.error(e.message); process.exit(1); });
}
