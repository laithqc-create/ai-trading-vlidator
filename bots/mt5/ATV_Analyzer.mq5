//+------------------------------------------------------------------+
//|  ATV_Analyzer.mq5                                                |
//|  AI Trade Validator — MT5 Expert Advisor                         |
//|  Sends OHLC + indicator data to backend for candle pattern       |
//|  analysis and receives drawing instructions back.                |
//|                                                                  |
//|  DISCLAIMER: This EA is a technical tool only. It does NOT       |
//|  provide financial advice or trading recommendations. You are    |
//|  solely responsible for any trades executed.                     |
//+------------------------------------------------------------------+
#property copyright "AI Trade Validator"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//── Input parameters ──────────────────────────────────────────────
input string WebhookURL      = "https://your-backend.example.com/webhook/ea/YOUR_TOKEN";
input string AnalysisURL     = "https://your-backend.example.com/api/ohlc/analyze";
input string DrawURL         = "https://your-backend.example.com/api/ohlc/draw-result";
input string UserToken       = "";          // Your webhook token from /start
input int    OHLCBars        = 50;          // Number of OHLC bars to send
input bool   AutoAnalyze     = true;        // Analyse on every new candle
input bool   DrawResults     = true;        // Draw AI results on chart
input color  BullishColor    = clrLime;
input color  BearishColor    = clrRed;
input color  NeutralColor    = clrYellow;

//── State ──────────────────────────────────────────────────────────
datetime g_last_bar_time = 0;
string   g_symbol;
int      g_tf_seconds;

