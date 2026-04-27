#!/usr/bin/env node
// Generate HANDOFF.docx via docx-js

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageOrientation, Header, Footer, PageNumber,
  NumberFormat, TabStopType, TabStopPosition
} = require("docx");
const fs = require("fs");

// ── Colours ──────────────────────────────────────────────────────────────────
const C = {
  darkBlue:  "1B3A5C",
  midBlue:   "2E75B6",
  lightBlue: "D5E8F0",
  green:     "1E7B4B",
  lightGreen:"E8F5EE",
  amber:     "C55A00",
  lightAmber:"FFF0E0",
  red:       "C00000",
  lightRed:  "FFE8E8",
  grey:      "595959",
  lightGrey: "F2F2F2",
  white:     "FFFFFF",
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const border  = (color = "CCCCCC") => ({ style: BorderStyle.SINGLE, size: 1, color });
const borders = (color = "CCCCCC") => ({ top: border(color), bottom: border(color), left: border(color), right: border(color) });
const cellMargins = { top: 100, bottom: 100, left: 140, right: 140 };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 320, after: 160 },
    children: [new TextRun({ text, bold: true, size: 36, color: C.darkBlue, font: "Arial" })],
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.midBlue, space: 4 } },
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, bold: true, size: 28, color: C.midBlue, font: "Arial" })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 180, after: 80 },
    children: [new TextRun({ text, bold: true, size: 24, color: C.darkBlue, font: "Arial" })],
  });
}

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text, size: 22, font: "Arial", color: C.grey, ...opts })],
  });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, size: 22, font: "Arial", color: C.grey })],
  });
}

function code(text) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    shading: { fill: "1E1E1E", type: ShadingType.CLEAR },
    children: [new TextRun({ text, font: "Courier New", size: 18, color: "D4D4D4" })],
  });
}

function spacer(lines = 1) {
  return Array.from({ length: lines }, () =>
    new Paragraph({ spacing: { before: 0, after: 0 }, children: [new TextRun("")] })
  );
}

// ── Status badge helper ───────────────────────────────────────────────────────
function statusCell(text, fill) {
  return new TableCell({
    borders: borders(fill),
    shading: { fill, type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text, bold: true, size: 18, font: "Arial", color: C.white })],
    })],
  });
}

function tableRow(cells, headerFill = null) {
  return new TableRow({
    children: cells.map(([text, width, fill, textColor, bold] = []) =>
      new TableCell({
        width: { size: width || 2000, type: WidthType.DXA },
        borders: borders("CCCCCC"),
        shading: { fill: fill || C.white, type: ShadingType.CLEAR },
        margins: cellMargins,
        children: [new Paragraph({
          children: [new TextRun({
            text: text || "",
            size: 20, font: "Arial",
            color: textColor || C.grey,
            bold: bold || false,
          })],
        })],
      })
    ),
  });
}

function headerRow(labels, widths, fill = C.darkBlue) {
  return new TableRow({
    tableHeader: true,
    children: labels.map((label, i) =>
      new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        borders: borders(fill),
        shading: { fill, type: ShadingType.CLEAR },
        margins: cellMargins,
        children: [new Paragraph({
          children: [new TextRun({ text: label, bold: true, size: 20, font: "Arial", color: C.white })],
        })],
      })
    ),
  });
}

// ── TITLE PAGE ────────────────────────────────────────────────────────────────
const titleSection = [
  ...spacer(3),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 200 },
    children: [new TextRun({ text: "AI TRADE VALIDATOR", bold: true, size: 72, font: "Arial", color: C.darkBlue })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 80 },
    children: [new TextRun({ text: "Telegram Bot — Complete Project Handoff", size: 36, font: "Arial", color: C.midBlue })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 40 },
    children: [new TextRun({ text: "Repository: github.com/laithqc-create/ai-trading-vlidator", size: 22, font: "Arial", color: C.grey })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 400 },
    children: [new TextRun({ text: "April 2026  |  50 Python Files  |  7,938 Lines of Code  |  4 Git Commits", size: 22, font: "Arial", color: C.grey })],
  }),

  // Stats boxes
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2340, 2340, 2340, 2340],
    rows: [
      new TableRow({ children: [
        ["50 Python Files",    2340, C.darkBlue,  C.white, true],
        ["7,938 Lines",        2340, C.midBlue,   C.white, true],
        ["4 Git Commits",      2340, C.green,     C.white, true],
        ["100% Syntax Clean",  2340, C.amber,     C.white, true],
      ].map(([text, width, fill, color, bold]) => new TableCell({
        width: { size: width, type: WidthType.DXA },
        borders: borders(fill),
        shading: { fill, type: ShadingType.CLEAR },
        margins: { top: 160, bottom: 160, left: 140, right: 140 },
        children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
          new TextRun({ text, bold, size: 26, font: "Arial", color }),
        ]})],
      }))}),
    ],
  }),
  ...spacer(2),
];

