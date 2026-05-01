#!/usr/bin/env node
"use strict";

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageOrientation, Header, Footer, PageNumber,
} = require("docx");
const fs = require("fs");

// ── Colours ───────────────────────────────────────────────────────
const C = {
  darkBlue:   "1B3A5C", midBlue:  "2E75B6", lightBlue: "D5E8F0",
  green:      "1E7B4B", lightGreen:"E8F5EE",
  amber:      "C55A00", lightAmber:"FFF0E0",
  red:        "C00000", lightRed:  "FFE8E8",
  purple:     "5B2D8E", lightPurple:"F0EAF9",
  grey:       "595959", lightGrey: "F2F2F2", white: "FFFFFF",
};

// ── Layout constants ──────────────────────────────────────────────
const W = 9360;   // content width (US Letter, 1" margins)

// ── Helpers ───────────────────────────────────────────────────────
const b  = (color="CCCCCC") => ({ style: BorderStyle.SINGLE, size:1, color });
const bs = (color="CCCCCC") => ({ top:b(color), bottom:b(color), left:b(color), right:b(color) });
const cm = { top:90, bottom:90, left:130, right:130 };

const sp = (before=0, after=0) => ({ before, after });

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: sp(320,140),
    border: { bottom: { style: BorderStyle.SINGLE, size:8, color:C.midBlue, space:4 } },
    children: [new TextRun({ text, bold:true, size:36, color:C.darkBlue, font:"Arial" })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: sp(220,100),
    children: [new TextRun({ text, bold:true, size:28, color:C.midBlue, font:"Arial" })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: sp(160,80),
    children: [new TextRun({ text, bold:true, size:24, color:C.darkBlue, font:"Arial" })],
  });
}
function p(text, color=C.grey) {
  return new Paragraph({
    spacing: sp(50,50),
    children: [new TextRun({ text, size:22, font:"Arial", color })],
  });
}
function bullet(text, level=0) {
  return new Paragraph({
    numbering: { reference:"bullets", level },
    spacing: sp(30,30),
    children: [new TextRun({ text, size:22, font:"Arial", color:C.grey })],
  });
}
function code(text) {
  return new Paragraph({
    spacing: sp(40,40),
    shading: { fill:"1E1E1E", type:ShadingType.CLEAR },
    children: [new TextRun({ text, font:"Courier New", size:18, color:"D4D4D4" })],
  });
}
function gap(n=1) {
  return Array.from({length:n}, () =>
    new Paragraph({ spacing: sp(0,0), children:[new TextRun("")] })
  );
}

function hdr(cols, widths, fill=C.darkBlue) {
  return new TableRow({
    tableHeader: true,
    children: cols.map((text,i) => new TableCell({
      width: { size:widths[i], type:WidthType.DXA },
      borders: bs(fill), shading: { fill, type:ShadingType.CLEAR }, margins:cm,
      children: [new Paragraph({ children:[new TextRun({text, bold:true, size:20, font:"Arial", color:C.white})] })],
    })),
  });
}
function row(cells) {
  return new TableRow({
    children: cells.map(([text,width,fill=C.white,textColor=C.grey,bold=false]) =>
      new TableCell({
        width: { size:width, type:WidthType.DXA },
        borders: bs("CCCCCC"), shading: { fill, type:ShadingType.CLEAR }, margins:cm,
        children: [new Paragraph({ children:[new TextRun({text,size:20,font:"Arial",color:textColor,bold})] })],
      })
    ),
  });
}
function tbl(columnWidths, rows) {
  return new Table({ width:{size:W,type:WidthType.DXA}, columnWidths, rows });
}

// ══════════════════════════════════════════════════════════════════
//  SECTION BUILDERS
// ══════════════════════════════════════════════════════════════════

// ── TITLE PAGE ───────────────────────────────────────────────────
const titlePage = [
  ...gap(3),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: sp(0,160),
    children:[new TextRun({text:"AI TRADE VALIDATOR",bold:true,size:72,font:"Arial",color:C.darkBlue})],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: sp(0,60),
    children:[new TextRun({text:"Complete Project Handoff — v1.4.0",size:36,font:"Arial",color:C.midBlue})],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: sp(0,30),
    children:[new TextRun({text:"github.com/laithqc-create/ai-trading-vlidator",size:22,font:"Arial",color:C.grey})],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: sp(0,300),
    children:[new TextRun({text:"May 2026  |  54 Python Files  |  10,007 Lines of Code  |  10 Commits",size:22,font:"Arial",color:C.grey})],
  }),
  tbl([2340,2340,2340,2340],[
    new TableRow({ children:[
      ["54 Python Files",   2340,C.darkBlue, C.white,true],
      ["7,298 Py Lines",    2340,C.midBlue,  C.white,true],
      ["2,709 JS/HTML/CSS", 2340,C.green,    C.white,true],
      ["5 Release Tags",    2340,C.amber,    C.white,true],
    ].map(([text,width,fill,color,bold]) => new TableCell({
      width:{size:width,type:WidthType.DXA}, borders:bs(fill),
      shading:{fill,type:ShadingType.CLEAR},
      margins:{top:140,bottom:140,left:130,right:130},
      children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({text,bold,size:24,font:"Arial",color})]})],
    }))}),
  ]),
  ...gap(2),
];

