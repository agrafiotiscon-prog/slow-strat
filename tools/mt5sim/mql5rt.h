// mql5rt.h -- minimal MetaTrader 5 runtime emulation for compiling and backtesting an
// MQL5 Expert Advisor that has been mechanically translated to C++ (see mql2cpp.py).
//
// Emulates: MQL5 value types (string, datetime, dynamic arrays), time functions,
// symbol / account / terminal info, bar series built on broker server time
// (M5/H1/H4/D1 aggregated from base bars), iATR / iMA(SMA) / iRSI exactly as MT5
// computes them, CTrade market orders / modify / close, positions, intrabar SL/TP
// (conservative: SL first), swaps at rollover, commissions, global variables,
// deal history and OnTradeTransaction, file logging.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <functional>
#include <initializer_list>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

typedef unsigned char uchar;
typedef unsigned short ushort;
typedef unsigned int uint;
typedef unsigned long ulong;   // 64-bit on LP64 (same as glibc's sys/types.h)
typedef long long datetime;
typedef unsigned int color;

// ---------------------------------------------------------------- string
class string {
 public:
  std::string s;
  string() {}
  string(const char* c) : s(c ? c : "") {}
  string(const std::string& x) : s(x) {}
  string(char c) : s(1, c) {}
  string(int v) : s(std::to_string(v)) {}
  string(uint v) : s(std::to_string(v)) {}
  string(long v) : s(std::to_string(v)) {}
  string(long long v) : s(std::to_string(v)) {}
  string(unsigned long v) : s(std::to_string(v)) {}
  string(unsigned long long v) : s(std::to_string(v)) {}
  string(double v) { char b[64]; snprintf(b, sizeof b, "%.8g", v); s = b; }
  const char* c_str() const { return s.c_str(); }
  string& operator+=(const string& o) { s += o.s; return *this; }
  string& operator+=(const char* o) { s += o; return *this; }
  bool operator==(const string& o) const { return s == o.s; }
  bool operator!=(const string& o) const { return s != o.s; }
  bool operator==(const char* o) const { return s == o; }
  bool operator!=(const char* o) const { return s != o; }
  bool operator<(const string& o) const { return s < o.s; }
};
inline string operator+(const string& a, const string& b) { return string(a.s + b.s); }
inline string operator+(const string& a, const char* b) { return string(a.s + b); }
inline string operator+(const char* a, const string& b) { return string(std::string(a) + b.s); }

// ---------------------------------------------------------------- dynamic arrays
template <class T>
class MqlArr {
 public:
  std::vector<T> v;
  bool series = false;
  MqlArr() {}
  MqlArr(std::initializer_list<T> il) : v(il) {}
  T& operator[](int i) { return series ? v[v.size() - 1 - i] : v[i]; }
  const T& operator[](int i) const { return series ? v[v.size() - 1 - i] : v[i]; }
};
template <class T> int ArraySize(const MqlArr<T>& a) { return (int)a.v.size(); }
template <class T> int ArrayResize(MqlArr<T>& a, int n, int reserve = 0) { a.v.resize(n); return n; }
template <class T> bool ArraySetAsSeries(MqlArr<T>& a, bool f) { a.series = f; return true; }
template <class T> void ZeroMemory(T& x) { x = T(); }

// ---------------------------------------------------------------- constants / enums
#define EMPTY_VALUE 1.7976931348623157e308
#define DBL_MAX 1.7976931348623157e308
#define INVALID_HANDLE (-1)
#define INIT_SUCCEEDED 0
#define INIT_FAILED 1
#define TIME_DATE 1
#define TIME_MINUTES 2
#define TIME_SECONDS 4
#define SEEK_END 2
#define FILE_READ 1
#define FILE_WRITE 2
#define FILE_CSV 8
#define FILE_ANSI 32
#define FILE_SHARE_READ 128

enum ENUM_TIMEFRAMES { PERIOD_CURRENT = 0, PERIOD_M1 = 1, PERIOD_M5 = 5, PERIOD_M15 = 15, PERIOD_H1 = 16385,
                       PERIOD_H4 = 16388, PERIOD_D1 = 16408 };
enum ENUM_MA_METHOD { MODE_SMA = 0, MODE_EMA = 1 };
enum ENUM_APPLIED_PRICE { PRICE_CLOSE = 1 };
enum ENUM_SERIESMODE { MODE_OPEN = 0, MODE_LOW = 1, MODE_HIGH = 2, MODE_CLOSE = 3 };
enum ENUM_ORDER_TYPE { ORDER_TYPE_BUY = 0, ORDER_TYPE_SELL = 1 };
enum ENUM_POSITION_TYPE { POSITION_TYPE_BUY = 0, POSITION_TYPE_SELL = 1 };
enum ENUM_SYMBOL_INFO_DOUBLE { SYMBOL_BID, SYMBOL_ASK, SYMBOL_POINT, SYMBOL_VOLUME_MIN, SYMBOL_VOLUME_MAX,
                               SYMBOL_VOLUME_STEP, SYMBOL_TRADE_TICK_VALUE_LOSS, SYMBOL_TRADE_TICK_SIZE };
