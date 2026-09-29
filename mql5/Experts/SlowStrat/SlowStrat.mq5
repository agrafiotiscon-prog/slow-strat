//+------------------------------------------------------------------+
//|                                                    SlowStrat.mq5 |
//|  Gold trend-breakout + gold Asian-range breakout + US-index      |
//|  dip-buyer portfolio EA.                                         |
//|                                                                  |
//|  Research, backtests and the exact rules this EA implements are  |
//|  documented in README.md and research/ of the slow-strat repo.   |
//|                                                                  |
//|  NO trading system can guarantee profits. Past results (even     |
//|  out-of-sample) do not guarantee future results. Test on a demo  |
//|  account first and only risk money you can afford to lose.       |
//+------------------------------------------------------------------+
#property copyright   "slow-strat"
#property version     "2.00"
#property description "Low-drawdown portfolio EA: XAUUSD H4 trend breakout, XAUUSD Asian-range breakout,"
#property description "US index (US500/NAS100/US30) daily dip-buyer with a US Dollar Index filter. Risk-based sizing, drawdown brake,"
#property description "economic-calendar news filter, rollover/spread protection. Use a hedging account."

#include <Trade/Trade.mqh>

//--- presets -------------------------------------------------------
enum ENUM_SS_PRESET
  {
   SS_PRESET_CONSERVATIVE = 0, // Conservative (lowest drawdown)
   SS_PRESET_BALANCED     = 1, // Balanced (default: ~6% drawdown target in today's market)
   SS_PRESET_GROWTH       = 2, // Growth (more return, ~7% drawdown in today's market)
   SS_PRESET_AGGRESSIVE   = 3, // Aggressive (highest return, highest drawdown)
   SS_PRESET_CUSTOM       = 4  // Custom (use the risk inputs below)
  };

//=================================================================== inputs
input group "=== Portfolio & risk ==="
input ENUM_SS_PRESET InpPreset          = SS_PRESET_BALANCED; // Risk preset
input double InpRiskMultiplier          = 1.0;   // Extra multiplier on every module's risk (1.0 = as preset)
input double InpCustomGoldTrendRisk     = 0.60;  // [Custom] Gold trend risk % per trade
input double InpCustomGoldAsiaRisk      = 0.50;  // [Custom] Gold Asia risk % per trade
input double InpCustomIndexRisk         = 1.50;  // [Custom] Index dip risk % per trade (each index)
input double InpMaxOpenRiskPct          = 6.0;   // Max total open risk % (sum of initial SL risk)
input long   InpMagicBase               = 7102600; // Magic number base (module adds +1/+2/+3)

input group "=== Drawdown protection ==="
input bool   InpDDBrake                 = true;  // Reduce risk while in drawdown
input double InpDDBrakeStartPct         = 3.0;   // Brake starts at this drawdown % from equity peak
input double InpDDBrakeFullPct          = 8.0;   // Brake reaches the floor at this drawdown %
input double InpDDBrakeFloor            = 0.5;   // Minimum risk multiplier while braking
input double InpDailyLossLimitPct       = 3.0;   // No new entries for the rest of the server day after this loss % (0=off)
input double InpHardStopDDPct           = 20.0;  // Close everything and halt at this drawdown % (0=off)
input bool   InpResetPeakOnStart        = false; // Reset stored equity peak / halt flag at start

input group "=== Module 1: Gold H4 trend breakout ==="
input bool   InpGoldTrendEnable         = true;  // Enable
input string InpGoldSymbol              = "";    // Gold symbol ("" = auto-detect XAUUSD/GOLD)
input int    InpGT_Channel              = 80;    // Breakout channel length (H4 bars)
input int    InpGT_ATR                  = 20;    // ATR period (H4)
input double InpGT_SLATR                = 1.0;   // Stop loss = x * ATR
input double InpGT_TrailR               = 3.0;   // Trailing stop distance in R (initial risk)
input int    InpGT_TrendSMA             = 200;   // D1 SMA trend filter period
input double InpGoldCommissionPerLot    = 7.0;   // Round-trip commission per 1.0 lot (account currency), for sizing

input group "=== Module 2: Gold Asian-range breakout (high win-rate) ==="
input bool   InpGoldAsiaEnable          = true;  // Enable
input int    InpGA_RangeEndUTC          = 7;     // Asian range = 00:00 .. this UTC hour
input int    InpGA_TradeEndUTC          = 12;    // Breakouts accepted until this UTC hour
input int    InpGA_ATRDays              = 14;    // Daily ATR period (UTC days)
input int    InpGA_TrendEMA             = 50;    // Daily EMA trend filter (UTC days)
input double InpGA_SLATR                = 1.0;   // Stop loss = x * daily ATR
input double InpGA_TPRange              = 1.0;   // Take profit = x * Asian range
input double InpGA_MinRangeATR          = 0.3;   // Skip day if range < x * daily ATR
input double InpGA_MaxRangeATR          = 2.0;   // Skip day if range > x * daily ATR

input group "=== Module 3: US index daily dip buyer ==="
input bool   InpIndexEnable             = true;  // Enable
input string InpIndexSymbols            = "";    // Index symbols, comma separated ("" = auto-detect US500,NAS100,US30)
input int    InpID_RSIPeriod            = 2;     // RSI period (D1)
input double InpID_RSIMax               = 10.0;  // Buy when RSI below
input double InpID_IBSMax               = 0.25;  // ...and internal bar strength below
input int    InpID_TrendSMA             = 200;   // ...and close above SMA
input int    InpID_ExitSMA              = 5;     // Exit when close above SMA
input int    InpID_ATR                  = 10;    // ATR period (D1)
input double InpID_SLATR                = 2.0;   // Stop loss = x * ATR
input int    InpID_MaxHoldDays          = 10;    // Time exit after N daily bars
input double InpIndexCommissionPerLot   = 0.0;   // Round-trip commission per 1.0 lot, for sizing
input int    InpID_MaxConcurrent        = 3;     // Max index positions open at the same time
input bool   InpID_DXYFilter            = true;  // Only buy dips when the US Dollar Index is not strong
input double InpID_DXYMaxAboveSMA       = 1.0;   // ...Dollar Index at most this % above its SMA
input int    InpID_DXYSMA               = 200;   // ...SMA period (daily bars)
input string InpDXYSymbols              = "";    // FX symbols for the Dollar Index ("" = auto EURUSD,USDJPY,GBPUSD,USDCAD,USDSEK,USDCHF)

input group "=== Broker time ==="
input bool   InpAutoGMTOffset           = true;  // Live: detect server GMT offset automatically
input int    InpServerGMTOffsetWinter   = 2;     // Server GMT offset in (northern) winter (tester / manual)
input bool   InpServerUsesUSDST         = true;  // Server shifts +1h with US daylight saving (NY-close brokers)
input int    InpRolloverBeforeMin       = 30;    // No entries from 17:00 NY minus this
input int    InpRolloverAfterMin        = 90;    // ...until 17:00 NY plus this

input group "=== News filter (MT5 economic calendar, live only) ==="
input bool   InpNewsFilter              = true;  // Block new entries around high-impact news
input string InpNewsCurrencies          = "USD"; // Currencies to watch (comma separated)
input int    InpNewsBeforeMin           = 30;    // Block entries this many minutes before
input int    InpNewsAfterMin            = 20;    // ...and after a high-impact release
input bool   InpNewsIncludeMedium       = false; // Also block around medium-impact events