// ── SECTION 1: OVERVIEW ──────────────────────────────────────────
const s1 = [
  h1("1. System Overview"),
  p("AI Trade Validator is a complete trading AI platform combining a Telegram bot, a browser extension, and a cloud backend. The system validates trading signals using two AI engines working together:"),
  ...gap(1),
  bullet("OpenTrade.ai (The Trader) — LangGraph multi-agent pipeline with 8 specialist AI agents. Fetches Yahoo Finance data, calculates RSI/MACD/Bollinger Bands, generates trading decisions with confidence scores."),
  bullet("RAGFlow (The Mentor) — Self-hosted RAG engine. Stores user's personal trading rules, retrieves historical patterns, validates and critiques the Trader's decisions, provides citations."),
  ...gap(1),
  h2("Three Products + Two Free Tools"),
  tbl([500,2000,1600,3000,2260],[
    hdr(["#","Product","Price","Entry Methods","Output"],[500,2000,1600,3000,2260]),
    row([["1",500],["Indicator Validator",2000],["$19/mo",1600,C.lightGreen,C.green],["Webhook / Share Code / AI Generate Pine Script",3000],["Signal verdict + confidence",2260]]),
    row([["2",500],["EA Analyzer",2000],["$49/mo",1600,C.lightGreen,C.green],["EA log monitor / AI Generate MQL5",3000],["Win/loss analysis + why",2260]]),
    row([["3",500],["Manual Validator",2000],["$19/mo",1600,C.lightGreen,C.green],["/check AAPL BUY 175",3000],["Second opinion + risk",2260]]),
    row([["—",500],["Pro Bundle",2000],["$79/mo",1600,C.lightBlue,C.midBlue,true],["All products",3000],["Everything + crowd insights",2260]]),
    row([["🆓",500],["Pine Script Generator",2000],["Free ($5 cap)",1600,C.lightAmber,C.amber],["English description",3000],["Pine Script v6 code",2260]]),
    row([["🆓",500],["MQL5 EA Generator",2000],["Free ($5 cap)",1600,C.lightAmber,C.amber],["English description",3000],["MQL5 Expert Advisor code",2260]]),
  ]),
  ...gap(1),
  h2("Browser Extension (New in v1.1–v1.4)"),
  p("A Chrome/Edge/Firefox extension that adds a capture button to TradingView. The extension has two modes:"),
  bullet("Validate My Analysis — user describes their trade setup (SMC/ICT or classic TA), AI validates against live market data and returns a Market Alignment confidence score"),
  bullet("AI Analyse My Chart — user selects patterns from 4 categories (34 total), AI scans the screenshot and returns per-pattern cards with found/not-found status, price zones, and drawing instructions"),
];

// ── SECTION 2: ARCHITECTURE ──────────────────────────────────────
const s2 = [
  h1("2. System Architecture"),
  h2("Core Data Flow"),
  code("Telegram User  OR  Browser Extension"),
  code("       |                    |"),
  code("       +--------------------+"),
  code("                   |"),
  code("      FastAPI Webhook Server  (main.py, port 8000)"),
  code("                   |  (returns 200 immediately)"),
  code("            Redis Task Queue"),
  code("                   |"),
  code("           Celery Worker"),
  code("                   |"),
  code("    +--------------+------------------+"),
  code("    |                                 |"),
  code("OpenTrade.ai (Trader)         RAGFlow (Mentor)"),
  code("  Yahoo Finance data           User's personal rules"),
  code("  RSI / MACD / BB / ATR        System rules (13 base)"),
  code("  LangGraph 8-agent FSM        Historical patterns"),
  code("  yfinance fallback            RAG retrieval"),
  code("    |                                 |"),
  code("    +----------Combined result--------+"),
  code("                   |"),
  code("    Celery pushes result to user via Telegram API"),
  code("    OR stored in Redis for Extension to poll"),
  ...gap(1),
  h2("Tech Stack"),
  tbl([2000,2800,4560],[
    hdr(["Layer","Technology","Purpose"],[2000,2800,4560]),
    row([["Telegram Bot",2000],["aiogram 3.20 + aiogram-dialog",2800],["FSM, keyboards, middleware, 16 bot commands",4560]]),
    row([["Browser Extension",2000],["Chrome MV3 (JS/HTML/CSS)",2800],["Screenshot capture, dual-mode analysis popup",4560]]),
    row([["Web API",2000],["FastAPI + Uvicorn",2800],["5 webhook endpoints + rate limiting + CORS",4560]]),
    row([["Task Queue",2000],["Celery + Redis",2800],["Async processing + Beat scheduler (3 jobs)",4560]]),
    row([["AI Trader",2000],["OpenTrade.ai (LangGraph)",2800],["Technical analysis, 8 specialist agents",4560]]),
    row([["AI Mentor",2000],["RAGFlow (self-hosted Docker)",2800],["RAG, user rules, knowledge base retrieval",4560]]),
    row([["Code Generator",2000],["DeepSeek API (OpenAI-compat)",2800],["Pine Script v6 + MQL5 EA generation",4560]]),
    row([["Market Data",2000],["Yahoo Finance + Polygon.io",2800],["OHLCV, real-time prices, news sentiment",4560]]),
    row([["Database",2000],["PostgreSQL + SQLAlchemy async",2800],["5 tables, Alembic migrations",4560]]),
    row([["Payments",2000],["Whop Payments",2800],["241 territories, HMAC webhook verification",4560]]),
    row([["Containers",2000],["Docker Compose",2800],["7 services: postgres, redis, api, worker, beat, ragflow, ollama",4560]]),
  ]),
];