enum ENUM_SYMBOL_INFO_INTEGER { SYMBOL_DIGITS, SYMBOL_SPREAD, SYMBOL_TRADE_STOPS_LEVEL, SYMBOL_TRADE_MODE };
enum ENUM_SYMBOL_TRADE_MODE { SYMBOL_TRADE_MODE_DISABLED = 0, SYMBOL_TRADE_MODE_LONGONLY = 1,
                              SYMBOL_TRADE_MODE_SHORTONLY = 2, SYMBOL_TRADE_MODE_CLOSEONLY = 3,
                              SYMBOL_TRADE_MODE_FULL = 4 };
enum ENUM_ACCOUNT_INFO_DOUBLE { ACCOUNT_EQUITY, ACCOUNT_BALANCE };
enum ENUM_ACCOUNT_INFO_INTEGER { ACCOUNT_MARGIN_MODE, ACCOUNT_LOGIN };
enum ENUM_ACCOUNT_MARGIN_MODE { ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0, ACCOUNT_MARGIN_MODE_EXCHANGE = 1,
                                ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2 };
enum ENUM_POSITION_PROPERTY_INTEGER { POSITION_MAGIC, POSITION_TYPE, POSITION_TIME, POSITION_TIME_MSC, POSITION_TICKET };
enum ENUM_POSITION_PROPERTY_DOUBLE { POSITION_SL, POSITION_TP, POSITION_PRICE_OPEN, POSITION_VOLUME };
enum ENUM_POSITION_PROPERTY_STRING { POSITION_SYMBOL, POSITION_COMMENT };
enum ENUM_MQL_INFO_INTEGER { MQL_TESTER, MQL_VISUAL_MODE };
enum ENUM_TERMINAL_INFO_INTEGER { TERMINAL_TRADE_ALLOWED };
enum ENUM_STATISTICS { STAT_PROFIT, STAT_EQUITY_DDREL_PERCENT, STAT_INITIAL_DEPOSIT };
enum ENUM_CALENDAR_EVENT_IMPORTANCE { CALENDAR_IMPORTANCE_NONE, CALENDAR_IMPORTANCE_LOW, CALENDAR_IMPORTANCE_MODERATE,
                                      CALENDAR_IMPORTANCE_HIGH };
enum ENUM_TRADE_TRANSACTION_TYPE { TRADE_TRANSACTION_ORDER_ADD, TRADE_TRANSACTION_DEAL_ADD };
enum ENUM_DEAL_PROPERTY_INTEGER { DEAL_MAGIC, DEAL_ENTRY, DEAL_POSITION_ID, DEAL_REASON };
enum ENUM_DEAL_PROPERTY_DOUBLE { DEAL_PROFIT, DEAL_SWAP, DEAL_COMMISSION };
enum ENUM_DEAL_PROPERTY_STRING { DEAL_SYMBOL };
enum ENUM_DEAL_ENTRY { DEAL_ENTRY_IN = 0, DEAL_ENTRY_OUT = 1, DEAL_ENTRY_INOUT = 2, DEAL_ENTRY_OUT_BY = 3 };
enum ENUM_DEAL_REASON { DEAL_REASON_CLIENT = 0, DEAL_REASON_EXPERT = 3, DEAL_REASON_SL = 4, DEAL_REASON_TP = 5 };
#define TRADE_RETCODE_REQUOTE 10004
#define TRADE_RETCODE_PLACED 10008
#define TRADE_RETCODE_DONE 10009
#define TRADE_RETCODE_DONE_PARTIAL 10010
#define TRADE_RETCODE_TIMEOUT 10012
#define TRADE_RETCODE_INVALID_STOPS 10016
#define TRADE_RETCODE_PRICE_CHANGED 10020
#define TRADE_RETCODE_PRICE_OFF 10021
#define TRADE_RETCODE_CONNECTION 10031

struct MqlDateTime { int year = 0, mon = 0, day = 0, hour = 0, min = 0, sec = 0, day_of_week = 0, day_of_year = 0; };
struct MqlRates { datetime time = 0; double open = 0, high = 0, low = 0, close = 0; long tick_volume = 0; int spread = 0; long real_volume = 0; };
struct MqlCalendarValue { ulong id = 0; ulong event_id = 0; datetime time = 0; };
struct MqlCalendarEvent { ulong id = 0; ENUM_CALENDAR_EVENT_IMPORTANCE importance = CALENDAR_IMPORTANCE_NONE; string name; };
struct MqlTradeTransaction { ulong deal = 0; ulong order = 0; string symbol; ENUM_TRADE_TRANSACTION_TYPE type = TRADE_TRANSACTION_DEAL_ADD; };
struct MqlTradeRequest { int action = 0; };
struct MqlTradeResult { uint retcode = 0; };

