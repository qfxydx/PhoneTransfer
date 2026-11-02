"""App theme definitions and stylesheet generation."""

from __future__ import annotations


class AppTheme:
    """Semantic colors aligned with HTML prototype (light / dark)."""

    def __init__(self, dark: bool) -> None:
        self.dark = dark
        if dark:
            self.bg = "#1e1e20"
            self.card = "#1e1e20"
            self.line = "#3a3a3c"
            self.primary = "#f5f5f7"
            self.secondary = "#98989d"
            self.tertiary = "#8e8e93"
            self.quaternary = "#636366"
            self.accent = "#0071e3"
            self.accent_hover = "#0077ed"
            self.seg_bg = "#3a3a3c"
            self.seg_sel = "#48484a"
            self.btn_disabled_bg = "#3a3a3c"
            self.btn_disabled_text = "#636366"
            self.green = "#34c759"
            self.empty_icon_bg = "#3a3a3c"
            self.row_bg = "#1e1e20"
            self.log_bg = "#2c2c2e"
            self.log_bar_bg = "#252527"
        else:
            self.bg = "#ffffff"
            self.card = "#ffffff"
            self.line = "#d1d1d6"
            self.primary = "#1d1d1f"
            self.secondary = "#6e6e73"
            self.tertiary = "#86868b"
            self.quaternary = "#aeaeb2"
            self.accent = "#0071e3"
            self.accent_hover = "#0077ed"
            self.seg_bg = "#e5e5ea"
            self.seg_sel = "#ffffff"
            self.btn_disabled_bg = "#e5e5ea"
            self.btn_disabled_text = "#a5a5aa"
            self.green = "#34c759"
            self.empty_icon_bg = "#ececf1"
            self.row_bg = "#ffffff"
            self.log_bg = "#fafafc"
            self.log_bar_bg = "#fafafc"

    def stylesheet(self, symbol_font: str) -> str:
        t = self
        return f"""
      QWidget#root {{
        background: {t.bg};
        color: {t.primary};
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
        font-size: 13px;
      }}
      QWidget#mainArea, QWidget#cardHost {{
        background: transparent;
      }}
      QFrame#card {{
        background: {t.card};
        border: 1px solid {t.line};
        border-radius: 12px;
      }}
      QFrame#titleStrip {{
        background: {t.log_bar_bg};
        border: none;
        border-bottom: 1px solid {t.line};
      }}
      QFrame#segmentControl {{
        background: {t.seg_bg};
        border: none;
        border-radius: 8px;
      }}
      QFrame#emptyIconBox {{
        background: {t.empty_icon_bg};
        border: none;
        border-radius: 16px;
      }}
      QFrame#fileRow {{
        background: {t.row_bg};
        border: 1px solid {t.line};
        border-radius: 10px;
      }}
      QFrame#fileRow:hover {{
        border-color: {t.secondary};
      }}
      QFrame#fileRow[selected="true"] {{
        background: {t.seg_sel if t.dark else "#edf5ff"};
        border: 1.5px solid {t.accent};
      }}
      QPushButton#installRowBtn {{
        background: rgba(52, 199, 89, 0.12);
        border: 1px solid {t.green};
        border-radius: 5px;
        color: {t.green};
        font-size: 11px;
        font-weight: 600;
        padding: 1px 6px;
        min-height: 22px;
      }}
      QPushButton#installRowBtn:hover {{
        background: {t.green};
        color: #ffffff;
      }}
      QFrame#logBar {{
        background: {t.log_bar_bg};
        border: none;
        border-top: 1px solid {t.line};
      }}
      QFrame#dropHighlight {{
        border: 2px dashed {t.accent};
        border-radius: 12px;
        background: rgba(0, 113, 227, 0.06);
      }}
      QLabel#eyebrow {{
        font-size: 13px;
        font-weight: 600;
        color: {t.tertiary};
        letter-spacing: 0.6px;
      }}
      QLabel#sectionTitle {{
        font-size: 22px;
        font-weight: 600;
        color: {t.primary};
      }}
      QWidget#cardHeader {{
        background: transparent;
      }}
      QLabel#sectionSubtitle {{
        font-size: 15px;
        font-weight: 600;
        color: {t.primary};
      }}
      QLabel#emptyHint {{
        font-size: 13px;
        color: {t.secondary};
      }}
      QLabel#sectionLabel {{
        font-size: 13px;
        color: {t.secondary};
      }}
      QLabel#fileName {{
        font-size: 13px;
        font-weight: 500;
        color: {t.primary};
      }}
      QLabel#fileSize {{
        font-size: 12px;
        color: {t.tertiary};
      }}
      QLabel#summaryLabel {{
        font-size: 12px;
        font-weight: 500;
        color: {t.secondary};
      }}
      QLabel#spaceSpinner {{
        font-size: 13px;
        font-weight: 700;
        color: {t.accent};
      }}
      QLabel#spaceLabel {{
        font-size: 13px;
        font-weight: 600;
        color: {t.tertiary};
        letter-spacing: 0.6px;
      }}
      QLabel#deviceName {{
        font-size: 13px;
        font-weight: 500;
        color: {t.primary};
      }}
      QToolButton#devicePickerBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 2px 4px 2px 6px;
        font-size: 13px;
        font-weight: 500;
        color: {t.primary};
      }}
      QToolButton#devicePickerBtn:hover {{
        background: {t.seg_bg};
      }}
      QToolButton#devicePickerBtn:disabled {{
        color: {t.tertiary};
      }}
      QToolButton#devicePickerBtn::menu-indicator {{
        image: none;
        width: 0px;
      }}
      QToolButton#deviceChevron {{
        background: transparent;
        border: none;
        border-radius: 4px;
        color: {t.tertiary};
        font-family: "{symbol_font}";
        font-size: 11px;
        padding: 2px;
        min-width: 16px;
        max-width: 16px;
        min-height: 16px;
        max-height: 16px;
      }}
      QToolButton#deviceChevron:hover {{
        color: {t.primary};
        background: {t.seg_bg};
      }}
      QLabel#statusConnected {{
        font-size: 13px;
        color: {t.secondary};
      }}
      QLabel#statusDotOnline {{
        background: {t.green};
        border-radius: 4px;
        min-width: 8px; max-width: 8px;
        min-height: 8px; max-height: 8px;
      }}
      QLabel#statusDotOffline, QLabel#statusDotBusy {{
        background: {t.quaternary};
        border-radius: 4px;
        min-width: 8px; max-width: 8px;
        min-height: 8px; max-height: 8px;
      }}
      QLabel#logText {{
        font-size: 12px;
        color: {t.secondary};
      }}
      QLabel#transferHint {{
        font-size: 12px;
        color: {t.tertiary};
      }}
      QFrame#transferToast {{
        background: {t.card};
        border: 1px solid {t.line};
        border-radius: 12px;
      }}
      QLabel#toastIcon {{
        font-size: 16px;
        color: {t.green};
      }}
      QLabel#toastText {{
        font-size: 13px;
        font-weight: 500;
        color: {t.primary};
      }}
      QLabel#bodyText {{
        font-size: 13px;
        color: {t.primary};
      }}
      QLabel#caption, QLabel#secondaryText {{
        font-size: 13px;
        color: {t.secondary};
      }}
      QLabel#fileBadge {{
        font-size: 11px;
        font-weight: 600;
        color: #ffffff;
      }}
      QLabel#emptySymbol {{
        font-family: "{symbol_font}";
        font-size: 28px;
        color: {t.secondary};
        background: transparent;
      }}
      QPushButton#pickBtn {{
        background: {t.accent};
        color: #ffffff;
        border: none;
        border-radius: 12px;
        min-height: 40px;
        padding: 0 20px;
        font-size: 13px;
        font-weight: 600;
      }}
      QPushButton#pickBtn:hover {{ background: {t.accent_hover}; }}
      QPushButton#pickBtn:pressed {{ background: #0068d0; }}
      QPushButton#clearBtn {{
        background: transparent;
        color: {t.accent};
        border: none;
        border-radius: 6px;
        padding: 4px 6px;
        font-size: 12px;
        font-weight: 500;
        min-height: 24px;
      }}
      QPushButton#clearBtn:hover {{
        background: rgba(0, 113, 227, 0.08);
      }}
      QPushButton#segmentBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        min-height: 26px;
        padding: 0 4px;
        color: {t.secondary};
        font-size: 12px;
      }}
      QPushButton#segmentBtn:hover {{
        color: {t.primary};
      }}
      QPushButton#segmentBtn:checked {{
        background: {t.seg_sel};
        color: {t.primary};
        font-weight: 500;
      }}
      QPushButton#quickTagBtn {{
        background: {t.seg_bg};
        color: {t.secondary};
        border: 1px solid transparent;
        border-radius: 6px;
        min-height: 24px;
        font-size: 11px;
        font-weight: 500;
        padding: 0 4px;
      }}
      QPushButton#quickTagBtn:hover {{
        background: {t.seg_sel};
        color: {t.primary};
      }}
      QPushButton#quickTagBtn:checked {{
        background: {t.accent};
        color: #ffffff;
        font-weight: 600;
      }}
      QPushButton#dangerBtn {{
        background: #e8685a;
        color: #ffffff;
        border: none;
        border-radius: 7px;
        font-size: 13px;
        font-weight: 600;
        padding: 6px 14px;
      }}
      QPushButton#dangerBtn:hover {{
        background: #d9534f;
      }}
      QPushButton#dangerBtn:pressed {{
        background: #c9302c;
      }}
      QPushButton#transferBtn {{
        background: {t.btn_disabled_bg};
        color: {t.btn_disabled_text};
        border: none;
        border-radius: 22px;
        min-height: 44px;
        padding: 0 28px;
        font-size: 14px;
        font-weight: 600;
      }}
      QPushButton#transferBtn[ready="true"] {{
        background: {t.accent};
        color: #ffffff;
      }}
      QPushButton#transferBtn[ready="true"]:hover {{
        background: {t.accent_hover};
      }}
      QPushButton#transferBtn[ready="true"]:pressed {{
        background: #0068d0;
      }}
      QPushButton#removeBtn {{
        background: transparent;
        border: none;
        color: {t.quaternary};
        font-size: 16px;
        padding: 4px;
        border-radius: 4px;
        min-width: 20px;
      }}
      QPushButton#removeBtn:hover {{
        color: {t.primary};
        background: rgba(0, 0, 0, 0.04);
      }}
      QToolButton#refreshBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        color: {t.secondary};
        font-family: "{symbol_font}";
        font-size: 14px;
        padding: 4px;
      }}
      QToolButton#refreshBtn:hover {{
        background: {t.seg_bg};
      }}
      QToolButton#swapBtn {{
        background: {t.card};
        border: 1px solid {t.line};
        border-radius: 18px;
        color: {t.secondary};
        font-family: "{symbol_font}";
        font-size: 16px;
        min-width: 36px;
        max-width: 36px;
        min-height: 36px;
        max-height: 36px;
      }}
      QToolButton#swapBtn:hover {{
        background: {t.seg_bg};
        color: {t.primary};
      }}
      QToolButton#navBackBtn, QToolButton#navOpenBtn, QToolButton#navActionBtn {{
        background: transparent;
        border: none;
        color: {t.secondary};
        font-family: "{symbol_font}";
        font-size: 14px;
        padding: 2px;
      }}
      QToolButton#navBackBtn:hover, QToolButton#navOpenBtn:hover, QToolButton#navActionBtn:hover {{
        color: {t.accent};
        background: {t.seg_bg};
        border-radius: 6px;
      }}
      QToolButton#navBackBtn:disabled, QToolButton#navActionBtn:disabled {{
        color: {t.quaternary};
      }}
      QMenu {{
        background-color: {t.card};
        color: {t.primary};
        border: 1px solid {t.line};
        border-radius: 8px;
        padding: 4px;
      }}
      QMenu::item {{
        padding: 6px 18px 6px 12px;
        border-radius: 4px;
        font-size: 12px;
        color: {t.primary};
      }}
      QMenu::item:selected {{
        background-color: {t.accent};
        color: #ffffff;
      }}
      QMenu::item:disabled {{
        color: {t.quaternary};
      }}
      QMenu::separator {{
        height: 1px;
        background: {t.line};
        margin: 4px 6px;
      }}
      QLineEdit#filterSearchEdit {{
        background: {t.seg_bg};
        border: 1px solid transparent;
        border-radius: 6px;
        color: {t.primary};
        font-size: 11px;
        padding: 2px 8px;
        min-height: 24px;
        max-height: 24px;
      }}
      QLineEdit#filterSearchEdit:focus {{
        border-color: {t.accent};
        background: {t.card};
      }}
      QPushButton#filterCategoryBtn {{
        background: {t.seg_bg};
        color: {t.secondary};
        border: 1px solid transparent;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 500;
        padding: 0 4px;
        min-height: 24px;
        max-height: 24px;
      }}
      QPushButton#filterCategoryBtn:hover {{
        background: {t.seg_sel};
        color: {t.primary};
      }}
      QPushButton#filterCategoryBtn[active="true"] {{
        background: {t.accent};
        color: #ffffff;
        font-weight: 600;
      }}
      QCheckBox#browseCheck {{
        spacing: 0px;
      }}
      QCheckBox#browseCheck::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {t.line};
        background: {t.card};
      }}
      QCheckBox#browseCheck::indicator:checked {{
        background: {t.accent};
        border-color: {t.accent};
      }}
      QPushButton#logLink {{
        background: transparent;
        border: none;
        color: {t.accent};
        font-size: 12px;
        padding: 2px 0;
      }}
      QPushButton#logLink:hover {{
        text-decoration: underline;
      }}
      QLineEdit#pathEdit {{
        background: {t.row_bg};
        color: {t.primary};
        border: 1px solid {t.line};
        border-radius: 7px;
        padding: 0 10px;
        min-height: 30px;
        font-size: 12px;
        font-family: "SF Mono", Menlo, Monaco, monospace;
      }}
      QLineEdit#pathEdit:focus {{
        border-color: {t.accent};
      }}
      QScrollArea#fileScroll {{
        background: transparent;
        border: none;
      }}
      QScrollArea#fileScroll QScrollBar:vertical,
      QScrollArea#fileScroll QScrollBar:horizontal {{
        width: 0px;
        height: 0px;
        background: transparent;
      }}
      QPushButton#stopBtn {{
        background: transparent;
        border: 1px solid {t.line};
        border-radius: 10px;
        color: {t.primary};
        padding: 6px 14px;
        font-size: 13px;
      }}
      QPushButton#stopBtn:hover {{ background: {t.seg_bg}; }}
      QProgressBar#transferBar {{
        background: {t.seg_bg};
        border: none;
        border-radius: 4px;
        min-height: 6px;
        max-height: 6px;
      }}
      QProgressBar#transferBar::chunk {{
        background: {t.accent};
        border-radius: 4px;
      }}
      QFrame#logDetail {{
        background: {t.log_bg};
        border: 1px solid {t.line};
        border-radius: 8px;
      }}
      QScrollArea#logDetailScroll {{
        background: transparent;
        border: none;
      }}
      QScrollArea#logDetailScroll QWidget#logDetailContainer {{
        background: transparent;
      }}
      QScrollArea#logDetailScroll QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 4px 2px 4px 0;
      }}
      QScrollArea#logDetailScroll QScrollBar::handle:vertical {{
        background: {t.quaternary};
        border-radius: 3px;
        min-height: 24px;
      }}
      QScrollArea#logDetailScroll QScrollBar::add-line:vertical,
      QScrollArea#logDetailScroll QScrollBar::sub-line:vertical {{
        height: 0px;
      }}
      QFrame#logRow {{
        background: transparent;
        border-bottom: 1px solid {t.line};
      }}
      QFrame#logRow[last="true"] {{
        border-bottom: none;
      }}
      QLabel#logRowTitle {{
        font-size: 12px;
        font-weight: 500;
        color: {t.primary};
      }}
      QLabel#logRowDetail {{
        font-size: 11px;
        color: {t.tertiary};
      }}
      QLabel#logEmpty {{
        font-size: 12px;
        color: {t.tertiary};
      }}
      QLabel#caption {{
        font-size: 12px;
        color: {t.tertiary};
      }}
      QToolButton#wifiBtn,
      QToolButton#sendTextBtn,
      QToolButton#scrcpyBtn,
      QToolButton#coffeeBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        color: {t.secondary};
        font-size: 14px;
        padding: 4px;
      }}
      QToolButton#wifiBtn:hover,
      QToolButton#sendTextBtn:hover,
      QToolButton#scrcpyBtn:hover,
      QToolButton#coffeeBtn:hover {{
        background: {t.seg_bg};
      }}
    """

