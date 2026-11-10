# Builds dist\HockeyScoreWidget.exe: one file, no console window.
python -m PyInstaller --noconfirm --onefile --windowed --name HockeyScoreWidget `
  --icon assets\icon.ico `
  --add-data "assets\icon.ico;assets" `
  --add-data "hockey_widget\widget.html;hockey_widget" `
  --add-data "hockey_widget\fonts;hockey_widget\fonts" `
  --hidden-import resvg_py `
  --collect-data customtkinter `
  Lancer.pyw