// ---------------------------------------------------------------- math & strings
inline double MathMax(double a, double b) { return a > b ? a : b; }
inline double MathMin(double a, double b) { return a < b ? a : b; }
inline double MathAbs(double a) { return std::fabs(a); }
inline double MathFloor(double a) { return std::floor(a); }
inline double MathRound(double a) { return std::round(a); }
inline bool MathIsValidNumber(double a) { return std::isfinite(a); }
inline double NormalizeDouble(double v, int d) { double p = std::pow(10.0, d); return std::round(v * p) / p; }
inline string DoubleToString(double v, int d = 8) { char b[64]; snprintf(b, sizeof b, "%.*f", d, v); return string(b); }
inline int StringLen(const string& s) { return (int)s.s.size(); }
inline int StringFind(const string& s, const string& f, int start = 0) { auto p = s.s.find(f.s, start); return p == std::string::npos ? -1 : (int)p; }
inline int StringTrimLeft(string& s) { size_t i = s.s.find_first_not_of(" \t\r\n"); s.s = (i == std::string::npos) ? "" : s.s.substr(i); return 0; }
inline int StringTrimRight(string& s) { size_t i = s.s.find_last_not_of(" \t\r\n"); s.s = (i == std::string::npos) ? "" : s.s.substr(0, i + 1); return 0; }
inline int StringSplit(const string& s, ushort sep, MqlArr<string>& out) {
  out.v.clear(); std::string cur;
  for (char c : s.s) { if ((ushort)c == sep) { out.v.push_back(string(cur)); cur.clear(); } else cur += c; }
  out.v.push_back(string(cur)); return (int)out.v.size();
}
template <class T> string EnumToString(T v) { return string((long long)v); }

// printf-style formatting with MQL5 extensions (%I64d / %I64u)
inline long long fmt_arg(int v) { return v; }
inline long long fmt_arg(long v) { return v; }
inline long long fmt_arg(long long v) { return v; }
inline unsigned long long fmt_arg(unsigned long v) { return v; }
inline unsigned long long fmt_arg(unsigned long long v) { return v; }
inline long long fmt_arg(uint v) { return v; }
inline long long fmt_arg(bool v) { return v; }
inline double fmt_arg(double v) { return v; }
inline const char* fmt_arg(const string& v) { return v.c_str(); }
inline const char* fmt_arg(const char* v) { return v; }
template <class E, class = typename std::enable_if<std::is_enum<E>::value>::type> long long fmt_arg(E v) { return (long long)v; }

inline std::string fix_fmt(const char* f) {
  std::string s(f), out;
  // MQL5: %I64d / %I64u ; ints are promoted to long long by fmt_arg, so %d -> %lld etc.
  for (size_t i = 0; i < s.size(); i++) {
    if (s[i] == '%' && i + 1 < s.size() && s[i + 1] == '%') { out += "%%"; i++; continue; }
    if (s[i] != '%') { out += s[i]; continue; }
    size_t j = i + 1;
    std::string spec = "%";
    while (j < s.size() && strchr("-+ #0123456789.", s[j])) spec += s[j++];
    if (s.compare(j, 3, "I64") == 0) j += 3;
    if (j < s.size()) {
      char c = s[j];
      if (c == 'd' || c == 'i') spec += "lld";
      else if (c == 'u') spec += "llu";
      else if (c == 'x' || c == 'X') { spec += "ll"; spec += c; }
      else spec += c;
    }
    out += spec; i = j;
  }
  return out;
}
template <class... A> string StringFormat(const char* f, A... a) {
  std::string ff = fix_fmt(f);
  int n = snprintf(nullptr, 0, ff.c_str(), fmt_arg(a)...);
  std::vector<char> b(n + 1);
  snprintf(b.data(), b.size(), ff.c_str(), fmt_arg(a)...);
  return string(b.data());
}
template <class... A> string StringFormat(const string& f, A... a) { return StringFormat(f.c_str(), a...); }

extern bool g_rt_quiet;
inline void rt_print(const std::string& s) { if (!g_rt_quiet) fprintf(stderr, "%s\n", s.c_str()); }
inline void to_str_cat(std::string&) {}
template <class T> std::string rt_tostr(const T& v) { return std::string(string(v).c_str()); }
inline std::string rt_tostr(const string& v) { return v.s; }
inline std::string rt_tostr(const char* v) { return v; }
template <class T, class... R> void to_str_cat(std::string& o, const T& v, const R&... r) { o += rt_tostr(v); to_str_cat(o, r...); }
template <class... A> void Print(const A&... a) { std::string o; to_str_cat(o, a...); rt_print(o); }
template <class... A> void PrintFormat(const char* f, A... a) { rt_print(StringFormat(f, a...).s); }
inline void Comment(const string&) {}
inline void Sleep(int) {}
inline void ResetLastError();
inline int GetLastError();