input group "=== Execution ==="
input double InpMaxSpreadBpsGold        = 4.0;   // Max spread for gold entries (basis points of price)
input double InpMaxSpreadBpsIndex       = 3.0;   // Max spread for index entries (basis points of price)
input int    InpSlippagePoints          = 50;    // Max deviation in points
input bool   InpWriteTradeLog           = true;  // Write signals/trades to MQL5/Files/SlowStrat_log.csv
input bool   InpShowPanel               = true;  // Show status panel on chart

//=================================================================== constants
#define MOD_GT   1
#define MOD_GA   2
#define MOD_ID   3
#define MAX_IDX  8
#define MAX_FX   6

//=================================================================== state
CTrade   g_trade;
string   g_gold = "";
int      g_hGT_ATR = INVALID_HANDLE, g_hGT_SMA = INVALID_HANDLE;
double   g_riskGT = 0, g_riskGA = 0, g_riskID = 0;
int      g_gmtWinter = 2;
bool     g_hedging = true;
bool     g_isTester = false;
string   g_prefix = "";

// gold trend
datetime g_gtLastEval = 0;
int      g_gtIntentDir = 0;
double   g_gtIntentSL = 0;
datetime g_gtIntentBar = 0;
datetime g_lastM5Bar = 0;

// gold asia
datetime g_gaDayUTC = 0;       // UTC date (00:00) currently tracked
bool     g_gaDayReady = false;
bool     g_gaTaken = false;
double   g_gaRH = 0, g_gaRL = 0, g_gaATR = 0, g_gaEMA = 0, g_gaPrevClose = 0;
datetime g_gaLastBar = 0;
int      g_gaIntentDir = 0;
double   g_gaIntentSL = 0, g_gaIntentTP = 0;
datetime g_gaIntentTime = 0;

// indices
int      g_nIdx = 0;
string   g_idx[MAX_IDX];
int      g_hID_RSI[MAX_IDX], g_hID_SMA[MAX_IDX], g_hID_EXIT[MAX_IDX], g_hID_ATR[MAX_IDX];
datetime g_idLastEval[MAX_IDX];
int      g_idEntryIntent[MAX_IDX];
double   g_idIntentSL[MAX_IDX];
bool     g_idExitIntent[MAX_IDX];

// US Dollar Index (ICE formula) built from broker FX pairs; weights signed for the quote direction
int      g_nFx = 0;
string   g_fx[MAX_FX];
double   g_fxW[MAX_FX];
datetime g_dxyCacheBar = 0;
double   g_dxyCacheRatio = 0;
bool     g_dxyCacheOk = false;

// risk state
double   g_peak = 0;
bool     g_halted = false;
datetime g_dayStart = 0;
double   g_dayStartEquity = 0;
datetime g_lastProcess = 0;

// news cache
datetime g_newsTimes[];
string   g_newsNames[];
datetime g_newsLoaded = 0;
bool     g_newsAvailable = true;

//=================================================================== utils: time
datetime NthSunday(const int year, const int month, const int n)
  {
   MqlDateTime s;
   ZeroMemory(s);
   s.year = year; s.mon = month; s.day = 1;
   datetime d = StructToTime(s);
   MqlDateTime t;
   TimeToStruct(d, t);
   int add = (7 - t.day_of_week) % 7;
   return d + (datetime)((add + 7 * (n - 1)) * 86400);
  }

bool IsUSDST(const datetime utc)
  {
   MqlDateTime t;
   TimeToStruct(utc, t);
   datetime st = NthSunday(t.year, 3, 2) + 7 * 3600;   // 2nd Sunday of March, 02:00 EST
   datetime en = NthSunday(t.year, 11, 1) + 6 * 3600;  // 1st Sunday of November, 02:00 EDT
   return (utc >= st && utc < en);
  }

int ServerOffsetForUTC(const datetime utc)
  {
   return g_gmtWinter + ((InpServerUsesUSDST && IsUSDST(utc)) ? 1 : 0);
  }

datetime ServerToUTC(const datetime srv)
  {
   datetime approx = srv - g_gmtWinter * 3600;
   return srv - ServerOffsetForUTC(approx) * 3600;
  }

datetime UTCToServer(const datetime utc) { return utc + ServerOffsetForUTC(utc) * 3600; }
datetime UTCToNY(const datetime utc)     { return utc - (IsUSDST(utc) ? 4 : 5) * 3600; }
datetime NowServer()                     { return TimeTradeServer() > 0 ? TimeTradeServer() : TimeCurrent(); }

int MinuteOfDay(const datetime t)
  {
   MqlDateTime s;
   TimeToStruct(t, s);
   return s.hour * 60 + s.min;
  }

datetime DateOf(const datetime t) { return (datetime)(((long)t / 86400) * 86400); }

bool InRolloverBlock(const datetime srv)
  {
   int m = MinuteOfDay(UTCToNY(ServerToUTC(srv)));
   return (m >= 17 * 60 - InpRolloverBeforeMin && m < 17 * 60 + InpRolloverAfterMin);
  }

void DetectGMTOffset()
  {
   g_gmtWinter = InpServerGMTOffsetWinter;
   if(g_isTester || !InpAutoGMTOffset)
      return;
   datetime gmt = TimeGMT();
   datetime srv = TimeTradeServer();
   if(gmt <= 0 || srv <= 0)
      return;
   int off = (int)MathRound((double)(srv - gmt) / 3600.0);
   int winter = off - ((InpServerUsesUSDST && IsUSDST(gmt)) ? 1 : 0);
   if(winter != InpServerGMTOffsetWinter)
      PrintFormat("SlowStrat: detected server GMT offset %+d (winter %+d) differs from input %+d - using detected value.",
                  off, winter, InpServerGMTOffsetWinter);
   g_gmtWinter = winter;
  }

//=================================================================== utils: symbols
bool TrySymbol(const string name)
  {
   if(name == "")
      return false;
   bool custom = false;
   if(!SymbolExist(name, custom))
      return false;
   SymbolSelect(name, true);
   return true;
  }

// find a tradable symbol whose name starts with one of the candidates (handles suffixes like XAUUSD.r / XAUUSDm)
string ResolveSymbol(const string &cands[])
  {
   for(int c = 0; c < ArraySize(cands); c++)
      if(TrySymbol(cands[c]))
         return cands[c];
   int total = SymbolsTotal(false);
   for(int c = 0; c < ArraySize(cands); c++)
      for(int i = 0; i < total; i++)
        {
         string s = SymbolName(i, false);
         if(StringFind(s, cands[c]) == 0 && StringLen(s) <= StringLen(cands[c]) + 4)
           {
            SymbolSelect(s, true);
            return s;
           }
        }
   return "";
  }

//=================================================================== utils: indicators
double Buf(const int handle, const int shift, const int buffer = 0)
  {
   double b[1];
   if(handle == INVALID_HANDLE)
      return EMPTY_VALUE;
   if(CopyBuffer(handle, buffer, shift, 1, b) != 1)
      return EMPTY_VALUE;
   return b[0];
  }

bool Valid(const double v) { return (v != EMPTY_VALUE && MathIsValidNumber(v)); }

// last D1 bar completed at or before server time t
int CompletedD1Shift(const string sym, const datetime t)
  {
   int d = iBarShift(sym, PERIOD_D1, t - 1, false);
   if(d < 0)
      return -1;
   datetime o = iTime(sym, PERIOD_D1, d);
   if(o + 86400 <= t)
      return d;
   return d + 1;
  }

