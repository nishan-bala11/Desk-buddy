// What Claude is doing, made by hand with buddy_screens.h's helpers and fonts (not from the Screen Designer):
// the current step over the Claude screens, a card with Claude's question while it waits for you, and the
// SolidWorks pages (the model as Claude builds it on the left, the steps on the right).
#pragma once

namespace cs {

using buddy::ALIGN_CENTER;

static const int SW_SCENE = 50;   // scene numbers DeskBuddy.ino uses: + 1 with a notification on the right,
static const int SW_WITH_NOTIFICATION = 1, SW_WITH_VOLUME = 2;   // + 2 with the volume
static inline bool isSwScene(int scene) { return scene >= SW_SCENE && scene <= SW_SCENE + SW_WITH_VOLUME; }

static const uint16_t SW_RED = 0xEA26;
static const uint16_t WHITE = 0xEF5E, DIM = 0x9CD4, FAINT = 0x2946, CARD = 0x10A3;
static const buddy::Font &I18 = buddyFont_g_Inter_700_18_info, &I15 = buddyFont_g_Inter_700_15_info,
                         &I11 = buddyFont_g_Inter_700_11_info, &R15 = buddyFont_g_Inter_400_15_info,
                         &R12 = buddyFont_g_Inter_400_12_info, &B22 = buddyFont_g_Bebas_Neue_400_22_info;

static const int RECENT = 3;

struct Activity {
  char what[24] = "";     // "Editing"
  char target[40] = "";   // "claude_screens.h"
};

struct Ask {
  char title[20] = "";    // "NEEDS YOU" (empty = no question)
  char text[180] = "";
  char opt[2][28] = {};   // the next-step box's reply buttons, picked with the left / right button
};

struct SolidWorks {
  char doc[32] = "";
  char step[32] = "";
  char recent[RECENT][26] = {};
  uint16_t steps = 0;
  uint32_t at = 0;        // millis() of the last message (0 = none yet)
};

// ---------------------------------------------------------------- the current step
// Below the tokens on the Claude dashboard's right screen
static void dashboardActivity(Arduino_GFX *g, const Activity &a, const BuddyData &d) {
  buddy::text(g, 120, 188, a.what, 1, buddy::statusColor(d.claude), ALIGN_CENTER, 22, 1, I15);
  buddy::text(g, 120, 206, a.target, 1, DIM, ALIGN_CENTER, 21, 1, R12);
}

// In place of the status line ("Working") on the music + Claude right screen
static void audioActivity(Arduino_GFX *g, const Activity &a, const BuddyData &d) {
  char t[66];
  g->fillRect(24, 150, 192, 24, 0x0000);
  if (a.target[0]) snprintf(t, sizeof t, "%s %s", a.what, a.target);
  else strlcpy(t, a.what, sizeof t);
  buddy::text(g, 120, 154, t, 1, buddy::statusColor(d.claude), ALIGN_CENTER, 25, 1, R12);
}

// ---------------------------------------------------------------- Claude's question
static void askCard(Arduino_GFX *g, const Ask &a) {
  g->fillScreen(0x0000);
  buddy::ring(g, 120, 120, 119, 6, 0.0f, 360.0f, buddy::statusColor('A'), false, FAINT, 1.0f);
  char t[32];
  snprintf(t, sizeof t, "CLAUDE %s", a.title);
  buddy::text(g, 120, 36, t, 1, buddy::statusColor('A'), ALIGN_CENTER, 22, 1, I15);
  g->drawFastHLine(64, 58, 112, FAINT);
  buddy::text(g, 120, 68, a.text, 1, WHITE, ALIGN_CENTER, 23, 5, R15);
  buddy::text(g, 120, 190, "Answer in Claude", 1, DIM, ALIGN_CENTER, 0, 1, I11);
}

// The question on the left, its two buttons on the right: top = left button, bottom = right button
static void askChoice(Arduino_GFX *l, Arduino_GFX *r, const Ask &a) {
  askCard(l, a);
  l->fillRect(40, 182, 160, 24, 0x0000);   // no "Answer in Claude": the buttons answer it
  r->fillScreen(0x0000);
  buddy::ring(r, 120, 120, 119, 6, 0.0f, 360.0f, buddy::statusColor('A'), false, FAINT, 1.0f);
  for (int i = 0; i < 2; i++) {
    if (!a.opt[i][0]) continue;
    int y = i ? 128 : 56;
    r->fillRoundRect(28, y, 184, 56, 14, i ? CARD : WHITE);
    buddy::text(r, 120, y + 9, i ? "RIGHT BUTTON" : "LEFT BUTTON", 1, i ? DIM : 0x4208, ALIGN_CENTER, 0, 1, I11);
    buddy::text(r, 120, y + 26, a.opt[i], 1, i ? WHITE : 0x0000, ALIGN_CENTER, 19, 1, I15);
  }
}

// ---------------------------------------------------------------- SolidWorks
// The model, or a drawn box until the first picture arrives
static void swLeft(Arduino_Canvas *g, const uint16_t *picture) {
  if (picture) {
    memcpy(g->getFramebuffer(), picture, 240 * 240 * 2);
  } else {
    g->fillScreen(0x0000);
    const int x[] = {120, 170, 120, 70}, y[] = {62, 90, 118, 90}, h = 58;
    for (int i = 0; i < 4; i++) {
      int j = (i + 1) % 4;
      buddy::line(g, x[i], y[i], x[j], y[j], 2, SW_RED);
      if (i != 0) buddy::line(g, x[i], y[i], x[i], y[i] + h, 2, SW_RED);
      if (i >= 1 && i < 3) buddy::line(g, x[i], y[i] + h, x[i + 1], y[i + 1] + h, 2, SW_RED);
    }
    buddy::text(g, 120, 192, "Waiting for the model", 1, DIM, ALIGN_CENTER, 0, 1, R12);
  }
  buddy::ring(g, 120, 120, 119, 3, 0.0f, 360.0f, SW_RED, false, FAINT, 1.0f);
}

static void swRight(Arduino_GFX *g, const SolidWorks &s, const BuddyData &d, const char *song) {
  char t[32];
  g->fillScreen(0x0000);
  buddy::ring(g, 120, 120, 119, 3, 0.0f, 360.0f, SW_RED, false, FAINT, 1.0f);
  buddy::text(g, 120, 22, "SOLIDWORKS", 1, SW_RED, ALIGN_CENTER, 0, 1, I11);
  buddy::text(g, 120, 39, s.doc[0] ? s.doc : "New model", 1, DIM, ALIGN_CENTER, 22, 1, R12);
  buddy::text(g, 120, 62, s.step[0] ? s.step : "Getting ready", 1, WHITE, ALIGN_CENTER, 17, 2, I18);
  snprintf(t, sizeof t, "STEP %u", (unsigned)s.steps);
  buddy::text(g, 120, 112, t, 1, buddy::statusColor(d.claude), ALIGN_CENTER, 0, 1, B22);
  g->drawFastHLine(56, 138, 128, FAINT);
  for (int i = 0; i < RECENT; i++) buddy::text(g, 120, 146 + i * 16, s.recent[i], 1, DIM, ALIGN_CENTER, 26, 1, R12);
  if (song[0]) buddy::text(g, 120, 198, song, 1, 0x8C72, ALIGN_CENTER, 22, 1, R12);
}

}  // namespace cs