// ── SECTION 3: FILE STRUCTURE ────────────────────────────────────
const s3 = [
  h1("3. Complete File Structure (62 files, 10,007 lines)"),
  h2("TG_Bot/ — Aiogram 3.x UI Layer"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["TG_Bot/main.py",3200],["Bot + Dispatcher factory. Redis FSM storage. on_startup registers 17 commands.",6160]]),
    row([["TG_Bot/config.py",3200],["Env loader for bot layer (reads root .env).",6160]]),
    row([["TG_Bot/states/states.py",3200],["6 FSM StatesGroups: GeneratePineScriptSG, GenerateMQL5SG, ShareCodeSG, ManualCheckSG, AddRuleSG, OutcomeSG",6160]]),
    row([["TG_Bot/middleware/subscription.py",3200],["Runs before every handler: auto-creates users, injects user object, rate-limits 20 req/min",6160]]),
    row([["TG_Bot/keyboards/main_menu.py",3200],["ReplyKeyboard: 6 persistent bottom-screen menu buttons",6160]]),
    row([["TG_Bot/keyboards/product_kb.py",3200],["InlineKeyboard: plan selector, verdict WIN/LOSS buttons, history, account. All 11 callbacks handled.",6160]]),
    row([["TG_Bot/keyboards/strategy_kb.py",3200],["3-button Product 1 selector, EA entry, signal BUY/SELL/HOLD, code result actions",6160]]),
    row([["TG_Bot/handlers/start.py",3200],["/start, menu routing (6 buttons), /help, /status, back callbacks",6160]]),
    row([["TG_Bot/handlers/generate.py",3200],["/generate (FSM), /generate_ea (FSM), /share_code (FSM + .pine file upload), /my_usage",6160]]),
    row([["TG_Bot/handlers/validate.py",3200],["/check, /outcome, /history, /add_rule, /my_rules, /connect_indicator, /connect_ea, /link + all missing callbacks",6160]]),
    row([["TG_Bot/handlers/subscription.py",3200],["/subscribe (Whop), /insights (Pro), plan comparison, cancel callback",6160]]),
  ]),
  ...gap(1),
  h2("Core Application Layer"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["main.py",3200],["FastAPI: /webhook/telegram, /webhook/indicator/{token}, /webhook/ea/{token}, /webhook/whop, /webhook/screenshot, /health",6160]]),
    row([["config/settings.py",3200],["Pydantic settings: 20 env vars. Whop + DeepSeek. No Stripe.",6160]]),
    row([["db/models.py",3200],["User, Validation, UserRule, EALog. Whop billing + generation tracking + ext_user_id.",6160]]),
    row([["db/migrations/001",3200],["Initial schema (4 tables)",6160]]),
    row([["db/migrations/002",3200],["Stripe → Whop + DeepSeek generation tracking columns",6160]]),
    row([["db/migrations/003",3200],["ext_user_id, linked_telegram_id, validations.source",6160]]),
  ]),
  ...gap(1),
  h2("Services Layer"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["services/validation.py",3200],["Orchestrates Trader + Mentor. validate_manual(), validate_indicator(), analyze_ea_trade(). Polygon.io wired. user_description support. _append_user_description().",6160]]),
    row([["services/user.py",3200],["CRUD, webhook tokens, daily counter, Whop plan, DeepSeek budget helpers (increment_generation_cost, is_over_generation_cap)",6160]]),
    row([["services/subscription.py",3200],["WhopService: get_checkout_url(), verify_subscription(), verify_webhook_signature(), parse_plan_from_product_id()",6160]]),
    row([["services/deepseek.py",3200],["DeepSeekService: generate_pine_script(), generate_mql5(). Pine/MQL5 system prompts, fence stripping, tenacity retry",6160]]),
    row([["services/market_data.py",3200],["PolygonService: get_snapshot(), get_previous_close(), get_news()",6160]]),
  ]),
  ...gap(1),
  h2("AI Integration Layer"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["opentrade/service.py",3200],["OpenTradeService: LangGraph pipeline wrapper + full yfinance/ta fallback. Parses 8-agent state into TraderAnalysis dataclass.",6160]]),
    row([["ragflow/service.py",3200],["RAGFlowService: dataset management, add_rule_to_dataset(), validate_signal() with user_description enrichment, seed_system_knowledge_base() (13 rules)",6160]]),
  ]),
  ...gap(1),
  h2("Workers Layer"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["workers/celery_app.py",3200],["Celery + Redis broker. Task autodiscovery. 5-min hard limit.",6160]]),
    row([["workers/tasks.py",3200],["3 async tasks: validate_manual_task, validate_indicator_task, analyze_ea_task. Each saves to DB + pushes Telegram message.",6160]]),
    row([["workers/scheduler.py",3200],["Celery Beat: reset_daily_counters (midnight UTC), expire_stale_validations (hourly), aggregate_crowd_insights (weekly)",6160]]),
  ]),
  ...gap(1),
  h2("Browser Extension (extension/)"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["manifest.json",3200],["MV3. Permissions: activeTab, storage, tabs, scripting. Content script on *.tradingview.com.",6160]]),
    row([["popup.html",3200],["4-step UI: Capture → Mode Select → (Validate/Analyse) → Result",6160]]),
    row([["popup.js",3200],["711 lines. Screenshot persistence (5h). Category tabs. Pattern checkboxes. Dual-mode submit. Pattern card rendering. History.",6160]]),
    row([["styles.css",3200],["387 lines. Catppuccin Mocha dark theme. Mode cards, category tabs, pattern grid, pattern cards, confidence bar.",6160]]),
    row([["background.js",3200],["Service worker: install → onboarding.html, badge, context menu on TradingView",6160]]),
    row([["content.js",3200],["4-strategy ticker detection (DOM/URL/title/search). Price detection from chart legend.",6160]]),
    row([["onboarding.html",3200],["Setup page on first install: API URL + bot username. 4-step visual guide.",6160]]),
    row([["history.html",3200],["Full-page history viewer: stats, search, filter, pagination (15/page), clear all.",6160]]),
    row([["generate_icons.py",3200],["Generates icon16/48/128.png from Pillow (camera + chart bars design).",6160]]),
  ]),
  ...gap(1),
  h2("Backend Extension Endpoint"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["webhooks/screenshot.py",3200],["547 lines. POST /webhook/screenshot (validate|analyse mode, SL/TP, patterns JSON). GET /result/{id}. _parse_pattern_results() with heuristics for 34 patterns. Redis async storage.",6160]]),
  ]),
  ...gap(1),
  h2("Scripts & Tests"),
  tbl([3200,6160],[
    hdr(["File","Purpose"],[3200,6160]),
    row([["scripts/setup.py",3200],["One-shot: register Telegram webhook, seed RAGFlow KB (13 rules), test all connections",6160]]),
    row([["scripts/ea_monitor.py",3200],["MT4/MT5 log-tailer: tails EA.log, parses MT4 patterns, deduplication, POSTs to webhook",6160]]),
    row([["scripts/ea_snippet.mq5",3200],["MQL5 OnTradeTransaction() snippet for MT5 EAs — paste to send completed trades",6160]]),
    row([["tests/test_suite.py",3200],["60+ tests: OpenTrade, RAGFlow, ValidationService, Polygon, rate limiter, scheduler, EA monitor, bot commands, screenshot endpoint, DeepSeek, Whop, user description flow",6160]]),
  ]),
];