//=================================================================== utils: logging
void Log(const string what)
  {
   if(!InpWriteTradeLog)
      return;
   int h = FileOpen("SlowStrat_log.csv", FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ, ';');
   if(h == INVALID_HANDLE)
      return;
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, TimeToString(NowServer(), TIME_DATE | TIME_SECONDS), what);
   FileClose(h);
  }

//=================================================================== risk
long ModuleMagic(const int mod) { return InpMagicBase + mod; }

double BrakeMultiplier()
  {
   if(!InpDDBrake || g_peak <= 0)
      return 1.0;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dd = 100.0 * (1.0 - eq / g_peak);
   if(dd <= InpDDBrakeStartPct)
      return 1.0;
   double span = MathMax(0.01, InpDDBrakeFullPct - InpDDBrakeStartPct);
   double m = 1.0 - (dd - InpDDBrakeStartPct) / span * (1.0 - InpDDBrakeFloor);
   return MathMax(InpDDBrakeFloor, m);
  }

double CurrentDDPct()
  {
   if(g_peak <= 0)
      return 0;
   return 100.0 * (1.0 - AccountInfoDouble(ACCOUNT_EQUITY) / g_peak);
  }

// money lost per 1.0 lot if price moves slDist against the position, plus commission
double LossPerLot(const string sym, const int dir, const double price, const double slDist, const double commission)
  {
   double profit = 0;
   ENUM_ORDER_TYPE t = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double close = (dir > 0) ? price - slDist : price + slDist;
   if(!OrderCalcProfit(t, sym, 1.0, price, close, profit))
     {
      double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS);
      double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
      if(tv <= 0 || ts <= 0)
         return 0;
      profit = -slDist / ts * tv;
     }
   return MathAbs(profit) + commission;
  }

double NormalizeLots(const string sym, const double lots)
  {
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double mn = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step <= 0)
      step = 0.01;
   double v = MathFloor(lots / step + 1e-9) * step;
   if(v < mn)
      return 0;
   if(v > mx)
      v = mx;
   return NormalizeDouble(v, 8);
  }

// open risk (money at stop) of all EA positions as % of equity
double OpenRiskPct()
  {
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= 0)
      return 0;
   double tot = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0)
         continue;
      long mg = PositionGetInteger(POSITION_MAGIC);
      if(mg <= InpMagicBase || mg > InpMagicBase + 3)
         continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      double sl = PositionGetDouble(POSITION_SL);
      double op = PositionGetDouble(POSITION_PRICE_OPEN);
      double vol = PositionGetDouble(POSITION_VOLUME);
      int dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      if(sl <= 0)
         continue;
      double dist = (op - sl) * dir;
      if(dist <= 0)
         continue;            // stop already in profit: no open risk
      tot += LossPerLot(sym, dir, op, dist, 0) * vol;
     }
   return 100.0 * tot / eq;
  }

double SpreadBps(const string sym)
  {
   double a = SymbolInfoDouble(sym, SYMBOL_ASK), b = SymbolInfoDouble(sym, SYMBOL_BID);
   if(a <= 0 || b <= 0)
      return 1e9;
   return 1e4 * (a - b) / b;
  }

//=================================================================== news
void LoadNews()
  {
   if(!InpNewsFilter || g_isTester)
      return;
   datetime now = NowServer();
   if(g_newsLoaded != 0 && now - g_newsLoaded < 900)
      return;
   g_newsLoaded = now;
   ArrayResize(g_newsTimes, 0);
   ArrayResize(g_newsNames, 0);
   string cur[];
   int nc = StringSplit(InpNewsCurrencies, ',', cur);
   bool any = false;
   for(int c = 0; c < nc; c++)
     {
      string ccy = cur[c];
      StringTrimLeft(ccy);
      StringTrimRight(ccy);
      MqlCalendarValue vals[];
      ResetLastError();
      CalendarValueHistory(vals, now - 6 * 3600, now + 48 * 3600, NULL, ccy);
      int err = GetLastError();
      int n = ArraySize(vals);
      if(n == 0 && err != 0)
         continue;
      any = true;
      for(int i = 0; i < n; i++)
        {
         MqlCalendarEvent ev;
         if(!CalendarEventById(vals[i].event_id, ev))
            continue;
         bool hi = (ev.importance == CALENDAR_IMPORTANCE_HIGH);
         bool md = (ev.importance == CALENDAR_IMPORTANCE_MODERATE);
         if(!(hi || (InpNewsIncludeMedium && md)))
            continue;
         int k = ArraySize(g_newsTimes);
         ArrayResize(g_newsTimes, k + 1);
         ArrayResize(g_newsNames, k + 1);
         g_newsTimes[k] = vals[i].time;
         g_newsNames[k] = ccy + " " + ev.name;
        }
     }
   if(!any && g_newsAvailable)
     {
      g_newsAvailable = false;
      Print("SlowStrat: economic calendar not available - news filter inactive. Check the calendar is enabled in the terminal.");
     }
   else if(any)
      g_newsAvailable = true;
  }

bool NewsBlocked(string &why)
  {
   if(!InpNewsFilter || g_isTester)
      return false;
   LoadNews();
   datetime now = NowServer();
   for(int i = 0; i < ArraySize(g_newsTimes); i++)
     {
      if(now >= g_newsTimes[i] - InpNewsBeforeMin * 60 && now <= g_newsTimes[i] + InpNewsAfterMin * 60)
        {
         why = g_newsNames[i] + " @ " + TimeToString(g_newsTimes[i], TIME_DATE | TIME_MINUTES);
         return true;
        }
     }
   return false;
  }

string NextNews()
  {
   if(!InpNewsFilter || g_isTester)
      return "news filter off in tester";
   if(!g_newsAvailable)
      return "calendar unavailable";
   datetime now = NowServer();
   string s = "";
   int shown = 0;
   for(int i = 0; i < ArraySize(g_newsTimes) && shown < 3; i++)
      if(g_newsTimes[i] >= now - InpNewsAfterMin * 60)
        {
         s += "\n   " + TimeToString(g_newsTimes[i], TIME_DATE | TIME_MINUTES) + "  " + g_newsNames[i];
         shown++;
        }
   return shown ? s : "none in next 48h";
  }

//=================================================================== entry gating
bool CanEnter(const string sym, const double maxSpreadBps, string &why)
  {
   datetime now = NowServer();
   if(g_halted)
     { why = "halted (hard drawdown stop)"; return false; }
   if(InRolloverBlock(now))
     { why = "rollover window"; return false; }
   if(InpDailyLossLimitPct > 0 && g_dayStartEquity > 0 &&
      AccountInfoDouble(ACCOUNT_EQUITY) < g_dayStartEquity * (1.0 - InpDailyLossLimitPct / 100.0))
     { why = "daily loss limit"; return false; }
   if(NewsBlocked(why))
      return false;
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && !g_isTester)
     { why = "algo trading disabled in terminal"; return false; }
   long mode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
   if(mode != SYMBOL_TRADE_MODE_FULL && mode != SYMBOL_TRADE_MODE_LONGONLY && mode != SYMBOL_TRADE_MODE_SHORTONLY)
     { why = "symbol not tradable now"; return false; }
   double sp = SpreadBps(sym);
   if(sp > maxSpreadBps)
     { why = StringFormat("spread %.1fbp > %.1fbp", sp, maxSpreadBps); return false; }
   return true;
  }

//=================================================================== positions
int CountPositions(const int mod, const string sym)
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != ModuleMagic(mod))
         continue;
      if(sym != "" && PositionGetString(POSITION_SYMBOL) != sym)
         continue;
      n++;
     }
   return n;
  }

