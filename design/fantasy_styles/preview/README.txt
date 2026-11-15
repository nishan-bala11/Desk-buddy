Draws the fantasy pages as pictures, with the buddy's real fonts (read from buddy_screens.h) and the
same drawing as Arduino_GFX / the buddy:: helpers, so a design can be checked without uploading.
The page code mirrors DeskBuddy/fantasy_screens.h by hand: change both together.

  fantasy_bball.py    the three basketball styles that are built (Jumbotron, Neon, Court; one a day)
  fantasy_combined.py the music and Claude screens with the score added while a game is on
  fantasy_styles.py   the seven styles first offered (football sample data) + shared helpers
  preview_fantasy.py  the drawing primitives, fonts, and the first "Rings" pages

Needs Python 3 with Pillow. From this folder:

  python fantasy_bball.py ..\..\..\DeskBuddy\buddy_screens.h ..\basketball "%USERPROFILE%\OneDrive\Documents\Arduino\libraries\GFX_Library_for_Arduino\src\font\glcdfont.h"

(the last path is the GFX library's 5x7 font; adjust it if the Arduino libraries folder is elsewhere)