// ── SECTION 1: OVERVIEW ───────────────────────────────────────────────────────
const overviewSection = [
  h1("1. Project Overview"),
  p("AI Trade Validator is a production-ready Telegram bot that validates trading signals using two AI systems working together:"),
  bullet("OpenTrade.ai (The Trader) — LangGraph multi-agent pipeline: fetches Yahoo Finance data, calculates RSI/MACD/Bollinger Bands, runs 8 specialist agents, generates trading decisions"),
  bullet("RAGFlow (The Mentor) — Self-hosted RAG engine: stores user rules and historical patterns, retrieves relevant context, validates and critiques the Trader's decisions"),
  ...spacer(1),
  h2("Three Products"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [500, 2200, 2000, 2600, 2060],
    rows: [
      headerRow(["#", "Product", "Price", "Input", "Output"], [500, 2200, 2000, 2600, 2060]),
      tableRow([["1", 500], ["Indicator Validator", 2200], ["$19/mo", 2000, C.lightGreen, C.green], ["TradingView webhook / source code / AI generate", 2600], ["Confidence score + verdict", 2060]]),
      tableRow([["2", 500], ["EA Analyzer", 2200], ["$49/mo", 2000, C.lightGreen, C.green], ["EA log file (via monitor script)", 2600], ["Win/loss analysis + why", 2060]]),
      tableRow([["3", 500], ["Manual Validator", 2200], ["$19/mo", 2000, C.lightGreen, C.green], ["/check AAPL BUY 175", 2600], ["Second opinion + risk assessment", 2060]]),
      tableRow([["—", 500], ["Pro Bundle", 2200], ["$79/mo", 2000, C.lightBlue, C.midBlue, true], ["All products", 2600], ["Everything + crowd insights", 2060]]),
    ],
  }),
  ...spacer(1),
  h2("Free Loss Leader Features"),
  bullet("Pine Script Generator: /generate <strategy> → Pine Script v6 code (DeepSeek AI, ~$0.002/call)"),
  bullet("MQL5 EA Generator: /generate_ea <strategy> → MetaTrader 5 EA code (same cost)"),
  bullet("Cost absorbed up to $5/user lifetime — ~2,500 generations before cap"),
  bullet("Every generation ends with an upsell prompt to subscribe"),
];

