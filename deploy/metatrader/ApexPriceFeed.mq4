//+------------------------------------------------------------------+
//| ApexPriceFeed.mq4 — APEX OS MetaTrader price + multi-TF candles  |
//| Price: POST /api/v1/prices/update every 5s                       |
//| Candles: POST /api/v1/candles/update on M5/M15/H1/H4/D1 close    |
//| Bootstrap: POST /api/v1/candles/bootstrap — 500 H1 bars on attach|
//+------------------------------------------------------------------+
#property copyright "APEX OS"
#property link      "https://github.com/ibrahim94i/apex-os"
#property version   "3.06"
#property strict

//--- inputs
input string InpApiUrl          = "https://apex-os-production-9adc.up.railway.app/api/v1/prices/update";
input string InpCandleApiUrl    = "https://apex-os-production-9adc.up.railway.app/api/v1/candles/update";
input string InpBootstrapApiUrl = "https://apex-os-production-9adc.up.railway.app/api/v1/candles/bootstrap";
input string InpApiKey          = "apex_mt_CNj4vVEZvXwkPBKXkNGEoRndbg3J9mgaybydnWO0H50";
input string InpApexSymbol      = "XAUUSD";
input int    InpTimerSeconds    = 5;
input int    InpTimeoutMs       = 8000;
input int    InpBootstrapBars   = 500;
input int    InpBootstrapTimeoutMs = 30000;
input bool   InpSendBootstrapOnInit = true;
input bool   InpResendBootstrapOnInit = false;
input bool   InpShowComment      = true;

#define TF_COUNT 5
#define H1_PERIOD_SECONDS 3600

//--- state
datetime g_last_ok_utc = 0;
int      g_fail_count  = 0;
int      g_ok_count    = 0;

int      g_tf_periods[TF_COUNT];
string   g_tf_labels[TF_COUNT];
int      g_tf_seconds[TF_COUNT];
datetime g_tf_last_open_sent[TF_COUNT];
int      g_tf_ok_count[TF_COUNT];
int      g_tf_fail_count[TF_COUNT];
int      g_bootstrap_ok_count = 0;
int      g_bootstrap_fail_count = 0;
bool     g_bootstrap_sent = false;

//+------------------------------------------------------------------+
void InitTimeframes()
{
   g_tf_periods[0] = PERIOD_M5;
   g_tf_labels[0]  = "M5";
   g_tf_seconds[0] = 300;

   g_tf_periods[1] = PERIOD_M15;
   g_tf_labels[1]  = "M15";
   g_tf_seconds[1] = 900;

   g_tf_periods[2] = PERIOD_H1;
   g_tf_labels[2]  = "H1";
   g_tf_seconds[2] = 3600;

   g_tf_periods[3] = PERIOD_H4;
   g_tf_labels[3]  = "H4";
   g_tf_seconds[3] = 14400;

   g_tf_periods[4] = PERIOD_D1;
   g_tf_labels[4]  = "D1";
   g_tf_seconds[4] = 86400;

   for(int i = 0; i < TF_COUNT; i++)
   {
      g_tf_last_open_sent[i] = 0;
      g_tf_ok_count[i] = 0;
      g_tf_fail_count[i] = 0;
   }
}

//+------------------------------------------------------------------+
bool ShouldRunBootstrapOnInit()
{
   if(InpResendBootstrapOnInit)
      return(true);
   if(InpSendBootstrapOnInit && !g_bootstrap_sent)
      return(true);
   return(false);
}

//+------------------------------------------------------------------+
int OnInit()
{
   if(StringLen(InpApiKey) < 8)
   {
      Alert("APEX Price Feed: InpApiKey is empty or too short.");
      return(INIT_PARAMETERS_INCORRECT);
   }

   if(InpTimerSeconds < 1)
   {
      Alert("APEX Price Feed: InpTimerSeconds must be >= 1.");
      return(INIT_PARAMETERS_INCORRECT);
   }

   InitTimeframes();

   if(!EventSetTimer(InpTimerSeconds))
   {
      Print("APEX Price Feed: EventSetTimer failed, err=", GetLastError());
      return(INIT_FAILED);
   }

   Print(
      "APEX Feed started | price timer=", InpTimerSeconds,
      "s | symbol=", InpApexSymbol,
      " | bootstrapOnInit=", InpSendBootstrapOnInit,
      " | resendBootstrap=", InpResendBootstrapOnInit
   );

   if(ShouldRunBootstrapOnInit())
   {
      if(InpResendBootstrapOnInit)
      {
         g_bootstrap_sent = false;
         Print("APEX bootstrap: forced resend requested (InpResendBootstrapOnInit=true)");
      }
      SendH1Bootstrap("init");
   }
   else
   {
      Print("APEX bootstrap: skipped on init (already sent)");
   }

   SendPriceToApex("init");
   CheckAndSendAllCandles("init");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if(InpShowComment)
      Comment("");
   Print("APEX Feed stopped, reason=", reason);
}

