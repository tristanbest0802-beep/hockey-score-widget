"""Main window: sidebar on the left, three pages (preview, customise, settings)."""

from __future__ import annotations

import ctypes
import re
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import colorchooser, filedialog

import customtkinter as ctk

from hockey_widget import nhl_api, obs, preview, settings as settings_store, teams
from hockey_widget.server import start_server
from hockey_widget.settings import PRESETS, SIZES
from hockey_widget.widget_state import LOGO_TYPES, DelayedFeed, build_state, custom_logo, team_color

APP_TITLE = "Hockey Score Widget"
TAB_NAMES = ("Aperçu", "Personnaliser", "Réglages")

# Neutral darks; green (the streamer's soft jade) only as accent: active tab, controls, titles.
COL_BG = "#111214"
COL_SIDEBAR = "#0B0C0D"
COL_CARD = "#18191C"
COL_CARD_HOVER = "#212327"
COL_BORDER = "#2A2C31"
GREEN = "#2D7F55"          # buttons: white text on it is about 5:1 (WCAG AA)
GREEN_HOVER = "#256B47"
GREEN_TEXT = "#6FCF9A"     # green used as text on the dark background
COL_TEXT = "#ECEDEF"
COL_MUTED = "#9A9DA4"
COL_RED = "#E5484D"
COL_STAGE = "#0B0C0D"      # behind the scoreboard preview, like a dark stream scene
FONT_FAMILY = "Segoe UI"   # same family as OBS-Dynamics, always present on Windows
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def apply_theme() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    theme = ctk.ThemeManager.theme
    for widget, keys in {
        "CTkButton": ("fg_color", "hover_color"),
        "CTkSegmentedButton": ("selected_color", "selected_hover_color"),
        "CTkSwitch": ("progress_color", None),
        "CTkSlider": ("button_color", "button_hover_color"),
    }.items():
        theme[widget][keys[0]] = [GREEN, GREEN]
        if keys[1]:
            theme[widget][keys[1]] = [GREEN_HOVER, GREEN_HOVER]
    theme["CTkSlider"]["progress_color"] = [GREEN, GREEN]
    # Default greys clash with the green-tinted dark: tint inputs to match.
    theme["CTkEntry"].update(fg_color=["#0E0F11", "#0E0F11"], border_color=[COL_BORDER, COL_BORDER])
    theme["CTkSegmentedButton"].update(fg_color=[COL_CARD_HOVER] * 2, unselected_color=[COL_CARD_HOVER] * 2,
                                       unselected_hover_color=[COL_BORDER] * 2)
    theme["CTkSwitch"].update(fg_color=[COL_BORDER] * 2)
    theme["CTkSlider"].update(fg_color=[COL_BORDER] * 2)
    theme["CTkScrollbar"].update(button_color=[COL_BORDER] * 2, button_hover_color=[GREEN_HOVER] * 2)


def card(master, **kwargs) -> ctk.CTkFrame:
    return ctk.CTkFrame(master, fg_color=COL_CARD, corner_radius=12, border_width=1,
                        border_color=COL_BORDER, **kwargs)


def section_title(master, text: str) -> ctk.CTkFrame:
    """Card title with a short green bar in front: one of the few green touches."""
    box = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkFrame(box, fg_color=GREEN, width=4, height=16, corner_radius=2).pack(side="left", padx=(0, 9))
    ctk.CTkLabel(box, text=text, font=font(13, "bold"), text_color=COL_TEXT, anchor="w").pack(side="left")
    return box


def ghost_button(master, text: str, command, width: int = 110) -> ctk.CTkButton:
    return ctk.CTkButton(master, text=text, width=width, height=30, font=font(12), fg_color="transparent",
                         border_width=1, border_color=COL_BORDER, hover_color=COL_CARD_HOVER,
                         text_color=COL_TEXT, command=command)


def muted(master, text: str, **kwargs) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, font=font(12), text_color=COL_MUTED, anchor="w",
                        justify="left", **kwargs)