// ── SECTION 2: ARCHITECTURE ───────────────────────────────────────────────────
const architectureSection = [
  h1("2. System Architecture"),
  h2("Data Flow"),
  p("Every validation follows this async pipeline:"),
  code("Telegram User"),
  code("  ↓ (command or webhook)"),
  code("FastAPI Webhook Server  (port 8000, main.py)"),
  code("  ↓ (acknowledges immediately → returns 200)"),
  code("Celery Worker  (async task, Redis queue)"),
  code("  ↓"),
  code("┌─────────────────────┬──────────────────────────┐"),
  code("│  OpenTrade.ai       │  RAGFlow                 │"),
  code("│  (The Trader)       │  (The Mentor)            │"),
  code("│  • Yahoo Finance    │  • User's personal rules │"),
  code("│  • RSI/MACD/BB      │  • System rules (13)     │"),
  code("│  • 8 AI agents      │  • Historical patterns   │"),
  code("│  • LangGraph FSM    │  • RAG retrieval         │"),
  code("└─────────────────────┴──────────────────────────┘"),
  code("  ↓ Combined verdict + confidence score"),
  code("Telegram Bot pushes result message to user"),
  ...spacer(1),
  h2("Why Async (Celery)?"),
  p("Telegram requires webhook responses within 30 seconds. The OpenTrade.ai LangGraph pipeline with a local LLM takes 60-120 seconds. Solution: acknowledge the webhook immediately, queue the analysis task in Redis, Celery worker processes it, then pushes the result directly to the user via Telegram API."),
  ...spacer(1),
  h2("Tech Stack"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2500, 3000, 3860],
    rows: [
      headerRow(["Layer", "Technology", "Purpose"], [2500, 3000, 3860]),
      tableRow([["Bot Framework", 2500], ["aiogram 3.20.0 + aiogram-dialog", 3000], ["Telegram UI, FSM, keyboards", 3860]]),
      tableRow([["Web API", 2500], ["FastAPI + Uvicorn", 3000], ["Webhook receiver, REST endpoints", 3860]]),
      tableRow([["Task Queue", 2500], ["Celery + Redis", 3000], ["Async processing, Beat scheduler", 3860]]),
      tableRow([["AI Trader", 2500], ["OpenTrade.ai (LangGraph)", 3000], ["Technical analysis, trading signals", 3860]]),
      tableRow([["AI Mentor", 2500], ["RAGFlow (self-hosted Docker)", 3000], ["RAG, user rules, knowledge base", 3860]]),
      tableRow([["Code Generator", 2500], ["DeepSeek API (openai-compat)", 3000], ["Pine Script + MQL5 generation", 3860]]),
      tableRow([["Market Data", 2500], ["Yahoo Finance + Polygon.io", 3000], ["OHLCV, real-time prices, news", 3860]]),
      tableRow([["Database", 2500], ["PostgreSQL + SQLAlchemy async", 3000], ["Users, validations, rules, EA logs", 3860]]),
      tableRow([["Payments", 2500], ["Whop Payments", 3000], ["241 territories, instant activation", 3860]]),
      tableRow([["Migrations", 2500], ["Alembic", 3000], ["Schema versioning (2 migrations)", 3860]]),
      tableRow([["Containers", 2500], ["Docker Compose", 3000], ["All services orchestrated", 3860]]),
    ],
  }),
];

