"""Application and Domain-Specific System 1 Decision Models."""

from core.decision.domains.spotify import SpotifyDomainModel
from core.decision.domains.media import MediaPlaybackDomainModel
from core.decision.domains.window_manager import WindowManagerDomainModel
from core.decision.domains.terminal import TerminalDomainModel
from core.decision.domains.browser import BrowserDomainModel
from core.decision.domains.screen_gui import ScreenGUIDomainModel
from core.decision.domains.system_control import SystemControlDomainModel

__all__ = [
    "SpotifyDomainModel",
    "MediaPlaybackDomainModel",
    "WindowManagerDomainModel",
    "TerminalDomainModel",
    "BrowserDomainModel",
    "ScreenGUIDomainModel",
    "SystemControlDomainModel",
]