//+------------------------------------------------------------------+
void OnTimer()
{
   SendPriceToApex("timer");

   if(!g_bootstrap_sent && ShouldRunBootstrapOnInit())
      SendH1Bootstrap("timer-retry");

   CheckAndSendAllCandles("timer");
}

//+------------------------------------------------------------------+
void OnTick()
{
   // Timer-based only.
}

//+------------------------------------------------------------------+
string BuildUtcTimeString(datetime utc_time)
{
   return(TimeToString(utc_time, TIME_DATE | TIME_SECONDS));
}

//+------------------------------------------------------------------+
datetime BrokerTimeToUtc(datetime brokerTime)
{
   return(brokerTime + (TimeGMT() - TimeCurrent()));
}

//+------------------------------------------------------------------+
string BuildBarCloseUtcString(datetime bar_open, int period_seconds)
{
   datetime bar_close_broker = bar_open + period_seconds;
   datetime bar_close_utc = BrokerTimeToUtc(bar_close_broker);
   return(BuildUtcTimeString(bar_close_utc));
}

//+------------------------------------------------------------------+
string FormatJsonNumber(const double value, const int digits)
{
   string s = DoubleToString(NormalizeDouble(value, digits), digits);
   StringReplace(s, " ", "");
   StringReplace(s, ",", ".");
   return(s);
}

//+------------------------------------------------------------------+
string BuildPriceJson(const double bid, const double ask, const int digits, const string time_utc)
{
   return(
      "{"
      + "\"symbol\":\"" + InpApexSymbol + "\","
      + "\"bid\":" + FormatJsonNumber(bid, digits) + ","
      + "\"ask\":" + FormatJsonNumber(ask, digits) + ","
      + "\"time\":\"" + time_utc + "\""
      + "}"
   );
}

//+------------------------------------------------------------------+
string BuildCandleJson(
   const string timeframe,
   const double open,
   const double high,
   const double low,
   const double close,
   const long volume,
   const int digits,
   const string close_utc
)
{
   return(
      "{"
      + "\"symbol\":\"" + InpApexSymbol + "\","
      + "\"timeframe\":\"" + timeframe + "\","
      + "\"open\":" + FormatJsonNumber(open, digits) + ","
      + "\"high\":" + FormatJsonNumber(high, digits) + ","
      + "\"low\":" + FormatJsonNumber(low, digits) + ","
      + "\"close\":" + FormatJsonNumber(close, digits) + ","
      + "\"volume\":" + IntegerToString((int)volume) + ","
      + "\"time\":\"" + close_utc + "\""
      + "}"
   );
}

//+------------------------------------------------------------------+
string BuildBootstrapCandleItem(
   const double open,
   const double high,
   const double low,
   const double close,
   const long volume,
   const int digits,
   const string close_utc
)
{
   return(
      "{"
      + "\"open\":" + FormatJsonNumber(open, digits) + ","
      + "\"high\":" + FormatJsonNumber(high, digits) + ","
      + "\"low\":" + FormatJsonNumber(low, digits) + ","
      + "\"close\":" + FormatJsonNumber(close, digits) + ","
      + "\"volume\":" + IntegerToString((int)volume) + ","
      + "\"time\":\"" + close_utc + "\""
      + "}"
   );
}

//+------------------------------------------------------------------+
bool GetQuote(double &bid, double &ask)
{
   string chart_symbol = Symbol();
   bid = MarketInfo(chart_symbol, MODE_BID);
   ask = MarketInfo(chart_symbol, MODE_ASK);

   if(bid <= 0.0 || ask <= 0.0)
   {
      RefreshRates();
      bid = MarketInfo(chart_symbol, MODE_BID);
      ask = MarketInfo(chart_symbol, MODE_ASK);
   }

   if(bid <= 0.0 || ask <= 0.0)
      return(false);

   if(ask < bid)
   {
      double tmp = bid;
      bid = ask;
      ask = tmp;
   }

   return(true);
}