// ── SECTION 3: FILE STRUCTURE ─────────────────────────────────────────────────
const fileSection = [
  h1("3. Complete File Structure (50 Files)"),

  h2("TG_Bot/ — Aiogram UI Layer (17 files)"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3500, 5860],
    rows: [
      headerRow(["File", "Purpose"], [3500, 5860]),
      tableRow([["TG_Bot/main.py", 3500], ["Bot + Dispatcher factory, Redis FSM, polling/webhook modes, 16-command menu registration", 5860]]),
      tableRow([["TG_Bot/config.py", 3500], ["Environment variable loader (reads root .env)", 5860]]),
      tableRow([["TG_Bot/states/states.py", 3500], ["6 FSM StatesGroups: GeneratePineScriptSG, GenerateMQL5SG, ShareCodeSG, ManualCheckSG, AddRuleSG, OutcomeSG", 5860]]),
      tableRow([["TG_Bot/middleware/subscription.py", 3500], ["Runs before every handler: auto-creates users, injects user object, rate limits 20 req/min", 5860]]),
      tableRow([["TG_Bot/keyboards/main_menu.py", 3500], ["ReplyKeyboard: 6 persistent menu buttons at screen bottom", 5860]]),
      tableRow([["TG_Bot/keyboards/product_kb.py", 3500], ["InlineKeyboard: plan selector, verdict WIN/LOSS buttons, history actions, account overview", 5860]]),
      tableRow([["TG_Bot/keyboards/strategy_kb.py", 3500], ["3-button Product 1 selector (Webhook/Code/Generate), EA selector, signal picker, code result actions", 5860]]),
      tableRow([["TG_Bot/handlers/start.py", 3500], ["/start, menu routing (6 buttons), /help, /status, /back callbacks", 5860]]),
      tableRow([["TG_Bot/handlers/generate.py", 3500], ["/generate FSM, /generate_ea FSM, /share_code FSM + file upload, /my_usage, save/regen callbacks", 5860]]),
      tableRow([["TG_Bot/handlers/validate.py", 3500], ["/check, /outcome, /history, /add_rule, /my_rules, /connect_indicator, /connect_ea, stats callback", 5860]]),
      tableRow([["TG_Bot/handlers/subscription.py", 3500], ["/subscribe (Whop), /insights (Pro SQLAlchemy case()), plan comparison, cancel prompt", 5860]]),
    ],
  }),

  ...spacer(1),
  h2("Core Application Layer"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3500, 5860],
    rows: [
      headerRow(["File", "Purpose"], [3500, 5860]),
      tableRow([["main.py", 3500], ["FastAPI app: /webhook/telegram, /webhook/indicator/{token}, /webhook/ea/{token}, /webhook/whop, /health. CORS + rate limiting.", 5860]]),
      tableRow([["config/settings.py", 3500], ["Pydantic settings: all env vars with defaults. No Stripe — uses Whop + DeepSeek.", 5860]]),
      tableRow([["db/models.py", 3500], ["SQLAlchemy models: User, Validation, UserRule, EALog. Whop fields + generation tracking.", 5860]]),
      tableRow([["db/database.py", 3500], ["Async engine, AsyncSessionLocal, init_db(), get_db(), get_db_context()", 5860]]),
      tableRow([["db/migrations/versions/001_initial.py", 3500], ["Creates all 4 tables from scratch", 5860]]),
      tableRow([["db/migrations/versions/002_whop_deepseek.py", 3500], ["Removes Stripe columns, adds Whop + generation tracking columns", 5860]]),
    ],
  }),

  ...spacer(1),
  h2("Services Layer"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3500, 5860],
    rows: [
      headerRow(["File", "Purpose"], [3500, 5860]),
      tableRow([["services/validation.py", 3500], ["ValidationService: orchestrates Trader + Mentor. validate_manual(), validate_indicator(), analyze_ea_trade(). Polygon.io wired in.", 5860]]),
      tableRow([["services/user.py", 3500], ["UserService: get_or_create, webhook tokens, daily counter, Whop plan update, generation budget helpers", 5860]]),
      tableRow([["services/subscription.py", 3500], ["WhopService: get_checkout_url(), verify_subscription(), verify_webhook_signature(), parse_plan_from_product_id()", 5860]]),
      tableRow([["services/deepseek.py", 3500], ["DeepSeekService: generate_pine_script(), generate_mql5(). Pine/MQL5 system prompts, fence stripping, retry logic, CODE_DISCLAIMER", 5860]]),
      tableRow([["services/market_data.py", 3500], ["PolygonService: get_snapshot(), get_previous_close(), get_news() — used for Product 3 live data", 5860]]),
    ],
  }),

  ...spacer(1),
  h2("AI Integration Layer"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3500, 5860],
    rows: [
      headerRow(["File", "Purpose"], [3500, 5860]),
      tableRow([["opentrade/service.py", 3500], ["OpenTradeService: LangGraph pipeline wrapper + full yfinance/ta fallback. Parses 8-agent state dict into TraderAnalysis dataclass.", 5860]]),
      tableRow([["ragflow/service.py", 3500], ["RAGFlowService: create_user_dataset(), add_rule_to_dataset(), validate_signal() (retrieval), seed_system_knowledge_base() (13 base rules)", 5860]]),
    ],
  }),

  ...spacer(1),
  h2("Workers Layer"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3500, 5860],
    rows: [
      headerRow(["File", "Purpose"], [3500, 5860]),
      tableRow([["workers/celery_app.py", 3500], ["Celery app: Redis broker, task settings (5 min hard limit, late ack), autodiscover tasks", 5860]]),
      tableRow([["workers/tasks.py", 3500], ["3 Celery tasks: validate_manual_task, validate_indicator_task, analyze_ea_task. Each saves to DB then pushes Telegram message.", 5860]]),
      tableRow([["workers/scheduler.py", 3500], ["Celery Beat: reset_daily_counters (midnight UTC), expire_stale_validations (hourly), aggregate_crowd_insights (weekly Sunday)", 5860]]),
    ],
  }),

  ...spacer(1),
  h2("Scripts & Tests"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3500, 5860],
    rows: [
      headerRow(["File", "Purpose"], [3500, 5860]),
      tableRow([["scripts/setup.py", 3500], ["One-shot setup: register Telegram webhook, seed RAGFlow system KB, test all connections", 5860]]),
      tableRow([["scripts/ea_monitor.py", 3500], ["Python log-tailer for MT4/MT5 VPS: tails EA.log, parses MT4 patterns, POSTs to webhook, deduplication", 5860]]),
      tableRow([["scripts/ea_snippet.mq5", 3500], ["MQL5 code users paste into MT5 EA: OnTradeTransaction() sends completed trades to webhook", 5860]]),
      tableRow([["tests/test_suite.py", 3500], ["40+ tests: OpenTrade fallback, RAGFlow parsing, ValidationService, Polygon wiring, rate limiter, scheduler, EA monitor, bot commands", 5860]]),
    ],
  }),
];

