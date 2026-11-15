// fantasy_screens.h - ESPN fantasy basketball (head-to-head points) pages for the two screens
//
// Three styles, one a day in turn (the day number from the PC's clock message): Jumbotron (an arena
// scoreboard in dot-matrix LEDs), Neon (glowing cyan for you, magenta for them) and Court (hardwood,
// team-colour baseline and paint). Each has four pages, 8 s each:
//   Matchup     left: you - team, score, projection, record    right: them, and the lead
//   Win chance  left: your chance to win (live projections)    right: the projected finals
//   Lead        left: your lead through the week, as a chart   right: the lead now, best and worst
//   Season      left: record, place, streak, points for        right: the top of the standings
// Music and the Claude dashboard don't give way to them: they show the score in their own style
// instead (overlay(), at the end). The previews are in design/fantasy_styles/basketball.
//
// Made by hand in the style of buddy_screens.h, whose helpers and fonts it uses, not in the Screen
// Designer: re-exporting buddy_screens.h keeps them, as long as the design still has these fonts
// (Bebas Neue 400 75 / 49 / 22, Inter 700 22 / 18 / 16 / 15 / 11, Inter 400 15 / 14 / 13 / 12,
// Roboto 700 17, Nunito 800 15). The LED style draws the GFX library's built-in 5x7 font as dots.
//
// While NBA games are on (the PC helper's "F" message says live), DeskBuddy.ino shows the pages in
// turn when nothing else is on the screens (in place of the eyes or a time-of-day scene).
#pragma once
#include "buddy_screens.h"

