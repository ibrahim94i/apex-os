//+------------------------------------------------------------------+
//| ApexPriceFeed.mq4 — APEX OS MetaTrader price + H1 candle stream  |
//| Price: POST /api/v1/prices/update every 5s                       |
//| H1 candle: POST /api/v1/candles/update on each H1 close          |
//+------------------------------------------------------------------+
#property copyright "APEX OS"
#property link      "https://github.com/ibrahim94i/apex-os"
#property version   "3.01"
#property strict

//--- inputs
input string InpApiUrl       = "https://apex-os-production-9adc.up.railway.app/api/v1/prices/update";
input string InpCandleApiUrl = "https://apex-os-production-9adc.up.railway.app/api/v1/candles/update";
input string InpApiKey       = "apex_mt_CNj4vVEZvXwkPBKXkNGEoRndbg3J9mgaybydnWO0H50";
input string InpApexSymbol   = "XAUUSD";
input int    InpTimerSeconds = 5;
input int    InpTimeoutMs    = 8000;
input bool   InpShowComment   = true;

#define H1_PERIOD_SECONDS 3600

//--- state
datetime g_last_ok_utc      = 0;
datetime g_last_h1_open_sent = 0;
int      g_fail_count       = 0;
int      g_ok_count         = 0;
int      g_candle_ok_count  = 0;
int      g_candle_fail_count = 0;

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

   if(!EventSetTimer(InpTimerSeconds))
   {
      Print("APEX Price Feed: EventSetTimer failed, err=", GetLastError());
      return(INIT_FAILED);
   }

   Print("APEX Feed started | price timer=", InpTimerSeconds, "s | symbol=", InpApexSymbol);
   SendPriceToApex("init");
   CheckAndSendH1Candle("init");
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
   CheckAndSendH1Candle("timer");
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
//| JSON numbers must use dot decimal separator (not locale comma).  |
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
string BuildH1CandleJson(
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
      + "\"timeframe\":\"H1\","
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
   int &fail_counter
)
{
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
      InpTimeoutMs,
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

   return PostJsonToApex(InpApiUrl, json, trigger, "PRICE", g_ok_count, g_fail_count);
}

//+------------------------------------------------------------------+
void CheckAndSendH1Candle(const string trigger)
{
   datetime bar_open = iTime(Symbol(), PERIOD_H1, 1);
   if(bar_open <= 0)
      return;

   if(bar_open == g_last_h1_open_sent)
      return;

   if(SendH1CandleToApex(bar_open, trigger))
      g_last_h1_open_sent = bar_open;
}

//+------------------------------------------------------------------+
bool SendH1CandleToApex(datetime bar_open, const string trigger)
{
   double open  = iOpen(Symbol(), PERIOD_H1, 1);
   double high  = iHigh(Symbol(), PERIOD_H1, 1);
   double low   = iLow(Symbol(), PERIOD_H1, 1);
   double close = iClose(Symbol(), PERIOD_H1, 1);
   long   volume = iVolume(Symbol(), PERIOD_H1, 1);

   if(open <= 0.0 || high <= 0.0 || low <= 0.0 || close <= 0.0)
   {
      g_candle_fail_count++;
      Print("APEX H1 candle: invalid OHLC for ", Symbol(), " trigger=", trigger);
      return(false);
   }

   int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(digits < 0)
      digits = 2;

   datetime bar_close = bar_open + H1_PERIOD_SECONDS;
   string close_utc = BuildUtcTimeString(bar_close);

   string json = BuildH1CandleJson(open, high, low, close, volume, digits, close_utc);
   Print("APEX H1 json=", json);

   return PostJsonToApex(
      InpCandleApiUrl,
      json,
      trigger,
      "H1",
      g_candle_ok_count,
      g_candle_fail_count
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
      " | H1 on close",
      " | ", detail,
      "\nprice ok=", g_ok_count,
      " fail=", g_fail_count,
      " | H1 ok=", g_candle_ok_count,
      " fail=", g_candle_fail_count,
      "\nlast=", TimeToString(g_last_ok_utc, TIME_DATE | TIME_SECONDS)
   );
}
//+------------------------------------------------------------------+