// ── SECTION 4: BOT COMMANDS ───────────────────────────────────────────────────
const commandsSection = [
  h1("4. All Bot Commands"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2200, 1400, 3200, 2560],
    rows: [
      headerRow(["Command", "Tier", "Description", "Handler File"], [2200, 1400, 3200, 2560]),
      tableRow([["/start", 2200], ["Free", 1400, C.lightGreen, C.green], ["Welcome + main menu keyboard", 3200], ["handlers/start.py", 2560]]),
      tableRow([["/generate <strategy>", 2200], ["Free", 1400, C.lightGreen, C.green], ["English → Pine Script v6 (DeepSeek, $5 cap)", 3200], ["handlers/generate.py", 2560]]),
      tableRow([["/generate_ea <strategy>", 2200], ["Free", 1400, C.lightGreen, C.green], ["English → MQL5 EA (DeepSeek, same cap)", 3200], ["handlers/generate.py", 2560]]),
      tableRow([["/share_code", 2200], ["Free", 1400, C.lightGreen, C.green], ["Paste Pine Script → stored in RAGFlow KB", 3200], ["handlers/generate.py", 2560]]),
      tableRow([["/my_usage", 2200], ["Free", 1400, C.lightGreen, C.green], ["Show DeepSeek generation budget bar", 3200], ["handlers/generate.py", 2560]]),
      tableRow([["/check TICKER SIGNAL", 2200], ["Paid", 1400, C.lightBlue, C.midBlue], ["Manual trade validation (P3 or Pro)", 3200], ["handlers/validate.py", 2560]]),
      tableRow([["/outcome WIN|LOSS [#id]", 2200], ["Free", 1400, C.lightGreen, C.green], ["Report trade result, updates crowd insights", 3200], ["handlers/validate.py", 2560]]),
      tableRow([["/add_rule <text>", 2200], ["Free", 1400, C.lightGreen, C.green], ["Add personal rule to RAGFlow KB", 3200], ["handlers/validate.py", 2560]]),
      tableRow([["/my_rules", 2200], ["Free", 1400, C.lightGreen, C.green], ["List personal trading rules", 3200], ["handlers/validate.py", 2560]]),
      tableRow([["/history", 2200], ["Free", 1400, C.lightGreen, C.green], ["Last 10 validations + self-reported accuracy", 3200], ["handlers/validate.py", 2560]]),
      tableRow([["/insights", 2200], ["Pro ⭐", 1400, C.lightAmber, C.amber], ["Crowd win-rate stats (anonymized)", 3200], ["handlers/subscription.py", 2560]]),
      tableRow([["/connect_indicator", 2200], ["P1/Pro", 1400, C.lightBlue, C.midBlue], ["Generate TradingView webhook URL", 3200], ["handlers/validate.py", 2560]]),
      tableRow([["/connect_ea", 2200], ["P2/Pro", 1400, C.lightBlue, C.midBlue], ["EA monitor script + MQL5 snippet", 3200], ["handlers/validate.py", 2560]]),
      tableRow([["/subscribe", 2200], ["All", 1400], ["Whop plan selection (4 tiers)", 3200], ["handlers/subscription.py", 2560]]),
      tableRow([["/status", 2200], ["All", 1400], ["Plan, usage, connections overview", 3200], ["handlers/start.py", 2560]]),
      tableRow([["/help", 2200], ["All", 1400], ["Full command reference", 3200], ["handlers/start.py", 2560]]),
    ],
  }),
];