// ---------------------------------------------------------------- time
inline void TimeToStruct(datetime t, MqlDateTime& s) {
  time_t tt = (time_t)t; struct tm g; gmtime_r(&tt, &g);
  s.year = g.tm_year + 1900; s.mon = g.tm_mon + 1; s.day = g.tm_mday; s.hour = g.tm_hour; s.min = g.tm_min;
  s.sec = g.tm_sec; s.day_of_week = g.tm_wday; s.day_of_year = g.tm_yday;
}
inline datetime StructToTime(const MqlDateTime& s) {
  struct tm g; memset(&g, 0, sizeof g);
  g.tm_year = s.year - 1900; g.tm_mon = s.mon - 1; g.tm_mday = s.day; g.tm_hour = s.hour; g.tm_min = s.min; g.tm_sec = s.sec;
  return (datetime)timegm(&g);
}
inline string TimeToString(datetime t, int flags = TIME_DATE | TIME_MINUTES) {
  MqlDateTime s; TimeToStruct(t, s); char b[64]; std::string o;
  if (flags & TIME_DATE) { snprintf(b, sizeof b, "%04d.%02d.%02d", s.year, s.mon, s.day); o += b; }
  if (flags & (TIME_MINUTES | TIME_SECONDS)) {
    if (!o.empty()) o += " ";
    if (flags & TIME_SECONDS) snprintf(b, sizeof b, "%02d:%02d:%02d", s.hour, s.min, s.sec);
    else snprintf(b, sizeof b, "%02d:%02d", s.hour, s.min);
    o += b;
  }
  return string(o);
}
inline int PeriodSeconds(ENUM_TIMEFRAMES tf) {
  switch (tf) { case PERIOD_M1: return 60; case PERIOD_M5: return 300; case PERIOD_M15: return 900; case PERIOD_H1: return 3600;
    case PERIOD_H4: return 14400; case PERIOD_D1: return 86400; default: return 60; }
}

// ================================================================= market simulation state
struct Bar { datetime t; double o, h, l, c, sp; };  // server time, bid OHLC, spread (price)

struct SymbolSpec {
  std::string name; double contract = 1, point = 0.01, vmin = 0.01, vmax = 1000, vstep = 0.01; int digits = 2;
  double commission_side = 0;   // per lot per side, account currency
  double slip = 0;              // price units, market & stop fills
  double swap_long = 0, swap_short = 0;  // annual rate on notional (negative = cost)
  int triple_dow = 3;           // server weekday on which rollover charges 3 nights (3 = Wed)
};

struct TFSeries {
  std::vector<Bar> bars;          // aggregated bars (server time)
  std::vector<int> base_to_tf;    // base index -> tf bar index
  std::vector<int> first_base;    // tf bar -> first base index
  std::vector<double> atr[64], sma[512], rsi[64];  // cached by period (index = period)
};

struct SymbolData {
  SymbolSpec spec;
  std::vector<Bar> base; int base_tf = PERIOD_M5;
  std::map<int, TFSeries> tf;
  int cur = -1;              // current (forming) base bar
  double bid = 0, ask = 0;
};

struct Position {
  ulong ticket; std::string sym; int type; double vol, open, sl, tp; datetime time; long long magic;
  double swap = 0, commission = 0; std::string comment;
};

struct Deal {
  ulong ticket; std::string sym; long long magic; int entry; ulong pos_id; double profit, swap, commission; int reason;
  datetime time; int type; double vol, price;
};

struct TradeRecord {  // closed trade summary for analysis
  ulong ticket; std::string sym; long long magic; int dir; double vol, open, close, sl0; datetime t_open, t_close;
  double pnl; std::string reason;
};

struct Runtime {
  std::map<std::string, SymbolData> syms;
  datetime now = 0;
  double balance = 0;
  std::vector<Position> pos;
  std::vector<Deal> deals;
  std::vector<TradeRecord> trades;
  std::map<ulong, double> sl0;  // initial stop distance per position (for analysis)
  ulong next_ticket = 1000;
  std::map<std::string, double> gv;
  std::vector<MqlTradeTransaction> pending_tx;
  int last_error = 0;
  std::string file_dir = ".";
  std::map<int, std::unique_ptr<std::ofstream>> files; int next_file = 1;
  // indicator handles
  struct Ind { std::string sym; int tf; int kind; int period; };  // kind 0 atr 1 sma 2 rsi
  std::vector<Ind> inds;
  double peak_equity = 0, max_dd = 0, init_deposit = 0;
};
extern Runtime RT;

inline void ResetLastError() { RT.last_error = 0; }
inline int GetLastError() { return RT.last_error; }

