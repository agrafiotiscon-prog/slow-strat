// sim.cpp -- run a translated MQL5 EA (ea_translated.cpp) through historical bars.
//
// usage: sim DATA_DIR OUT_DIR [Input=Value ...] [--start=YYYY-MM-DD] [--end=YYYY-MM-DD] [--deposit=N]
//
// Each step is the OPEN of a base bar (gold M5 / index H1-or-D1) in broker server time:
//   1. prices = bar open (bid), ask = bid + modelled spread; swaps charged when the server day changes
//   2. EA OnTick()  (evaluates completed bars, trails, enters/exits at market)
//   3. stops/targets checked against the bar's range (SL first if both are touched; gaps fill at the open)
#include "mql5rt.h"
bool g_rt_quiet = true;
Runtime RT;
#include "ea_translated.cpp"

#include <sys/stat.h>

static std::map<std::string, double> g_slip;

static std::vector<Bar> load_bin(const std::string& path) {
  std::vector<Bar> v;
  FILE* f = fopen(path.c_str(), "rb");
  if (!f) { fprintf(stderr, "cannot open %s\n", path.c_str()); return v; }
  long long n = 0;
  if (fread(&n, 8, 1, f) != 1) { fclose(f); return v; }
  struct Rec { long long t; double o, h, l, c, sp; };
  std::vector<Rec> r(n);
  size_t got = fread(r.data(), sizeof(Rec), n, f);
  fclose(f);
  v.reserve(got);
  for (size_t i = 0; i < got; i++) v.push_back({r[i].t, r[i].o, r[i].h, r[i].l, r[i].c, r[i].sp});
  return v;
}

static void build_tf(SymbolData& s, int tf, int secs) {
  TFSeries ts;
  ts.base_to_tf.resize(s.base.size());
  for (size_t i = 0; i < s.base.size(); i++) {
    const Bar& b = s.base[i];
    datetime open = b.t - (b.t % secs);
    if (ts.bars.empty() || ts.bars.back().t != open) {
      ts.bars.push_back({open, b.o, b.h, b.l, b.c, b.sp});
      ts.first_base.push_back((int)i);
    } else {
      Bar& a = ts.bars.back();
      a.h = std::max(a.h, b.h); a.l = std::min(a.l, b.l); a.c = b.c;
    }
    ts.base_to_tf[i] = (int)ts.bars.size() - 1;
  }
  s.tf[tf] = std::move(ts);
}

// ------------------------------------------------------------------ account mechanics
double rt_equity() {
  double eq = RT.balance;
  for (auto& p : RT.pos) {
    SymbolData& s = RT.syms[p.sym];
    double px = p.type == 0 ? s.bid : s.ask;
    eq += (px - p.open) * (p.type == 0 ? 1 : -1) * p.vol * s.spec.contract + p.swap - 2 * s.spec.commission_side * p.vol;
  }
  return eq;
}

static void queue_tx(ulong deal) { MqlTradeTransaction t; t.deal = deal; t.type = TRADE_TRANSACTION_DEAL_ADD; RT.pending_tx.push_back(t); }

bool rt_open_position(const std::string& sym, int type, double vol, double sl, double tp, long long magic,
                      const std::string& cmt, double& fill, ulong& ticket, uint& retcode) {
  auto it = RT.syms.find(sym);
  if (it == RT.syms.end() || it->second.cur < 0) { retcode = 10018; return false; }
  SymbolData& s = it->second;
  if (vol < s.spec.vmin - 1e-12) { retcode = 10014; return false; }
  double px = type == 0 ? s.ask + s.spec.slip : s.bid - s.spec.slip;
  if (type == 0 && ((sl > 0 && sl >= s.bid) || (tp > 0 && tp <= s.ask))) { retcode = TRADE_RETCODE_INVALID_STOPS; return false; }
  if (type == 1 && ((sl > 0 && sl <= s.ask) || (tp > 0 && tp >= s.bid))) { retcode = TRADE_RETCODE_INVALID_STOPS; return false; }
  Position p;
  p.ticket = ++RT.next_ticket; p.sym = sym; p.type = type; p.vol = vol; p.open = px; p.sl = sl; p.tp = tp;
  p.time = RT.now; p.magic = magic; p.comment = cmt;
  RT.pos.push_back(p);
  RT.sl0[p.ticket] = sl > 0 ? std::fabs(px - sl) : 0;
  Deal d{++RT.next_ticket, sym, magic, DEAL_ENTRY_IN, p.ticket, 0, 0, -s.spec.commission_side * vol, DEAL_REASON_EXPERT, RT.now, type, vol, px};
  RT.deals.push_back(d);
  queue_tx(d.ticket);
  fill = px; ticket = p.ticket; retcode = TRADE_RETCODE_DONE;
  return true;
}