// on netting accounts two gold modules cannot hold separate positions on the same symbol
bool SymbolBusyNetting(const string sym)
  {
   if(g_hedging)
      return false;
   return PositionSelect(sym);
  }

string GVKey(const ulong ticket) { return g_prefix + "R_" + (string)ticket; }

bool OpenPosition(const int mod, const string sym, const int dir, const double slDist, const double tpDist,
                  const double riskPct, const double commission, const string tag)
  {
   if(slDist <= 0 || riskPct <= 0)
      return false;
   double price = (dir > 0) ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
   if(price <= 0)
      return false;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double effRisk = riskPct * InpRiskMultiplier * BrakeMultiplier();
   // total-open-risk cap
   if(OpenRiskPct() + effRisk > InpMaxOpenRiskPct)
     {
      PrintFormat("SlowStrat %s: skip %s - open risk cap (%.2f%% + %.2f%% > %.2f%%)", tag, sym, OpenRiskPct(), effRisk, InpMaxOpenRiskPct);
      return false;
     }
   double lpl = LossPerLot(sym, dir, price, slDist, commission);
   if(lpl <= 0)
      return false;
   double lots = NormalizeLots(sym, eq * effRisk / 100.0 / lpl);
   if(lots <= 0)
     {
      double mn = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
      PrintFormat("SlowStrat %s: skip %s - account too small: min lot %.2f would risk %.2f%% (target %.2f%%)",
                  tag, sym, mn, 100.0 * mn * lpl / eq, effRisk);
      return false;
     }
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   double minDist = (SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) + SymbolInfoInteger(sym, SYMBOL_SPREAD)) * point;
   double sl = NormalizeDouble(price - dir * MathMax(slDist, minDist), digits);
   double tp = (tpDist > 0) ? NormalizeDouble(price + dir * MathMax(tpDist, minDist), digits) : 0.0;

   g_trade.SetExpertMagicNumber(ModuleMagic(mod));
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetTypeFillingBySymbol(sym);
   bool ok = false;
   for(int attempt = 0; attempt < 3 && !ok; attempt++)
     {
      if(attempt > 0)
        {
         Sleep(300);
         price = (dir > 0) ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
         sl = NormalizeDouble(price - dir * MathMax(slDist, minDist), digits);
         tp = (tpDist > 0) ? NormalizeDouble(price + dir * MathMax(tpDist, minDist), digits) : 0.0;
        }
      string cmt = "SS " + tag;
      ok = (dir > 0) ? g_trade.Buy(lots, sym, price, sl, tp, cmt) : g_trade.Sell(lots, sym, price, sl, tp, cmt);
      uint rc = g_trade.ResultRetcode();
      if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL))
         break;
      ok = false;
      if(rc != TRADE_RETCODE_REQUOTE && rc != TRADE_RETCODE_PRICE_CHANGED && rc != TRADE_RETCODE_PRICE_OFF &&
         rc != TRADE_RETCODE_TIMEOUT && rc != TRADE_RETCODE_CONNECTION)
        {
         PrintFormat("SlowStrat %s: order failed on %s, retcode %u (%s)", tag, sym, rc, g_trade.ResultRetcodeDescription());
         return false;
        }
     }
   if(!ok)
      return false;
   // find the resulting position, re-anchor SL/TP to the actual fill so 1R is exact
   double fill = g_trade.ResultPrice();
   ulong posTicket = 0;
   ulong ord = g_trade.ResultOrder();
   if(ord > 0 && PositionSelectByTicket(ord))
      posTicket = ord;                          // hedging: position ticket == opening order ticket
   else
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong tk = PositionGetTicket(i);
         if(tk == 0)
            continue;
         if(PositionGetInteger(POSITION_MAGIC) == ModuleMagic(mod) && PositionGetString(POSITION_SYMBOL) == sym)
           {
            posTicket = tk;
            break;
           }
        }
   if(fill <= 0 && posTicket > 0 && PositionSelectByTicket(posTicket))
      fill = PositionGetDouble(POSITION_PRICE_OPEN);
   if(posTicket > 0 && fill > 0)
     {
      double nsl = NormalizeDouble(fill - dir * MathMax(slDist, minDist), digits);
      double ntp = (tpDist > 0) ? NormalizeDouble(fill + dir * MathMax(tpDist, minDist), digits) : 0.0;
      if(PositionSelectByTicket(posTicket) &&
         (MathAbs(PositionGetDouble(POSITION_SL) - nsl) > point || MathAbs(PositionGetDouble(POSITION_TP) - ntp) > point))
         g_trade.PositionModify(posTicket, nsl, ntp);
      GlobalVariableSet(GVKey(posTicket), slDist);
     }
   string msg = StringFormat("OPEN;%s;%s;%s;lots=%.2f;fill=%s;slDist=%s;tpDist=%s;risk=%.2f%%",
                             tag, sym, dir > 0 ? "BUY" : "SELL", lots, DoubleToString(fill, digits),
                             DoubleToString(slDist, digits), DoubleToString(tpDist, digits), effRisk);
   Print("SlowStrat ", msg);
   Log(msg);
   return true;
  }

void ClosePositions(const int mod, const string sym, const string reason)
  {
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != ModuleMagic(mod))
         continue;
      if(sym != "" && PositionGetString(POSITION_SYMBOL) != sym)
         continue;
      string s = PositionGetString(POSITION_SYMBOL);
      if(g_trade.PositionClose(tk, InpSlippagePoints))
        {
         Log(StringFormat("CLOSE;%d;%s;%s", mod, s, reason));
         GlobalVariableDel(GVKey(tk));
        }
      else
         PrintFormat("SlowStrat: close failed %s ticket %I64u retcode %u", s, tk, g_trade.ResultRetcode());
     }
  }

void CloseAll(const string reason)
  {
   ClosePositions(MOD_GT, "", reason);
   ClosePositions(MOD_GA, "", reason);
   ClosePositions(MOD_ID, "", reason);
  }

//=================================================================== module 1: gold trend
void GoldTrendEvaluate()
  {
   if(!InpGoldTrendEnable || g_gold == "")
      return;
   datetime sigBar = iTime(g_gold, PERIOD_H4, 1);
   if(sigBar == 0 || sigBar == g_gtLastEval)
      return;
   if(Bars(g_gold, PERIOD_H4) < InpGT_Channel + 5)
      return;
   g_gtLastEval = sigBar;
   GlobalVariableSet(g_prefix + "GT_LAST", (double)sigBar);
   g_gtIntentDir = 0;

   double c1 = iClose(g_gold, PERIOD_H4, 1);
   int hi = iHighest(g_gold, PERIOD_H4, MODE_HIGH, InpGT_Channel, 2);
   int lo = iLowest(g_gold, PERIOD_H4, MODE_LOW, InpGT_Channel, 2);
   if(hi < 0 || lo < 0)
      return;
   double hh = iHigh(g_gold, PERIOD_H4, hi);
   double ll = iLow(g_gold, PERIOD_H4, lo);
   double atr = Buf(g_hGT_ATR, 1);
   datetime closeT = sigBar + PeriodSeconds(PERIOD_H4);
   int d = CompletedD1Shift(g_gold, closeT);
   if(d < 0 || !Valid(atr) || atr <= 0)
      return;
   double dClose = iClose(g_gold, PERIOD_D1, d);
   double dSma = Buf(g_hGT_SMA, d);
   if(!Valid(dSma) || dSma <= 0)
      return;
   int dir = 0;
   if(c1 > hh && dClose > dSma)
      dir = 1;
   else if(c1 < ll && dClose < dSma)
      dir = -1;
   if(dir == 0)
      return;
   g_gtIntentDir = dir;
   g_gtIntentSL = InpGT_SLATR * atr;
   g_gtIntentBar = sigBar;
   Log(StringFormat("SIGNAL;GOLD_TREND;%s;%s;close=%.2f;hh=%.2f;ll=%.2f;atr=%.2f;d1close=%.2f;d1sma=%.2f",
                    g_gold, dir > 0 ? "BUY" : "SELL", c1, hh, ll, atr, dClose, dSma));
  }