// ---------------------------------------------------------------- series helpers
inline int tf_key(ENUM_TIMEFRAMES tf) { return tf == PERIOD_CURRENT ? PERIOD_M5 : (int)tf; }
inline TFSeries* series(const string& sym, ENUM_TIMEFRAMES tf) {
  auto it = RT.syms.find(sym.s);
  if (it == RT.syms.end() || it->second.cur < 0) return nullptr;
  auto jt = it->second.tf.find(tf_key(tf));
  if (jt == it->second.tf.end()) return nullptr;
  return &jt->second;
}
inline int cur_tf_index(const string& sym, ENUM_TIMEFRAMES tf) {
  TFSeries* s = series(sym, tf); if (!s) return -1;
  return s->base_to_tf[RT.syms[sym.s].cur];
}
// bar at shift (shift 0 = forming bar: only data up to the current base bar's OPEN is visible)
inline bool bar_at(const string& sym, ENUM_TIMEFRAMES tf, int shift, Bar& out) {
  TFSeries* s = series(sym, tf); if (!s) return false;
  SymbolData& sd = RT.syms[sym.s];
  int ci = s->base_to_tf[sd.cur]; int idx = ci - shift;
  if (idx < 0 || shift < 0) return false;
  if (shift > 0) { out = s->bars[idx]; return true; }
  Bar b = s->bars[idx]; const Bar& cb = sd.base[sd.cur];
  double h = cb.o, l = cb.o;
  for (int k = s->first_base[idx]; k < sd.cur; k++) { h = std::max(h, sd.base[k].h); l = std::min(l, sd.base[k].l); }
  b.h = h; b.l = l; b.c = cb.o; out = b; return true;
}
inline datetime iTime(const string& sym, ENUM_TIMEFRAMES tf, int shift) { Bar b; return bar_at(sym, tf, shift, b) ? b.t : 0; }
inline double iOpen(const string& sym, ENUM_TIMEFRAMES tf, int shift) { Bar b; return bar_at(sym, tf, shift, b) ? b.o : 0; }
inline double iHigh(const string& sym, ENUM_TIMEFRAMES tf, int shift) { Bar b; return bar_at(sym, tf, shift, b) ? b.h : 0; }
inline double iLow(const string& sym, ENUM_TIMEFRAMES tf, int shift) { Bar b; return bar_at(sym, tf, shift, b) ? b.l : 0; }
inline double iClose(const string& sym, ENUM_TIMEFRAMES tf, int shift) { Bar b; return bar_at(sym, tf, shift, b) ? b.c : 0; }
inline int Bars(const string& sym, ENUM_TIMEFRAMES tf) { int c = cur_tf_index(sym, tf); return c < 0 ? 0 : c + 1; }
inline int iBarShift(const string& sym, ENUM_TIMEFRAMES tf, datetime t, bool exact = false) {
  TFSeries* s = series(sym, tf); if (!s) return -1;
  int ci = cur_tf_index(sym, tf);
  // last bar with open <= t among bars[0..ci]
  int lo = 0, hi = ci, ans = -1;
  while (lo <= hi) { int m = (lo + hi) / 2; if (s->bars[m].t <= t) { ans = m; lo = m + 1; } else hi = m - 1; }
  if (ans < 0) return -1;
  if (exact && s->bars[ans].t != t) return -1;
  return ci - ans;
}
inline int iHighest(const string& sym, ENUM_TIMEFRAMES tf, ENUM_SERIESMODE mode, int count, int start) {
  int best = -1; double bv = -1e300;
  for (int sh = start; sh < start + count; sh++) {
    Bar b; if (!bar_at(sym, tf, sh, b)) break;
    double v = mode == MODE_HIGH ? b.h : mode == MODE_LOW ? b.l : mode == MODE_OPEN ? b.o : b.c;
    if (v > bv) { bv = v; best = sh; }
  }
  return best;
}
inline int iLowest(const string& sym, ENUM_TIMEFRAMES tf, ENUM_SERIESMODE mode, int count, int start) {
  int best = -1; double bv = 1e300;
  for (int sh = start; sh < start + count; sh++) {
    Bar b; if (!bar_at(sym, tf, sh, b)) break;
    double v = mode == MODE_HIGH ? b.h : mode == MODE_LOW ? b.l : mode == MODE_OPEN ? b.o : b.c;
    if (v < bv) { bv = v; best = sh; }
  }
  return best;
}
inline MqlRates to_rates(const Bar& b) { MqlRates r; r.time = b.t; r.open = b.o; r.high = b.h; r.low = b.l; r.close = b.c; return r; }
inline int CopyRates(const string& sym, ENUM_TIMEFRAMES tf, int start_pos, int count, MqlArr<MqlRates>& out) {
  out.v.clear(); int ci = cur_tf_index(sym, tf); if (ci < 0) { RT.last_error = 4401; return -1; }
  int first = std::max(0, ci - start_pos - count + 1), last = ci - start_pos;
  for (int i = first; i <= last; i++) { Bar b; bar_at(sym, tf, ci - i, b); out.v.push_back(to_rates(b)); }
  return (int)out.v.size();
}
inline int CopyRates(const string& sym, ENUM_TIMEFRAMES tf, datetime from, datetime to, MqlArr<MqlRates>& out) {
  out.v.clear(); TFSeries* s = series(sym, tf); if (!s) { RT.last_error = 4401; return -1; }
  int ci = cur_tf_index(sym, tf);
  for (int i = 0; i <= ci; i++) {
    if (s->bars[i].t < from || s->bars[i].t > to) continue;
    Bar b; bar_at(sym, tf, ci - i, b); out.v.push_back(to_rates(b));
  }
  return (int)out.v.size();
}