// ── SECTION 4: BOT COMMANDS ──────────────────────────────────────
const s4 = [
  h1("4. All Bot Commands (17 total)"),
  tbl([2000,1300,3200,2860],[
    hdr(["Command","Tier","Description","Handler"],[2000,1300,3200,2860]),
    row([["/start",2000],["Free",1300,C.lightGreen,C.green],["Welcome + main menu keyboard",3200],["handlers/start.py",2860]]),
    row([["/generate <strategy>",2000],["Free",1300,C.lightGreen,C.green],["English → Pine Script v6 (DeepSeek, $5 cap)",3200],["handlers/generate.py",2860]]),
    row([["/generate_ea <strategy>",2000],["Free",1300,C.lightGreen,C.green],["English → MQL5 EA (DeepSeek, same cap)",3200],["handlers/generate.py",2860]]),
    row([["/share_code",2000],["Free",1300,C.lightGreen,C.green],["Paste Pine Script → stored in RAGFlow KB",3200],["handlers/generate.py",2860]]),
    row([["/my_usage",2000],["Free",1300,C.lightGreen,C.green],["DeepSeek generation budget bar",3200],["handlers/generate.py",2860]]),
    row([["/check TICKER SIGNAL",2000],["Paid",1300,C.lightBlue,C.midBlue],["Manual trade validation (P3 or Pro)",3200],["handlers/validate.py",2860]]),
    row([["/outcome WIN|LOSS [#id]",2000],["Free",1300,C.lightGreen,C.green],["Report trade result → crowd insights",3200],["handlers/validate.py",2860]]),
    row([["/add_rule <text>",2000],["Free",1300,C.lightGreen,C.green],["Add personal rule to RAGFlow KB",3200],["handlers/validate.py",2860]]),
    row([["/my_rules",2000],["Free",1300,C.lightGreen,C.green],["List personal trading rules",3200],["handlers/validate.py",2860]]),
    row([["/history",2000],["Free",1300,C.lightGreen,C.green],["Last 10 validations + self-reported accuracy",3200],["handlers/validate.py",2860]]),
    row([["/link EXT_ID",2000],["Free",1300,C.lightGreen,C.green],["Link browser extension to Telegram account",3200],["handlers/validate.py",2860]]),
    row([["/insights",2000],["Pro",1300,C.lightAmber,C.amber],["Crowd win-rate stats (anonymized)",3200],["handlers/subscription.py",2860]]),
    row([["/connect_indicator",2000],["P1/Pro",1300,C.lightBlue,C.midBlue],["TradingView webhook URL",3200],["handlers/validate.py",2860]]),
    row([["/connect_ea",2000],["P2/Pro",1300,C.lightBlue,C.midBlue],["EA monitor script + MQL5 snippet",3200],["handlers/validate.py",2860]]),
    row([["/subscribe",2000],["All",1300],["Whop plan selection (4 tiers)",3200],["handlers/subscription.py",2860]]),
    row([["/status",2000],["All",1300],["Plan, usage, connections overview",3200],["handlers/start.py",2860]]),
    row([["/help",2000],["All",1300],["Full command reference",3200],["handlers/start.py",2860]]),
  ]),
];