void GoldTrendExecute()
  {
   if(g_gtIntentDir == 0)
      return;
   if(CountPositions(MOD_GT, g_gold) > 0)
     { g_gtIntentDir = 0; return; }            // already in a trade: signal ignored (max 1 position)
   if(SymbolBusyNetting(g_gold))
     { g_gtIntentDir = 0; return; }
   string why = "";
   if(!CanEnter(g_gold, InpMaxSpreadBpsGold, why))
      return;                                  // keep intent, retry until the next H4 bar
   if(OpenPosition(MOD_GT, g_gold, g_gtIntentDir, g_gtIntentSL, 0.0, g_riskGT, InpGoldCommissionPerLot, "GOLD_TREND"))
      g_gtIntentDir = 0;
  }

// trailing stop: best price since entry (completed M5 bars) minus TrailR * initial risk
void GoldTrendTrail()
  {
   if(g_gold == "")
      return;
   datetime m5 = iTime(g_gold, PERIOD_M5, 1);
   if(m5 == 0 || m5 == g_lastM5Bar)
      return;
   g_lastM5Bar = m5;
   double point = SymbolInfoDouble(g_gold, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(g_gold, SYMBOL_DIGITS);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || PositionGetInteger(POSITION_MAGIC) != ModuleMagic(MOD_GT))
         continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      int dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      double op = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
      double R = GlobalVariableCheck(GVKey(tk)) ? GlobalVariableGet(GVKey(tk)) : 0;
      if(R <= 0)
        {
         if(sl <= 0)
            continue;
         R = MathAbs(op - sl);                 // fallback: assume stop has not moved yet
         GlobalVariableSet(GVKey(tk), R);
        }
      int startShift = iBarShift(sym, PERIOD_M5, ot, false);
      if(startShift < 1)
         continue;
      double best;
      if(dir > 0)
        {
         int h = iHighest(sym, PERIOD_M5, MODE_HIGH, startShift, 1);
         best = MathMax(op, h >= 0 ? iHigh(sym, PERIOD_M5, h) : op);
         double nsl = NormalizeDouble(best - InpGT_TrailR * R, digits);
         double bid = SymbolInfoDouble(sym, SYMBOL_BID);
         double lim = bid - (SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) + 1) * point;
         if(nsl > sl + point && nsl < lim)
            if(g_trade.PositionModify(tk, nsl, tp))
               Log(StringFormat("TRAIL;GOLD_TREND;%s;sl=%s", sym, DoubleToString(nsl, digits)));
        }
      else
        {
         int l = iLowest(sym, PERIOD_M5, MODE_LOW, startShift, 1);
         double spread = SymbolInfoInteger(sym, SYMBOL_SPREAD) * point;
         best = MathMin(op, (l >= 0 ? iLow(sym, PERIOD_M5, l) : op) + spread);
         double nsl = NormalizeDouble(best + InpGT_TrailR * R, digits);
         double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
         double lim = ask + (SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) + 1) * point;
         if((sl <= 0 || nsl < sl - point) && nsl > lim)
            if(g_trade.PositionModify(tk, nsl, tp))
               Log(StringFormat("TRAIL;GOLD_TREND;%s;sl=%s", sym, DoubleToString(nsl, digits)));
        }
     }
  }

//=================================================================== module 2: gold asia
// Build UTC daily bars from H1 data and compute ATR(n) and EMA(m) of completed UTC days before dayUTC.
bool GoldAsiaDailyStats(const datetime dayUTC, double &atr, double &ema, double &prevClose)
  {
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int need = 24 * 400;
   int got = CopyRates(g_gold, PERIOD_H1, 0, need, r);
   if(got < 24 * 120)
      return false;
   double dO[], dH[], dL[], dC[];
   datetime dT[];
   int nd = 0;
   for(int i = 0; i < got; i++)
     {
      datetime u = ServerToUTC(r[i].time);
      datetime dd = DateOf(u);
      if(dd >= dayUTC)
         break;
      if(nd == 0 || dT[nd - 1] != dd)
        {
         nd++;
         ArrayResize(dT, nd); ArrayResize(dO, nd); ArrayResize(dH, nd); ArrayResize(dL, nd); ArrayResize(dC, nd);
         dT[nd - 1] = dd; dO[nd - 1] = r[i].open; dH[nd - 1] = r[i].high; dL[nd - 1] = r[i].low; dC[nd - 1] = r[i].close;
        }
      else
        {
         dH[nd - 1] = MathMax(dH[nd - 1], r[i].high);
         dL[nd - 1] = MathMin(dL[nd - 1], r[i].low);
         dC[nd - 1] = r[i].close;
        }
     }
   if(nd < MathMax(InpGA_ATRDays, InpGA_TrendEMA) + 20)
      return false;
   // ATR = simple average of true range over the last n completed days (matches MT5 iATR / research)
   double s = 0;
   for(int k = nd - InpGA_ATRDays; k < nd; k++)
     {
      double tr = dH[k] - dL[k];
      if(k > 0)
         tr = MathMax(tr, MathMax(MathAbs(dH[k] - dC[k - 1]), MathAbs(dL[k] - dC[k - 1])));
      s += tr;
     }
   atr = s / InpGA_ATRDays;
   double a = 2.0 / (InpGA_TrendEMA + 1.0);
   ema = dC[0];
   for(int k = 1; k < nd; k++)
      ema = a * dC[k] + (1 - a) * ema;
   prevClose = dC[nd - 1];
   return true;
  }

