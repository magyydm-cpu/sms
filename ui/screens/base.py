"""Base screen with top bar, error handling and navigation helpers."""
from __future__ import annotations

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.screen import MDScreen

from ui.widgets import make_top_bar, show_message


class BaseScreen(MDScreen):
    screen_name = ""
    screen_title = ""

    def __init__(self, app, **kwargs):
        self.app = app
        self.data = {}
        kwargs.setdefault("name", self.screen_name)
        super().__init__(**kwargs)
        self.content = MDBoxLayout(orientation="vertical")
        self.add_widget(self.content)
        self.build()

    # -- lifecycle -------------------------------------------------------
    def build(self) -> None:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def load(self, **kwargs) -> None:
        """Receive navigation parameters before the screen becomes visible."""
        self.data = kwargs

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self) -> None:
        """Re-read data from the services. Subclasses override."""

    # -- helpers ---------------------------------------------------------
    def add_top_bar(self, title=None, on_back=True, actions=None):
        bar = make_top_bar(
            title or self.screen_title,
            on_back=self.go_back if on_back else None,
            actions=actions,
        )
        self.content.add_widget(bar)
        return bar

    def go_back(self) -> None:
        self.app.back()

    def handle_error(self, exc: Exception) -> None:
        message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
        show_message("تنبيه", message)

    def notify(self, text: str, title: str = "تم") -> None:
        show_message(title, text)
