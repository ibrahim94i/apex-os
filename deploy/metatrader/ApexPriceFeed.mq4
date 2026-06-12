//+------------------------------------------------------------------+
//| ApexPriceFeed.mq4 — APEX OS MetaTrader price stream (timer-based)|
//| Sends bid/ask every 5 seconds to POST /api/v1/prices/update    |
//| Display price layer only — no trading execution                  |
//+------------------------------------------------------------------+
#property copyright "APEX OS"
#property link      "https://github.com/ibrahim94i/apex-os"
#property version   "2.00"
#property strict

//--- inputs
input string InpApiUrl      = "https://apex-os-production-9adc.up.railway.app/api/v1/prices/update";
input string InpApiKey      = "apex_mt_CNj4vVEZvXwkPBKXkNGEoRndbg3J9mgaybydnWO0H50";
input string InpApexSymbol  = "XAUUSD";   // symbol name expected by APEX backend
input int    InpTimerSeconds = 5;         // fixed send interval (seconds)
input int    InpTimeoutMs   = 8000;       // WebRequest timeout
input bool   InpShowComment = true;       // show status on chart

//--- state
datetime g_last_ok_utc = 0;
int      g_fail_count  = 0;
int      g_ok_count    = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
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

   Print("APEX Price Feed started | timer=", InpTimerSeconds, "s | apex_symbol=", InpApexSymbol);
   SendPriceToApex("init");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if(InpShowComment)
      Comment("");
   Print("APEX Price Feed stopped, reason=", reason);
}

//+------------------------------------------------------------------+
//| Timer event — primary send loop (every 5 seconds)                |
//+------------------------------------------------------------------+
void OnTimer()
{
   SendPriceToApex("timer");
}

//+------------------------------------------------------------------+
//| Tick event — intentionally unused (timer-based streaming)        |
//+------------------------------------------------------------------+
void OnTick()
{
   // Timer-based only — do not send on tick.
}

//+------------------------------------------------------------------+
//| Build UTC timestamp string for backend (YYYY.MM.DD HH:MM:SS)     |
//+------------------------------------------------------------------+
string BuildUtcTimeString()
{
   datetime utc = TimeGMT();
   return(TimeToString(utc, TIME_DATE | TIME_SECONDS));
}

//+------------------------------------------------------------------+
//| Resolve bid/ask from chart symbol                                |
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
//| POST JSON price update to APEX backend                           |
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

   string time_utc = BuildUtcTimeString();
   string json = StringFormat(
      "{\"symbol\":\"%s\",\"bid\":%.*f,\"ask\":%.*f,\"time\":\"%s\"}",
      InpApexSymbol,
      digits, bid,
      digits, ask,
      time_utc
   );

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
      InpApiUrl,
      req_headers,
      InpTimeoutMs,
      post,
      result,
      resp_headers
   );

   if(http_status == -1)
   {
      int err = GetLastError();
      g_fail_count++;
      Print(
         "APEX WebRequest failed err=", err,
         " | add URL to Tools->Options->Expert Advisors->Allow WebRequest",
         " | url=", InpApiUrl,
         " | trigger=", trigger
      );
      UpdateChartComment(false, "WebRequest err " + IntegerToString(err));
      return(false);
   }

   string response = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);

   if(http_status >= 200 && http_status < 300)
   {
      g_ok_count++;
      g_last_ok_utc = TimeGMT();
      Print("APEX OK http=", http_status, " trigger=", trigger, " response=", response);
      UpdateChartComment(true, "HTTP " + IntegerToString(http_status));
      return(true);
   }

   g_fail_count++;
   Print(
      "APEX HTTP error status=", http_status,
      " trigger=", trigger,
      " response=", response
   );
   UpdateChartComment(false, "HTTP " + IntegerToString(http_status));
   return(false);
}

//+------------------------------------------------------------------+
//| Chart comment helper                                             |
//+------------------------------------------------------------------+
void UpdateChartComment(const bool ok, const string detail)
{
   if(!InpShowComment)
      return;

   string status = ok ? "APEX OK" : "APEX ERR";
   Comment(
      status,
      " | ", InpApexSymbol,
      " | every ", InpTimerSeconds, "s",
      " | ", detail,
      "\nok=", g_ok_count,
      " fail=", g_fail_count,
      "\nlast=", TimeToString(g_last_ok_utc, TIME_DATE | TIME_SECONDS)
   );
}
//+------------------------------------------------------------------+