void GoldAsiaEvaluate()
  {
   if(!InpGoldAsiaEnable || g_gold == "")
      return;
   datetime bar = iTime(g_gold, PERIOD_M5, 1);        // last completed M5 bar (server time)
   if(bar == 0 || bar == g_gaLastBar)
      return;
   g_gaLastBar = bar;
   datetime utc = ServerToUTC(bar);
   datetime day = DateOf(utc);
   int hour = (int)((utc - day) / 3600);
   if(day != g_gaDayUTC)
     {
      g_gaDayUTC = day;
      g_gaDayReady = false;
      g_gaTaken = false;
      g_gaIntentDir = 0;
     }
   if(hour < InpGA_RangeEndUTC || hour >= InpGA_TradeEndUTC || g_gaTaken)
      return;
   if(!g_gaDayReady)
     {
      // Asian range from M5 bars 00:00 .. RangeEnd UTC of this UTC day
      datetime from = UTCToServer(day);
      datetime to = UTCToServer(day + InpGA_RangeEndUTC * 3600) - 1;
      MqlRates m[];
      int n = CopyRates(g_gold, PERIOD_M5, from, to, m);
      if(n <= 0)
        { g_gaTaken = true; return; }
      g_gaRH = -DBL_MAX; g_gaRL = DBL_MAX;
      for(int i = 0; i < n; i++)
        {
         datetime mu = ServerToUTC(m[i].time);
         if(mu < day || mu >= day + InpGA_RangeEndUTC * 3600)
            continue;
         g_gaRH = MathMax(g_gaRH, m[i].high);
         g_gaRL = MathMin(g_gaRL, m[i].low);
        }
      if(g_gaRH <= g_gaRL || !GoldAsiaDailyStats(day, g_gaATR, g_gaEMA, g_gaPrevClose))
        { g_gaTaken = true; return; }
      g_gaDayReady = true;
     }
   double rng = g_gaRH - g_gaRL;
   if(rng < InpGA_MinRangeATR * g_gaATR || rng > InpGA_MaxRangeATR * g_gaATR)
     { g_gaTaken = true; return; }
   double c = iClose(g_gold, PERIOD_M5, 1);
   int dir = 0;
   if(c > g_gaRH && g_gaPrevClose > g_gaEMA)
      dir = 1;
   else if(c < g_gaRL && g_gaPrevClose < g_gaEMA)
      dir = -1;
   if(dir == 0)
      return;
   g_gaTaken = true;                                  // first qualifying breakout consumes the day
   g_gaIntentDir = dir;
   g_gaIntentSL = InpGA_SLATR * g_gaATR;
   g_gaIntentTP = InpGA_TPRange * rng;
   g_gaIntentTime = NowServer();
   Log(StringFormat("SIGNAL;GOLD_ASIA;%s;%s;close=%.2f;rh=%.2f;rl=%.2f;atrD=%.2f;ema=%.2f;prevC=%.2f",
                    g_gold, dir > 0 ? "BUY" : "SELL", c, g_gaRH, g_gaRL, g_gaATR, g_gaEMA, g_gaPrevClose));
  }

void GoldAsiaExecute()
  {
   if(g_gaIntentDir == 0)
      return;
   if(NowServer() - g_gaIntentTime > 15 * 60)
     { g_gaIntentDir = 0; return; }                  // stale: research enters on the next M5 open
   if(CountPositions(MOD_GA, g_gold) > 0 || SymbolBusyNetting(g_gold))
     { g_gaIntentDir = 0; return; }
   string why = "";
   if(!CanEnter(g_gold, InpMaxSpreadBpsGold, why))
      return;
   if(OpenPosition(MOD_GA, g_gold, g_gaIntentDir, g_gaIntentSL, g_gaIntentTP, g_riskGA, InpGoldCommissionPerLot, "GOLD_ASIA"))
      g_gaIntentDir = 0;
  }

//=================================================================== US Dollar Index filter
void ResolveDXYSymbols()
  {
   g_nFx = 0;
   string names[6] = {"EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"};
   double w[6] = {-0.576, 0.136, -0.119, 0.091, 0.042, 0.036};
   string custom[];
   int nc = 0;
   if(InpDXYSymbols != "")
      nc = StringSplit(InpDXYSymbols, ',', custom);
   for(int i = 0; i < 6; i++)
     {
      string found = "";
      if(nc > 0)
        {
         for(int j = 0; j < nc; j++)
           {
            string c = custom[j];
            StringTrimLeft(c);
            StringTrimRight(c);
            if(StringFind(c, names[i]) == 0 && TrySymbol(c))
               found = c;
           }
        }
      else
        {
         string cand[];
         ArrayResize(cand, 1);
         cand[0] = names[i];
         found = ResolveSymbol(cand);
        }
      if(found == "")
         continue;
      g_fx[g_nFx] = found;
      g_fxW[g_nFx] = w[i];
      g_nFx++;
     }
   if(InpID_DXYFilter && InpIndexEnable)
     {
      if(g_nFx == 0)
         Print("SlowStrat: no FX symbols for the Dollar Index found - DXY filter inactive.");
      else if(g_nFx < 6)
         PrintFormat("SlowStrat: Dollar Index built from %d of 6 FX pairs (missing pairs are left out).", g_nFx);
     }
  }

// Dollar Index vs its SMA, using FX daily closes of the day BEFORE the index signal bar
// (the research used the previous day's official noon rates, so there is no look-ahead).
bool DXYRatio(const datetime sigBar, double &ratio)
  {
   if(g_nFx == 0)
      return false;
   if(sigBar == g_dxyCacheBar)
     {
      ratio = g_dxyCacheRatio;
      return g_dxyCacheOk;
     }
   g_dxyCacheBar = sigBar;
   g_dxyCacheOk = false;
   string ref = g_fx[0];
   int s0 = iBarShift(ref, PERIOD_D1, sigBar - 1, false);
   int n = InpID_DXYSMA;
   if(s0 < 0 || Bars(ref, PERIOD_D1) < s0 + n + 1)
      return false;
   double sum = 0, first = 0;
   for(int k = 0; k < n; k++)
     {
      datetime t = iTime(ref, PERIOD_D1, s0 + k);
      double lg = 0;
      for(int i = 0; i < g_nFx; i++)
        {
         int sh = (i == 0) ? s0 + k : iBarShift(g_fx[i], PERIOD_D1, t, false);
         double c = (sh >= 0) ? iClose(g_fx[i], PERIOD_D1, sh) : 0;
         if(c <= 0)
            return false;
         lg += g_fxW[i] * MathLog(c);
        }
      double v = MathExp(lg);
      if(k == 0)
         first = v;
      sum += v;
     }
   ratio = first / (sum / n) - 1.0;
   g_dxyCacheRatio = ratio;
   g_dxyCacheOk = true;
   return true;
  }

//=================================================================== module 3: index dips
void IndexEvaluate()
  {
   if(!InpIndexEnable)
      return;
   for(int k = 0; k < g_nIdx; k++)
     {
      string sym = g_idx[k];
      datetime bar = iTime(sym, PERIOD_D1, 1);
      if(bar == 0 || bar == g_idLastEval[k])
         continue;
      if(Bars(sym, PERIOD_D1) < InpID_TrendSMA + 5)
         continue;
      g_idLastEval[k] = bar;
      GlobalVariableSet(g_prefix + "ID_LAST_" + sym, (double)bar);
      g_idEntryIntent[k] = 0;
      double c = iClose(sym, PERIOD_D1, 1), h = iHigh(sym, PERIOD_D1, 1), l = iLow(sym, PERIOD_D1, 1);
      double rsi = Buf(g_hID_RSI[k], 1), sma = Buf(g_hID_SMA[k], 1), xs = Buf(g_hID_EXIT[k], 1), atr = Buf(g_hID_ATR[k], 1);
      if(!Valid(rsi) || !Valid(sma) || !Valid(xs) || !Valid(atr))
         continue;
      bool inPos = CountPositions(MOD_ID, sym) > 0;
      // exits: close above exit SMA, or held for MaxHoldDays daily bars
      if(inPos)
        {
         bool timeUp = false;
         for(int i = PositionsTotal() - 1; i >= 0; i--)
           {
            ulong tk = PositionGetTicket(i);
            if(tk == 0 || PositionGetInteger(POSITION_MAGIC) != ModuleMagic(MOD_ID) || PositionGetString(POSITION_SYMBOL) != sym)
               continue;
            int held = iBarShift(sym, PERIOD_D1, (datetime)PositionGetInteger(POSITION_TIME), false);
            if(held >= InpID_MaxHoldDays)
               timeUp = true;
           }
         if(c > xs || timeUp)
           {
            g_idExitIntent[k] = true;
            Log(StringFormat("SIGNAL;INDEX_EXIT;%s;close=%.2f;sma%d=%.2f;timeUp=%d", sym, c, InpID_ExitSMA, xs, timeUp));
           }
        }
      double ibs = (h > l) ? (c - l) / (h - l) : 1.0;
      if(rsi < InpID_RSIMax && ibs < InpID_IBSMax && c > sma && atr > 0)
        {
         if(InpID_DXYFilter && g_nFx > 0)
           {
            double ratio = 0;
            if(DXYRatio(bar, ratio) && 100.0 * ratio > InpID_DXYMaxAboveSMA)
              {
               Log(StringFormat("SKIP;INDEX_DIP;%s;dollar index %.2f%% above SMA%d", sym, 100.0 * ratio, InpID_DXYSMA));
               continue;
              }
           }
         g_idEntryIntent[k] = 1;
         g_idIntentSL[k] = InpID_SLATR * atr;
         Log(StringFormat("SIGNAL;INDEX_DIP;%s;BUY;close=%.2f;rsi=%.2f;ibs=%.3f;sma=%.2f;atr=%.2f", sym, c, rsi, ibs, sma, atr));
        }
     }
  }