namespace ff {
#include "font/glcdfont.h"   // ff::font: 5 bytes (columns, bit 0 at the top) per character

enum : uint8_t { STYLE_JUMBOTRON = 0, STYLE_NEON, STYLE_COURT, STYLES };
enum : uint8_t { PAGE_MATCHUP = 0, PAGE_CHANCE, PAGE_LEAD, PAGE_SEASON, PAGES };
static const int SCENE_FIRST = 100;   // the scene numbers DeskBuddy.ino uses: 100 + style * 10 + page,
static const int WITH_NOTIFICATION = 100, WITH_VOLUME = 200;   // + these for a notification / the volume on the right
static const char *const STYLE_NAMES[STYLES] = {"jumbotron", "neon", "court"};
static const char *const PAGE_NAMES[PAGES] = {"matchup", "win chance", "lead", "season"};
static uint32_t day = 0;   // the day number from the PC's clock message: today's style is day % STYLES

static const buddy::Font &B75 = buddyFont_g_Bebas_Neue_400_75_info, &B49 = buddyFont_g_Bebas_Neue_400_49_info,
                         &B22 = buddyFont_g_Bebas_Neue_400_22_info;
static const buddy::Font &I22 = buddyFont_g_Inter_700_22_info, &I18 = buddyFont_g_Inter_700_18_info,
                         &I16 = buddyFont_g_Inter_700_16_info, &I15 = buddyFont_g_Inter_700_15_info,
                         &I11 = buddyFont_g_Inter_700_11_info;
static const buddy::Font &R15 = buddyFont_g_Inter_400_15_info, &R14 = buddyFont_g_Inter_400_14_info,
                         &R13 = buddyFont_g_Inter_400_13_info, &R12 = buddyFont_g_Inter_400_12_info;
static const buddy::Font &RB17 = buddyFont_g_Roboto_700_17_info, &N15 = buddyFont_g_Nunito_800_15_info;
using buddy::ALIGN_LEFT;
using buddy::ALIGN_CENTER;
using buddy::ALIGN_RIGHT;

// ---------------------------------------------------------------- data

// The PC helper's "L" message: the season around the matchup
static const int ROWS = 5;
struct Row { uint8_t place; char team[20]; char record[10]; };
static char streak[6] = "", pointsFor[12] = "", oppRecord[12] = "";
static uint8_t oppPlace = 0, rows = 0;
static Row row[ROWS];

// Your lead (your points minus theirs) at each "F" message this week, for the chart. When it's full
// every other point goes, so the chart always covers the whole week
static const int LEAD_MAX = 120;
static float lead[LEAD_MAX];
static int leads = 0;
static float best = 0, worst = 0;
static uint8_t leadWeek = 0;
static char leadOpp[32] = "";

static void onMatchup(uint8_t week, const char *opp, float myScore, float oppScore) {
  if (week != leadWeek || strcmp(opp, leadOpp)) {   // a new week: start over
    leads = 0;
    leadWeek = week;
    strlcpy(leadOpp, opp, sizeof leadOpp);
  }
  float l = myScore - oppScore;
  if (leads && fabsf(lead[leads - 1] - l) < 0.05f) return;   // the same again (sent after a reconnect)
  if (leads == LEAD_MAX) {
    for (int i = 0; i < LEAD_MAX / 2; i++) lead[i] = lead[i * 2 + 1];
    leads = LEAD_MAX / 2;
  }
  if (!leads) best = worst = l;
  best = fmaxf(best, l);
  worst = fminf(worst, l);
  lead[leads++] = l;
}

// f: streak, points for, their record, their place, then place / team / record per standings row
static void onLeague(char **f, int n) {
  strlcpy(streak, f[0], sizeof streak);
  strlcpy(pointsFor, f[1], sizeof pointsFor);
  strlcpy(oppRecord, f[2], sizeof oppRecord);
  oppPlace = atoi(f[3]);
  rows = 0;
  for (int i = 4; i + 2 < n && rows < ROWS; i += 3) {
    row[rows].place = atoi(f[i]);
    strlcpy(row[rows].team, f[i + 1], sizeof row[rows].team);
    strlcpy(row[rows].record, f[i + 2], sizeof row[rows].record);
    rows++;
  }
}

static inline bool bye(const BuddyData &d) { return !strcmp(d.ffOppTeam, "BYE"); }
static inline bool projected(const BuddyData &d) { return d.ffMyProj > 0 || d.ffOppProj > 0; }
static inline float myFinal(const BuddyData &d) { return fmaxf(d.ffMyProj, d.ffMyScore); }
static inline float oppFinal(const BuddyData &d) { return fmaxf(d.ffOppProj, d.ffOppScore); }

// Your chance to win from the live projections. The points still to come for each team vary by
// about 2.4 x their square root either way (a 1,100-point week: +-80), so the final margin is the
// projected one give or take that
static inline float winChance(const BuddyData &d) {
  float me = myFinal(d), them = oppFinal(d);
  float spread = 2.4f * sqrtf((me - d.ffMyScore) + (them - d.ffOppScore));
  if (spread < 0.5f) return me > them ? 1.0f : me < them ? 0.0f : 0.5f;   // everyone has played
  return 0.5f * (1.0f + erff((me - them) / (spread * 1.41421356f)));
}
static inline bool decided(float c) { return c <= 0.0f || c >= 1.0f; }
static inline int chancePct(float c) {   // not over yet: never 0% or 100%
  int p = (int)lroundf(c * 100.0f);
  return decided(c) ? p : p < 1 ? 1 : p > 99 ? 99 : p;
}

// The lead between chart columns x0 .. x1 at x
static inline float leadAt(int x, int x0, int x1) {
  if (leads < 2) return leads ? lead[0] : 0.0f;
  float pos = (float)(x - x0) / (x1 - x0) * (leads - 1);
  int i = (int)pos;
  return i + 1 < leads ? lead[i] + (lead[i + 1] - lead[i]) * (pos - i) : lead[leads - 1];
}
static inline float leadSpan() { return fmaxf(10.0f, fmaxf(fabsf(best), fabsf(worst))); }

// ---------------------------------------------------------------- text

// Weekly basketball totals: one decimal under 1000, whole numbers from there ("742.5", "1084")
static inline void pts(char *out, size_t n, float v) { snprintf(out, n, v >= 999.95f ? "%.0f" : "%.1f", v); }

static inline void ordinal(char *out, size_t n, unsigned r, bool caps) {
  unsigned k = r % 100;
  const char *s = k >= 11 && k <= 13 ? "th" : r % 10 == 1 ? "st" : r % 10 == 2 ? "nd" : r % 10 == 3 ? "rd" : "th";
  if (caps) snprintf(out, n, "%u%c%c", r, s[0] - 32, s[1] - 32);   // "3RD"
  else snprintf(out, n, "%u%s", r, s);                              // "3rd"
}

static inline const char *upper(char *out, size_t n, const char *s) {
  size_t i = 0;
  for (; s[i] && i + 1 < n; i++) out[i] = s[i] >= 'a' && s[i] <= 'z' ? s[i] - 32 : s[i];
  out[i] = 0;
  return out;
}

// For the LED font: in capitals, whole words within maxChars ("Triple Doubles", 10 -> "TRIPLE")
static inline const char *words(char *out, size_t n, const char *s, int maxChars) {
  upper(out, n, s);
  if (maxChars < 1) maxChars = 1;
  int len = (int)strlen(out);
  if (len <= maxChars) return out;
  int cut = maxChars;
  while (cut > 0 && out[cut] != ' ') cut--;
  out[cut > 0 ? cut : maxChars] = 0;
  return out;
}

// s cut to fit maxW pixels in font f, ending in ".." if it was cut (team names, song titles)
static inline const char *fit(char *out, size_t n, const char *s, const buddy::Font &f, int maxW) {
  strlcpy(out, s, n);
  int len = (int)strlen(out);
  if (buddy::textWidth(f, out, len, 1) <= maxW || n < 4) return out;
  int dots = buddy::textWidth(f, "..", 2, 1);
  while (len > 0 && (buddy::textWidth(f, out, len, 1) + dots > maxW || len + 3 > (int)n)) len--;
  while (len > 0 && out[len - 1] == ' ') len--;   // no space before the dots
  strcpy(out + len, "..");
  return out;
}

// The first of two fonts the whole of s fits in, else the second with s cut to fit
static inline const buddy::Font &fitFont(char *out, size_t n, const char *s, const buddy::Font &a, const buddy::Font &b, int maxW) {
  strlcpy(out, s, n);
  if (buddy::textWidth(a, out, (int)strlen(out), 1) <= maxW) return a;
  fit(out, n, s, b, maxW);
  return b;
}

static inline void label(Arduino_GFX *g, int x, int y, const char *s, uint16_t c, uint8_t align, const buddy::Font &f, bool middle) {
  if (middle) buddy::textAt(g, x, y, buddy::VALIGN_MIDDLE, s, 1, c, align, 0, 1, f);
  else buddy::text(g, x, y, s, 1, c, align, 0, 1, f);
}

// Text with a halo round it (Neon), or a drop shadow (Court)
static void glow(Arduino_GFX *g, int x, int y, const char *s, uint16_t c, uint16_t halo, uint8_t align, const buddy::Font &f,
                 bool middle = false) {
  static const int8_t AROUND[8][2] = {{-2, 0}, {2, 0}, {0, -2}, {0, 2}, {-1, -1}, {1, 1}, {-1, 1}, {1, -1}};
  for (auto &o : AROUND) label(g, x + o[0], y + o[1], s, halo, align, f, middle);
  label(g, x, y, s, c, align, f, middle);
}

static void shadow(Arduino_GFX *g, int x, int y, const char *s, uint16_t c, uint16_t sh, uint8_t align, const buddy::Font &f,
                   bool middle = false, int off = 3) {
  label(g, x + off, y + off, s, sh, align, f, middle);
  label(g, x, y, s, c, align, f, middle);
}

// Dot-matrix text in the 5x7 font, each dot a round LED pitch px apart; the unlit ones in 'off' too
// (they make the character cells show, as on a scoreboard) unless off is NO_DOTS. y = the top
static const int32_t NO_DOTS = -1;
static void led(Arduino_GFX *g, int x, int y, const char *s, int pitch, int r, uint16_t on, int32_t off = NO_DOTS,
                uint8_t align = ALIGN_CENTER) {
  int n = (int)strlen(s), w = n * 6 * pitch - pitch;
  int x0 = align == ALIGN_CENTER ? x - w / 2 : align == ALIGN_RIGHT ? x - w : x;
  for (int k = 0; k < n; k++) {
    int cols = off != NO_DOTS && k < n - 1 ? 6 : 5;   // the gap between characters is unlit dots too
    for (int i = 0; i < cols; i++) {
      uint8_t col = i < 5 ? font[(uint8_t)s[k] * 5 + i] : 0;
      for (int j = 0; j < 7; j++) {
        bool lit = col >> j & 1;
        if (lit || off != NO_DOTS)
          g->fillCircle(x0 + (k * 6 + i) * pitch + pitch / 2, y + j * pitch + pitch / 2, r, lit ? on : (uint16_t)off);
      }
    }
  }
}

// ---------------------------------------------------------------- shared drawing

static void basketball(Arduino_GFX *g, int x, int y, int r, uint16_t c, uint16_t seam) {
  g->fillCircle(x, y, r, c);
  g->fillRect(x - r, y - 1, 2 * r + 1, 2, seam);   // across
  g->fillRect(x - 1, y - r, 2, 2 * r + 1, seam);   // down
  g->fillArc(x - r - 2, y, r + 3, r + 1, -45.0f, 45.0f, seam);    // the two curved seams
  g->fillArc(x + r + 2, y, r + 3, r + 1, 135.0f, 225.0f, seam);
}

// The lead through the week as an area chart between x0..x1 and top..bottom: the area between the
// lead and zero, the zero line, then the line itself (with a halo for Neon). Sets where it ends
static void leadChart(Arduino_GFX *g, int x0, int x1, int top, int bottom, uint16_t upArea, uint16_t downArea, uint16_t zero,
                      uint16_t up, uint16_t down, int32_t upHalo, int32_t downHalo, int &endX, int &endY) {
  int mid = (top + bottom) / 2;
  float k = (bottom - top) / 2.0f / leadSpan();
  for (int x = x0; x <= x1; x++) {
    int y = (int)lroundf(mid - leadAt(x, x0, x1) * k);
    if (y < mid) g->drawFastVLine(x, y, mid - y, upArea);
    else if (y > mid) g->drawFastVLine(x, mid + 1, y - mid, downArea);
  }
  g->drawFastHLine(x0, mid, x1 - x0 + 1, zero);
  for (int i = 1; i < leads; i++) {
    int xa = x0 + (x1 - x0) * (i - 1) / (leads - 1), xb = x0 + (x1 - x0) * i / (leads - 1);
    int ya = (int)lroundf(mid - lead[i - 1] * k), yb = (int)lroundf(mid - lead[i] * k);
    bool upward = lead[i - 1] + lead[i] >= 0;
    if (upHalo != NO_DOTS) buddy::line(g, xa, ya, xb, yb, 6, (uint16_t)(upward ? upHalo : downHalo));
    buddy::line(g, xa, ya, xb, yb, 2, upward ? up : down);
  }
  endX = x1;
  endY = (int)lroundf(mid - (leads ? lead[leads - 1] : 0.0f) * k);
}

static inline float winShare(const char *record) {   // "6-2" -> 0.75 (ties count half)
  int w = 0, l = 0, t = 0;
  sscanf(record, "%d-%d-%d", &w, &l, &t);
  return w + l + t ? (w + t * 0.5f) / (w + l + t) : 0.0f;
}

// ================================================================ Jumbotron (arena scoreboard)
static const uint16_t AMB = 0xFD80, AMB_OFF = 0x1880;    // amber LEDs, lit and unlit
static const uint16_t LRED = 0xF963, LRED_OFF = 0x2040, LGRN = 0x2FEB, LGRN_OFF = 0x0101;
static const uint16_t PANEL_DOT = 0x1082, CHART_DOT = 0x10A2;

static void ledPanel(Arduino_GFX *g) {   // black with a faint grid of dots, like the board's face
  g->fillScreen(0x0000);
  for (int y = 1; y < 240; y += 6)
    for (int x = 1; x < 240; x += 6) g->fillRect(x, y, 2, 2, PANEL_DOT);
}

static void ledRing(Arduino_GFX *g, float v, uint16_t on, uint16_t off) {   // 60 LEDs round the edge
  for (int i = 0; i < 60; i++) {
    float a = i * 6.0f * 0.0174532925f;
    g->fillCircle((int)lroundf(120 + 112 * sinf(a)), (int)lroundf(120 - 112 * cosf(a)), 3, i < v * 60 ? on : off);
  }
}

// The lead with an arrow pointing at whoever leads, like a possession arrow (your screen is the left one)
static inline void arrowLead(char *out, size_t n, float l) {
  if (l >= 0) snprintf(out, n, "\x11 %+.1f", l);
  else snprintf(out, n, "%+.1f \x10", l);
}

static void jMatchup(Arduino_GFX *g, const BuddyData &d, bool me) {
  char t[40], name[24], p[12];
  ledPanel(g);
  if (!me && bye(d)) {
    led(g, 120, 84, "BYE", 7, 3, LRED, LRED_OFF);
    led(g, 120, 150, "NO GAME", 2, 1, LRED);
    return;
  }
  uint16_t on = me ? AMB : LRED, off = me ? AMB_OFF : LRED_OFF;
  float share = buddy::value(d, buddy::VAL_FF_SHARE);
  ledRing(g, me ? share : 1.0f - share, on, off);
  led(g, 120, 30, me ? "HOME" : "GUEST", 3, 1, on);
  led(g, 120, 58, words(name, sizeof name, me ? d.ffMyTeam : d.ffOppTeam, 14), 2, 1, on);
  pts(t, sizeof t, me ? d.ffMyScore : d.ffOppScore);
  led(g, 120, 92, t, 6, 2, on, off);
  if (projected(d)) {
    pts(p, sizeof p, me ? d.ffMyProj : d.ffOppProj);
    snprintf(t, sizeof t, "PROJ %s", p);
    led(g, 120, 150, t, 2, 1, on);
  }
  if (me) {
    ordinal(p, sizeof p, d.ffRank, true);
    snprintf(t, sizeof t, "%s %s", d.ffRecord, p);
    led(g, 120, 172, t, 2, 1, AMB);
  } else {
    float l = d.ffMyScore - d.ffOppScore;
    arrowLead(t, sizeof t, l);
    led(g, 120, 170, t, 3, 1, l >= 0 ? LGRN : LRED);
  }
}

static void jChanceL(Arduino_GFX *g, const BuddyData &d) {
  char t[16];
  ledPanel(g);
  float c = winChance(d);
  led(g, 120, 40, decided(c) ? (c >= 1.0f ? "WON" : "LOST") : "WIN", 3, 1, AMB);
  snprintf(t, sizeof t, "%d%%", chancePct(c));
  led(g, 120, 76, t, 7, 3, LGRN, LGRN_OFF);
  int lit = (int)lroundf(20 * c);
  for (int i = 0; i < 20; i++)
    for (int r = 0; r < 3; r++) g->fillCircle(44 + i * 8, 140 + r * 8, 3, i < lit ? LGRN : LGRN_OFF);
  snprintf(t, sizeof t, "WEEK %u", (unsigned)d.ffWeek);
  led(g, 120, 176, t, 2, 1, AMB);
}

static void jChanceR(Arduino_GFX *g, const BuddyData &d) {
  char t[24], p[12];
  ledPanel(g);
  float me = myFinal(d), them = oppFinal(d);
  led(g, 120, 36, "PROJECTED", 2, 1, AMB);
  pts(p, sizeof p, me);
  snprintf(t, sizeof t, "HOME %s", p);
  led(g, 120, 70, t, 3, 1, AMB, AMB_OFF);
  pts(p, sizeof p, them);
  snprintf(t, sizeof t, "GUEST %s", p);
  led(g, 120, 106, t, 3, 1, LRED, LRED_OFF);
  snprintf(t, sizeof t, "EDGE %+.0f", me - them);
  led(g, 120, 146, t, 2, 1, me >= them ? LGRN : LRED);
  snprintf(t, sizeof t, "%d%% SCORED", buddy::pct(buddy::value(d, buddy::VAL_FF_PROJ) * 100.0f));
  led(g, 120, 168, t, 2, 1, AMB);
}

static void jLeadL(Arduino_GFX *g, const BuddyData &d) {
  char t[16];
  ledPanel(g);
  led(g, 120, 34, "LEAD", 3, 1, AMB);
  // an LED bar graph: columns up from the middle row while you lead, down while you trail
  const int cols = 21, x0 = 40, y0 = 66, p = 8;
  float span = leadSpan();
  for (int i = 0; i < cols; i++) {
    float v = leadAt(x0 + i * p, x0, x0 + (cols - 1) * p);
    int h = (int)lroundf(fabsf(v) / span * 6);
    for (int j = 0; j < 13; j++) {
      int up = 6 - j;   // rows above the middle
      uint16_t c;
      if (up == 0) c = h == 0 ? AMB_OFF : v > 0 ? LGRN : LRED;
      else if (up > 0) c = v > 0 && up <= h ? LGRN : CHART_DOT;
      else c = v < 0 && -up <= h ? LRED : CHART_DOT;
      g->fillCircle(x0 + i * p, y0 + j * p, 2, c);
    }
  }
  snprintf(t, sizeof t, "WEEK %u", (unsigned)d.ffWeek);
  led(g, 120, 176, t, 2, 1, AMB);
}

static void jLeadR(Arduino_GFX *g, const BuddyData &d) {
  char t[24];
  ledPanel(g);
  float l = d.ffMyScore - d.ffOppScore;
  bool ahead = l >= 0;
  led(g, 120, 44, ahead ? "YOU LEAD BY" : "YOU TRAIL BY", 2, 1, ahead ? LGRN : LRED);
  snprintf(t, sizeof t, "%.1f", fabsf(l));
  led(g, 120, 76, t, 6, 2, ahead ? LGRN : LRED, ahead ? LGRN_OFF : LRED_OFF);
  snprintf(t, sizeof t, "BEST %+.1f", best);
  led(g, 120, 138, t, 2, 1, AMB);
  snprintf(t, sizeof t, "WORST %+.1f", worst);
  led(g, 120, 160, t, 2, 1, AMB);
}

static void jSeasonL(Arduino_GFX *g, const BuddyData &d) {
  char t[24], p[12];
  ledPanel(g);
  ledRing(g, winShare(d.ffRecord), AMB, AMB_OFF);
  led(g, 120, 34, "SEASON", 3, 1, AMB);
  bool longRecord = strlen(d.ffRecord) > 3;   // "10-12": smaller LEDs so it fits
  led(g, 120, longRecord ? 77 : 70, d.ffRecord, longRecord ? 5 : 7, longRecord ? 2 : 3, AMB, AMB_OFF);
  ordinal(p, sizeof p, d.ffRank, true);
  snprintf(t, sizeof t, "%s PLACE", p);
  led(g, 120, 134, t, 2, 1, AMB);
  if (streak[0]) {
    snprintf(t, sizeof t, "STREAK %s", streak);
    led(g, 120, 156, t, 2, 1, LGRN);
  }
  if (pointsFor[0]) {
    pts(p, sizeof p, atof(pointsFor));
    snprintf(t, sizeof t, "PF %s", p);
    led(g, 120, 178, t, 2, 1, AMB);
  }
}

static void jSeasonR(Arduino_GFX *g, const BuddyData &d) {
  char t[8], name[24];
  ledPanel(g);
  led(g, 120, 32, "STANDINGS", 2, 1, AMB);
  for (int i = 0; i < rows; i++) {
    int y = 58 + i * 26;
    uint16_t c = row[i].place == d.ffRank ? LGRN : AMB;
    snprintf(t, sizeof t, "%u", (unsigned)row[i].place);
    led(g, 28, y, t, 2, 1, c, NO_DOTS, ALIGN_LEFT);
    int nameX = 28 + (int)strlen(t) * 12 - 2 + 8, recW = (int)strlen(row[i].record) * 12 - 2;
    led(g, nameX, y, words(name, sizeof name, row[i].team, (214 - recW - 8 - nameX + 2) / 12), 2, 1, c, NO_DOTS, ALIGN_LEFT);
    led(g, 214, y, row[i].record, 2, 1, c, NO_DOTS, ALIGN_RIGHT);
  }
}

// ================================================================ Neon
static const uint16_t NBG = 0x0823, CYAN = 0x077F, CYAN_G = 0x020A, MAG = 0xF979, MAG_G = 0x4848;
static const uint16_t NTRACK = 0x20A8, LAV = 0x93FB, ROW_HI = 0x1886, N_UP = 0x0105, N_DOWN = 0x3045;
static const uint16_t BALL = 0xFC03, BALL_G = 0x5941, BALL_SEAM = 0x1040;

static void neonRing(Arduino_GFX *g, float v, uint16_t c, uint16_t halo) {
  buddy::ring(g, 120, 120, 112, 3, 0.0f, 360.0f, c, true, NTRACK, 0.0f);
  buddy::ring(g, 120, 120, 116, 11, 0.0f, 360.0f, halo, false, 0, v);
  buddy::ring(g, 120, 120, 112, 3, 0.0f, 360.0f, c, false, 0, v);
}

static void nMatchup(Arduino_GFX *g, const BuddyData &d, bool me) {
  char t[48], p[12];
  g->fillScreen(NBG);
  if (!me && bye(d)) {
    glow(g, 120, 108, "BYE", 0xFFFF, MAG_G, ALIGN_CENTER, B75, true);
    buddy::text(g, 120, 152, "No game this week", 1, LAV, ALIGN_CENTER, 0, 1, R15);
    return;
  }
  uint16_t c = me ? CYAN : MAG, h = me ? CYAN_G : MAG_G;
  float share = buddy::value(d, buddy::VAL_FF_SHARE);
  neonRing(g, me ? share : 1.0f - share, c, h);
  if (me) {
    snprintf(t, sizeof t, "LIVE  WEEK %u", (unsigned)d.ffWeek);
    glow(g, 120, 34, t, MAG, MAG_G, ALIGN_CENTER, I11);
  } else {
    if (oppRecord[0] && oppPlace) {
      ordinal(p, sizeof p, oppPlace, false);
      snprintf(t, sizeof t, "VS  %s  %s", oppRecord, p);
    } else {
      strlcpy(t, "VS", sizeof t);
    }
    buddy::text(g, 120, 34, t, 1, LAV, ALIGN_CENTER, 0, 1, I11);
  }
  const buddy::Font &f = fitFont(t, sizeof t, me ? d.ffMyTeam : d.ffOppTeam, I18, I15, 172);
  glow(g, 120, 56, t, 0xFFFF, h, ALIGN_CENTER, f);
  pts(t, sizeof t, me ? d.ffMyScore : d.ffOppScore);
  glow(g, 120, 120, t, 0xFFFF, h, ALIGN_CENTER, B75, true);
  if (projected(d)) {
    pts(p, sizeof p, me ? d.ffMyProj : d.ffOppProj);
    snprintf(t, sizeof t, "PROJ %s", p);
    buddy::text(g, 120, 160, t, 1, LAV, ALIGN_CENTER, 0, 1, R15);
  }
  if (me) {
    ordinal(p, sizeof p, d.ffRank, false);
    snprintf(t, sizeof t, "%s  |  %s", d.ffRecord, p);
    glow(g, 120, 184, t, CYAN, CYAN_G, ALIGN_CENTER, I15);
  } else {
    float l = d.ffMyScore - d.ffOppScore;
    snprintf(t, sizeof t, "YOU %+.1f", l);
    glow(g, 120, 182, t, l >= 0 ? CYAN : MAG, l >= 0 ? CYAN_G : MAG_G, ALIGN_CENTER, I18);
  }
}

static void nChanceL(Arduino_GFX *g, const BuddyData &d) {
  char t[16];
  g->fillScreen(NBG);
  const int cx = 120, cy = 130, r = 92;
  float c = winChance(d);
  buddy::ring(g, cx, cy, r, 3, 240.0f, 240.0f, CYAN, true, NTRACK, 0.0f);
  buddy::ring(g, cx, cy, r + 4, 11, 240.0f, 240.0f, CYAN_G, false, 0, c);
  buddy::ring(g, cx, cy, r, 3, 240.0f, 240.0f, CYAN, false, 0, c);
  for (int k = 0; k < 9; k++) buddy::hand(g, cx, cy, r - 20, r - 12, 2, 240.0f + k * 30, LAV);   // ticks
  buddy::hand(g, cx, cy, 0, r - 18, 5, 240.0f + 240.0f * c, MAG_G);                               // needle
  buddy::hand(g, cx, cy, 0, r - 18, 3, 240.0f + 240.0f * c, MAG);
  g->fillCircle(cx, cy, 13, BALL_G);   // its hub: a glowing basketball
  basketball(g, cx, cy, 10, BALL, BALL_SEAM);
  snprintf(t, sizeof t, "%d%%", chancePct(c));
  glow(g, 120, 178, t, 0xFFFF, CYAN_G, ALIGN_CENTER, B49, true);
  buddy::text(g, 120, 210, decided(c) ? (c >= 1.0f ? "YOU WON" : "YOU LOST") : "WIN CHANCE", 1, CYAN, ALIGN_CENTER, 0, 1, I11);
}

static void nChanceR(Arduino_GFX *g, const BuddyData &d) {
  char t[40], v[12];
  g->fillScreen(NBG);
  glow(g, 120, 40, "PROJECTED", MAG, MAG_G, ALIGN_CENTER, I15);
  float me = myFinal(d), them = oppFinal(d), top = fmaxf(fmaxf(me, them), 1.0f);
  for (int k = 0; k < 2; k++) {
    int y = 70 + k * 52;
    float val = k ? them : me;
    uint16_t c = k ? MAG : CYAN, h = k ? MAG_G : CYAN_G;
    pts(v, sizeof v, val);
    glow(g, 200, y, v, 0xFFFF, h, ALIGN_RIGHT, I18);
    fit(t, sizeof t, k ? d.ffOppTeam : d.ffMyTeam, I15, 150 - buddy::textWidth(I18, v, (int)strlen(v), 1));
    buddy::text(g, 40, y + 2, t, 1, c, ALIGN_LEFT, 0, 1, I15);
    g->fillRoundRect(38, y + 25, 164, 12, 6, h);
    int w = (int)lroundf(160 * val / top);
    if (w >= 8) g->fillRoundRect(40, y + 27, w, 8, 4, c);
  }
  snprintf(t, sizeof t, "%d%% OF YOUR PROJECTION", buddy::pct(buddy::value(d, buddy::VAL_FF_PROJ) * 100.0f));
  buddy::text(g, 120, 180, t, 1, LAV, ALIGN_CENTER, 0, 1, R12);
}

static void nLeadL(Arduino_GFX *g, const BuddyData &d) {
  char t[16];
  int x, y;
  g->fillScreen(NBG);
  glow(g, 120, 36, "LEAD TRACKER", MAG, MAG_G, ALIGN_CENTER, I15);
  leadChart(g, 30, 210, 64, 176, N_UP, N_DOWN, NTRACK, CYAN, MAG, CYAN_G, MAG_G, x, y);
  g->fillCircle(x, y, 6, CYAN_G);   // now
  g->fillCircle(x, y, 3, 0xFFFF);
  // the scale (the design's 12 px font has no real "+", so 13 px)
  snprintf(t, sizeof t, "+%d", (int)lroundf(leadSpan()));
  buddy::text(g, 34, 64, t, 1, LAV, ALIGN_LEFT, 0, 1, R13);
  snprintf(t, sizeof t, "-%d", (int)lroundf(leadSpan()));
  buddy::text(g, 34, 161, t, 1, LAV, ALIGN_LEFT, 0, 1, R13);
  snprintf(t, sizeof t, "WEEK %u", (unsigned)d.ffWeek);
  buddy::text(g, 120, 190, t, 1, LAV, ALIGN_CENTER, 0, 1, I11);
}

static void nLeadR(Arduino_GFX *g, const BuddyData &d) {
  char t[40], a[12], b[12];
  g->fillScreen(NBG);
  float l = d.ffMyScore - d.ffOppScore;
  bool ahead = l >= 0;
  neonRing(g, buddy::value(d, buddy::VAL_FF_SHARE), ahead ? CYAN : MAG, ahead ? CYAN_G : MAG_G);
  buddy::text(g, 120, 56, ahead ? "YOU LEAD BY" : "YOU TRAIL BY", 1, LAV, ALIGN_CENTER, 0, 1, RB17);
  snprintf(t, sizeof t, "%.1f", fabsf(l));
  glow(g, 120, 116, t, 0xFFFF, ahead ? CYAN_G : MAG_G, ALIGN_CENTER, B75, true);
  snprintf(t, sizeof t, "BEST %+.1f   WORST %+.1f", best, worst);
  buddy::text(g, 120, 160, t, 1, LAV, ALIGN_CENTER, 0, 1, R13);
  pts(a, sizeof a, d.ffMyScore);
  pts(b, sizeof b, d.ffOppScore);
  snprintf(t, sizeof t, "%s - %s", a, b);
  glow(g, 120, 182, t, CYAN, CYAN_G, ALIGN_CENTER, I15);
}

static void nSeasonL(Arduino_GFX *g, const BuddyData &d) {
  char t[32], p[12];
  g->fillScreen(NBG);
  neonRing(g, winShare(d.ffRecord), MAG, MAG_G);
  glow(g, 120, 40, "SEASON", MAG, MAG_G, ALIGN_CENTER, I15);
  glow(g, 120, 102, d.ffRecord, 0xFFFF, CYAN_G, ALIGN_CENTER, B75, true);
  ordinal(p, sizeof p, d.ffRank, false);
  snprintf(t, sizeof t, "%s place", p);
  glow(g, 120, 144, t, CYAN, CYAN_G, ALIGN_CENTER, I18);
  if (streak[0]) {
    snprintf(t, sizeof t, "Streak %s", streak);
    buddy::text(g, 120, 172, t, 1, LAV, ALIGN_CENTER, 0, 1, R14);
  }
  if (pointsFor[0]) {
    pts(p, sizeof p, atof(pointsFor));
    snprintf(t, sizeof t, "%s points for", p);
    buddy::text(g, 120, 192, t, 1, LAV, ALIGN_CENTER, 0, 1, R14);
  }
}

static void nSeasonR(Arduino_GFX *g, const BuddyData &d) {
  char t[8], name[24];
  g->fillScreen(NBG);
  glow(g, 120, 32, "STANDINGS", MAG, MAG_G, ALIGN_CENTER, I15);
  buddy::line(g, 60, 56, 180, 56, 3, CYAN_G);
  buddy::line(g, 60, 56, 180, 56, 1, CYAN);
  for (int i = 0; i < rows; i++) {
    int y = 66 + i * 26;
    bool mine = row[i].place == d.ffRank;
    const buddy::Font &f = mine ? I15 : R15;
    int room = 206 - 8 - 58 - buddy::textWidth(I15, row[i].record, (int)strlen(row[i].record), 1);
    fit(name, sizeof name, row[i].team, f, room);
    snprintf(t, sizeof t, "%u", (unsigned)row[i].place);
    if (mine) {
      g->fillRoundRect(26, y - 4, 188, 25, 8, ROW_HI);
      glow(g, 34, y, t, CYAN, CYAN_G, ALIGN_LEFT, I15);
      glow(g, 58, y, name, 0xFFFF, CYAN_G, ALIGN_LEFT, f);
      glow(g, 206, y, row[i].record, CYAN, CYAN_G, ALIGN_RIGHT, I15);
    } else {
      buddy::text(g, 34, y, t, 1, LAV, ALIGN_LEFT, 0, 1, I15);
      buddy::text(g, 58, y, name, 1, LAV, ALIGN_LEFT, 0, 1, f);
      buddy::text(g, 206, y, row[i].record, 1, LAV, ALIGN_RIGHT, 0, 1, I15);
    }
  }
}

// ================================================================ Court (hardwood)
static const uint16_t WOOD[3] = {0xD50C, 0xCCAB, 0xDD4D};
static const uint16_t WSEAM = 0xABC8, WSH = 0x4942, CLINE = 0xFFBD, ORANGE = 0xEB83, BSEAM = 0x28A1;
static const uint16_t CBLUE = 0x02B6, CBLUE_D = 0x01D0, CRED = 0xB8C4, CRED_D = 0x8083, GOLD = 0xC482, LIVE = 0xD0E5;
static const uint16_t BOARD = 0x19C4, FRAME = 0x7A85, CHALK = 0xEF7C, FAINT = 0x4309, YELLOW = 0xFF2B;
static const uint16_t C_UP = 0x22E6, C_DOWN = 0x7143, C_ZERO = 0x9368, C_UPL = 0x46ED, C_DOWNL = 0xFB08;

static void hardwood(Arduino_GFX *g) {   // planks in three shades, their ends staggered
  for (int k = 0; k < 20; k++) {
    g->fillRect(k * 12, 0, 12, 240, WOOD[k % 3]);
    g->fillRect(k * 12, 0, 1, 240, WSEAM);
    for (int y = (k * 37) % 64; y < 240; y += 64) g->fillRect(k * 12, y, 12, 1, WSEAM);
  }
}

static void baseline(Arduino_GFX *g, uint16_t c) {   // a team-colour banner along the top
  g->fillRect(0, 0, 240, 62, c);
  g->fillRect(0, 62, 240, 3, CLINE);
}

static void cMatchup(Arduino_GFX *g, const BuddyData &d, bool me) {
  char t[40], p[12];
  hardwood(g);
  if (!me && bye(d)) {
    baseline(g, CRED);
    shadow(g, 120, 30, "BYE WEEK", 0xFFFF, WSH, ALIGN_CENTER, B22, false, 2);
    shadow(g, 120, 136, "BYE", 0xFFFF, WSH, ALIGN_CENTER, B75, true);
    return;
  }
  uint16_t col = me ? CBLUE : CRED;
  baseline(g, col);
  g->fillRect(84, 65, 72, 34, me ? CBLUE_D : CRED_D);   // the lane (the paint), outlined
  g->fillRect(84, 65, 3, 35, CLINE);
  g->fillRect(153, 65, 3, 35, CLINE);
  g->fillRect(84, 97, 72, 3, CLINE);
  char caps[40];
  upper(caps, sizeof caps, me ? d.ffMyTeam : d.ffOppTeam);
  const buddy::Font &f = fitFont(t, sizeof t, caps, B22, I15, 140);
  shadow(g, 120, 20, t, 0xFFFF, WSH, ALIGN_CENTER, f, false, 2);
  const char *rec = me ? d.ffRecord : oppRecord;
  unsigned place = me ? d.ffRank : oppPlace;
  if (rec[0] && place) {
    ordinal(p, sizeof p, place, true);
    snprintf(t, sizeof t, "%s  |  %s", rec, p);
    buddy::text(g, 120, 46, t, 1, 0xFFFF, ALIGN_CENTER, 0, 1, I11);
  }
  if (projected(d)) {
    pts(p, sizeof p, me ? d.ffMyProj : d.ffOppProj);
    snprintf(t, sizeof t, "PROJ %s", p);
    buddy::text(g, 120, 75, t, 1, 0xFFFF, ALIGN_CENTER, 0, 1, I11);
  }
  pts(t, sizeof t, me ? d.ffMyScore : d.ffOppScore);
  shadow(g, 120, 146, t, 0xFFFF, WSH, ALIGN_CENTER, B75, true);
  if (me) {
    snprintf(t, sizeof t, "LIVE  WEEK %u", (unsigned)d.ffWeek);
    buddy::pill(g, 120, 190, t, 1, LIVE, 0xFFFF, 10, 4, 10, 0, I11);
  } else {
    snprintf(t, sizeof t, "%+.1f", d.ffMyScore - d.ffOppScore);
    buddy::pill(g, 120, 188, t, 1, 0xFFFF, WSH, 12, 3, 11, 0, I18);
  }
}

static void cChanceL(Arduino_GFX *g, const BuddyData &d) {
  char t[16];
  hardwood(g);
  buddy::ring(g, 198, 96, 84, 3, 180.0f, 180.0f, CLINE, false, 0, 1.0f);   // the three-point line
  g->fillRect(213, 66, 4, 42, 0xFFFF);                                     // backboard
  static const uint8_t NET[4][2] = {{186, 190}, {193, 195}, {203, 201}, {210, 206}};
  for (auto &n : NET) buddy::line(g, n[0], 98, n[1], 116, 1, 0xFFFF);
  g->drawFastHLine(190, 116, 17, 0xFFFF);
  g->fillEllipse(198, 96, 14, 5, ORANGE);                                  // rim
  g->fillEllipse(198, 96, 11, 3, WOOD[0]);
  // the shot: the further along its arc, the better your chance
  float c = winChance(d);
  for (int k = 0; k <= 25; k++) {
    float s = k / 25.0f;
    float x = 40 + 152 * s, y = 196 - 106 * s - 184 * s * (1 - s);
    g->fillCircle((int)lroundf(x), (int)lroundf(y), 2, s <= c ? 0xFFFF : WSEAM);
  }
  basketball(g, (int)lroundf(40 + 152 * c), (int)lroundf(196 - 106 * c - 184 * c * (1 - c)), 13, ORANGE, BSEAM);
  snprintf(t, sizeof t, "%d%%", chancePct(c));
  shadow(g, 74, 70, t, 0xFFFF, WSH, ALIGN_CENTER, B49, true);
  buddy::pill(g, 120, 196, decided(c) ? (c >= 1.0f ? "YOU WON" : "YOU LOST") : "WIN CHANCE", 1, WSH, 0xFFFF, 10, 4, 10, 0, I11);
}

static void cChanceR(Arduino_GFX *g, const BuddyData &d) {
  char t[40], v[12], caps[40];
  hardwood(g);
  shadow(g, 120, 30, "PROJECTED", 0xFFFF, WSH, ALIGN_CENTER, B22, false, 2);
  for (int k = 0; k < 2; k++) {
    int y = 64 + k * 52;
    g->fillRoundRect(26, y, 188, 44, 8, k ? CRED : CBLUE);
    pts(v, sizeof v, k ? oppFinal(d) : myFinal(d));
    buddy::text(g, 204, y + 10, v, 1, 0xFFFF, ALIGN_RIGHT, 0, 1, I22);
    upper(caps, sizeof caps, k ? d.ffOppTeam : d.ffMyTeam);
    const buddy::Font &f = fitFont(t, sizeof t, caps, I15, I11, 168 - 20 - buddy::textWidth(I22, v, (int)strlen(v), 1));
    buddy::text(g, 36, y + (&f == &I15 ? 14 : 16), t, 1, 0xFFFF, ALIGN_LEFT, 0, 1, f);
  }
  snprintf(t, sizeof t, "EDGE %+.0f", myFinal(d) - oppFinal(d));
  buddy::pill(g, 120, 178, t, 1, WSH, 0xFFFF, 10, 3, 11, 0, I15);
}

static void cLeadL(Arduino_GFX *g, const BuddyData &d) {
  char t[16];
  int x, y;
  hardwood(g);
  shadow(g, 120, 28, "LEAD TRACKER", 0xFFFF, WSH, ALIGN_CENTER, B22, false, 2);
  g->fillRoundRect(24, 56, 192, 124, 12, WSH);
  leadChart(g, 34, 206, 66, 170, C_UP, C_DOWN, C_ZERO, C_UPL, C_DOWNL, NO_DOTS, NO_DOTS, x, y);
  basketball(g, x, y, 6, ORANGE, BSEAM);   // now
  snprintf(t, sizeof t, "WEEK %u", (unsigned)d.ffWeek);
  buddy::pill(g, 120, 190, t, 1, LIVE, 0xFFFF, 10, 4, 10, 0, I11);
}

static void cLeadR(Arduino_GFX *g, const BuddyData &d) {
  char t[48], a[12], b[12];
  hardwood(g);
  float l = d.ffMyScore - d.ffOppScore;
  bool ahead = l >= 0;
  baseline(g, ahead ? CBLUE : CRED);
  shadow(g, 120, 30, ahead ? "YOU LEAD BY" : "YOU TRAIL BY", 0xFFFF, WSH, ALIGN_CENTER, B22, false, 2);
  snprintf(t, sizeof t, "%.1f", fabsf(l));
  shadow(g, 120, 124, t, 0xFFFF, WSH, ALIGN_CENTER, B75, true);
  snprintf(t, sizeof t, "BEST %+.1f  |  WORST %+.1f", best, worst);
  buddy::pill(g, 120, 164, t, 1, WSH, 0xFFFF, 10, 4, 10, 0, I11);
  pts(a, sizeof a, d.ffMyScore);
  pts(b, sizeof b, d.ffOppScore);
  snprintf(t, sizeof t, "%s - %s", a, b);
  buddy::pill(g, 120, 190, t, 1, 0xFFFF, WSH, 12, 3, 11, 0, I15);
}

static void cSeasonL(Arduino_GFX *g, const BuddyData &d) {
  char t[40], p[12];
  hardwood(g);
  baseline(g, GOLD);
  shadow(g, 120, 30, "SEASON", 0xFFFF, WSH, ALIGN_CENTER, B22, false, 2);
  shadow(g, 120, 112, d.ffRecord, 0xFFFF, WSH, ALIGN_CENTER, B75, true);
  ordinal(p, sizeof p, d.ffRank, true);
  snprintf(t, sizeof t, "%s PLACE", p);
  buddy::pill(g, 120, 152, t, 1, WSH, 0xFFFF, 12, 3, 11, 0, I18);
  if (streak[0] || pointsFor[0]) {
    pts(p, sizeof p, atof(pointsFor));
    if (streak[0] && pointsFor[0]) snprintf(t, sizeof t, "STREAK %s  |  PF %s", streak, p);
    else if (streak[0]) snprintf(t, sizeof t, "STREAK %s", streak);
    else snprintf(t, sizeof t, "PF %s", p);
    buddy::pill(g, 120, 186, t, 1, LIVE, 0xFFFF, 10, 4, 10, 0, I11);
  }
}

static void cSeasonR(Arduino_GFX *g, const BuddyData &d) {   // the coach's chalkboard
  char t[8], name[24];
  g->fillScreen(BOARD);
  buddy::ring(g, 120, 120, 119, 9, 0.0f, 360.0f, FRAME, false, 0, 1.0f);
  buddy::line(g, 99, 197, 109, 207, 2, FAINT);   // an X and an O, like a play drawn on the board
  buddy::line(g, 99, 207, 109, 197, 2, FAINT);
  buddy::ring(g, 136, 202, 6, 2, 0.0f, 360.0f, FAINT, false, 0, 1.0f);
  buddy::text(g, 120, 30, "STANDINGS", 1, CHALK, ALIGN_CENTER, 0, 1, N15);
  buddy::line(g, 74, 52, 166, 52, 2, CHALK);
  for (int i = 0; i < rows; i++) {
    int y = 62 + i * 26;
    bool mine = row[i].place == d.ffRank;
    uint16_t c = mine ? YELLOW : CHALK;
    if (mine) g->fillTriangle(20, y + 2, 20, y + 14, 28, y + 8, YELLOW);
    snprintf(t, sizeof t, "%u", (unsigned)row[i].place);
    buddy::text(g, 34, y, t, 1, c, ALIGN_LEFT, 0, 1, N15);
    buddy::text(g, 208, y, row[i].record, 1, c, ALIGN_RIGHT, 0, 1, N15);
    int room = 208 - 8 - 56 - buddy::textWidth(N15, row[i].record, (int)strlen(row[i].record), 1);
    buddy::text(g, 56, y, fit(name, sizeof name, row[i].team, N15, room), 1, c, ALIGN_LEFT, 0, 1, N15);
  }
}

// ---------------------------------------------------------------- the pages in turn

// The scene for turn 'slot' (DeskBuddy.ino's FANTASY_PAGE_MS), in today's style: the pages with
// something to show, one after the other
static int pageScene(uint32_t slot, const BuddyData &d) {
  uint8_t list[4];
  int n = 0;
  list[n++] = PAGE_MATCHUP;
  if (projected(d) && !bye(d)) list[n++] = PAGE_CHANCE;
  if (!bye(d) && leads >= 2) list[n++] = PAGE_LEAD;
  if (rows) list[n++] = PAGE_SEASON;
  return SCENE_FIRST + (int)(day % STYLES) * 10 + list[slot % n];
}

// A page's left (you) and right screen; style * 10 + page
static void drawLeft(int which, Arduino_GFX *g, const BuddyData &d) {
  switch (which) {
    case STYLE_JUMBOTRON * 10 + PAGE_MATCHUP: jMatchup(g, d, true); break;
    case STYLE_JUMBOTRON * 10 + PAGE_CHANCE:  jChanceL(g, d); break;
    case STYLE_JUMBOTRON * 10 + PAGE_LEAD:    jLeadL(g, d);   break;
    case STYLE_JUMBOTRON * 10 + PAGE_SEASON:  jSeasonL(g, d); break;
    case STYLE_NEON * 10 + PAGE_MATCHUP:      nMatchup(g, d, true); break;
    case STYLE_NEON * 10 + PAGE_CHANCE:       nChanceL(g, d); break;
    case STYLE_NEON * 10 + PAGE_LEAD:         nLeadL(g, d);   break;
    case STYLE_NEON * 10 + PAGE_SEASON:       nSeasonL(g, d); break;
    case STYLE_COURT * 10 + PAGE_MATCHUP:     cMatchup(g, d, true); break;
    case STYLE_COURT * 10 + PAGE_CHANCE:      cChanceL(g, d); break;
    case STYLE_COURT * 10 + PAGE_LEAD:        cLeadL(g, d);   break;
    case STYLE_COURT * 10 + PAGE_SEASON:      cSeasonL(g, d); break;
    default: break;
  }
}

static void drawRight(int which, Arduino_GFX *g, const BuddyData &d) {
  switch (which) {
    case STYLE_JUMBOTRON * 10 + PAGE_MATCHUP: jMatchup(g, d, false); break;
    case STYLE_JUMBOTRON * 10 + PAGE_CHANCE:  jChanceR(g, d); break;
    case STYLE_JUMBOTRON * 10 + PAGE_LEAD:    jLeadR(g, d);   break;
    case STYLE_JUMBOTRON * 10 + PAGE_SEASON:  jSeasonR(g, d); break;
    case STYLE_NEON * 10 + PAGE_MATCHUP:      nMatchup(g, d, false); break;
    case STYLE_NEON * 10 + PAGE_CHANCE:       nChanceR(g, d); break;
    case STYLE_NEON * 10 + PAGE_LEAD:         nLeadR(g, d);   break;
    case STYLE_NEON * 10 + PAGE_SEASON:       nSeasonR(g, d); break;
    case STYLE_COURT * 10 + PAGE_MATCHUP:     cMatchup(g, d, false); break;
    case STYLE_COURT * 10 + PAGE_CHANCE:      cChanceR(g, d); break;
    case STYLE_COURT * 10 + PAGE_LEAD:        cLeadR(g, d);   break;
    case STYLE_COURT * 10 + PAGE_SEASON:      cSeasonR(g, d); break;
    default: break;
  }
}

// A page on both screens, or its left screen with a notification / the volume on the right (the
// designed "idle eyes + notification / volume" scenes' right screens)
static void draw(int scene, Arduino_GFX *left, Arduino_GFX *right, const BuddyData &d) {
  int with = (scene - SCENE_FIRST) / 100 * 100, which = (scene - SCENE_FIRST) % 100;
  drawLeft(which, left, d);
  if (with == WITH_NOTIFICATION) buddyDraw_idle_eyes_notfication_right(right, d);
  else if (with == WITH_VOLUME) buddyDraw_idle_eyes_volume_right(right, d);
  else drawRight(which, right, d);
}

// "court lead + notification" for the Serial Monitor
static inline const char *name(int scene, char *out, size_t n) {
  int with = (scene - SCENE_FIRST) / 100 * 100, which = (scene - SCENE_FIRST) % 100;
  int style = which / 10, page = which % 10;
  if (style < 0 || style >= STYLES || page < 0 || page >= PAGES) return "?";
  snprintf(out, n, "%s %s%s", STYLE_NAMES[style], PAGE_NAMES[page],
           with == WITH_NOTIFICATION ? " + notification" : with == WITH_VOLUME ? " + volume" : "");
  return out;
}

// ---------------------------------------------------------------- the buddy's own screens, with the score
// While a game is on, music and the Claude dashboard stay on the screens and show the score in their
// own style, drawn over the scene DeskBuddy.ino has just drawn: a banner across the bottom of the album
// cover, a row under the Claude usage bars.
static const uint16_t UP = 0x368B, DOWN = 0xFA27, TIED = 0xFDE5;   // rgb(48, 209, 88), (255, 69, 58), (255, 190, 40)
static const uint16_t BANNER = 0x10A3;   // the Claude dashboard's pill text colour

static inline uint16_t leadColor(const BuddyData &d) {
  float l = d.ffMyScore - d.ffOppScore;
  return bye(d) ? 0x9CD4 : l > 0.05f ? UP : l < -0.05f ? DOWN : TIED;
}

static inline void leadWords(char *out, size_t n, const BuddyData &d) {   // "DOWN 80.0"
  float l = d.ffMyScore - d.ffOppScore;
  if (bye(d)) strlcpy(out, "BYE WEEK", n);
  else if (l > 0.05f) snprintf(out, n, "UP %.1f", l);
  else if (l < -0.05f) snprintf(out, n, "DOWN %.1f", -l);
  else strlcpy(out, "TIED", n);
}

static inline void scores(char *out, size_t n, const BuddyData &d, const char *between) {   // "309.0 - 389.0"
  char a[12], b[12];
  pts(a, sizeof a, d.ffMyScore);
  if (bye(d)) {
    strlcpy(out, a, n);
    return;
  }
  pts(b, sizeof b, d.ffOppScore);
  snprintf(out, n, "%s%s%s", a, between, b);
}

static void coverBanner(Arduino_GFX *g, const BuddyData &d) {
  char t[40], w[16];
  uint16_t c = leadColor(d);
  g->fillRoundRect(48, 160, 144, 50, 14, BANNER);
  g->fillRoundRect(48, 160, 144, 4, 2, c);   // a strip in the lead's colour along the top
  scores(t, sizeof t, d, " - ");
  buddy::text(g, 120, 168, t, 1, 0xEF5E, ALIGN_CENTER, 0, 1, I18);
  leadWords(w, sizeof w, d);
  snprintf(t, sizeof t, "%s  |  WK %u", w, (unsigned)d.ffWeek);
  buddy::text(g, 120, 192, t, 1, c, ALIGN_CENTER, 0, 1, I11);
}

static void claudeScore(Arduino_GFX *g, const BuddyData &d) {
  char t[40];
  buddy::line(g, 64, 176, 176, 176, 1, 0x31A7);
  buddy::text(g, 40, 184, "Fantasy", 1, buddy::statusColor(d.claude), ALIGN_LEFT, 0, 1, R15);
  scores(t, sizeof t, d, "-");
  buddy::text(g, 200, 184, t, 1, 0xEF5E, ALIGN_RIGHT, 0, 1, I15);
  leadWords(t, sizeof t, d);
  buddy::text(g, 120, 206, t, 1, leadColor(d), ALIGN_CENTER, 0, 1, I11);
}

// DeskBuddy.ino calls this after drawing one of the designed scenes while a game is on
// On a notification card (the left screen while music plays): the scores, between the app logo and
// the message, on the lead's colour
static void cardScore(Arduino_GFX *g, const BuddyData &d) {
  char t[40];
  scores(t, sizeof t, d, " - ");
  buddy::pill(g, 120, 72, t, 1, leadColor(d), 0x0000, 8, 2, 8, 0, I11);
}

// Under the tokens on the Claude status screen (its left one shows the notification then)
static void claudeRightScore(Arduino_GFX *g, const BuddyData &d) {
  char t[40];
  scores(t, sizeof t, d, " - ");
  buddy::text(g, 120, 194, t, 1, leadColor(d), ALIGN_CENTER, 0, 1, I15);
}

static void overlay(int scene, Arduino_GFX *left, Arduino_GFX *right, const BuddyData &d) {
  switch (scene) {
    case BUDDY_SCENE_MEDIA_PLAYING:          // the album cover is on the left screen of these
    case BUDDY_SCENE_AUDIO_CLAUDE:
    case BUDDY_SCENE_AUDIO_CLAUDE_ANY_STATUS:
    case BUDDY_SCENE_VOLUME_BIG_NUMBER_BOLD:
    case BUDDY_SCENE_MEDIA_PLAYING_VOLUME:
    case BUDDY_SCENE_AUDIO_CLAUDE_VOLUME: coverBanner(left, d); break;
    case BUDDY_SCENE_MEDIA_PLAYING_NOTIFICATION:   // a notification card on the left of these
    case BUDDY_SCENE_AUDIO_CLAUDE_NOTIFICATION:
    case BUDDY_SCENE_AUDIO_CLAUDE_ANY_STATUS_NOTIFICATI: cardScore(left, d); break;
    case BUDDY_SCENE_CLAUDE_DASHBOARD_BOLD:   // the usage bars on the left of these
    case BUDDY_SCENE_CLAUDE_DASHBOARD_BOLD_IDLE: claudeScore(left, d); break;
    case BUDDY_SCENE_CLAUDE_DASHBOARD_BOLD_NOTIFCATION:   // the notification on the left, Claude on the right
    case BUDDY_SCENE_CLAUDE_DASHBOARD_BOLD_NOTIFICATION: claudeRightScore(right, d); break;
    default: break;
  }
}

}  // namespace ff