// ── SECTION 5: API ENDPOINTS ──────────────────────────────────────────────────
const apiSection = [
  h1("5. API Endpoints (FastAPI)"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [600, 3500, 5260],
    rows: [
      headerRow(["Method", "Endpoint", "Purpose"], [600, 3500, 5260]),
      tableRow([["GET", 600, C.lightGreen, C.green], ["/health", 3500], ["Health check — returns {status: ok}", 5260]]),
      tableRow([["POST", 600, C.lightBlue, C.midBlue], ["/webhook/telegram", 3500], ["Telegram updates → aiogram feed_update()", 5260]]),
      tableRow([["POST", 600, C.lightBlue, C.midBlue], ["/webhook/indicator/{token}", 3500], ["TradingView signal → validate_indicator_task (rate: 60/min/token)", 5260]]),
      tableRow([["POST", 600, C.lightBlue, C.midBlue], ["/webhook/ea/{token}", 3500], ["EA trade log → analyze_ea_task (rate: 60/min/token)", 5260]]),
      tableRow([["POST", 600, C.lightBlue, C.midBlue], ["/webhook/whop", 3500], ["Whop payment events → plan activation/cancellation", 5260]]),
    ],
  }),
  ...spacer(1),
  h2("Whop Webhook Events Handled"),
  bullet("subscription.created → activate plan + notify user in Telegram"),
  bullet("subscription.cancelled → downgrade to FREE + notify user"),
  bullet("payment.failed → warn user to update payment method"),
  ...spacer(1),
  h2("Indicator Webhook Payload (TradingView → POST)"),
  code('{ "ticker": "AAPL", "signal": "BUY", "price": 175.50, "indicator": "MyRSI" }'),
  h2("EA Webhook Payload (ea_monitor.py → POST)"),
  code('{ "ea_name": "SuperScalper", "ticker": "EURUSD", "action": "BUY", "result": "LOSS", "pnl": -2.3 }'),
];

// ── SECTION 6: ENVIRONMENT VARIABLES ─────────────────────────────────────────
const envSection = [
  h1("6. Environment Variables (.env)"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3200, 1800, 4360],
    rows: [
      headerRow(["Variable", "Required", "Notes"], [3200, 1800, 4360]),
      tableRow([["TELEGRAM_BOT_TOKEN", 3200], ["YES", 1800, C.lightRed, C.red], ["From @BotFather", 4360]]),
      tableRow([["TELEGRAM_WEBHOOK_URL", 3200], ["Prod only", 1800, C.lightAmber, C.amber], ["https://your-domain.com/webhook/telegram", 4360]]),
      tableRow([["DATABASE_URL", 3200], ["YES", 1800, C.lightRed, C.red], ["postgresql+asyncpg://user:pass@host/db", 4360]]),
      tableRow([["REDIS_URL", 3200], ["YES", 1800, C.lightRed, C.red], ["redis://localhost:6379/0", 4360]]),
      tableRow([["RAGFLOW_API_KEY", 3200], ["YES", 1800, C.lightRed, C.red], ["From RAGFlow UI after first Docker start", 4360]]),
      tableRow([["RAGFLOW_BASE_URL", 3200], ["YES", 1800, C.lightRed, C.red], ["http://localhost:9380 (or remote host)", 4360]]),
      tableRow([["WHOP_API_KEY", 3200], ["YES", 1800, C.lightRed, C.red], ["dash.whop.com → Settings → Developer", 4360]]),
      tableRow([["WHOP_WEBHOOK_SECRET", 3200], ["YES", 1800, C.lightRed, C.red], ["Whop dashboard → Webhooks", 4360]]),
      tableRow([["WHOP_PRODUCT_ID_PRODUCT1", 3200], ["YES", 1800, C.lightRed, C.red], ["prod_xxx from Whop dashboard ($19/mo)", 4360]]),
      tableRow([["WHOP_PRODUCT_ID_PRODUCT2", 3200], ["YES", 1800, C.lightRed, C.red], ["prod_xxx ($49/mo)", 4360]]),
      tableRow([["WHOP_PRODUCT_ID_PRODUCT3", 3200], ["YES", 1800, C.lightRed, C.red], ["prod_xxx ($19/mo)", 4360]]),
      tableRow([["WHOP_PRODUCT_ID_PRO", 3200], ["YES", 1800, C.lightRed, C.red], ["prod_xxx ($79/mo)", 4360]]),
      tableRow([["DEEPSEEK_API_KEY", 3200], ["YES", 1800, C.lightRed, C.red], ["platform.deepseek.com", 4360]]),
      tableRow([["DEEPSEEK_MODEL", 3200], ["Optional", 1800, C.lightGreen, C.green], ["Default: deepseek-chat", 4360]]),
      tableRow([["POLYGON_API_KEY", 3200], ["Recommended", 1800, C.lightAmber, C.amber], ["polygon.io — for Product 3 live data", 4360]]),
      tableRow([["LLM_PROVIDER", 3200], ["Optional", 1800, C.lightGreen, C.green], ["ollama (default) | openai | lmstudio", 4360]]),
      tableRow([["LLM_MODEL", 3200], ["Optional", 1800, C.lightGreen, C.green], ["llama3 (default) | gpt-4o-mini", 4360]]),
      tableRow([["OLLAMA_BASE_URL", 3200], ["Optional", 1800, C.lightGreen, C.green], ["http://localhost:11434 (default)", 4360]]),
      tableRow([["FREE_TIER_DAILY_LIMIT", 3200], ["Optional", 1800, C.lightGreen, C.green], ["Default: 5 validations/day", 4360]]),
      tableRow([["DEEPSEEK_FREE_CAP", 3200], ["Optional", 1800, C.lightGreen, C.green], ["Default: 5.00 (dollars per user lifetime)", 4360]]),
    ],
  }),
];