void IndexExecute()
  {
   if(!InpIndexEnable)
      return;
   datetime now = NowServer();
   for(int k = 0; k < g_nIdx; k++)
     {
      string sym = g_idx[k];
      if(g_idExitIntent[k])
        {
         if(CountPositions(MOD_ID, sym) == 0)
            g_idExitIntent[k] = false;
         else if(!InRolloverBlock(now) && SymbolInfoInteger(sym, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_DISABLED)
           {
            ClosePositions(MOD_ID, sym, "exit signal");
            if(CountPositions(MOD_ID, sym) == 0)
               g_idExitIntent[k] = false;
           }
        }
      if(g_idEntryIntent[k] != 0)
        {
         if(CountPositions(MOD_ID, sym) > 0 && !g_idExitIntent[k])
           { g_idEntryIntent[k] = 0; continue; }
         if(g_idExitIntent[k] || SymbolBusyNetting(sym))
            continue;
         if(CountPositions(MOD_ID, "") >= InpID_MaxConcurrent)
           { g_idEntryIntent[k] = 0; continue; }       // correlated exposure cap
         string why = "";
         if(!CanEnter(sym, InpMaxSpreadBpsIndex, why))
            continue;
         if(OpenPosition(MOD_ID, sym, 1, g_idIntentSL[k], 0.0, g_riskID, InpIndexCommissionPerLot, "INDEX_DIP"))
            g_idEntryIntent[k] = 0;
        }
     }
  }

//=================================================================== risk bookkeeping
void UpdateRiskState()
  {
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= 0)
      return;
   if(eq > g_peak)
     {
      g_peak = eq;
      GlobalVariableSet(g_prefix + "PEAK", g_peak);
     }
   datetime srvDay = DateOf(NowServer());
   if(srvDay != g_dayStart)
     {
      g_dayStart = srvDay;
      g_dayStartEquity = eq;
     }
   if(!g_halted && InpHardStopDDPct > 0 && CurrentDDPct() >= InpHardStopDDPct)
     {
      g_halted = true;
      GlobalVariableSet(g_prefix + "HALT", 1);
      PrintFormat("SlowStrat: HARD STOP - drawdown %.2f%% >= %.2f%%. Closing all positions and halting. "
                  "Set InpResetPeakOnStart=true to resume after review.", CurrentDDPct(), InpHardStopDDPct);
      Log("HALT;drawdown hard stop");
      CloseAll("hard stop");
     }
  }

void ApplyPreset()
  {
   switch(InpPreset)
     {
      case SS_PRESET_CONSERVATIVE: g_riskGT = 0.30; g_riskGA = 0.25; g_riskID = 0.75; break;
      case SS_PRESET_BALANCED:     g_riskGT = 0.48; g_riskGA = 0.40; g_riskID = 1.20; break;
      case SS_PRESET_GROWTH:       g_riskGT = 0.60; g_riskGA = 0.50; g_riskID = 1.50; break;
      case SS_PRESET_AGGRESSIVE:   g_riskGT = 0.90; g_riskGA = 0.75; g_riskID = 2.25; break;
      default:                     g_riskGT = InpCustomGoldTrendRisk; g_riskGA = InpCustomGoldAsiaRisk; g_riskID = InpCustomIndexRisk;
     }
  }

//=================================================================== panel
void DrawPanel()
  {
   if(!InpShowPanel)
      return;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   string s = "SlowStrat v2.00  |  " + EnumToString(InpPreset) + "\n";
   s += StringFormat("Equity %.2f  peak %.2f  DD %.2f%%  brake x%.2f%s\n", eq, g_peak, CurrentDDPct(), BrakeMultiplier(),
                     g_halted ? "  ** HALTED **" : "");
   s += StringFormat("Open risk %.2f%% (cap %.1f%%)   today %.2f%%\n", OpenRiskPct(), InpMaxOpenRiskPct,
                     g_dayStartEquity > 0 ? 100.0 * (eq / g_dayStartEquity - 1) : 0.0);
   datetime srv = NowServer();
   s += StringFormat("Server %s  UTC %s  NY %s  (GMT%+d)%s\n", TimeToString(srv, TIME_MINUTES),
                     TimeToString(ServerToUTC(srv), TIME_MINUTES), TimeToString(UTCToNY(ServerToUTC(srv)), TIME_MINUTES),
                     ServerOffsetForUTC(ServerToUTC(srv)), InRolloverBlock(srv) ? "  [rollover: no entries]" : "");
   if(g_gold != "")
      s += StringFormat("Gold %s: trend %s (%d pos, risk %.2f%%)  asia %s (%d pos, risk %.2f%%)  spread %.1fbp\n", g_gold,
                        InpGoldTrendEnable ? "ON" : "off", CountPositions(MOD_GT, g_gold), g_riskGT * InpRiskMultiplier,
                        InpGoldAsiaEnable ? "ON" : "off", CountPositions(MOD_GA, g_gold), g_riskGA * InpRiskMultiplier, SpreadBps(g_gold));
   else
      s += "Gold: symbol not found\n";
   s += "Index dips (" + DoubleToString(g_riskID * InpRiskMultiplier, 2) + "% each): ";
   for(int k = 0; k < g_nIdx; k++)
      s += g_idx[k] + (CountPositions(MOD_ID, g_idx[k]) > 0 ? "[IN] " : " ");
   if(g_nIdx == 0)
      s += "no symbols found";
   if(InpID_DXYFilter && g_nFx > 0)
     {
      double r = 0;
      bool ok = DXYRatio(iTime(g_fx[0], PERIOD_D1, 0), r);
      s += ok ? StringFormat("\nDollar Index vs SMA%d: %+.2f%% (%d/6 pairs) -> index dips %s", InpID_DXYSMA, 100 * r, g_nFx,
                             100 * r > InpID_DXYMaxAboveSMA ? "BLOCKED (strong USD)" : "allowed")
                : "\nDollar Index: not enough FX history";
     }
   s += "\nHigh-impact news: " + NextNews();
   Comment(s);
  }

