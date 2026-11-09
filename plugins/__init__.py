"""KiCad PCM package entry point."""

import wx


# ActionPlugin.register() requires an initialized KiCad GUI program instance.
# Headless test runners can still import the geometry and panelizer modules
# without attempting GUI registration.
if wx.GetApp() is not None:
    from . import kicad_panelizer  # noqa: F401