void rt_close_position(size_t idx, double price, int reason) {
  Position p = RT.pos[idx];
  SymbolData& s = RT.syms[p.sym];
  double gross = (price - p.open) * (p.type == 0 ? 1 : -1) * p.vol * s.spec.contract;
  double comm = -2 * s.spec.commission_side * p.vol;
  RT.balance += gross + p.swap + comm;
  Deal d{++RT.next_ticket, p.sym, p.magic, DEAL_ENTRY_OUT, p.ticket, gross, p.swap, -s.spec.commission_side * p.vol, reason, RT.now,
         1 - p.type, p.vol, price};
  RT.deals.push_back(d);
  TradeRecord tr{p.ticket, p.sym, p.magic, p.type == 0 ? 1 : -1, p.vol, p.open, price, RT.sl0[p.ticket], p.time, RT.now,
                 gross + p.swap + comm, reason == DEAL_REASON_SL ? "SL" : reason == DEAL_REASON_TP ? "TP" : "EXPERT"};
  RT.trades.push_back(tr);
  RT.pos.erase(RT.pos.begin() + idx);
  queue_tx(d.ticket);
}

static void flush_tx() {
  auto q = RT.pending_tx; RT.pending_tx.clear();
  MqlTradeRequest rq; MqlTradeResult rs;
  for (auto& t : q) OnTradeTransaction(t, rq, rs);
}

// intrabar stop/target processing for positions on `sym` using base bar b (bid OHLC + spread)
static void process_stops(const std::string& sym, const Bar& b) {
  SymbolData& s = RT.syms[sym];
  for (size_t i = 0; i < RT.pos.size();) {
    Position& p = RT.pos[i];
    if (p.sym != sym) { i++; continue; }
    bool hit = false; double xp = 0; int reason = DEAL_REASON_SL;
    if (p.type == 0) {
      bool slh = p.sl > 0 && b.l <= p.sl, tph = p.tp > 0 && b.h >= p.tp;
      if (slh) { hit = true; xp = std::min(b.o, p.sl) - s.spec.slip; if (tph && b.o >= p.tp) { xp = b.o; reason = DEAL_REASON_TP; } }
      else if (tph) { hit = true; xp = std::max(b.o, p.tp); reason = DEAL_REASON_TP; }
    } else {
      double ah = b.h + b.sp, al = b.l + b.sp, ao = b.o + b.sp;
      bool slh = p.sl > 0 && ah >= p.sl, tph = p.tp > 0 && al <= p.tp;
      if (slh) { hit = true; xp = std::max(ao, p.sl) + s.spec.slip; if (tph && ao <= p.tp) { xp = ao; reason = DEAL_REASON_TP; } }
      else if (tph) { hit = true; xp = std::min(ao, p.tp); reason = DEAL_REASON_TP; }
    }
    if (hit) rt_close_position(i, xp, reason); else i++;
  }
}

static int weekday(datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.day_of_week; }