def rounded_rect(canvas: tk.Canvas, x0, y0, x1, y1, r, **kwargs) -> int:
    points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
              x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class GameList(tk.Canvas):
    """Today's games, drawn on a single canvas.

    The rows are canvas drawings, not one widget each: scrolling moves them as one block,
    with no tearing however fast the wheel turns.
    """

    ROW, GAP, STEP = 42, 6, 40

    def __init__(self, master, on_select) -> None:
        super().__init__(master, bg=COL_CARD, highlightthickness=0, bd=0, yscrollincrement=1)
        self.on_select = on_select
        self.games: list[nhl_api.Game] = []
        self.selected_id: int | None = None
        self.hover: int | None = None
        self.scrollbar = ctk.CTkScrollbar(master, command=self.yview, button_color=COL_BORDER,
                                          button_hover_color=GREEN_HOVER)
        self.configure(yscrollcommand=self._on_scroll)
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<Button-1>", self._on_click)

    def _scale(self) -> float:
        return ctk.ScalingTracker.get_widget_scaling(self)

    def set_games(self, games: list[nhl_api.Game], selected_id: int | None) -> None:
        self.games, self.selected_id = games, selected_id
        self.draw()

    def _row_at(self, y: float) -> int | None:
        pitch = (self.ROW + self.GAP) * self._scale()
        index, offset = divmod(self.canvasy(y), pitch)
        inside = offset <= self.ROW * self._scale()
        return int(index) if inside and 0 <= index < len(self.games) else None

    def draw(self) -> None:
        self.delete("all")
        k, width = self._scale(), self.winfo_width()
        if not self.games:
            self.create_text(6 * k, 18 * k, text="Aucun match chargé pour l'instant.", anchor="w",
                             fill=COL_MUTED, font=(FONT_FAMILY, -round(12 * k)))
            self.configure(scrollregion=(0, 0, width, 40 * k))
            return
        bold, normal = (FONT_FAMILY, -round(13 * k), "bold"), (FONT_FAMILY, -round(13 * k))
        for i, game in enumerate(self.games):
            y0 = i * (self.ROW + self.GAP) * k
            y1 = y0 + self.ROW * k
            mid = (y0 + y1) / 2
            selected = game.id == self.selected_id
            fill = GREEN if selected else (COL_CARD_HOVER if i == self.hover else COL_CARD)
            rounded_rect(self, 1, y0 + 1, width - 2, y1 - 1, 8 * k, fill=fill,
                         outline="" if selected else COL_BORDER)
            score = "" if game.away.score is None else f"{game.away.score} – {game.home.score}"
            self.create_text(16 * k, mid, anchor="w", fill=COL_TEXT, font=bold,
                             text=f"{game.away.abbrev}  @  {game.home.abbrev}")
            self.create_text(150 * k, mid, anchor="w", fill=COL_TEXT, font=bold, text=score)
            self.create_text(width - 16 * k, mid, anchor="e", font=bold if selected else normal,
                             fill="#FFFFFF" if selected else COL_MUTED, text=nhl_api.status_text(game))
        self.configure(scrollregion=(0, 0, width, len(self.games) * (self.ROW + self.GAP) * k))

    def _on_scroll(self, first, last) -> None:
        self.scrollbar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.scrollbar.grid_remove()
        else:
            self.scrollbar.grid()

    def _on_wheel(self, event) -> None:
        if self.yview() != (0.0, 1.0):
            self.yview_scroll(round(-event.delta / 120 * self.STEP * self._scale()), "units")
            self._on_motion(event)

    def _set_hover(self, index: int | None) -> None:
        if index != self.hover:
            self.hover = index
            self.configure(cursor="hand2" if index is not None else "")
            self.draw()

    def _on_motion(self, event) -> None:
        self._set_hover(self._row_at(event.y))

    def _on_click(self, event) -> None:
        index = self._row_at(event.y)
        if index is not None:
            self.on_select(self.games[index])