//+------------------------------------------------------------------+
bool PostJsonToApex(
   const string url,
   const string json,
   const string trigger,
   const string label,
   int &ok_counter,
   int &fail_counter,
   const int timeout_ms
)
{
   int request_timeout = timeout_ms;
   if(request_timeout <= 0)
      request_timeout = InpTimeoutMs;
   char post[];
   char result[];
   string req_headers = "Content-Type: application/json\r\n"
                        + "X-MT-Key: " + InpApiKey + "\r\n";
   string resp_headers = "";

   StringToCharArray(json, post, 0, WHOLE_ARRAY, CP_UTF8);
   if(ArraySize(post) > 0)
      ArrayResize(post, ArraySize(post) - 1);

   ResetLastError();
   int http_status = WebRequest(
      "POST",
      url,
      req_headers,
      request_timeout,
      post,
      result,
      resp_headers
   );

   if(http_status == -1)
   {
      int err = GetLastError();
      fail_counter++;
      Print(
         "APEX ", label, " WebRequest failed err=", err,
         " trigger=", trigger,
         " url=", url
      );
      UpdateChartComment(false, label + " err " + IntegerToString(err));
      return(false);
   }

   string response = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);

   if(http_status >= 200 && http_status < 300)
   {
      ok_counter++;
      g_last_ok_utc = TimeGMT();
      Print("APEX ", label, " OK http=", http_status, " trigger=", trigger, " response=", response);
      UpdateChartComment(true, label + " HTTP " + IntegerToString(http_status));
      return(true);
   }

   fail_counter++;
   Print(
      "APEX ", label, " HTTP error status=", http_status,
      " trigger=", trigger,
      " response=", response
   );
   UpdateChartComment(false, label + " HTTP " + IntegerToString(http_status));
   return(false);
}

//+------------------------------------------------------------------+
bool SendPriceToApex(const string trigger)
{
   double bid = 0.0;
   double ask = 0.0;
   if(!GetQuote(bid, ask))
   {
      g_fail_count++;
      Print("APEX Price Feed: invalid quote for chart symbol ", Symbol(), " trigger=", trigger);
      UpdateChartComment(false, "no quote");
      return(false);
   }

   int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(digits < 0)
      digits = 2;

   string time_utc = BuildUtcTimeString(TimeGMT());
   string json = BuildPriceJson(bid, ask, digits, time_utc);

   return PostJsonToApex(InpApiUrl, json, trigger, "PRICE", g_ok_count, g_fail_count, InpTimeoutMs);
}

//+------------------------------------------------------------------+
bool SendH1Bootstrap(const string trigger)
{
   if(g_bootstrap_sent && !InpResendBootstrapOnInit)
   {
      Print("APEX bootstrap: skipped (already sent, resend=false) trigger=", trigger);
      return(true);
   }

   int available = iBars(Symbol(), PERIOD_H1) - 1;
   int count = InpBootstrapBars;
   if(count > available)
      count = available;
   if(count < 1)
   {
      Print("APEX bootstrap: not enough closed H1 bars (available=", available, ")");
      return(false);
   }

   int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(digits < 0)
      digits = 2;

   string json = "{"
      + "\"symbol\":\"" + InpApexSymbol + "\","
      + "\"timeframe\":\"H1\","
      + "\"candles\":[";

   bool first_item = true;
   int candle_count = 0;
   for(int shift = count; shift >= 1; shift--)
   {
      double open  = iOpen(Symbol(), PERIOD_H1, shift);
      double high  = iHigh(Symbol(), PERIOD_H1, shift);
      double low   = iLow(Symbol(), PERIOD_H1, shift);
      double close = iClose(Symbol(), PERIOD_H1, shift);
      long   volume = iVolume(Symbol(), PERIOD_H1, shift);

      if(open <= 0.0 || high <= 0.0 || low <= 0.0 || close <= 0.0)
         continue;

      datetime bar_open = iTime(Symbol(), PERIOD_H1, shift);
      if(bar_open <= 0)
         continue;

      string close_utc = BuildBarCloseUtcString(bar_open, H1_PERIOD_SECONDS);

      if(!first_item)
         json += ",";
      first_item = false;
      candle_count++;

      json += BuildBootstrapCandleItem(open, high, low, close, volume, digits, close_utc);
   }

   json += "]}";

   if(candle_count < 1)
   {
      Print("APEX bootstrap: no valid H1 candles built trigger=", trigger);
      return(false);
   }

   Print(
      "APEX bootstrap sending ", candle_count,
      " H1 candles (requested=", count, ") trigger=", trigger,
      " url=", InpBootstrapApiUrl
   );

   bool ok = PostJsonToApex(
      InpBootstrapApiUrl,
      json,
      trigger,
      "BOOTSTRAP",
      g_bootstrap_ok_count,
      g_bootstrap_fail_count,
      InpBootstrapTimeoutMs
   );
   if(ok)
   {
      g_bootstrap_sent = true;
      // Re-post latest closed H1 via live ingest so backend runs pipeline/SNR.
      g_tf_last_open_sent[2] = 0;
      Print("APEX bootstrap: success, candles=", candle_count);
   }
   else
   {
      Print("APEX bootstrap: POST failed trigger=", trigger);
   }
   return(ok);
}