// ── SECTION 7: DEPLOYMENT ─────────────────────────────────────────────────────
const deploySection = [
  h1("7. Deployment"),
  h2("VPS Requirements"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3120, 3120, 3120],
    rows: [
      headerRow(["Component", "Minimum (8 GB)", "Recommended (16 GB)"], [3120, 3120, 3120]),
      tableRow([["RAM", 3120], ["8 GB", 3120], ["16 GB", 3120]]),
      tableRow([["CPU", 3120], ["2 vCores", 3120], ["4 vCores", 3120]]),
      tableRow([["Storage", 3120], ["50 GB SSD", 3120], ["100 GB SSD", 3120]]),
      tableRow([["Cost/mo", 3120], ["~$30 (Hetzner CX31)", 3120], ["~$60 (Hetzner CX41)", 3120]]),
    ],
  }),
  ...spacer(1),
  h2("Quick Start (5 Commands)"),
  code("git clone https://github.com/laithqc-create/ai-trading-vlidator.git"),
  code("cd ai-trading-vlidator && cp .env.example .env && nano .env"),
  code("docker compose up -d postgres redis api worker beat"),
  code("docker compose exec api alembic upgrade head"),
  code("docker compose exec api python scripts/setup.py"),
  ...spacer(1),
  h2("Full Stack with RAGFlow (16 GB VPS)"),
  code("docker compose --profile full up -d"),
  p("RAGFlow UI: http://your-server:9380 — create admin account, copy API key → .env"),
  ...spacer(1),
  h2("Docker Services"),
  bullet("postgres — PostgreSQL 15 database"),
  bullet("redis — Redis 7 (task queue + FSM storage)"),
  bullet("api — FastAPI webhook server (port 8000)"),
  bullet("worker — Celery worker (4 concurrent tasks)"),
  bullet("beat — Celery Beat scheduler (3 periodic tasks)"),
  bullet("ragflow — RAGFlow AI engine (profile: full, needs 16 GB)"),
  bullet("ollama — Local LLM server (profile: full, optional GPU)"),
  ...spacer(1),
  h2("Development Mode (Polling)"),
  code("# No webhook needed — bot polls Telegram directly"),
  code("python TG_Bot/main.py"),
];

// ── SECTION 8: SCHEDULED TASKS ────────────────────────────────────────────────
const schedulerSection = [
  h1("8. Celery Beat Scheduled Tasks"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2800, 2200, 4360],
    rows: [
      headerRow(["Task", "Schedule", "What it does"], [2800, 2200, 4360]),
      tableRow([["reset_daily_counters", 2800], ["Midnight UTC", 2200], ["Resets free-tier validation counter (daily_validation_count = 0) for all free users", 4360]]),
      tableRow([["expire_stale_validations", 2800], ["Every hour", 2200], ["Marks PENDING validations stuck >10 minutes as FAILED to prevent orphaned records", 4360]]),
      tableRow([["aggregate_crowd_insights", 2800], ["Sunday 2am UTC", 2200], ["Counts WIN/LOSS outcomes per verdict+signal, saves anonymized insights to RAGFlow system KB", 4360]]),
    ],
  }),
];