// ── SECTION 5: EXTENSION FLOW ────────────────────────────────────
const s5 = [
  h1("5. Browser Extension — Full User Flow"),
  h2("Step 1 — Capture"),
  bullet("Click extension icon on any TradingView chart page"),
  bullet("Click 📸 Capture TradingView Chart — uses chrome.tabs.captureVisibleTab()"),
  bullet("Screenshot persists for 5 hours in chrome.storage — no retake needed each session"),
  bullet("Age chip shows '📸 12m ago', yellows at under 30 minutes remaining"),
  bullet("Auto-detect ticker: 4-strategy (TradingView DOM → URL → page title → search bar)"),
  bullet("Auto-detect price from chart legend"),
  ...gap(1),
  h2("Step 2 — Mode Select"),
  tbl([2200,7160],[
    hdr(["Mode","When to use"],[2200,7160]),
    row([["🧠 Validate My Analysis",2200],["Trader already has a view (SMC setup, classic pattern, etc.) and wants AI to check it against current market data",7160]]),
    row([["🔍 AI Analyse My Chart",2200],["Trader wants fresh eyes — selects patterns to check, AI scans the screenshot and returns per-pattern cards",7160]]),
  ]),
  ...gap(1),
  h2("Step 3a — Validate My Analysis"),
  bullet("Large textarea (800 chars) — describe your full trade setup in plain English"),
  bullet("Placeholder shows real trading example: BOS, FVG, liquidity sweep, SL/TP context"),
  bullet("Optional SL / TP / Entry Price in compact 3-column row"),
  bullet("AI enriches RAGFlow query with the user's thesis → validates against OpenTrade.ai data"),
  bullet("Result: Market Alignment % confidence score + 5-line validation response"),
  ...gap(1),
  h2("Step 3b — AI Analyse My Chart (34 Patterns, 4 Categories)"),
  tbl([2000,7360],[
    hdr(["Category","Patterns"],[2000,7360]),
    row([["SMC / ICT",2000],["Order Blocks, FVG, Breaker Blocks, Liquidity Sweeps, CHoCH, BOS, Equal Highs/Lows, Mitigation Blocks, SMT Divergence, Turtle Soup, Silver Bullet",7360]]),
    row([["Classic TA",2000],["Head & Shoulders, Double Top/Bottom, Triangles, Support/Resistance, Flags/Pennants, Cup & Handle, Wedges, Rounding Bottom",7360]]),
    row([["Scalper",2000],["Killzone Detection, Silver Bullet Setup, Micro Liquidity Sweeps, Micro Order Blocks, Turtle Soup (LTF), Judas Swing",7360]]),
    row([["Swing",2000],["Market Structure BOS/CHoCH, Previous Day/Week Levels, OTE, Head & Shoulders, Cup & Handle, Accumulation-Manipulation-Distribution",7360]]),
  ]),
  ...gap(1),
  h2("Step 4 — Results"),
  bullet("Verdict badge: CONFIRM / CAUTION / REJECT with colour coding"),
  bullet("Confidence bar: 'Market Alignment' (validate) or 'Pattern Match Score' (analyse)"),
  bullet("Validate mode: reasoning text + user's analysis echoed back with blue border"),
  bullet("Analyse mode: 2-column pattern cards — Found (green) shows zone, note, ✏️ drawing instructions; Not-found (muted) shows 'Not detected'"),
  bullet("Indicator chips: RSI, MACD, BB position, current price"),
  bullet("Copy to clipboard / Open Telegram / New Analysis buttons"),
  bullet("Every analysis saved to local history (last 50 entries)"),
];