int main(int argc, char** argv) {
  if (argc < 3) { fprintf(stderr, "usage: sim DATA_DIR OUT_DIR [Input=Value ...]\n"); return 1; }
  std::string data = argv[1], out = argv[2];
  mkdir(out.c_str(), 0755);
  RT.file_dir = out;
  remove((out + "/SlowStrat_log.csv").c_str());
  double deposit = 10000, spread_mult = 1.0, slip_mult = 1.0;
  datetime t_start = 0, t_end = (datetime)4e9;
  for (int a = 3; a < argc; a++) {
    std::string kv = argv[a];
    auto eq = kv.find('=');
    if (eq == std::string::npos) continue;
    std::string k = kv.substr(0, eq), v = kv.substr(eq + 1);
    if (k == "--deposit") deposit = atof(v.c_str());
    else if (k == "--spread_mult") spread_mult = atof(v.c_str());
    else if (k == "--slip_mult") slip_mult = atof(v.c_str());
    else if (k == "--start" || k == "--end") {
      MqlDateTime s; s.year = atoi(v.substr(0, 4).c_str()); s.mon = atoi(v.substr(5, 2).c_str()); s.day = atoi(v.substr(8, 2).c_str());
      (k == "--start" ? t_start : t_end) = StructToTime(s);
    } else if (k == "--verbose") g_rt_quiet = v == "0";
    else if (!rt_set_input(k, v)) { fprintf(stderr, "unknown input %s\n", k.c_str()); return 1; }
  }
  // slippage per symbol (research values)
  { std::ifstream f(data + "/slip.txt"); std::string n; double v; while (f >> n >> v) g_slip[n] = v; }
  struct Spec { const char* name; double contract, point, vmin, vstep, vmax; int digits; double comm, swl, sws; };
  Spec specs[] = {{"XAUUSD", 100, 0.01, 0.01, 0.01, 100, 2, 3.5, -0.055, -0.01},
                  {"US500", 1, 0.01, 0.01, 0.01, 10000, 2, 0.0, -0.07, -0.02},
                  {"NAS100", 1, 0.01, 0.01, 0.01, 10000, 2, 0.0, -0.07, -0.02},
                  {"US30", 1, 0.01, 0.01, 0.01, 10000, 2, 0.0, -0.07, -0.02},
                  // FX pairs: read only (Dollar Index filter), daily bars from official noon rates
                  {"EURUSD", 100000, 0.00001, 0.01, 0.01, 100, 5, 0, 0, 0}, {"USDJPY", 100000, 0.001, 0.01, 0.01, 100, 3, 0, 0, 0},
                  {"GBPUSD", 100000, 0.00001, 0.01, 0.01, 100, 5, 0, 0, 0}, {"USDCAD", 100000, 0.00001, 0.01, 0.01, 100, 5, 0, 0, 0},
                  {"USDSEK", 100000, 0.00001, 0.01, 0.01, 100, 5, 0, 0, 0}, {"USDCHF", 100000, 0.00001, 0.01, 0.01, 100, 5, 0, 0, 0}};
  for (auto& sp : specs) {
    std::vector<Bar> b = load_bin(data + "/" + sp.name + ".bin");
    if (b.empty()) continue;
    SymbolData& s = RT.syms[sp.name];
    s.spec.name = sp.name; s.spec.contract = sp.contract; s.spec.point = sp.point; s.spec.vmin = sp.vmin; s.spec.vstep = sp.vstep;
    s.spec.vmax = sp.vmax; s.spec.digits = sp.digits; s.spec.commission_side = sp.comm; s.spec.swap_long = sp.swl; s.spec.swap_short = sp.sws;
    s.spec.slip = (g_slip.count(sp.name) ? g_slip[sp.name] : 0) * slip_mult;
    for (auto& x : b) x.sp *= spread_mult;
    s.base = std::move(b);
    build_tf(s, PERIOD_M5, 300); build_tf(s, PERIOD_H1, 3600); build_tf(s, PERIOD_H4, 14400); build_tf(s, PERIOD_D1, 86400);
    if (std::string(sp.name) != "XAUUSD") s.tf.erase(PERIOD_M5);   // index data is H1/D1 only
  }
  // global timeline
  std::vector<datetime> steps;
  for (auto& kv : RT.syms) for (auto& b : kv.second.base) steps.push_back(b.t);
  std::sort(steps.begin(), steps.end());
  steps.erase(std::unique(steps.begin(), steps.end()), steps.end());
  // warm-up: position all symbols at t_start without trading (EA starts at t_start)
  RT.balance = deposit; RT.init_deposit = deposit; RT.peak_equity = deposit;
  bool inited = false;
  datetime prev_day = -1;
  std::map<std::string, size_t> nxt;
  for (auto& kv : RT.syms) nxt[kv.first] = 0;
  std::ofstream eqf(out + "/equity.csv");
  eqf << "time,equity,balance,worst,best\n";
  datetime last_eq_day = -1;
  double prev_close = deposit;
  double worst_today = 1e300, best_today = -1e300;
  for (datetime T : steps) {
    if (T > t_end) break;
    RT.now = T;
    std::vector<std::string> fresh;
    for (auto& kv : RT.syms) {
      SymbolData& s = kv.second;
      size_t& j = nxt[kv.first];
      while (j < s.base.size() && s.base[j].t <= T) { s.cur = (int)j; if (s.base[j].t == T) fresh.push_back(kv.first); j++; }
      if (s.cur >= 0) {
        const Bar& b = s.base[s.cur];
        if (b.t == T) { s.bid = b.o; s.ask = b.o + b.sp; }
      }
    }
    if (T < t_start) continue;
    if (!inited) {
      inited = true;
      if (OnInit() != INIT_SUCCEEDED) { fprintf(stderr, "OnInit failed\n"); return 1; }
    }
    // swaps at the server-day change (triple on the rollover that closes Wednesday)
    datetime day = T - (T % 86400);
    if (prev_day >= 0 && day != prev_day) {
      int mult = weekday(prev_day) == 3 ? 3 : 1;
      for (auto& p : RT.pos) {
        SymbolData& s = RT.syms[p.sym];
        double notional = s.bid * p.vol * s.spec.contract;
        double rate = p.type == 0 ? s.spec.swap_long : s.spec.swap_short;
        p.swap += notional * rate / 360.0 * mult;
      }
    }
    prev_day = day;
    OnTick();
    flush_tx();
    for (auto& sym : fresh) {
      SymbolData& s = RT.syms[sym];
      process_stops(sym, s.base[s.cur]);
    }
    flush_tx();
    // equity bookkeeping at the bar close
    double eq_close = RT.balance, eq_worst = RT.balance;
    for (auto& p : RT.pos) {
      SymbolData& s = RT.syms[p.sym];
      const Bar& b = s.base[s.cur];
      double extra = p.swap - 2 * s.spec.commission_side * p.vol;
      if (p.type == 0) { eq_close += (b.c - p.open) * p.vol * s.spec.contract + extra; eq_worst += (b.l - p.open) * p.vol * s.spec.contract + extra; }
      else { eq_close += (p.open - b.c - b.sp) * p.vol * s.spec.contract + extra; eq_worst += (p.open - b.h - b.sp) * p.vol * s.spec.contract + extra; }
    }
    RT.peak_equity = std::max(RT.peak_equity, eq_close);
    RT.max_dd = std::max(RT.max_dd, (RT.peak_equity - eq_worst) / RT.peak_equity);
    if (day != last_eq_day) {
      if (last_eq_day >= 0) eqf << last_eq_day << "," << prev_close << "," << RT.balance << "," << worst_today << "," << best_today << "\n";
      last_eq_day = day; worst_today = 1e300; best_today = -1e300;
    }
    worst_today = std::min(worst_today, eq_worst);
    best_today = std::max(best_today, eq_close);
    prev_close = eq_close;
  }
  eqf << last_eq_day << "," << prev_close << "," << RT.balance << "," << worst_today << "," << best_today << "\n";
  OnDeinit(0);
  std::ofstream tf(out + "/trades.csv");
  tf << "ticket,symbol,magic,dir,volume,open,close,sl_dist,t_open,t_close,pnl,reason\n";
  for (auto& t : RT.trades)
    tf << t.ticket << "," << t.sym << "," << t.magic << "," << t.dir << "," << t.vol << "," << t.open << "," << t.close << ","
       << t.sl0 << "," << t.t_open << "," << t.t_close << "," << t.pnl << "," << t.reason << "\n";
  printf("final equity %.2f  (deposit %.2f)  trades %zu  maxDD %.2f%%  OnTester %.3f\n", rt_equity(), deposit, RT.trades.size(),
         RT.max_dd * 100, OnTester());
  return 0;
}
