using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using cAlgo.API;
using cAlgo.API.Indicators;

// AI Trade Validator — cTrader cBot
// Sends OHLC + indicator data to backend for AI analysis.
// Draws results on chart as arrows with tooltips.
// DISCLAIMER: Technical tool only. Not financial advice.

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class ATV_Analyzer : Robot
    {
        [Parameter("Backend Analysis URL", DefaultValue = "https://your-backend.example.com/api/ohlc/analyze")]
        public string AnalysisURL { get; set; }

        [Parameter("EA Webhook URL", DefaultValue = "https://your-backend.example.com/webhook/ea/YOUR_TOKEN")]
        public string WebhookURL { get; set; }

        [Parameter("User Token", DefaultValue = "")]
        public string UserToken { get; set; }

        [Parameter("OHLC Bars to Send", DefaultValue = 100, MinValue = 50, MaxValue = 500)]
        public int OHLCBars { get; set; }

        [Parameter("Auto Analyse on Candle Close", DefaultValue = true)]
        public bool AutoAnalyze { get; set; }

        [Parameter("Draw Results on Chart", DefaultValue = true)]
        public bool DrawResults { get; set; }

        private RelativeStrengthIndex _rsi;
        private MacdCrossOver _macd;
        private readonly HttpClient _http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        private DateTime _lastBar = DateTime.MinValue;

        protected override void OnStart()
        {
            if (string.IsNullOrWhiteSpace(UserToken) || UserToken.Length < 8)
            {
                Print("ATV: Set your UserToken in cBot parameters");
                Stop();
                return;
            }

            _rsi  = Indicators.RelativeStrengthIndex(Bars.ClosePrices, 14);
            _macd = Indicators.MacdCrossOver(Bars.ClosePrices, 26, 12, 9);

            Positions.Closed += OnPositionClosed;
            Print($"ATV cBot initialized on {SymbolName} {TimeFrame}");
        }

        protected override void OnBar()
        {
            if (!AutoAnalyze) return;
            _ = SendOHLCAsync();
        }

        private void OnPositionClosed(PositionClosedEventArgs args)
        {
            var pos = args.Position;
            var outcome = pos.GrossProfit >= 0 ? "WIN" : "LOSS";
            var action  = pos.TradeType == TradeType.Buy ? "BUY" : "SELL";

            var payload = $"{{\"ea_name\":\"ATV_cBot\","
                        + $"\"ticker\":\"{SymbolName}\","
                        + $"\"action\":\"{action}\","
                        + $"\"result\":\"{outcome}\","
                        + $"\"pnl\":{pos.GrossProfit:F2},"
                        + $"\"token\":\"{UserToken}\"}}";

            _ = PostAsync(WebhookURL, payload);
        }

        private async Task SendOHLCAsync()
        {
            try
            {
                var sb = new StringBuilder("[");
                int count = Math.Min(OHLCBars, Bars.Count);
                for (int i = count - 1; i >= 0; i--)
                {
                    if (i < count - 1) sb.Append(",");
                    sb.Append($"{{\"t\":{new DateTimeOffset(Bars.OpenTimes[i]).ToUnixTimeSeconds()}"
                            + $",\"o\":{Bars.OpenPrices[i]:F5}"
                            + $",\"h\":{Bars.HighPrices[i]:F5}"
                            + $",\"l\":{Bars.LowPrices[i]:F5}"
                            + $",\"c\":{Bars.ClosePrices[i]:F5}"
                            + $",\"v\":{Bars.TickVolumes[i]}}}");
                }
                sb.Append("]");

                var payload = $"{{\"token\":\"{UserToken}\","
                            + $"\"symbol\":\"{SymbolName}\","
                            + $"\"timeframe\":\"{TimeFrame}\","
                            + $"\"candles\":{sb},"
                            + $"\"indicators\":{{\"rsi\":{_rsi.Result.LastValue:F2},"
                            + $"\"macd_main\":{_macd.MACD.LastValue:F5},"
                            + $"\"macd_signal\":{_macd.Signal.LastValue:F5}}},"
                            + $"\"platform\":\"ctrader\"}}";

                var response = await PostAsync(AnalysisURL, payload);
                if (DrawResults && !string.IsNullOrEmpty(response))
                    DrawResult(response);
            }
            catch (Exception ex)
            {
                Print($"ATV: Send error: {ex.Message}");
            }
        }

        private void DrawResult(string json)
        {
            string signal  = Extract(json, "signal");
            string pattern = Extract(json, "pattern");
            string reason  = Extract(json, "reason");
            if (string.IsNullOrEmpty(signal)) return;

            var bar   = Bars.Last(1);
            var color = signal.Contains("BUY")  ? Color.LimeGreen
                      : signal.Contains("SELL") ? Color.Red
                      : Color.Yellow;

            double price = signal.Contains("BUY")
                ? bar.Low  - 20 * Symbol.PipSize
                : bar.High + 20 * Symbol.PipSize;

            var name = $"ATV_{bar.OpenTime:yyyyMMddHHmm}";
            Chart.DrawIcon(name, signal.Contains("BUY") ? ChartIconType.UpArrow : ChartIconType.DownArrow,
                           bar.OpenTime, price, color);
        }

        private static string Extract(string json, string field)
        {
            var key   = $"\"{field}\":\"";
            var start = json.IndexOf(key, StringComparison.Ordinal);
            if (start < 0) return string.Empty;
            start += key.Length;
            var end = json.IndexOf('"', start);
            return end < 0 ? string.Empty : json.Substring(start, end - start);
        }

        private async Task<string> PostAsync(string url, string payload)
        {
            var content  = new StringContent(payload, Encoding.UTF8, "application/json");
            var response = await _http.PostAsync(url, content);
            return await response.Content.ReadAsStringAsync();
        }

        protected override void OnStop()
        {
            _http.Dispose();
        }
    }
}