//+------------------------------------------------------------------+
int OnInit()
{
    g_symbol = Symbol();
    g_tf_seconds = PeriodSeconds(Period());
    
    if(StringLen(UserToken) < 8) {
        Alert("ATV: Please set your UserToken in EA inputs");
        return INIT_PARAMETERS_INCORRECT;
    }
    
    Print("ATV Analyzer initialized on ", g_symbol, " ", EnumToString(Period()));
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnTick()
{
    // Only fire on new candle close
    datetime current_bar = iTime(g_symbol, Period(), 0);
    if(current_bar == g_last_bar_time) return;
    g_last_bar_time = current_bar;
    
    if(!AutoAnalyze) return;
    
    // Build OHLC payload and send
    string payload = BuildOHLCPayload();
    if(StringLen(payload) == 0) return;
    
    string response = PostToBackend(AnalysisURL, payload);
    if(StringLen(response) > 0 && DrawResults) {
        DrawAnalysisResult(response);
    }
}

//── Trade event — send completed trade to EA analyzer ─────────────
void OnTradeTransaction(
    const MqlTradeTransaction& trans,
    const MqlTradeRequest& request,
    const MqlTradeResult& result)
{
    if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
    
    CDealInfo deal;
    if(!deal.SelectByIndex(HistoryDealsTotal() - 1)) return;
    
    // Only process closed deals
    if(deal.Entry() != DEAL_ENTRY_OUT) return;
    
    string action = (deal.DealType() == DEAL_TYPE_BUY) ? "BUY" : "SELL";
    double profit = deal.Profit();
    string outcome = (profit >= 0) ? "WIN" : "LOSS";
    
    string ea_payload = StringFormat(
        "{\"ea_name\":\"ATV_Analyzer\","
        "\"ticker\":\"%s\","
        "\"action\":\"%s\","
        "\"result\":\"%s\","
        "\"pnl\":%.2f,"
        "\"token\":\"%s\"}",
        g_symbol, action, outcome, profit, UserToken
    );
    
    PostToBackend(WebhookURL, ea_payload);
}

//── Build OHLC JSON payload ────────────────────────────────────────
string BuildOHLCPayload()
{
    MqlRates rates[];
    int copied = CopyRates(g_symbol, Period(), 0, OHLCBars, rates);
    if(copied <= 0) return "";
    
    // Current indicators
    double rsi_buf[3];
    int rsi_handle = iRSI(g_symbol, Period(), 14, PRICE_CLOSE);
    if(CopyBuffer(rsi_handle, 0, 0, 3, rsi_buf) <= 0) ArrayFill(rsi_buf, 0, 3, 0);
    IndicatorRelease(rsi_handle);
    
    double macd_main[1], macd_signal[1];
    int macd_handle = iMACD(g_symbol, Period(), 12, 26, 9, PRICE_CLOSE);
    CopyBuffer(macd_handle, 0, 0, 1, macd_main);
    CopyBuffer(macd_handle, 1, 0, 1, macd_signal);
    IndicatorRelease(macd_handle);
    
    // Build candles JSON array
    string candles = "[";
    for(int i = ArraySize(rates) - 1; i >= 0; i--) {
        if(i < ArraySize(rates) - 1) candles += ",";
        candles += StringFormat(
            "{\"t\":%d,\"o\":%.5f,\"h\":%.5f,\"l\":%.5f,\"c\":%.5f,\"v\":%d}",
            (int)rates[i].time,
            rates[i].open,
            rates[i].high,
            rates[i].low,
            rates[i].close,
            (int)rates[i].tick_volume
        );
    }
    candles += "]";
    
    string payload = StringFormat(
        "{\"token\":\"%s\","
        "\"symbol\":\"%s\","
        "\"timeframe\":\"%s\","
        "\"candles\":%s,"
        "\"indicators\":{\"rsi\":%.2f,\"macd_main\":%.5f,\"macd_signal\":%.5f},"
        "\"platform\":\"mt5\"}",
        UserToken, g_symbol,
        TimeframeToString(Period()),
        candles,
        rsi_buf[0], macd_main[0], macd_signal[0]
    );
    
    return payload;
}

//── POST helper ────────────────────────────────────────────────────
string PostToBackend(string url, string payload)
{
    char post_data[];
    char result_data[];
    string result_headers;
    
    StringToCharArray(payload, post_data, 0, StringLen(payload));
    ArrayResize(post_data, ArraySize(post_data) - 1);  // remove null terminator
    
    string headers = "Content-Type: application/json\r\n";
    
    int res = WebRequest(
        "POST", url, headers, 5000,
        post_data, result_data, result_headers
    );
    
    if(res == -1) {
        int err = GetLastError();
        if(err == 4060) {
            Print("ATV: URL not whitelisted. Add this URL in Tools > Options > Expert Advisors: ", url);
        } else {
            Print("ATV: WebRequest error ", err);
        }
        return "";
    }
    
    return CharArrayToString(result_data);
}

//── Parse analysis response and draw on chart ─────────────────────
void DrawAnalysisResult(string json_response)
{
    // Parse signal from response
    string signal = ExtractJsonField(json_response, "signal");
    string pattern = ExtractJsonField(json_response, "pattern");
    string reason = ExtractJsonField(json_response, "reason");
    
    if(StringLen(signal) == 0) return;
    
    datetime bar_time = iTime(g_symbol, Period(), 1);  // draw on last closed candle
    double   bar_high = iHigh(g_symbol, Period(), 1);
    double   bar_low  = iLow(g_symbol, Period(), 1);
    
    color arrow_color = NeutralColor;
    int   arrow_code  = 159;   // circle
    double arrow_price = bar_high + (20 * _Point);
    
    if(StringFind(signal, "BUY") >= 0) {
        arrow_color = BullishColor;
        arrow_code  = 233;    // up arrow
        arrow_price = bar_low - (20 * _Point);
    } else if(StringFind(signal, "SELL") >= 0) {
        arrow_color = BearishColor;
        arrow_code  = 234;    // down arrow
        arrow_price = bar_high + (20 * _Point);
    }
    
    // Create arrow object
    string obj_name = "ATV_" + TimeToString(bar_time, TIME_DATE|TIME_MINUTES);
    ObjectDelete(0, obj_name);
    ObjectCreate(0, obj_name, OBJ_ARROW, 0, bar_time, arrow_price);
    ObjectSetInteger(0, obj_name, OBJPROP_ARROWCODE, arrow_code);
    ObjectSetInteger(0, obj_name, OBJPROP_COLOR, arrow_color);
    ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 2);
    ObjectSetString(0, obj_name, OBJPROP_TOOLTIP,
        signal + " | " + pattern + "\n" + reason);
    
    ChartRedraw(0);
    Print("ATV: Drew ", signal, " (", pattern, ") at ", TimeToString(bar_time));
}

//── Utilities ──────────────────────────────────────────────────────
string TimeframeToString(ENUM_TIMEFRAMES tf)
{
    switch(tf) {
        case PERIOD_M1:  return "1m";
        case PERIOD_M5:  return "5m";
        case PERIOD_M15: return "15m";
        case PERIOD_M30: return "30m";
        case PERIOD_H1:  return "1h";
        case PERIOD_H4:  return "4h";
        case PERIOD_D1:  return "1d";
        case PERIOD_W1:  return "1w";
        default:         return "1h";
    }
}

string ExtractJsonField(string json, string field)
{
    string search = "\"" + field + "\":\"";
    int start = StringFind(json, search);
    if(start < 0) return "";
    start += StringLen(search);
    int end = StringFind(json, "\"", start);
    if(end < 0) return "";
    return StringSubstr(json, start, end - start);
}
//+------------------------------------------------------------------+