// ---------------------------------------------------------------- indicators (MT5 formulas)
inline std::vector<double>& ind_series(const string& sym, int tf, int kind, int period) {
  TFSeries& s = RT.syms[sym.s].tf[tf];
  std::vector<double>* v = kind == 0 ? &s.atr[period] : kind == 1 ? &s.sma[period] : &s.rsi[period];
  if (!v->empty()) return *v;
  int n = (int)s.bars.size(); v->assign(n, EMPTY_VALUE);
  if (kind == 0) {  // iATR: simple moving average of true range
    std::vector<double> tr(n);
    for (int i = 0; i < n; i++) {
      double h = s.bars[i].h, l = s.bars[i].l;
      tr[i] = i == 0 ? h - l : std::max(h - l, std::max(std::fabs(h - s.bars[i - 1].c), std::fabs(l - s.bars[i - 1].c)));
    }
    double sum = 0;
    for (int i = 0; i < n; i++) { sum += tr[i]; if (i >= period) sum -= tr[i - period]; if (i >= period - 1) (*v)[i] = sum / period; }
  } else if (kind == 1) {
    double sum = 0;
    for (int i = 0; i < n; i++) { sum += s.bars[i].c; if (i >= period) sum -= s.bars[i - period].c; if (i >= period - 1) (*v)[i] = sum / period; }
  } else {  // iRSI: Wilder smoothing seeded with a simple average
    if (n > period) {
      double up = 0, dn = 0;
      for (int i = 1; i <= period; i++) { double d = s.bars[i].c - s.bars[i - 1].c; if (d > 0) up += d; else dn -= d; }
      up /= period; dn /= period;
      (*v)[period] = dn == 0 ? 100.0 : 100.0 - 100.0 / (1.0 + up / dn);
      for (int i = period + 1; i < n; i++) {
        double d = s.bars[i].c - s.bars[i - 1].c;
        up = (up * (period - 1) + (d > 0 ? d : 0)) / period; dn = (dn * (period - 1) + (d < 0 ? -d : 0)) / period;
        (*v)[i] = dn == 0 ? 100.0 : 100.0 - 100.0 / (1.0 + up / dn);
      }
    }
  }
  return *v;
}
inline int add_ind(const string& sym, ENUM_TIMEFRAMES tf, int kind, int period) {
  if (RT.syms.find(sym.s) == RT.syms.end() || RT.syms[sym.s].tf.find(tf_key(tf)) == RT.syms[sym.s].tf.end()) return INVALID_HANDLE;
  RT.inds.push_back({sym.s, tf_key(tf), kind, period}); return (int)RT.inds.size() - 1;
}
inline int iATR(const string& sym, ENUM_TIMEFRAMES tf, int period) { return add_ind(sym, tf, 0, period); }
inline int iMA(const string& sym, ENUM_TIMEFRAMES tf, int period, int shift, ENUM_MA_METHOD m, ENUM_APPLIED_PRICE p) {
  if (m != MODE_SMA || shift != 0) return INVALID_HANDLE;
  return add_ind(sym, tf, 1, period);
}
inline int iRSI(const string& sym, ENUM_TIMEFRAMES tf, int period, ENUM_APPLIED_PRICE p) { return add_ind(sym, tf, 2, period); }
inline bool IndicatorRelease(int h) { return true; }
inline int copy_buffer_impl(int h, int buffer, int shift, int count, double* dst) {
  if (h < 0 || h >= (int)RT.inds.size()) return -1;
  auto& d = RT.inds[h];
  string sym(d.sym);
  int ci = cur_tf_index(sym, (ENUM_TIMEFRAMES)d.tf); if (ci < 0) return -1;
  std::vector<double>& v = ind_series(sym, d.tf, d.kind, d.period);
  for (int k = 0; k < count; k++) {
    int sh = shift + count - 1 - k; int idx = ci - sh;
    if (idx < 0) return -1;
    dst[k] = (sh == 0) ? EMPTY_VALUE : v[idx];   // forming bar: not provided (EA must not use it)
  }
  return count;
}
template <size_t N> int CopyBuffer(int h, int buffer, int shift, int count, double (&dst)[N]) {
  if ((size_t)count > N) return -1; return copy_buffer_impl(h, buffer, shift, count, dst);
}
inline int CopyBuffer(int h, int buffer, int shift, int count, MqlArr<double>& dst) {
  dst.v.resize(count); return copy_buffer_impl(h, buffer, shift, count, dst.v.data());
}