class App(ctk.CTk):
    def __init__(self, settings_file: Path | None = None, start_services: bool = True) -> None:
        apply_theme()
        super().__init__(fg_color=COL_BG)
        self.title(APP_TITLE)
        self.geometry("1100x780")
        self.minsize(980, 720)  # every page fits: nothing scrolls except the games list
        icon = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
        if icon.exists():  # CustomTkinter sets its own icon after ~200 ms: set ours after it
            self.after(300, lambda: self.iconbitmap(str(icon)))

        self.settings_file = settings_file
        self.settings = settings_store.load(settings_file)
        self.games: list[nhl_api.Game] = []
        self.feed = DelayedFeed()
        self.server = None
        self._stop = threading.Event()
        self.logos = preview.LogoCache()
        self.preview_labels: list[ctk.CTkLabel] = []

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.pages: dict[str, ctk.CTkFrame] = {}
        for name, builder in zip(TAB_NAMES, (self._build_preview, self._build_customise, self._build_settings)):
            page = ctk.CTkFrame(self, fg_color=COL_BG, corner_radius=0)
            page.grid_columnconfigure(0, weight=1)
            builder(page)
            self.pages[name] = page
        self.current_page = ""
        self.show_page(TAB_NAMES[0])
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._push_state()
        if start_services:
            self._start_server()
            threading.Thread(target=self._poll_loop, daemon=True).start()
        self.after(1000, self._preview_loop)

    # ----- sidebar -------------------------------------------------------
    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COL_SIDEBAR, corner_radius=0, width=220)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(4, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=22, pady=(26, 30))
        ctk.CTkLabel(brand, text="Score", font=font(20, "bold"), text_color=GREEN_TEXT).pack(side="left")
        ctk.CTkLabel(brand, text=" Hockey", font=font(20, "bold"), text_color=COL_TEXT).pack(side="left")

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for row, name in enumerate(TAB_NAMES, start=1):
            button = ctk.CTkButton(bar, text=name, anchor="w", height=40, corner_radius=8,
                                   fg_color="transparent", hover_color=COL_CARD_HOVER,
                                   text_color=COL_MUTED, font=font(14),
                                   command=lambda n=name: self.show_page(n))
            button.grid(row=row, column=0, sticky="ew", padx=12, pady=2)
            self.nav_buttons[name] = button

        status = ctk.CTkFrame(bar, fg_color="transparent")
        status.grid(row=5, column=0, sticky="sew", padx=20, pady=20)
        self.api_status = self._status_line(status, "API NHL : en attente")
        self.server_status = self._status_line(status, "Widget : arrêté")

    def _status_line(self, master, text: str) -> ctk.CTkLabel:
        label = ctk.CTkLabel(master, text="●  " + text, font=font(12), text_color=COL_MUTED,
                             anchor="w", justify="left", wraplength=180)
        label.pack(fill="x", pady=2)
        return label

    def _set_status(self, label: ctk.CTkLabel, text: str, ok: bool) -> None:
        label.configure(text="●  " + text, text_color=GREEN_TEXT if ok else COL_RED)

    def show_page(self, name: str) -> None:
        if self.current_page:
            self.pages[self.current_page].grid_remove()
        self.pages[name].grid(row=0, column=1, sticky="nsew")
        for other, button in self.nav_buttons.items():
            active = other == name
            button.configure(fg_color=GREEN if active else "transparent",
                             hover_color=GREEN_HOVER if active else COL_CARD_HOVER,
                             text_color="#FFFFFF" if active else COL_MUTED,
                             font=font(14, "bold" if active else "normal"))
        self.current_page = name
        self.after(50, self._render_preview)  # fit the preview once the page has its real width

    def _page_header(self, page, title: str, subtitle: str) -> None:
        ctk.CTkLabel(page, text=title, font=font(24, "bold"), text_color=COL_TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 0))
        muted(page, subtitle).grid(row=1, column=0, sticky="ew", padx=28, pady=(2, 18))

    # ----- page 1: preview -----------------------------------------------
    def _build_preview(self, page) -> None:
        self._page_header(page, "Aperçu", "Ce que le widget affiche dans OBS, avec le retard choisi.")

        self._live_panel(page, row=2)

        follow = card(page)
        follow.grid(row=3, column=0, sticky="ew", padx=28, pady=(16, 0))
        follow.grid_columnconfigure(1, weight=1)
        section_title(follow, "Match suivi").grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 6))
        self.auto_var = ctk.BooleanVar(value=self.settings["auto_favourite"])
        ctk.CTkSwitch(follow, text="Suivre automatiquement l'équipe préférée", variable=self.auto_var,
                      font=font(13), command=self._on_follow_change).grid(row=1, column=0, sticky="w", padx=18)
        self.favourite_entry = ctk.CTkEntry(follow, width=80, font=font(13), justify="center")
        self.favourite_entry.insert(0, self.settings["favourite"])
        self.favourite_entry.grid(row=1, column=2, sticky="e", padx=18)
        self.favourite_entry.bind("<Return>", lambda _e: self._on_follow_change())
        self.favourite_entry.bind("<FocusOut>", lambda _e: self._on_follow_change())
        muted(follow, "Code de l'équipe, par exemple MTL. Sinon, choisissez un match ci-dessous.").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=18, pady=(4, 14))

        games_card = card(page)
        games_card.grid(row=4, column=0, sticky="nsew", padx=28, pady=(16, 24))
        games_card.grid_columnconfigure(0, weight=1)
        games_card.grid_rowconfigure(1, weight=1)
        page.grid_rowconfigure(4, weight=1)
        head = ctk.CTkFrame(games_card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        section_title(head, "Matchs du jour").pack(side="left")
        ctk.CTkButton(head, text="Actualiser", width=100, height=30, font=font(12, "bold"),
                      command=lambda: threading.Thread(target=self._fetch, daemon=True).start()).pack(side="right")
        self.games_list = GameList(games_card, self._select_game)
        self.games_list.grid(row=1, column=0, sticky="nsew", padx=(14, 4), pady=(0, 14))
        self.games_list.scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 14))
        self._render_games()

    def _render_games(self) -> None:
        followed = self._followed_game()
        self.games_list.set_games(self.games, followed.id if followed else None)

    def _select_game(self, game: nhl_api.Game) -> None:
        self.settings["selected_game"] = game.id
        if self.settings["auto_favourite"] and not game.has_team(self.settings["favourite"]):
            self.auto_var.set(False)  # a manual pick wins over the favourite team
            self.settings["auto_favourite"] = False
        self._save_and_push()
        self._render_games()

    def _on_follow_change(self) -> None:
        self.settings["auto_favourite"] = self.auto_var.get()
        self.settings["favourite"] = self.favourite_entry.get().strip().upper()[:3]
        self._save_and_push()
        self._render_games()

    def _followed_game(self) -> nhl_api.Game | None:
        favourite = self.settings["favourite"] if self.settings["auto_favourite"] else ""
        return nhl_api.pick_game(self.games, favourite, self.settings["selected_game"])

    def _live_panel(self, master, row: int, pady=(0, 0)) -> None:
        """Scoreboard preview plus the widget link: the same panel on Aperçu and Personnaliser."""
        panel = card(master)
        panel.grid(row=row, column=0, sticky="ew", padx=28, pady=pady)
        panel.grid_columnconfigure(0, weight=1)
        stage = ctk.CTkFrame(panel, fg_color=COL_STAGE, corner_radius=10)
        stage.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        label = ctk.CTkLabel(stage, text="Aucun match à afficher", font=font(13), text_color=COL_MUTED, height=96)
        label.pack(fill="x", padx=12, pady=12)
        self.preview_labels.append(label)

        link = ctk.CTkFrame(panel, fg_color="transparent")
        link.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        ctk.CTkLabel(link, text="Lien OBS", font=font(12, "bold"), text_color=COL_MUTED).pack(side="left")
        url = ctk.CTkLabel(link, text=self.widget_url(), font=font(12), text_color=GREEN_TEXT)
        url.pack(side="left", padx=10)
        self.url_labels = [*getattr(self, "url_labels", []), url]
        done = muted(link, "")
        ctk.CTkButton(link, text="Ouvrir dans le navigateur", width=170, height=30, font=font(12),
                      fg_color="transparent", border_width=1, border_color=COL_BORDER, hover_color=COL_CARD_HOVER,
                      text_color=COL_TEXT, command=lambda: webbrowser.open(self.widget_url())).pack(side="right")
        ctk.CTkButton(link, text="Copier le lien", width=120, height=30, font=font(12, "bold"),
                      command=lambda: self._copy_url(done)).pack(side="right", padx=8)
        done.pack(side="right", padx=4)

    def _render_preview(self) -> None:
        state = self.feed.current(self.settings["delay_seconds"])
        image = preview.render(state, self.settings, self.logos,
                               custom_logo=lambda abbrev: custom_logo(abbrev, self.settings))
        for label in self.preview_labels:
            if image is None:
                label.configure(image=None, text="Aucun match à afficher")
                label._preview = None
                continue
            room = max(200, label.winfo_width() - 8) if label.winfo_width() > 1 else 640
            factor = min(0.5, room / image.width)  # drawn at 2x: sharp on high-DPI screens
            size = (round(image.width * factor), round(image.height * factor))
            label._preview = ctk.CTkImage(light_image=image, dark_image=image, size=size)
            label.configure(image=label._preview, text="")

    def _preview_loop(self) -> None:
        self._render_preview()  # every second: delayed score, NHL logos once downloaded
        if not self._thumbs_ready:
            self._refresh_presets()
        if not self._stop.is_set():
            self.after(1000, self._preview_loop)

    # ----- page 2: customise ---------------------------------------------
    SIZE_GROUPS = (
        ("Barre", ("bar_height", "radius", "border", "skew", "team_padding")),
        ("Logo et nom", ("logo_size", "logo_gap", "name_size", "name_spacing")),
        ("Score", ("score_size", "score_width", "score_spacing")),
        ("Temps", ("clock_size", "clock_spacing", "period_size", "center_width")),
    )
    SWITCHES = (("team_colors", "Couleurs des équipes"), ("show_logos", "Logos"), ("show_names", "Noms"),
                ("show_status", "Bloc du temps"), ("show_period", "Période"), ("show_sog", "Tirs au but"),
                ("show_gloss", "Reflet brillant"))

    SECTIONS = ("Presets", "Style", "Équipes", "Barre et logo", "Score et temps", "Couleurs et retard")

    def _build_customise(self, page) -> None:
        self._page_header(page, "Personnaliser", "Chaque réglage s'applique tout de suite dans OBS.")
        self._live_panel(page, row=2)
        self.section_var = ctk.StringVar(value=self.SECTIONS[0])
        ctk.CTkSegmentedButton(page, values=list(self.SECTIONS), variable=self.section_var, font=font(13),
                               height=34, command=self._show_section).grid(
            row=3, column=0, sticky="w", padx=28, pady=(16, 12))
        self.sections: dict[str, ctk.CTkFrame] = {}

        def section(name: str) -> ctk.CTkFrame:
            frame = ctk.CTkFrame(page, fg_color="transparent")
            frame.grid(row=4, column=0, sticky="new", padx=28)
            frame.grid_columnconfigure((0, 1), weight=1, uniform="half")
            self.sections[name] = frame
            return frame

        # Presets: every ready-made look, one click each.
        presets = card(section("Presets"))
        presets.grid(row=0, column=0, columnspan=2, sticky="ew")
        presets.grid_columnconfigure((0, 1, 2), weight=1, uniform="third")
        section_title(presets, "Presets").grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 2))
        muted(presets, "Un clic applique le style et ses tailles. Noms, couleurs et logos des équipes restent "
                       "les vôtres.").grid(row=1, column=0, columnspan=3, sticky="w", padx=18, pady=(0, 8))
        self.preset_buttons = {}
        for index, (key, (label, _values)) in enumerate(PRESETS.items()):
            button = ctk.CTkButton(presets, text=label, compound="top", height=74, font=font(12, "bold"),
                                   fg_color=COL_STAGE, hover_color=COL_CARD_HOVER, text_color=COL_TEXT,
                                   border_width=1, border_color=COL_BORDER,
                                   command=lambda k=key: self._apply_preset(k))
            button.grid(row=2 + index // 3, column=index % 3, sticky="ew", padx=(18 if index % 3 == 0 else 6,
                        18 if index % 3 == 2 else 6), pady=5)
            self.preset_buttons[key] = button
        muted(presets, "").grid(row=5, column=0, pady=4)
        self._thumbs_ready = False
        self._refresh_presets()

        # Style: what is shown.
        style = card(section("Style"))
        style.grid(row=0, column=0, columnspan=2, sticky="ew")
        section_title(style, "Style").grid(row=0, column=0, columnspan=4, sticky="w", padx=18, pady=(14, 8))
        self.look_vars = {}
        for index, (key, text) in enumerate(self.SWITCHES):
            var = ctk.BooleanVar(value=self.settings[key])
            ctk.CTkSwitch(style, text=text, variable=var, font=font(13), command=self._on_look_change).grid(
                row=2 + index // 3, column=index % 3, sticky="w", padx=18, pady=4)
            self.look_vars[key] = var
        muted(style, "").grid(row=5, column=0, pady=2)

        # Teams of the followed game: name, colour, logo.
        names = card(section("Équipes"))
        names.grid(row=0, column=0, columnspan=2, sticky="ew")
        names.grid_columnconfigure(1, weight=1)
        section_title(names, "Équipes du match").grid(row=0, column=0, columnspan=5, sticky="w", padx=18, pady=(14, 6))
        muted(names, "Nom, couleur et logo de chaque équipe. « Par défaut » remet ceux de la LNH.").grid(
            row=1, column=0, columnspan=5, sticky="w", padx=18)
        self.format_var = ctk.StringVar(value="Abréviation" if self.settings["name_format"] == "abbrev" else "Nom")
        ctk.CTkSegmentedButton(names, values=["Abréviation", "Nom"], variable=self.format_var, font=font(12),
                               command=lambda _v: self._on_look_change()).grid(
            row=2, column=0, columnspan=5, sticky="w", padx=18, pady=(10, 8))
        self.name_rows = []
        self.team_buttons = []
        for row in (3, 4):
            code = ctk.CTkLabel(names, text="", font=font(13, "bold"), text_color=COL_TEXT, width=150, anchor="w")
            code.grid(row=row, column=0, sticky="w", padx=18, pady=4)
            entry = ctk.CTkEntry(names, font=font(13), placeholder_text="Nom de l'API")
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            entry.bind("<Return>", lambda _e: self._on_names_change())
            entry.bind("<FocusOut>", lambda _e: self._on_names_change())
            index = row - 3
            colour = ctk.CTkButton(names, text="", width=90, height=30, font=font(12, "bold"), border_width=1,
                                   border_color=COL_BORDER, command=lambda i=index: self._pick_team_colour(i))
            colour.grid(row=row, column=2, padx=(10, 0), pady=4)
            logo = ghost_button(names, "Logo LNH", lambda i=index: self._pick_team_logo(i), width=120)
            logo.grid(row=row, column=3, padx=(10, 0), pady=4)
            reset = ghost_button(names, "Par défaut", None, width=90)
            reset.grid(row=row, column=4, padx=(10, 18), pady=4)
            self.name_rows.append((code, entry, reset))
            self.team_buttons.append((colour, logo))
        muted(names, "").grid(row=5, column=0, pady=4)

        # Sizes: two cards side by side per section.
        self.size_widgets = {}
        for index, (title, keys) in enumerate(self.SIZE_GROUPS):
            name = "Barre et logo" if index < 2 else "Score et temps"
            host = self.sections.get(name) or section(name)
            box = card(host)
            box.grid(row=0, column=index % 2, sticky="nsew", padx=(0, 8) if index % 2 == 0 else (8, 0))
            box.grid_columnconfigure(1, weight=1)
            head = ctk.CTkFrame(box, fg_color="transparent")
            head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 6))
            section_title(head, title).pack(side="left")
            ghost_button(head, "Réinitialiser", lambda k=keys: self._reset_sizes(k), width=96).pack(side="right")
            for row, key in enumerate(keys, start=1):
                self._size_row(box, row, key)
            muted(box, "").grid(row=len(keys) + 1, column=0, pady=2)

        colours = card(section("Couleurs et retard"))
        colours.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        colours.grid_columnconfigure(0, weight=1)
        section_title(colours, "Couleurs").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(14, 6))
        self.colour_buttons = {}
        for row, (key, text) in enumerate((("accent", "Fond des équipes"),
                                           ("background", "Fond du temps"), ("text", "Texte")), start=1):
            ctk.CTkLabel(colours, text=text, font=font(13), text_color=COL_TEXT, anchor="w").grid(
                row=row, column=0, sticky="w", padx=18, pady=4)
            button = ctk.CTkButton(colours, text=self.settings[key], width=120, height=30, font=font(12, "bold"),
                                   fg_color=self.settings[key], hover_color=self.settings[key],
                                   text_color=self._ink(self.settings[key]),
                                   border_width=1, border_color=COL_BORDER,
                                   command=lambda k=key: self._pick_colour(k))
            button.grid(row=row, column=1, sticky="e", padx=(10, 18), pady=4)
            self.colour_buttons[key] = button
        muted(colours, "Fond des équipes : utilisé quand « Couleurs des équipes » est coupé.", wraplength=280).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=18, pady=(4, 14))

        delay = card(self.sections["Couleurs et retard"])
        delay.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        delay.grid_columnconfigure(0, weight=1)
        section_title(delay, "Retard du score").grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        muted(delay, "Le flux vidéo a du retard sur l'API (OnHockey, RDS, TVA Sports : ça varie). "
                     "Décalez le score pour ne pas annoncer un but avant l'image.", wraplength=280).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=18)
        self.delay_label = ctk.CTkLabel(delay, text="", font=font(13, "bold"), text_color=GREEN_TEXT, width=70)
        self.delay_label.grid(row=2, column=1, padx=18)
        self.delay_slider = ctk.CTkSlider(delay, from_=0, to=120, number_of_steps=120,
                                          command=lambda v: self._on_delay(int(v), save=False))
        self.delay_slider.set(self.settings["delay_seconds"])
        self.delay_slider.grid(row=2, column=0, sticky="ew", padx=18, pady=(10, 16))
        self.delay_slider.bind("<ButtonRelease-1>", lambda _e: self._on_delay(int(self.delay_slider.get())))
        self._on_delay(self.settings["delay_seconds"], save=False)
        self._refresh_name_rows()
        self._show_section(self.SECTIONS[0])

    def _show_section(self, name: str) -> None:
        for other, frame in self.sections.items():
            if other == name:
                frame.grid()
            else:
                frame.grid_remove()

    @staticmethod
    def _ink(colour: str) -> str:
        """Black or white text, whichever reads better on this colour."""
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        return "#111214" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#FFFFFF"

    def _size_row(self, master, row: int, key: str) -> None:
        label, low, high, _default = SIZES[key]
        ctk.CTkLabel(master, text=label, font=font(12), text_color=COL_TEXT, anchor="w", width=150).grid(
            row=row, column=0, sticky="w", padx=(18, 6), pady=3)
        slider = ctk.CTkSlider(master, from_=low, to=high, number_of_steps=high - low, height=16,
                               command=lambda v, k=key: self._on_size(k, int(round(v))))
        slider.set(self.settings[key])
        slider.grid(row=row, column=1, sticky="ew", pady=3)
        slider.bind("<ButtonRelease-1>", lambda _e: self._save())
        value = ctk.CTkLabel(master, text="", font=font(12, "bold"), text_color=GREEN_TEXT, width=48, anchor="e")
        value.grid(row=row, column=2, padx=(6, 18), pady=3)
        self.size_widgets[key] = (slider, value)
        self._show_size(key)

    def _show_size(self, key: str) -> None:
        slider, value = self.size_widgets[key]
        slider.set(self.settings[key])
        value.configure(text=f"{self.settings[key]}{'°' if key == 'skew' else ' px'}")

    def _on_size(self, key: str, value: int) -> None:
        if self.settings[key] == value:
            return
        self.settings[key] = value
        self._show_size(key)
        self._push_state()  # live while dragging; saved on release

    def _reset_sizes(self, keys) -> None:
        for key in keys:
            self.settings[key] = SIZES[key][3]
            self._show_size(key)
        self._save_and_push()

    def _followed_teams(self) -> list[nhl_api.Team]:
        game = self._followed_game()
        return [game.away, game.home] if game else []

    def _refresh_name_rows(self) -> None:
        teams = self._followed_teams()
        overrides = self.settings["name_overrides"]
        for index, ((code, entry, reset), (colour, logo)) in enumerate(zip(self.name_rows, self.team_buttons)):
            if index >= len(teams):
                code.configure(text="Aucun match")
                entry.delete(0, "end")
                for widget in (entry, reset, colour, logo):
                    widget.configure(state="disabled")
                colour.configure(text="", fg_color=COL_CARD_HOVER)
                continue
            team = teams[index]
            code.configure(text=f"{team.abbrev}  ·  {team.name}")
            for widget in (entry, reset, colour, logo):
                widget.configure(state="normal")
            if self.focus_get() is not entry._entry:  # never overwrite what the user is typing
                entry.delete(0, "end")
                entry.insert(0, overrides.get(team.abbrev, ""))
            entry._team = team.abbrev
            reset.configure(command=lambda a=team.abbrev, e=entry: self._reset_team(a, e))
            shade = team_color(team.abbrev, self.settings)
            colour.configure(text=shade, fg_color=shade, hover_color=shade, text_color=self._ink(shade))
            path = custom_logo(team.abbrev, self.settings)
            logo.configure(text=path.name[:16] if path else "Logo LNH",
                           border_color=GREEN if path else COL_BORDER)

    def _reset_team(self, abbrev: str, entry) -> None:
        entry.delete(0, "end")
        for key in ("color_overrides", "logo_overrides"):
            self.settings[key] = {k: v for k, v in self.settings[key].items() if k != abbrev}
        self._on_names_change()
        self._refresh_name_rows()

    def _team_at(self, index: int) -> str | None:
        teams = self._followed_teams()
        return teams[index].abbrev if index < len(teams) else None

    def _pick_team_colour(self, index: int) -> None:
        abbrev = self._team_at(index)
        if not abbrev:
            return
        chosen = colorchooser.askcolor(color=team_color(abbrev, self.settings), parent=self)[1]
        if chosen and HEX.match(chosen):
            self.settings["color_overrides"] = {**self.settings["color_overrides"], abbrev: chosen.upper()}
            self._save_and_push()
            self._refresh_name_rows()

    def _pick_team_logo(self, index: int) -> None:
        abbrev = self._team_at(index)
        if not abbrev:
            return
        patterns = " ".join("*" + ext for ext in LOGO_TYPES)
        chosen = filedialog.askopenfilename(parent=self, title=f"Logo pour {abbrev}",
                                            filetypes=[("Images", patterns)])
        if chosen and Path(chosen).suffix.lower() in LOGO_TYPES:
            self.settings["logo_overrides"] = {**self.settings["logo_overrides"], abbrev: chosen}
            self._save_and_push()
            self._refresh_name_rows()

    def _on_names_change(self) -> None:
        overrides = dict(self.settings["name_overrides"])
        for _code, entry, _reset in self.name_rows:
            abbrev = getattr(entry, "_team", None)
            if not abbrev or str(entry.cget("state")) == "disabled":
                continue
            value = entry.get().strip()[:30]
            if value:
                overrides[abbrev] = value
            else:
                overrides.pop(abbrev, None)
        self.settings["name_overrides"] = overrides
        self._save_and_push()

    # Sample game for the preset thumbnails: the same in every button, whatever is on tonight.
    SAMPLE = nhl_api.Game(0, "LIVE", "", nhl_api.Team("MTL", "Canadiens", 2, 18, teams.logo("MTL")),
                          nhl_api.Team("TOR", "Maple Leafs", 1, 16, teams.logo("TOR")), 2, "REG", "14:37", False)

    def _refresh_presets(self) -> None:
        """Thumbnails with the user's team overrides; redrawn until the NHL logos have downloaded."""
        self._thumbs_ready = all(self.logos.get(teams.logo(abbrev), 8) for abbrev in ("MTL", "TOR"))
        for key, button in self.preset_buttons.items():
            conf = dict(self.settings, **PRESETS[key][1])
            image = preview.render(build_state(self.SAMPLE, conf), conf, self.logos, scale=1.0,
                                   custom_logo=lambda abbrev: custom_logo(abbrev, self.settings))
            factor = min(220 / image.width, 46 / image.height)
            button._thumb = ctk.CTkImage(light_image=image, dark_image=image,
                                         size=(round(image.width * factor), round(image.height * factor)))
            chosen = key == self.settings["preset"]
            button.configure(image=button._thumb, border_width=2 if chosen else 1,
                             border_color=GREEN if chosen else COL_BORDER)

    def _apply_preset(self, key: str) -> None:
        self.settings.update(PRESETS[key][1])
        self.settings["preset"] = key
        for name, var in self.look_vars.items():
            var.set(self.settings[name])
        self.format_var.set("Abréviation" if self.settings["name_format"] == "abbrev" else "Nom")
        for name in SIZES:
            self._show_size(name)
        self._save_and_push()
        self._refresh_name_rows()
        self._refresh_presets()

    def _on_look_change(self) -> None:
        self.settings["name_format"] = "abbrev" if self.format_var.get() == "Abréviation" else "name"
        for key, var in self.look_vars.items():
            self.settings[key] = var.get()
        self._save_and_push()

    def _pick_colour(self, key: str) -> None:
        chosen = colorchooser.askcolor(color=self.settings[key], parent=self)[1]
        if chosen and HEX.match(chosen):
            self.settings[key] = chosen.upper()
            self.colour_buttons[key].configure(text=chosen.upper(), fg_color=chosen, hover_color=chosen,
                                               text_color=self._ink(chosen))
            self._save_and_push()

    def _on_delay(self, seconds: int, save: bool = True) -> None:
        self.delay_label.configure(text=f"{seconds} s")
        self.settings["delay_seconds"] = seconds
        if save:
            self._save()

    # ----- page 3: settings ----------------------------------------------
    def _build_settings(self, page) -> None:
        self._page_header(page, "Réglages", "Connexion à OBS et fonctionnement du logiciel.")

        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="ew", padx=28)
        cards.grid_columnconfigure((0, 1), weight=1, uniform="half")
        box = card(cards)
        box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        box.grid_columnconfigure(1, weight=1)
        section_title(box, "OBS WebSocket").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(14, 2))
        muted(box, "Dans OBS : Outils › Paramètres du serveur WebSocket.").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 8))
        self.fields = {}
        rows = (("obs_host", "Adresse", ""), ("obs_port", "Port", ""), ("obs_password", "Mot de passe", "•"),
                ("obs_scene", "Scène (vide = scène en cours)", ""), ("obs_source", "Nom de la source", ""))
        for row, (key, text, show) in enumerate(rows, start=2):
            self._field(box, row, key, text, show)
        actions = ctk.CTkFrame(box, fg_color="transparent")
        actions.grid(row=8, column=0, columnspan=2, sticky="ew", padx=18, pady=(10, 4))
        ctk.CTkButton(actions, text="Tester la connexion", height=34, font=font(12, "bold"),
                      fg_color="transparent", border_width=1, border_color=GREEN, text_color=COL_TEXT,
                      hover_color=COL_CARD_HOVER, command=lambda: self._obs_action(obs.test_connection)).pack(side="left")
        ctk.CTkButton(actions, text="Créer la source dans OBS", height=34, font=font(12, "bold"),
                      command=lambda: self._obs_action(
                          lambda s: obs.ensure_browser_source(s, self.widget_url()))).pack(side="left", padx=10)
        self.obs_result = muted(box, "", wraplength=280)
        self.obs_result.grid(row=9, column=0, columnspan=2, sticky="w", padx=18, pady=(4, 16))

        app_box = card(cards)
        app_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        app_box.grid_columnconfigure(1, weight=1)
        section_title(app_box, "Logiciel").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(14, 8))
        self._field(app_box, 1, "server_port", "Port du widget", "")
        self._field(app_box, 2, "poll_seconds", "Actualisation (s)", "")
        muted(app_box, "Port : redémarrage requis. Actualisation : 10 secondes minimum.", wraplength=280).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 16))
        url_row = ctk.CTkFrame(app_box, fg_color="transparent")
        url_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 8))
        self.url_label = ctk.CTkLabel(url_row, text=self.widget_url(), font=font(12), text_color=GREEN_TEXT)
        self.url_label.pack(side="left")
        ghost_button(url_row, "Copier l'URL", self._copy_url).pack(side="left", padx=12)

        bottom = ctk.CTkFrame(page, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=28, pady=(16, 28))
        ctk.CTkButton(bottom, text="Enregistrer", height=38, width=150, font=font(13, "bold"),
                      command=self._save_settings_page).pack(side="left")
        self.save_result = muted(bottom, "")
        self.save_result.pack(side="left", padx=14)

    def _field(self, master, row: int, key: str, text: str, show: str) -> None:
        ctk.CTkLabel(master, text=text, font=font(13), text_color=COL_TEXT, anchor="w").grid(
            row=row, column=0, sticky="w", padx=18, pady=4)
        entry = ctk.CTkEntry(master, font=font(13), show=show or None)
        entry.insert(0, str(self.settings[key]))
        entry.grid(row=row, column=1, sticky="ew", padx=(10, 18), pady=4)
        self.fields[key] = entry

    def _read_settings_page(self) -> str | None:
        """Copies the fields into the settings. Returns an error message, or None."""
        values = {key: entry.get().strip() for key, entry in self.fields.items()}
        values["obs_password"] = self.fields["obs_password"].get()  # spaces can be part of a password
        try:
            ports = [int(values["obs_port"]), int(values["server_port"])]
            poll = int(values["poll_seconds"])
        except ValueError:
            return "Les ports et l'actualisation doivent être des nombres entiers."
        if not all(1024 <= port <= 65535 for port in ports):
            return "Un port doit être entre 1024 et 65535."
        if not values["obs_host"]:
            return "L'adresse d'OBS est vide."
        self.settings.update(values, obs_port=ports[0], server_port=ports[1], poll_seconds=max(10, poll))
        return None

    def _save_settings_page(self) -> None:
        error = self._read_settings_page()
        if error:
            self.save_result.configure(text=error, text_color=COL_RED)
            return
        self._save()
        for label in (self.url_label, *self.url_labels):
            label.configure(text=self.widget_url())
        self.save_result.configure(text="Réglages enregistrés.", text_color=GREEN_TEXT)

    def _obs_action(self, action) -> None:
        error = self._read_settings_page()
        if error:
            self.obs_result.configure(text=error, text_color=COL_RED)
            return
        self._save()
        self.obs_result.configure(text="Connexion à OBS…", text_color=COL_MUTED)
        snapshot = dict(self.settings)

        def work() -> None:
            try:
                message, ok = action(snapshot), True
            except obs.OBSError as exc:
                message, ok = str(exc), False
            except Exception as exc:  # unexpected OBS reply: show it rather than crash
                message, ok = f"Erreur OBS : {exc}", False
            self.after(0, lambda: self.obs_result.configure(
                text=message, text_color=GREEN_TEXT if ok else COL_RED))
        threading.Thread(target=work, daemon=True).start()

    def widget_url(self) -> str:
        return f"http://127.0.0.1:{self.settings['server_port']}/widget"

    def _copy_url(self, feedback: ctk.CTkLabel | None = None) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.widget_url())
        if feedback is not None:
            feedback.configure(text="Copié", text_color=GREEN_TEXT)
            self.after(2000, lambda: feedback.configure(text=""))

    # ----- data flow -----------------------------------------------------
    def _save(self) -> None:
        try:
            settings_store.save(self.settings, self.settings_file)
        except OSError:
            self._set_status(self.server_status, "Réglages non enregistrés (disque)", False)

    def _save_and_push(self) -> None:
        self._save()
        self._push_state()

    def _push_state(self) -> None:
        self.feed.push(build_state(self._followed_game(), self.settings))
        self._render_preview()

    def _start_server(self) -> None:
        try:
            self.server = start_server(self.settings["server_port"],
                                       lambda: self.feed.current(self.settings["delay_seconds"]),
                                       lambda abbrev: custom_logo(abbrev, self.settings))
            self._set_status(self.server_status, f"Widget : port {self.settings['server_port']}", True)
        except OSError:
            self._set_status(self.server_status, f"Port {self.settings['server_port']} déjà pris", False)

    def _fetch(self) -> None:
        try:
            games = nhl_api.fetch_games()
        except Exception:  # network down, API changed: keep the last score
            self.after(0, lambda: self._set_status(self.api_status, "API NHL injoignable", False))
            return
        self.after(0, lambda: self._on_games(games))

    def _on_games(self, games: list[nhl_api.Game]) -> None:
        self.games = games
        self._set_status(self.api_status, f"API NHL : {len(games)} match(s)", True)
        self._push_state()
        self._render_games()
        self._refresh_name_rows()

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self._fetch()
            self._stop.wait(max(10, int(self.settings["poll_seconds"])))

    def close(self) -> None:
        self._stop.set()
        if self.server:
            self.server.shutdown()
        self.destroy()


def main() -> None:
    App().mainloop()