//=================================================================== init / events
int OnInit()
  {
   g_isTester = (bool)MQLInfoInteger(MQL_TESTER);
   g_hedging = (AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   g_prefix = "SS_" + (string)AccountInfoInteger(ACCOUNT_LOGIN) + "_" + (string)InpMagicBase + "_";
   if(g_isTester)
      g_prefix = "SST_" + (string)InpMagicBase + "_";
   ApplyPreset();
   DetectGMTOffset();
   if(!g_hedging)
      Print("SlowStrat: WARNING - netting account. Both gold modules share one XAUUSD position slot. A hedging account is recommended.");

   // gold
   if(InpGoldTrendEnable || InpGoldAsiaEnable)
     {
      if(InpGoldSymbol != "")
         g_gold = TrySymbol(InpGoldSymbol) ? InpGoldSymbol : "";
      else
        {
         string c[] = {"XAUUSD", "GOLD", "XAUUSD.", "XAUUSDm"};
         g_gold = ResolveSymbol(c);
        }
      if(g_gold == "")
         Print("SlowStrat: gold symbol not found - gold modules disabled. Set InpGoldSymbol.");
      else
        {
         g_hGT_ATR = iATR(g_gold, PERIOD_H4, InpGT_ATR);
         g_hGT_SMA = iMA(g_gold, PERIOD_D1, InpGT_TrendSMA, 0, MODE_SMA, PRICE_CLOSE);
         if(g_hGT_ATR == INVALID_HANDLE || g_hGT_SMA == INVALID_HANDLE)
            return INIT_FAILED;
        }
     }
   // indices
   g_nIdx = 0;
   if(InpIndexEnable)
     {
      string list[];
      int n = 0;
      if(InpIndexSymbols != "")
         n = StringSplit(InpIndexSymbols, ',', list);
      else
        {
         string a[] = {"US500", "SPX500", "US500Cash", "SP500", "USA500", "SPX"};
         string b[] = {"NAS100", "USTEC", "US100", "NDX100", "US100Cash", "NAS100Cash", "USTECH"};
         string d[] = {"US30", "DJ30", "WS30", "US30Cash", "DOW30", "USA30"};
         ArrayResize(list, 3);
         list[0] = ResolveSymbol(a); list[1] = ResolveSymbol(b); list[2] = ResolveSymbol(d);
         n = 3;
        }
      for(int i = 0; i < n && g_nIdx < MAX_IDX; i++)
        {
         string s = list[i];
         StringTrimLeft(s);
         StringTrimRight(s);
         if(s == "" || !TrySymbol(s))
           {
            if(s != "")
               Print("SlowStrat: index symbol not found: ", s);
            continue;
           }
         int k = g_nIdx++;
         g_idx[k] = s;
         g_hID_RSI[k] = iRSI(s, PERIOD_D1, InpID_RSIPeriod, PRICE_CLOSE);
         g_hID_SMA[k] = iMA(s, PERIOD_D1, InpID_TrendSMA, 0, MODE_SMA, PRICE_CLOSE);
         g_hID_EXIT[k] = iMA(s, PERIOD_D1, InpID_ExitSMA, 0, MODE_SMA, PRICE_CLOSE);
         g_hID_ATR[k] = iATR(s, PERIOD_D1, InpID_ATR);
         g_idLastEval[k] = (datetime)(GlobalVariableCheck(g_prefix + "ID_LAST_" + s) ? GlobalVariableGet(g_prefix + "ID_LAST_" + s) : 0);
         g_idEntryIntent[k] = 0;
         g_idExitIntent[k] = false;
        }
      if(g_nIdx == 0)
         Print("SlowStrat: no index symbols found - index module idle. Set InpIndexSymbols (e.g. US500,NAS100,US30).");
      ResolveDXYSymbols();
     }

   // persisted state
   if(InpResetPeakOnStart)
     {
      GlobalVariableDel(g_prefix + "PEAK");
      GlobalVariableDel(g_prefix + "HALT");
     }
   g_peak = GlobalVariableCheck(g_prefix + "PEAK") ? GlobalVariableGet(g_prefix + "PEAK") : AccountInfoDouble(ACCOUNT_EQUITY);
   g_halted = GlobalVariableCheck(g_prefix + "HALT") && GlobalVariableGet(g_prefix + "HALT") > 0;
   g_gtLastEval = (datetime)(GlobalVariableCheck(g_prefix + "GT_LAST") ? GlobalVariableGet(g_prefix + "GT_LAST") : 0);
   if(g_isTester)
     {
      g_peak = AccountInfoDouble(ACCOUNT_EQUITY);
      g_halted = false;
      g_gtLastEval = 0;
      for(int k = 0; k < g_nIdx; k++)
         g_idLastEval[k] = 0;
     }
   g_dayStart = DateOf(NowServer());
   g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);

   PrintFormat("SlowStrat init: gold=%s indices=%d preset=%s risk GT %.2f%% GA %.2f%% ID %.2f%% x%.2f, server GMT winter %+d%s, %s account",
               g_gold, g_nIdx, EnumToString(InpPreset), g_riskGT, g_riskGA, g_riskID, InpRiskMultiplier, g_gmtWinter,
               InpServerUsesUSDST ? " (+US DST)" : "", g_hedging ? "hedging" : "netting");
   if(!g_isTester && InpServerUsesUSDST && (g_gmtWinter != 2))
      Print("SlowStrat: NOTE - the strategy was researched on New-York-close servers (GMT+2 winter / GMT+3 summer). "
            "H4 and D1 bars on other server time zones differ; see README.");
   EventSetTimer(2);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
   if(g_hGT_ATR != INVALID_HANDLE) IndicatorRelease(g_hGT_ATR);
   if(g_hGT_SMA != INVALID_HANDLE) IndicatorRelease(g_hGT_SMA);
   for(int k = 0; k < g_nIdx; k++)
     {
      IndicatorRelease(g_hID_RSI[k]);
      IndicatorRelease(g_hID_SMA[k]);
      IndicatorRelease(g_hID_EXIT[k]);
      IndicatorRelease(g_hID_ATR[k]);
     }
  }

void Process()
  {
   datetime now = TimeCurrent();
   if(now == g_lastProcess && !g_isTester)
      return;
   g_lastProcess = now;
   UpdateRiskState();
   // 1) signal evaluation on completed bars
   GoldTrendEvaluate();
   GoldAsiaEvaluate();
   IndexEvaluate();
   // 2) exits / trailing
   GoldTrendTrail();
   // 3) entries
   if(!g_halted)
     {
      IndexExecute();
      GoldTrendExecute();
      GoldAsiaExecute();
     }
   else
      IndexExecute();   // still allows pending exit intents (entries are blocked by CanEnter)
   if(!g_isTester || MQLInfoInteger(MQL_VISUAL_MODE))
      DrawPanel();
  }

void OnTick()  { Process(); }
void OnTimer() { Process(); }

// clean up per-position state when positions close
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   long mg = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   if(mg <= InpMagicBase || mg > InpMagicBase + 3)
      return;
   long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
     {
      ulong pos = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
      double pr = HistoryDealGetDouble(trans.deal, DEAL_PROFIT) + HistoryDealGetDouble(trans.deal, DEAL_SWAP) +
                  HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
      long reason = HistoryDealGetInteger(trans.deal, DEAL_REASON);
      Log(StringFormat("DEAL_OUT;%I64d;%s;profit=%.2f;reason=%s", mg - InpMagicBase, HistoryDealGetString(trans.deal, DEAL_SYMBOL), pr,
                       reason == DEAL_REASON_SL ? "SL" : reason == DEAL_REASON_TP ? "TP" : "OTHER"));
      if(!PositionSelectByTicket(pos))
         GlobalVariableDel(GVKey(pos));
     }
  }

// custom optimisation criterion: return / max drawdown (use "Custom max" in the tester)
double OnTester()
  {
   double profit = TesterStatistics(STAT_PROFIT);
   double dd = TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   double init = TesterStatistics(STAT_INITIAL_DEPOSIT);
   if(init <= 0 || dd <= 0)
      return 0;
   return (100.0 * profit / init) / dd;
  }
//+------------------------------------------------------------------+