// ── SECTION 9: PRICING & MONETISATION ────────────────────────────────────────
const pricingSection = [
  h1("9. Pricing & Monetisation"),
  h2("Subscription Plans (via Whop)"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [1800, 1500, 4360, 1700],
    rows: [
      headerRow(["Plan", "Price", "Features", "Whop Config"], [1800, 1500, 4360, 1700]),
      tableRow([["Free", 1800], ["$0", 1500], ["5 validations/day + unlimited /generate + /generate_ea", 4360], ["No product ID needed", 1700]]),
      tableRow([["Product 1", 1800, C.lightGreen], ["$19/mo", 1500], ["Webhook validation + share code + personal KB", 4360], ["WHOP_PRODUCT_ID_PRODUCT1", 1700]]),
      tableRow([["Product 2", 1800, C.lightGreen], ["$49/mo", 1500], ["EA log analysis + win/loss explanations", 4360], ["WHOP_PRODUCT_ID_PRODUCT2", 1700]]),
      tableRow([["Product 3", 1800, C.lightGreen], ["$19/mo", 1500], ["Unlimited /check + Polygon.io live data", 4360], ["WHOP_PRODUCT_ID_PRODUCT3", 1700]]),
      tableRow([["Pro Bundle", 1800, C.lightBlue], ["$79/mo", 1500], ["All products + crowd insights + priority queue", 4360], ["WHOP_PRODUCT_ID_PRO", 1700]]),
    ],
  }),
  ...spacer(1),
  h2("DeepSeek Free Generation Costs"),
  bullet("Cost per generation: ~$0.002 (2/10 of a cent)"),
  bullet("Free cap per user: $5.00 lifetime (~2,500 generations before hitting cap)"),
  bullet("Budget tracked in DB: users.total_generations + users.total_generation_cost"),
  bullet("Warning shown at $4.50 spent. Hard block at $5.00."),
  bullet("Worst case monthly cost per heavy user: ~$0.50"),
  bullet("Every generation ends with: 'Want validation? Subscribe for $19/mo'"),
];

// ── SECTION 10: WHAT TO DO NEXT ───────────────────────────────────────────────
const nextSection = [
  h1("10. Next Steps for Developer"),
  h2("Immediate (Before Going Live)"),
  bullet("Create products in Whop dashboard → copy 4 product IDs → add to .env"),
  bullet("Get DeepSeek API key from platform.deepseek.com → add to .env"),
  bullet("Create Telegram bot via @BotFather → copy token → add to .env"),
  bullet("Get Polygon.io API key (free tier ok to start) → add to .env"),
  bullet("Provision VPS (Hetzner CX31 = €8/mo minimum, CX41 = €16/mo with RAGFlow)"),
  bullet("Run: docker compose up -d postgres redis api worker beat"),
  bullet("Run: docker compose exec api alembic upgrade head"),
  bullet("Run: docker compose exec api python scripts/setup.py"),
  bullet("Test: open Telegram → /start → /generate Buy when RSI below 30"),
  ...spacer(1),
  h2("Optional Enhancements"),
  bullet("Add GPU to VPS for faster Ollama inference (or switch to OpenAI API)"),
  bullet("Set up Nginx + SSL via certbot (see DEPLOYMENT.md)"),
  bullet("Configure Whop affiliate links for referral system"),
  bullet("Implement aiogram_dialog for richer multi-step UI flows (dialogs/ folder is ready)"),
  bullet("Add admin endpoint for subscription analytics"),
  bullet("Replace in-memory rate limiter with Redis-based for multi-instance deployments"),
  ...spacer(1),
  h2("Known Limitations"),
  bullet("OpenTrade.ai LangGraph pipeline is slow with local LLM (60-120s) — mitigated by async Celery, but users see 'analyzing...' for 1-2 min"),
  bullet("RAGFlow requires 16 GB RAM — use cloud RAGFlow or separate VPS if budget is tight"),
  bullet("In-memory rate limiter resets on restart — fine for single-instance, use Redis for scale"),
  bullet("Crowd insights need minimum 5 reported outcomes per category before displaying"),
];

// ── DOCUMENT ASSEMBLY ─────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "\u2022",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22, color: C.grey } },
    },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: C.darkBlue },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: C.midBlue },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: C.darkBlue },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    children: [
      ...titleSection,
      ...spacer(2),
      ...overviewSection,
      ...spacer(1),
      ...architectureSection,
      ...spacer(1),
      ...fileSection,
      ...spacer(1),
      ...commandsSection,
      ...spacer(1),
      ...apiSection,
      ...spacer(1),
      ...envSection,
      ...spacer(1),
      ...deploySection,
      ...spacer(1),
      ...schedulerSection,
      ...spacer(1),
      ...pricingSection,
      ...spacer(1),
      ...nextSection,
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/mnt/user-data/outputs/AI_Trade_Validator_Handoff.docx", buf);
  console.log("Done: AI_Trade_Validator_Handoff.docx");
});
