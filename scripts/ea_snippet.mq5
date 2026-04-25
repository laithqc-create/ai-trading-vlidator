//+------------------------------------------------------------------+
//|  AI Trade Validator — EA Integration Snippet                     |
//|  Paste into your EA's OnTrade() or after trade close logic       |
//|  Replace WEBHOOK_URL with your personal URL from /connect_ea     |
//+------------------------------------------------------------------+

// ─── CONFIGURATION ───────────────────────────────────────────────
#define WEBHOOK_URL "https://YOUR-SERVER.com/webhook/ea/YOUR_TOKEN_HERE"
#define EA_NAME     "MyEA"

//+------------------------------------------------------------------+
//| Call this function after a trade closes                          |
//+------------------------------------------------------------------+
void SendTradeToValidator(
    string   ticker,
    string   action,    // "BUY" or "SELL"
    string   result,    // "WIN" or "LOSS"
    double   pnl,       // profit/loss in account currency
    datetime tradeTime
)
{
    string headers = "Content-Type: application/json\r\n";
    char   post[], response[];
    string responseHeaders;

    // Build ISO timestamp
    string ts = TimeToString(tradeTime, TIME_DATE | TIME_SECONDS);
    StringReplace(ts, ".", "-");
    StringReplace(ts, " ", "T");
    ts += "Z";

    // Build JSON payload
    string json = StringFormat(
        "{\"ea_name\":\"%s\",\"ticker\":\"%s\",\"action\":\"%s\","
        "\"result\":\"%s\",\"pnl\":%.2f,\"trade_time\":\"%s\"}",
        EA_NAME, ticker, action, result, pnl, ts
    );

    StringToCharArray(json, post, 0, StringLen(json), CP_UTF8);

    // Send POST request
    int res = WebRequest(
        "POST",
        WEBHOOK_URL,
        headers,
        5000,           // timeout ms
        post,
        response,
        responseHeaders
    );

    if(res == 200)
        Print("[AIValidator] Trade sent: ", ticker, " ", action, " -> ", result);
    else
        Print("[AIValidator] Send failed, HTTP code: ", res);
}

//+------------------------------------------------------------------+
//| Example usage in OnTradeTransaction                              |
//+------------------------------------------------------------------+
void OnTradeTransaction(
    const MqlTradeTransaction &trans,
    const MqlTradeRequest     &request,
    const MqlTradeResult      &result
)
{
    // Detect trade close
    if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
    {
        if(trans.deal_type == DEAL_TYPE_BUY || trans.deal_type == DEAL_TYPE_SELL)
        {
            // Get trade details
            if(HistoryDealSelect(trans.deal))
            {
                long   entry     = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
                double profit    = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
                string symbol    = HistoryDealGetString(trans.deal, DEAL_SYMBOL);
                long   dealType  = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
                datetime time    = (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME);

                // Only send on position close (DEAL_ENTRY_OUT)
                if(entry == DEAL_ENTRY_OUT)
                {
                    string action = (dealType == DEAL_TYPE_BUY) ? "BUY" : "SELL";
                    string res    = (profit >= 0) ? "WIN" : "LOSS";

                    SendTradeToValidator(symbol, action, res, profit, time);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| IMPORTANT: Allow WebRequest in MT5                               |
//| Tools → Options → Expert Advisors → Allow WebRequests           |
//| Add your server URL to the allowed URLs list                     |
//+------------------------------------------------------------------+