// ── SECTION 6: API ENDPOINTS ─────────────────────────────────────
const s6 = [
  h1("6. API Endpoints (FastAPI)"),
  tbl([700,3600,5060],[
    hdr(["Method","Endpoint","Purpose"],[700,3600,5060]),
    row([["GET",700,C.lightGreen,C.green],["/health",3600],["Health check",5060]]),
    row([["POST",700,C.lightBlue,C.midBlue],["/webhook/telegram",3600],["Telegram updates → aiogram feed_update()",5060]]),
    row([["POST",700,C.lightBlue,C.midBlue],["/webhook/indicator/{token}",3600],["TradingView signal → validate_indicator_task (60/min/token)",5060]]),
    row([["POST",700,C.lightBlue,C.midBlue],["/webhook/ea/{token}",3600],["EA trade log → analyze_ea_task (60/min/token)",5060]]),
    row([["POST",700,C.lightBlue,C.midBlue],["/webhook/whop",3600],["Whop events: subscription.created/cancelled, payment.failed",5060]]),
    row([["POST",700,C.lightBlue,C.midBlue],["/webhook/screenshot",3600],["Extension screenshot → validate or analyse mode (20/min/user)",5060]]),
    row([["GET",700,C.lightGreen,C.green],["/webhook/screenshot/result/{id}",3600],["Poll for extension analysis result",5060]]),
  ]),
  ...gap(1),
  h2("Screenshot Endpoint — POST Fields"),
  tbl([2400,1600,5360],[
    hdr(["Field","Required","Notes"],[2400,1600,5360]),
    row([["screenshot",2400],["Yes",1600,C.lightRed,C.red],["PNG/JPEG image file, max 10 MB",5360]]),
    row([["ticker",2400],["Yes",1600,C.lightRed,C.red],["e.g. AAPL, EURUSD — max 12 chars",5360]]),
    row([["signal",2400],["Yes",1600,C.lightRed,C.red],["BUY / SELL / HOLD",5360]]),
    row([["mode",2400],["Yes",1600,C.lightRed,C.red],["validate | analyse",5360]]),
    row([["description",2400],["validate: Yes",1600,C.lightAmber,C.amber],["User's trade analysis text (max 800 chars)",5360]]),
    row([["patterns",2400],["analyse: Yes",1600,C.lightAmber,C.amber],["JSON array of pattern names to scan for",5360]]),
    row([["price / sl / tp",2400],["No",1600,C.lightGreen,C.green],["Optional entry price, stop loss, take profit",5360]]),
    row([["user_id",2400],["Yes",1600,C.lightRed,C.red],["Extension-generated ID (stored in chrome.storage)",5360]]),
  ]),
];

// ── SECTION 7: ENVIRONMENT VARIABLES ─────────────────────────────
const s7 = [
  h1("7. Environment Variables"),
  tbl([3000,1800,4560],[
    hdr(["Variable","Required","Where to get it"],[3000,1800,4560]),
    row([["TELEGRAM_BOT_TOKEN",3000],["YES",1800,C.lightRed,C.red],["@BotFather on Telegram",4560]]),
    row([["TELEGRAM_WEBHOOK_URL",3000],["Prod",1800,C.lightAmber,C.amber],["https://your-domain.com/webhook/telegram",4560]]),
    row([["DATABASE_URL",3000],["YES",1800,C.lightRed,C.red],["postgresql+asyncpg://user:pass@host/db",4560]]),
    row([["REDIS_URL",3000],["YES",1800,C.lightRed,C.red],["redis://localhost:6379/0",4560]]),
    row([["RAGFLOW_API_KEY",3000],["YES",1800,C.lightRed,C.red],["RAGFlow UI → Settings → API Key",4560]]),
    row([["RAGFLOW_BASE_URL",3000],["YES",1800,C.lightRed,C.red],["http://localhost:9380",4560]]),
    row([["WHOP_API_KEY",3000],["YES",1800,C.lightRed,C.red],["dash.whop.com → Settings → Developer",4560]]),
    row([["WHOP_WEBHOOK_SECRET",3000],["YES",1800,C.lightRed,C.red],["Whop Dashboard → Webhooks",4560]]),
    row([["WHOP_PRODUCT_ID_PRODUCT1",3000],["YES",1800,C.lightRed,C.red],["Whop Dashboard ($19/mo)",4560]]),
    row([["WHOP_PRODUCT_ID_PRODUCT2",3000],["YES",1800,C.lightRed,C.red],["Whop Dashboard ($49/mo)",4560]]),
    row([["WHOP_PRODUCT_ID_PRODUCT3",3000],["YES",1800,C.lightRed,C.red],["Whop Dashboard ($19/mo)",4560]]),
    row([["WHOP_PRODUCT_ID_PRO",3000],["YES",1800,C.lightRed,C.red],["Whop Dashboard ($79/mo)",4560]]),
    row([["DEEPSEEK_API_KEY",3000],["YES",1800,C.lightRed,C.red],["platform.deepseek.com",4560]]),
    row([["POLYGON_API_KEY",3000],["Rec.",1800,C.lightAmber,C.amber],["polygon.io — for Product 3 live data",4560]]),
    row([["LLM_PROVIDER",3000],["Optional",1800,C.lightGreen,C.green],["ollama (default) | openai | lmstudio",4560]]),
    row([["LLM_MODEL",3000],["Optional",1800,C.lightGreen,C.green],["llama3 (default) | gpt-4o-mini",4560]]),
    row([["DEEPSEEK_FREE_CAP",3000],["Optional",1800,C.lightGreen,C.green],["Default: 5.00 (dollars absorbed per user)",4560]]),
    row([["FREE_TIER_DAILY_LIMIT",3000],["Optional",1800,C.lightGreen,C.green],["Default: 5 validations/day on free plan",4560]]),
  ]),
];