// ---------------------------------------------------------------- symbols / account / terminal
inline bool SymbolExist(const string& name, bool& custom) { custom = false; return RT.syms.count(name.s) > 0; }
inline bool SymbolSelect(const string& name, bool) { return RT.syms.count(name.s) > 0; }
inline int SymbolsTotal(bool) { return (int)RT.syms.size(); }
inline string SymbolName(int i, bool) { int k = 0; for (auto& p : RT.syms) if (k++ == i) return string(p.first); return string(""); }
inline double SymbolInfoDouble(const string& sym, ENUM_SYMBOL_INFO_DOUBLE p) {
  auto it = RT.syms.find(sym.s); if (it == RT.syms.end()) return 0; SymbolData& s = it->second;
  switch (p) { case SYMBOL_BID: return s.bid; case SYMBOL_ASK: return s.ask; case SYMBOL_POINT: return s.spec.point;
    case SYMBOL_VOLUME_MIN: return s.spec.vmin; case SYMBOL_VOLUME_MAX: return s.spec.vmax; case SYMBOL_VOLUME_STEP: return s.spec.vstep;
    case SYMBOL_TRADE_TICK_SIZE: return s.spec.point; case SYMBOL_TRADE_TICK_VALUE_LOSS: return s.spec.point * s.spec.contract; }
  return 0;
}
inline long long SymbolInfoInteger(const string& sym, ENUM_SYMBOL_INFO_INTEGER p) {
  auto it = RT.syms.find(sym.s); if (it == RT.syms.end()) return 0; SymbolData& s = it->second;
  switch (p) { case SYMBOL_DIGITS: return s.spec.digits; case SYMBOL_SPREAD: return (long long)std::llround((s.ask - s.bid) / s.spec.point);
    case SYMBOL_TRADE_STOPS_LEVEL: return 0; case SYMBOL_TRADE_MODE: return s.cur >= 0 ? SYMBOL_TRADE_MODE_FULL : SYMBOL_TRADE_MODE_DISABLED; }
  return 0;
}
double rt_equity();
inline double AccountInfoDouble(ENUM_ACCOUNT_INFO_DOUBLE p) { return p == ACCOUNT_EQUITY ? rt_equity() : RT.balance; }
inline long long AccountInfoInteger(ENUM_ACCOUNT_INFO_INTEGER p) { return p == ACCOUNT_MARGIN_MODE ? ACCOUNT_MARGIN_MODE_RETAIL_HEDGING : 1; }
inline long long MQLInfoInteger(ENUM_MQL_INFO_INTEGER p) { return p == MQL_TESTER ? 1 : 0; }
inline long long TerminalInfoInteger(ENUM_TERMINAL_INFO_INTEGER) { return 1; }
inline datetime TimeCurrent() { return RT.now; }
inline datetime TimeTradeServer() { return RT.now; }
inline datetime TimeGMT() { return 0; }
inline bool EventSetTimer(int) { return true; }
inline void EventKillTimer() {}
inline double TesterStatistics(ENUM_STATISTICS s) {
  if (s == STAT_PROFIT) return rt_equity() - RT.init_deposit;
  if (s == STAT_EQUITY_DDREL_PERCENT) return RT.max_dd * 100;
  return RT.init_deposit;
}
// calendar: not available in the tester
inline int CalendarValueHistory(MqlArr<MqlCalendarValue>& v, datetime, datetime = 0, const char* = nullptr, const string& = string()) { v.v.clear(); RT.last_error = 5400; return -1; }
inline bool CalendarEventById(ulong, MqlCalendarEvent&) { return false; }

// ---------------------------------------------------------------- global variables & files
inline datetime GlobalVariableSet(const string& n, double v) { RT.gv[n.s] = v; return RT.now; }
inline double GlobalVariableGet(const string& n) { auto it = RT.gv.find(n.s); return it == RT.gv.end() ? 0 : it->second; }
inline bool GlobalVariableCheck(const string& n) { return RT.gv.count(n.s) > 0; }
inline bool GlobalVariableDel(const string& n) { return RT.gv.erase(n.s) > 0; }
inline int FileOpen(const string& name, int, ushort = ';') {
  auto f = std::make_unique<std::ofstream>(RT.file_dir + "/" + name.s, std::ios::app);
  if (!f->good()) return INVALID_HANDLE;
  int h = RT.next_file++; RT.files[h] = std::move(f); return h;
}
inline bool FileSeek(int, long, int) { return true; }
template <class... A> uint FileWrite(int h, const A&... a) {
  auto it = RT.files.find(h); if (it == RT.files.end()) return 0;
  std::vector<std::string> parts = {rt_tostr(a)...}; std::string o;
  for (size_t i = 0; i < parts.size(); i++) { if (i) o += ";"; o += parts[i]; }
  *it->second << o << "\n"; return (uint)o.size();
}
inline void FileClose(int h) { RT.files.erase(h); }

