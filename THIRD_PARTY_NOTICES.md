# Third-party notices

Hockey Score Widget is free software under the GNU General Public License v3.0 (see `LICENSE`).
The Windows program (`HockeyScoreWidget.exe`) also contains the components below, each under its own licence.
All of them allow free use, copying and redistribution. Their full licence texts ship with each package
and are linked here.

## Bundled in the program

| Component | Version | Licence | Use | Source |
| --- | --- | --- | --- | --- |
| Python | 3.14 | PSF License 2.0 | Language runtime | https://www.python.org/psf/license/ |
| Tcl/Tk (tkinter) | 9.0 | Tcl/Tk License (BSD-style) | Window toolkit | https://www.tcl.tk/software/tcltk/license.html |
| CustomTkinter | 6.0.0 | MIT | Modern widgets for the window | https://github.com/TomSchimansky/CustomTkinter |
| darkdetect | 0.8.0 | BSD-3-Clause | Dark mode detection (CustomTkinter) | https://github.com/albertosottile/darkdetect |
| packaging | 26.3 | Apache-2.0 or BSD-2-Clause | Version parsing (CustomTkinter) | https://github.com/pypa/packaging |
| simpleobsws | 1.4.3 | MIT | OBS WebSocket v5 client | https://github.com/IRLToolkit/simpleobsws |
| websockets | 17.1 | BSD-3-Clause | WebSocket connection (simpleobsws) | https://github.com/python-websockets/websockets |
| msgpack | 1.2.2 | Apache-2.0 | Message encoding (simpleobsws) | https://github.com/msgpack/msgpack-python |
| Pillow | 12.3.0 | MIT-CMU | Draws the scoreboard preview | https://github.com/python-pillow/Pillow |
| resvg-py | 0.5.0 | MIT | Turns SVG logos into images for the preview | https://github.com/baseplate-admin/resvg-py |
| resvg | (in resvg-py) | Apache-2.0 or MIT | SVG renderer used by resvg-py | https://github.com/linebender/resvg |
| Barlow Condensed font | 1.x | SIL Open Font License 1.1 | Scoreboard font (preview and widget) | https://github.com/jpt/barlow |

The Barlow Condensed licence text is in `hockey_widget/fonts/OFL.txt` (installed as `OFL-Barlow-Condensed.txt`).
Copyright 2017 The Barlow Project Authors.

## Used to build the program (not inside it, except the bootloader)

| Component | Licence | Note |
| --- | --- | --- |
| PyInstaller | GPL-2.0-or-later with bootloader exception | The exception allows shipping the bootloader inside any program. |
| Inno Setup | Inno Setup License (free, modified BSD-style) | Builds `HockeyScoreWidget-Setup.exe`. |

## Data and trademarks

- Scores come from the public NHL web API (`api-web.nhle.com`). It is free, needs no key, and is not officially
  documented: the NHL can change or close it at any time.
- Team logos are **not** shipped with the program. The widget and the preview load them at run time from the NHL's
  own servers (`assets.nhle.com`), the same way the NHL website does.
- NHL, the NHL Shield, team names and logos are registered trademarks of the National Hockey League and its teams.
  This project is independent and is not affiliated with, endorsed or sponsored by the NHL or any team.
  Team colours in `hockey_widget/teams.py` are plain colour values used to identify each team.
- Google Fonts serves Barlow Condensed to the OBS widget page (`fonts.googleapis.com`): OBS downloads it when it
  opens the widget.