// ── SECTION 8: DEPLOYMENT ────────────────────────────────────────
const s8 = [
  h1("8. Deployment"),
  h2("VPS Requirements"),
  tbl([3000,3000,3360],[
    hdr(["Component","Minimum","Recommended"],[3000,3000,3360]),
    row([["RAM",3000],["8 GB",3000],["16 GB (RAGFlow needs 16 GB)",3360]]),
    row([["CPU",3000],["2 vCores",3000],["4 vCores",3360]]),
    row([["Storage",3000],["50 GB SSD",3000],["100 GB SSD",3360]]),
    row([["Cost/mo",3000],["~$30 (Hetzner CX31)",3000],["~$60 (Hetzner CX41)",3360]]),
  ]),
  ...gap(1),
  h2("Quick Start (6 Commands)"),
  code("git clone https://github.com/laithqc-create/ai-trading-vlidator.git"),
  code("cd ai-trading-vlidator && cp .env.example .env && nano .env"),
  code("docker compose up -d postgres redis api worker beat"),
  code("docker compose exec api alembic upgrade head"),
  code("docker compose exec api python scripts/setup.py"),
  code("# Full stack with RAGFlow (16 GB VPS):"),
  code("docker compose --profile full up -d"),
  ...gap(1),
  h2("Load Browser Extension"),
  bullet("Run: cd extension && python3 generate_icons.py"),
  bullet("Chrome: chrome://extensions → Developer mode → Load unpacked → select extension/"),
  bullet("On first install: onboarding.html opens automatically — enter API URL + bot username"),
  bullet("Navigate to TradingView → click extension icon → 📸 Capture"),
  ...gap(1),
  h2("Celery Beat Scheduler"),
  tbl([2600,2200,4560],[
    hdr(["Task","Schedule","Action"],[2600,2200,4560]),
    row([["reset_daily_counters",2600],["Midnight UTC",2200],["Resets free-tier validation counter",4560]]),
    row([["expire_stale_validations",2600],["Every hour",2200],["Marks PENDING tasks >10 min as FAILED",4560]]),
    row([["aggregate_crowd_insights",2600],["Sunday 2am UTC",2200],["Builds anonymized win-rate stats in RAGFlow KB",4560]]),
  ]),
];

// ── SECTION 9: PRICING ───────────────────────────────────────────
const s9 = [
  h1("9. Pricing & Monetisation"),
  tbl([1800,1500,4200,2060],[
    hdr(["Plan","Price","Features","Whop Config"],[1800,1500,4200,2060]),
    row([["Free",1800],["$0",1500],["5 validations/day + unlimited /generate + /generate_ea",4200],["No product ID needed",2060]]),
    row([["Product 1",1800,C.lightGreen],["$19/mo",1500],["Webhook + share code + personal KB",4200],["WHOP_PRODUCT_ID_PRODUCT1",2060]]),
    row([["Product 2",1800,C.lightGreen],["$49/mo",1500],["EA log analysis + win/loss explanations",4200],["WHOP_PRODUCT_ID_PRODUCT2",2060]]),
    row([["Product 3",1800,C.lightGreen],["$19/mo",1500],["Unlimited /check + Polygon.io live data",4200],["WHOP_PRODUCT_ID_PRODUCT3",2060]]),
    row([["Pro Bundle",1800,C.lightBlue],["$79/mo",1500],["All products + crowd insights + priority queue",4200],["WHOP_PRODUCT_ID_PRO",2060]]),
  ]),
  ...gap(1),
  h2("Free Generation Cost Model"),
  bullet("DeepSeek cost per generation: $0.002 (2/10 of a cent)"),
  bullet("Free cap per user: $5.00 lifetime (~2,500 generations)"),
  bullet("Budget tracked: users.total_generations + users.total_generation_cost"),
  bullet("Warning shown at $4.50 spent. Hard block at $5.00."),
  bullet("Worst case monthly cost per heavy user: ~$0.50"),
  bullet("Extension screenshot analysis: uses same OpenTrade.ai + RAGFlow pipeline (no extra cost)"),
];

