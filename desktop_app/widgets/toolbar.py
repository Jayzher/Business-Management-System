import webbrowser

from PyQt5.QtCore import QSize, QUrl
from PyQt5.QtWidgets import QAction, QStyle, QToolBar


class NavigationToolBar(QToolBar):
    """Browser-style nav strip wired to a QWebEngineView."""

    def __init__(self, web_view, parent=None):
        super().__init__("Navigation", parent)
        self.web_view = web_view
        self.setMovable(False)
        self.setIconSize(QSize(18, 18))

        style = self.style()

        self.back_action = QAction(
            style.standardIcon(QStyle.SP_ArrowBack), "Back", self
        )
        self.back_action.triggered.connect(self.web_view.back)

        self.forward_action = QAction(
            style.standardIcon(QStyle.SP_ArrowForward), "Forward", self
        )
        self.forward_action.triggered.connect(self.web_view.forward)

        self.reload_action = QAction(
            style.standardIcon(QStyle.SP_BrowserReload), "Reload", self
        )
        self.reload_action.triggered.connect(self.web_view.reload)

        self.home_action = QAction(
            style.standardIcon(QStyle.SP_DirHomeIcon), "Home", self
        )
        self.home_action.triggered.connect(self.web_view.navigate_to_home)

        self.open_browser_action = QAction(
            style.standardIcon(QStyle.SP_DialogOpenButton), "Open in Browser", self
        )
        self.open_browser_action.triggered.connect(self._open_in_browser)

        self.addAction(self.back_action)
        self.addAction(self.forward_action)
        self.addAction(self.reload_action)
        self.addAction(self.home_action)
        self.addSeparator()
        self.addAction(self.open_browser_action)

        self._update_nav_state(False)
        self.web_view.urlChanged.connect(lambda _url: self._refresh_nav())
        self.web_view.loadFinished.connect(lambda _ok: self._refresh_nav())

    def _refresh_nav(self):
        self.back_action.setEnabled(self.web_view.history().canGoBack())
        self.forward_action.setEnabled(self.web_view.history().canGoForward())

    def _update_nav_state(self, enabled: bool):
        self.back_action.setEnabled(enabled)
        self.forward_action.setEnabled(enabled)

    def _open_in_browser(self):
        url: QUrl = self.web_view.url()
        target = url.toString() if url and not url.isEmpty() else f"http://127.0.0.1:{self.web_view.port}/"
        webbrowser.open(target)