// ---------------------------------------------------------------- positions
inline Position* rt_selected = nullptr;
inline int PositionsTotal() { return (int)RT.pos.size(); }
inline ulong PositionGetTicket(int i) { if (i < 0 || i >= (int)RT.pos.size()) return 0; rt_selected = &RT.pos[i]; return RT.pos[i].ticket; }
inline bool PositionSelectByTicket(ulong t) { for (auto& p : RT.pos) if (p.ticket == t) { rt_selected = &p; return true; } return false; }
inline bool PositionSelect(const string& sym) { for (auto& p : RT.pos) if (p.sym == sym.s) { rt_selected = &p; return true; } return false; }
inline long long PositionGetInteger(ENUM_POSITION_PROPERTY_INTEGER p) {
  if (!rt_selected) return 0;
  switch (p) { case POSITION_MAGIC: return rt_selected->magic; case POSITION_TYPE: return rt_selected->type;
    case POSITION_TIME: return rt_selected->time; case POSITION_TIME_MSC: return rt_selected->time * 1000; case POSITION_TICKET: return rt_selected->ticket; }
  return 0;
}
inline double PositionGetDouble(ENUM_POSITION_PROPERTY_DOUBLE p) {
  if (!rt_selected) return 0;
  switch (p) { case POSITION_SL: return rt_selected->sl; case POSITION_TP: return rt_selected->tp;
    case POSITION_PRICE_OPEN: return rt_selected->open; case POSITION_VOLUME: return rt_selected->vol; }
  return 0;
}
inline string PositionGetString(ENUM_POSITION_PROPERTY_STRING p) {
  if (!rt_selected) return string(""); return p == POSITION_SYMBOL ? string(rt_selected->sym) : string(rt_selected->comment);
}
inline bool OrderCalcProfit(ENUM_ORDER_TYPE t, const string& sym, double vol, double open, double close, double& profit) {
  auto it = RT.syms.find(sym.s); if (it == RT.syms.end()) return false;
  profit = (close - open) * (t == ORDER_TYPE_BUY ? 1 : -1) * vol * it->second.spec.contract; return true;
}

// deal history
inline Deal* rt_deal = nullptr;
inline bool HistoryDealSelect(ulong t) { for (auto& d : RT.deals) if (d.ticket == t) { rt_deal = &d; return true; } return false; }
inline long long HistoryDealGetInteger(ulong t, ENUM_DEAL_PROPERTY_INTEGER p) {
  if (!HistoryDealSelect(t)) return 0;
  switch (p) { case DEAL_MAGIC: return rt_deal->magic; case DEAL_ENTRY: return rt_deal->entry; case DEAL_POSITION_ID: return rt_deal->pos_id;
    case DEAL_REASON: return rt_deal->reason; }
  return 0;
}
inline double HistoryDealGetDouble(ulong t, ENUM_DEAL_PROPERTY_DOUBLE p) {
  if (!HistoryDealSelect(t)) return 0;
  return p == DEAL_PROFIT ? rt_deal->profit : p == DEAL_SWAP ? rt_deal->swap : rt_deal->commission;
}
inline string HistoryDealGetString(ulong t, ENUM_DEAL_PROPERTY_STRING) { return HistoryDealSelect(t) ? string(rt_deal->sym) : string(""); }

// core fill / close used by CTrade and by the stop engine
void rt_close_position(size_t idx, double price, int reason);
bool rt_open_position(const std::string& sym, int type, double vol, double sl, double tp, long long magic,
                      const std::string& cmt, double& fill, ulong& ticket, uint& retcode);

class CTrade {
  long long magic_ = 0; ulong dev_ = 10; uint rc_ = 0; double price_ = 0; ulong order_ = 0;
 public:
  void SetExpertMagicNumber(long long m) { magic_ = m; }
  void SetDeviationInPoints(ulong d) { dev_ = d; }
  bool SetTypeFillingBySymbol(const string&) { return true; }
  bool Buy(double vol, const string& sym, double price = 0, double sl = 0, double tp = 0, const string& cmt = string("")) {
    return rt_open_position(sym.s, 0, vol, sl, tp, magic_, cmt.s, price_, order_, rc_);
  }
  bool Sell(double vol, const string& sym, double price = 0, double sl = 0, double tp = 0, const string& cmt = string("")) {
    return rt_open_position(sym.s, 1, vol, sl, tp, magic_, cmt.s, price_, order_, rc_);
  }
  bool PositionModify(ulong ticket, double sl, double tp) {
    for (auto& p : RT.pos) if (p.ticket == ticket) {
      SymbolData& s = RT.syms[p.sym];
      // server-side validation: stops must be on the correct side of the current price
      if (p.type == 0 && ((sl > 0 && sl >= s.bid) || (tp > 0 && tp <= s.bid))) { rc_ = TRADE_RETCODE_INVALID_STOPS; return false; }
      if (p.type == 1 && ((sl > 0 && sl <= s.ask) || (tp > 0 && tp >= s.ask))) { rc_ = TRADE_RETCODE_INVALID_STOPS; return false; }
      p.sl = sl; p.tp = tp; rc_ = TRADE_RETCODE_DONE; return true;
    }
    rc_ = 10013; return false;
  }
  bool PositionClose(ulong ticket, ulong deviation = 0) {
    for (size_t i = 0; i < RT.pos.size(); i++) if (RT.pos[i].ticket == ticket) {
      SymbolData& s = RT.syms[RT.pos[i].sym];
      double px = RT.pos[i].type == 0 ? s.bid - s.spec.slip : s.ask + s.spec.slip;
      rt_close_position(i, px, DEAL_REASON_EXPERT); rc_ = TRADE_RETCODE_DONE; return true;
    }
    rc_ = 10013; return false;
  }
  uint ResultRetcode() const { return rc_; }
  string ResultRetcodeDescription() const { return string((long long)rc_); }
  double ResultPrice() const { return price_; }
  ulong ResultOrder() const { return order_; }
  ulong ResultDeal() const { return order_; }
};