// ── SECTION 10: RELEASE HISTORY ──────────────────────────────────
const s10 = [
  h1("10. Release History"),
  tbl([1200,9160],[
    hdr(["Tag","Changes"],[1200,9160]),
    row([["v1.0.0",1200],["Initial stable release: FastAPI backend, aiogram 3.x bot, OpenTrade.ai + RAGFlow integration, Whop payments, DeepSeek code generation, Celery + Beat, all bot commands, 40 tests",9160]]),
    row([["v1.1.0",1200],["Browser extension (Chrome MV3): screenshot capture, 3-step popup, backend /webhook/screenshot endpoint, optional trade notes field",9160]]),
    row([["v1.2.0",1200],["Gap closure: onboarding.html, history.html, Redis async fix, 60 tests total, .dockerignore",9160]]),
    row([["v1.3.0",1200],["All 11 missing callbacks handled, /link command (extension-Telegram linking), ext_user_id in DB (migration 003), stale bot layer deprecated",9160]]),
    row([["v1.4.0",1200],["Dual-mode extension: Validate My Analysis (user describes setup) + AI Analyse My Chart (34 patterns, 4 categories, per-pattern cards with drawing instructions). Full popup/JS/CSS/backend rewrite.",9160]]),
  ]),
];

// ── SECTION 11: NEXT STEPS ───────────────────────────────────────
const s11 = [
  h1("11. Next Steps — Go Live Checklist"),
  h2("Required Before First User"),
  bullet("Create products in Whop Dashboard → copy 4 product IDs → add to .env"),
  bullet("Get DeepSeek API key from platform.deepseek.com → add to .env"),
  bullet("Create Telegram bot via @BotFather → copy token → add to .env"),
  bullet("Provision VPS (Hetzner CX31 = €8/mo minimum, CX41 = €16/mo with RAGFlow)"),
  bullet("Install Ollama: curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3"),
  bullet("Run docker compose up -d && alembic upgrade head && python scripts/setup.py"),
  bullet("Load extension in Chrome and complete onboarding (set API URL)"),
  bullet("Test: /start → /generate Buy when RSI below 30 → /check AAPL BUY"),
  bullet("Test extension: TradingView chart → capture → validate mode → submit"),
  ...gap(1),
  h2("Optional Enhancements"),
  bullet("Vision AI: integrate GPT-4o Vision or Claude claude-opus-4-6 to actually read the screenshot image (current: heuristic pattern detection based on RSI/MACD/BB)"),
  bullet("Switch from heuristic _parse_pattern_results() to multimodal LLM for true chart vision"),
  bullet("Nginx + SSL: see DEPLOYMENT.md for certbot setup"),
  bullet("Whop affiliate links for referral system (built into Whop dashboard)"),
  bullet("Admin dashboard for subscription analytics"),
  bullet("Firefox extension: add WebExtensions polyfill, replace chrome.* with browser.*"),
  bullet("Chrome Web Store: zip extension/ → submit at chrome.google.com/webstore/devconsole ($5 one-time fee)"),
  ...gap(1),
  h2("Known Limitations"),
  bullet("Pattern detection is technical-indicator-based (RSI/MACD/BB heuristics), not true chart image vision — upgrade to multimodal LLM for accurate pattern recognition"),
  bullet("OpenTrade.ai LangGraph with local LLM is slow (60-120s) — users see 'analysing...' during this time. Switch to OpenAI API (LLM_PROVIDER=openai) for faster responses."),
  bullet("RAGFlow requires 16 GB RAM — run on separate VPS if budget is tight"),
  bullet("In-memory rate limiters reset on restart — use Redis-based limiter for multi-instance"),
];

// ══════════════════════════════════════════════════════════════════
//  DOCUMENT ASSEMBLY
// ══════════════════════════════════════════════════════════════════
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{ level:0, format:LevelFormat.BULLET, text:"•", alignment:AlignmentType.LEFT,
        style:{ paragraph:{ indent:{ left:720, hanging:360 } } } }],
    }],
  },
  styles: {
    default: { document:{ run:{ font:"Arial", size:22, color:C.grey } } },
    paragraphStyles: [
      { id:"Heading1", name:"Heading 1", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{ size:36, bold:true, font:"Arial", color:C.darkBlue },
        paragraph:{ spacing:{ before:320, after:140 }, outlineLevel:0 } },
      { id:"Heading2", name:"Heading 2", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{ size:28, bold:true, font:"Arial", color:C.midBlue },
        paragraph:{ spacing:{ before:220, after:100 }, outlineLevel:1 } },
      { id:"Heading3", name:"Heading 3", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{ size:24, bold:true, font:"Arial", color:C.darkBlue },
        paragraph:{ spacing:{ before:160, after:80 }, outlineLevel:2 } },
    ],
  },
  sections: [{
    properties: {
      page: { size:{ width:12240, height:15840 }, margin:{ top:1440, right:1440, bottom:1440, left:1440 } }
    },
    children: [
      ...titlePage,   ...gap(1),
      ...s1,          ...gap(1),
      ...s2,          ...gap(1),
      ...s3,          ...gap(1),
      ...s4,          ...gap(1),
      ...s5,          ...gap(1),
      ...s6,          ...gap(1),
      ...s7,          ...gap(1),
      ...s8,          ...gap(1),
      ...s9,          ...gap(1),
      ...s10,         ...gap(1),
      ...s11,
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/mnt/user-data/outputs/AI_Trade_Validator_Handoff_v1.4.0.docx", buf);
  console.log("Done — AI_Trade_Validator_Handoff_v1.4.0.docx");
});