//+------------------------------------------------------------------+
void CheckAndSendAllCandles(const string trigger)
{
   for(int i = 0; i < TF_COUNT; i++)
      CheckAndSendCandle(i, trigger);
}

//+------------------------------------------------------------------+
void CheckAndSendCandle(const int tf_index, const string trigger)
{
   if(tf_index < 0 || tf_index >= TF_COUNT)
      return;

   int period = g_tf_periods[tf_index];
   datetime bar_open = iTime(Symbol(), period, 1);
   if(bar_open <= 0)
      return;

   if(bar_open == g_tf_last_open_sent[tf_index])
      return;

   if(SendCandleToApex(tf_index, bar_open, trigger))
      g_tf_last_open_sent[tf_index] = bar_open;
}

//+------------------------------------------------------------------+
bool SendCandleToApex(const int tf_index, datetime bar_open, const string trigger)
{
   int period = g_tf_periods[tf_index];
   string timeframe = g_tf_labels[tf_index];
   int period_seconds = g_tf_seconds[tf_index];

   double open  = iOpen(Symbol(), period, 1);
   double high  = iHigh(Symbol(), period, 1);
   double low   = iLow(Symbol(), period, 1);
   double close = iClose(Symbol(), period, 1);
   long   volume = iVolume(Symbol(), period, 1);

   if(open <= 0.0 || high <= 0.0 || low <= 0.0 || close <= 0.0)
   {
      g_tf_fail_count[tf_index]++;
      Print("APEX ", timeframe, " candle: invalid OHLC for ", Symbol(), " trigger=", trigger);
      return(false);
   }

   int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(digits < 0)
      digits = 2;

   string close_utc = BuildBarCloseUtcString(bar_open, period_seconds);

   string json = BuildCandleJson(timeframe, open, high, low, close, volume, digits, close_utc);
   Print("APEX ", timeframe, " json=", json);

   return PostJsonToApex(
      InpCandleApiUrl,
      json,
      trigger,
      timeframe,
      g_tf_ok_count[tf_index],
      g_tf_fail_count[tf_index],
      InpTimeoutMs
   );
}

//+------------------------------------------------------------------+
void UpdateChartComment(const bool ok, const string detail)
{
   if(!InpShowComment)
      return;

   string status = ok ? "APEX OK" : "APEX ERR";
   Comment(
      status,
      " | ", InpApexSymbol,
      " | price ", InpTimerSeconds, "s",
      " | candles M5 M15 H1 H4 D1",
      " | bootstrap ", (g_bootstrap_sent ? "sent" : "pending"),
      " | resend=", (InpResendBootstrapOnInit ? "on" : "off"),
      " | ", detail,
      "\nprice ok=", g_ok_count,
      " fail=", g_fail_count,
      " | bootstrap ok=", g_bootstrap_ok_count,
      " fail=", g_bootstrap_fail_count,
      "\nM5 ok=", g_tf_ok_count[0], " fail=", g_tf_fail_count[0],
      " | M15 ok=", g_tf_ok_count[1], " fail=", g_tf_fail_count[1],
      " | H1 ok=", g_tf_ok_count[2], " fail=", g_tf_fail_count[2],
      "\nH4 ok=", g_tf_ok_count[3], " fail=", g_tf_fail_count[3],
      " | D1 ok=", g_tf_ok_count[4], " fail=", g_tf_fail_count[4],
      "\nlast=", TimeToString(g_last_ok_utc, TIME_DATE | TIME_SECONDS)
   );
}
//+------------------------------------------------------------------+
