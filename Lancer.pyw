# Double-click launcher: opens the app without a console, from any folder.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hockey_widget.app import main

main()
