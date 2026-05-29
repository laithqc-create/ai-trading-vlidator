//+------------------------------------------------------------------+
//|  ATV_Analyzer.mq4 — AI Trade Validator MT4 Expert Advisor        |
//|  Sends OHLC data to backend, draws AI analysis results on chart. |
//|  DISCLAIMER: Technical tool only. Not financial advice.          |
//+------------------------------------------------------------------+
#property copyright "AI Trade Validator"
#property version   "1.00"
#property strict

//── Inputs ────────────────────────────────────────────────────────
extern string WebhookURL   = "https://your-backend.example.com/webhook/ea/YOUR_TOKEN";
extern string AnalysisURL  = "https://your-backend.example.com/api/ohlc/analyze";
extern string UserToken    = "";
extern int    OHLCBars     = 50;
extern bool   AutoAnalyze  = true;
extern bool   DrawResults  = true;
extern color  BullishColor = clrLime;
extern color  BearishColor = clrRed;

//── State ──────────────────────────────────────────────────────────
datetime g_last_bar = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    if(StringLen(UserToken) < 8) {
        Alert("ATV: Set your UserToken in EA inputs");
        return INIT_PARAMETERS_INCORRECT;
    }
    Print("ATV MT4 initialized on ", Symbol(), " ", Period());
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnTick()
{
    datetime cur_bar = iTime(Symbol(), Period(), 0);
    if(cur_bar == g_last_bar) return;
    g_last_bar = cur_bar;
    if(!AutoAnalyze) return;
    
    string payload = BuildOHLCPayload();
    if(StringLen(payload) == 0) return;
    
    string response = "";
    int timeout = 5000;
    char data[], result[];
    string headers = "Content-Type: application/json\r\n";
    StringToCharArray(payload, data, 0, StringLen(payload));
    
    int ret = WebRequest("POST", AnalysisURL, headers, timeout, data, result, headers);
    if(ret > 0) {
        response = CharArrayToString(result);
        if(DrawResults && StringLen(response) > 0)
            DrawAnalysisResult(response);
    } else {
        int err = GetLastError();
        if(err == 4060)
            Print("ATV: Whitelist this URL in Tools > Options > Expert Advisors");
        else
            Print("ATV: WebRequest error ", err);
    }
}

//── EA trade closed callback ───────────────────────────────────────
void OnDeinit(const int reason) {}

void CheckClosedTrades()
{
    for(int i = OrdersHistoryTotal() - 1; i >= 0; i--) {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
        if(OrderCloseTime() == 0) continue;
        if(TimeCurrent() - OrderCloseTime() > 60) break;  // only last minute
        
        string action = (OrderType() == OP_BUY) ? "BUY" : "SELL";
        double profit = OrderProfit() + OrderSwap() + OrderCommission();
        string outcome = (profit >= 0) ? "WIN" : "LOSS";
        
        string ea_payload = StringFormat(
            "{\"ea_name\":\"ATV_MT4\",\"ticker\":\"%s\","
            "\"action\":\"%s\",\"result\":\"%s\","
            "\"pnl\":%.2f,\"token\":\"%s\"}",
            OrderSymbol(), action, outcome, profit, UserToken
        );
        
        char ep[], er[]; string eh;
        StringToCharArray(ea_payload, ep, 0, StringLen(ea_payload));
        WebRequest("POST", WebhookURL, "Content-Type: application/json\r\n", 5000, ep, er, eh);
    }
}

//── Build OHLC payload ─────────────────────────────────────────────
string BuildOHLCPayload()
{
    string sym = Symbol();
    int tf = Period();
    
    double rsi = iRSI(sym, tf, 14, PRICE_CLOSE, 1);
    double macd_main, macd_signal;
    macd_main   = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 1);
    macd_signal = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
    
    string candles = "[";
    for(int i = OHLCBars - 1; i >= 0; i--) {
        if(i < OHLCBars - 1) candles += ",";
        candles += StringFormat(
            "{\"t\":%d,\"o\":%.5f,\"h\":%.5f,\"l\":%.5f,\"c\":%.5f,\"v\":%d}",
            (int)iTime(sym, tf, i),
            iOpen(sym, tf, i), iHigh(sym, tf, i),
            iLow(sym, tf, i),  iClose(sym, tf, i),
            (int)iVolume(sym, tf, i)
        );
    }
    candles += "]";
    
    string tf_str;
    if(tf == 1) tf_str = "1m";
    else if(tf == 5) tf_str = "5m";
    else if(tf == 15) tf_str = "15m";
    else if(tf == 60) tf_str = "1h";
    else if(tf == 240) tf_str = "4h";
    else if(tf == 1440) tf_str = "1d";
    else tf_str = "1h";
    
    return StringFormat(
        "{\"token\":\"%s\",\"symbol\":\"%s\",\"timeframe\":\"%s\","
        "\"candles\":%s,"
        "\"indicators\":{\"rsi\":%.2f,\"macd_main\":%.5f,\"macd_signal\":%.5f},"
        "\"platform\":\"mt4\"}",
        UserToken, sym, tf_str, candles,
        rsi, macd_main, macd_signal
    );
}

//── Draw results on chart ─────────────────────────────────────────
void DrawAnalysisResult(string json)
{
    string signal  = ExtractField(json, "signal");
    string pattern = ExtractField(json, "pattern");
    string reason  = ExtractField(json, "reason");
    if(StringLen(signal) == 0) return;
    
    datetime t = iTime(Symbol(), Period(), 1);
    double hi = iHigh(Symbol(), Period(), 1);
    double lo = iLow(Symbol(), Period(), 1);
    
    color  col   = clrYellow;
    int    code  = 159;
    double price = hi + 20 * Point;
    
    if(StringFind(signal, "BUY") >= 0)  { col = BullishColor; code = 233; price = lo - 20*Point; }
    if(StringFind(signal, "SELL") >= 0) { col = BearishColor;  code = 234; price = hi + 20*Point; }
    
    string name = "ATV_" + TimeToStr(t, TIME_DATE|TIME_MINUTES);
    ObjectDelete(name);
    ObjectCreate(name, OBJ_ARROW, 0, t, price);
    ObjectSet(name, OBJPROP_ARROWCODE, code);
    ObjectSet(name, OBJPROP_COLOR, col);
    ObjectSet(name, OBJPROP_WIDTH, 2);
    ObjectSetText(name, signal + " | " + pattern);
    WindowRedraw();
}

string ExtractField(string json, string field)
{
    string s = "\"" + field + "\":\"";
    int i = StringFind(json, s);
    if(i < 0) return "";
    i += StringLen(s);
    int j = StringFind(json, "\"", i);
    if(j < 0) return "";
    return StringSubstr(json, i, j - i);
}
//+------------------------------------------------------------------+
