"""PixProRefsel -- resize the active selection in Pixelmator Pro.

Copyright (c) 2026 Tim McCoy. All rights reserved.
Developed with assistance from Claude (Anthropic).

A small floating panel with one slider that rests at the center. Drag left
to shrink the selection, right to grow it, and watch it change live; the
size is fixed when the mouse button is released, and the slider returns to
the center for the next nudge.

How the live preview works. Pixelmator's `refine selection ... expand N`
moves every edge of the selection by exactly N pixels (-100 .. 100 per
call; measured: a 200 px square expanded by 10 becomes 220 px), but it
works on the selection as it stands. So each slider step first UNDOES the
previous step of the same drag, then applies the new total. A drag leaves
one clean change behind, and Undo in Pixelmator reverses it.

After a release the change is shown in a field. Type a different amount and
press Return to refine it: the drag's step is undone and the new total applied.
That is only done while the selection is still exactly as the drag left it.

Nothing is activated: the panel is nonactivating so Pixelmator keeps focus.
"""

import re
import subprocess
import threading

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSEventTypeLeftMouseUp,
    NSFont,
    NSMakeRect,
    NSPanel,
    NSPopUpButton,
    NSSlider,
    NSStatusWindowLevel,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSTextField,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskUtilityWindow,
    NSWorkspace,
)
from Foundation import NSObject, NSUserDefaults
from PyObjCTools import AppHelper

VERSION = "1.4.1"
BUNDLE_IDS = ("com.apple.pixelmator", "com.pixelmatorteam.pixelmator.x")
LIMIT = 200          # slider range in pixels, each way
MAX_REFINE = 1000      # largest grow accepted from the Change field
CHUNK = 100          # Pixelmator's per-call expand limit
PANEL_W = 320
# (menu title, abbreviation, centimeters or inches per inch)
UNITS = (("pixels", "px", None), ("centimeters", "cm", 2.54), ("inches", "in", 1.0))
UNIT_KEY = "unit"
PLACE_KEY = "place"
PLACES = ("Above current layer", "Below current layer")

HELP = (
    "Make a selection in Pixelmator Pro, then drag the slider: left shrinks it, "
    "right grows it, live. The size is fixed when you let go and the slider "
    "returns to the center. Type in the Change field to refine the amount. "
    "New Layer turns the selection into a shape on its own layer, above or "
    "below the current one."
)


# Index 1 is the top layer. The shape layer is created on top; the original
# current layer has then moved down one if the new layer sits at or above it.
LAYER_SCRIPT = '''tell application "%s" to tell the front document
    set c to index of current layer
    set s to convert selection into shape
    if (index of s) <= c then set c to c + 1
    move s to %s layer c
    try
        select s
    end try
end tell'''


def target():
    """Bundle path of the Pixelmator build to drive ("" if none running).

    A path rather than a bundle id: copies of one build share an id and
    `tell application id` would launch the wrong one. Frontmost build wins.
    """
    running = []
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() in BUNDLE_IDS and app.bundleURL() is not None:
            running.append((bool(app.isActive()), str(app.bundleURL().path())))
    running.sort(key=lambda r: not r[0])
    return running[0][1] if running else ""


def chunks(px):
    """Split a signed pixel total into steps Pixelmator accepts."""
    out, left = [], abs(px)
    sign = 1 if px > 0 else -1
    while left > 0:
        step = min(left, CHUNK)
        out.append(sign * step)
        left -= step
    return out


def osa(script):
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return p.returncode == 0, (p.stdout if p.returncode == 0 else p.stderr).strip()


def read_selection():
    """(True, (width, height, ppi, bounds)) or (False, message)."""
    path = target()
    if not path:
        return False, "Pixelmator Pro is not running."
    ok, out = osa(
        'tell application "%s" to tell the front document to '
        "get {selection bounds, resolution}" % path)
    if not ok:
        return False, "No document is open."
    if "missing value" in out:
        return False, "Needs an active selection."
    nums = [float(x) for x in out.split(",") if x.strip()]
    if len(nums) < 5:
        return False, "Needs an active selection."
    return True, (nums[2], nums[3], nums[4], tuple(int(n) for n in nums[:4]))


def apply_steps(undo_count, new_px):
    """Undo the drag's previous steps, then apply the new total."""
    path = target()
    if not path:
        return False, "Pixelmator Pro is not running."
    lines = ["undo"] * undo_count + ["refine selection expand %d" % c for c in chunks(new_px)]
    ok, out = osa('tell application "%s" to tell the front document\n%s\nend tell'
                  % (path, "\n".join(lines)))
    return ok, "" if ok else out[:80]


class Controller(NSObject):
    # ── UI ──────────────────────────────────────────────────────────────
    @objc.python_method
    def _add(self, view):
        self.panel.contentView().addSubview_(view)
        return view

    @objc.python_method
    def _label(self, text, size=12, bold=False, align=None, color=None):
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
        f.setStringValue_(text)
        f.setEditable_(False)
        f.setBordered_(False)
        f.setDrawsBackground_(False)
        f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
        if align is not None:
            f.setAlignment_(align)
        if color is not None:
            f.setTextColor_(color)
        return self._add(f)

    @objc.python_method
    def _button(self, title, action):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
        b.setTitle_(title)
        b.setBezelStyle_(1)            # rounded
        b.setTarget_(self)
        b.setAction_(action)
        return self._add(b)

    @objc.python_method
    def _build_panel(self):
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_W, 200),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskUtilityWindow
            | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setTitle_("PixProRefsel %s" % VERSION)
        # Keep the palette up when focus goes to Pixelmator: this app is
        # always "deactivated", so level + collection behavior are needed.
        panel.setLevel_(NSStatusWindowLevel)
        panel.setHidesOnDeactivate_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setReleasedWhenClosed_(False)
        panel.setDelegate_(self)
        self.panel = panel

        self.unit_label = self._label("Units")
        self.unit_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(0, 0, 10, 10), False)
        for name, _abbr, _k in UNITS:
            self.unit_popup.addItemWithTitle_(name)
        saved = NSUserDefaults.standardUserDefaults().stringForKey_(UNIT_KEY)
        if saved in [u[0] for u in UNITS]:
            self.unit_popup.selectItemWithTitle_(saved)
        self.unit_popup.setTarget_(self)
        self.unit_popup.setAction_("unitChanged:")
        self._add(self.unit_popup)

        self.shrink_label = self._label("Shrink")
        self.grow_label = self._label("Grow", align=NSTextAlignmentRight)
        self.slider = NSSlider.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
        self.slider.setMinValue_(-LIMIT)
        self.slider.setMaxValue_(LIMIT)
        self.slider.setDoubleValue_(0)
        self.slider.setNumberOfTickMarks_(5)
        self.slider.setContinuous_(True)
        self.slider.setTarget_(self)
        self.slider.setAction_("slid:")
        self._add(self.slider)

        self.readout = self._label("", size=20, bold=True, align=NSTextAlignmentCenter)
        self.status = self._label("", align=NSTextAlignmentCenter,
                                  color=NSColor.secondaryLabelColor())
        # Shown in the status row after a release: the amount just applied,
        # editable. Return refines it.
        self.chg_label = self._label("Change", align=NSTextAlignmentRight)
        self.chg_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
        self.chg_field.setAlignment_(NSTextAlignmentCenter)
        self.chg_field.setTarget_(self)
        self.chg_field.setAction_("changeEdited:")
        self._add(self.chg_field)
        self.chg_unit = self._label("")
        for v in (self.chg_label, self.chg_field, self.chg_unit):
            v.setHidden_(True)
        self.help_text = self._label(HELP, size=11, color=NSColor.secondaryLabelColor())
        self.help_text.cell().setWraps_(True)
        self.help_button = self._button("Hide Help", "toggleHelp:")
        self.place_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(0, 0, 10, 10), False)
        for name in PLACES:
            self.place_popup.addItemWithTitle_(name)
        saved_place = NSUserDefaults.standardUserDefaults().stringForKey_(PLACE_KEY)
        if saved_place in PLACES:
            self.place_popup.selectItemWithTitle_(saved_place)
        self.place_popup.setTarget_(self)
        self.place_popup.setAction_("placeChanged:")
        self._add(self.place_popup)
        self.layer_button = self._button("New Layer", "newLayer:")
        self.dismiss_button = self._button("Dismiss", "dismiss:")

        self.help_visible = True          # help is showing when the app opens
        self._layout()
        self._update_readout(0)
        panel.center()
        panel.orderFrontRegardless()

    @objc.python_method
    def _layout(self):
        M = 16
        W = PANEL_W - 2 * M
        # Height the wrapped help text actually needs at this width.
        help_h = 0
        if self.help_visible:
            help_h = int(self.help_text.cell().cellSizeForBounds_(
                NSMakeRect(0, 0, W, 1000)).height) + 4
        H = 240 + (help_h + 12 if self.help_visible else 0)
        old = self.panel.frame()
        top = old.origin.y + old.size.height
        self.panel.setContentSize_((PANEL_W, H))
        new = self.panel.frame()
        self.panel.setFrameOrigin_((old.origin.x, top - new.size.height))

        y = H - 32
        self.unit_label.setFrame_(NSMakeRect(M, y, 44, 20))
        self.unit_popup.setFrame_(NSMakeRect(M + 46, y - 3, 140, 24))
        y -= 26
        self.shrink_label.setFrame_(NSMakeRect(M, y, 80, 16))
        self.grow_label.setFrame_(NSMakeRect(PANEL_W - M - 80, y, 80, 16))
        y -= 24
        self.slider.setFrame_(NSMakeRect(M, y, W, 24))
        y -= 34
        self.readout.setFrame_(NSMakeRect(M, y, W, 26))
        y -= 20
        self.chg_label.setFrame_(NSMakeRect(M, y - 3, 98, 20))
        self.chg_field.setFrame_(NSMakeRect(M + 104, y - 4, 72, 22))
        self.chg_unit.setFrame_(NSMakeRect(M + 182, y - 3, 60, 20))
        y -= 22
        self.status.setFrame_(NSMakeRect(M, y, W, 16))
        self.help_text.setHidden_(not self.help_visible)
        self.help_text.setFrame_(NSMakeRect(M, 88, W, help_h))
        self.place_popup.setFrame_(NSMakeRect(M, 50, 172, 26))
        self.layer_button.setFrame_(NSMakeRect(PANEL_W - M - 104, 49, 104, 28))
        self.help_button.setFrame_(NSMakeRect(M, 12, 100, 28))
        self.dismiss_button.setFrame_(NSMakeRect(PANEL_W - M - 100, 12, 100, 28))
        self.help_button.setTitle_("Hide Help" if self.help_visible else "Help")

    # ── Units ───────────────────────────────────────────────────────────
    @objc.python_method
    def _unit(self):
        title = str(self.unit_popup.titleOfSelectedItem())
        return next(u for u in UNITS if u[0] == title)

    @objc.python_method
    def _fmt(self, px, signed=True):
        """Pixels as text in the chosen unit, using the document's ppi."""
        _name, abbr, per_inch = self._unit()
        if per_inch is None:
            txt = "%d" % round(px)
        else:
            txt = "%.2f" % (px / self.ppi * per_inch)
        if signed and round(px) > 0:
            txt = "+" + txt
        return "%s %s" % (txt, abbr)

    @objc.python_method
    def _update_readout(self, px):
        self.readout.setStringValue_(self._fmt(px))

    def unitChanged_(self, _sender):
        NSUserDefaults.standardUserDefaults().setObject_forKey_(
            str(self.unit_popup.titleOfSelectedItem()), UNIT_KEY)
        self._update_readout(int(round(self.slider.doubleValue())))
        if self.shown_change:
            self._show_change(self.shown_change)

    @objc.python_method
    def _show_change(self, px):
        """Show the applied amount in the editable field; None hides it."""
        self.shown_change = px
        show = bool(px)
        for v in (self.chg_label, self.chg_field, self.chg_unit):
            v.setHidden_(not show)
        if show:
            self.chg_field.setEnabled_(True)
            _n, abbr, per_inch = self._unit()
            amount = px if per_inch is None else px / self.ppi * per_inch
            self.chg_field.setStringValue_("%+d" % px if per_inch is None else "%+.2f" % amount)
            self.chg_unit.setStringValue_(abbr)
            self.chg_label.setStringValue_("Change")

    @objc.python_method
    def _parse_px(self, text):
        m = re.search(r"[-+]?\s*\d*\.?\d+", text.replace("\u2212", "-"))
        if not m:
            return None
        value = float(m.group().replace(" ", ""))
        _n, _abbr, per_inch = self._unit()
        return int(round(value if per_inch is None else value / per_inch * self.ppi))

    def changeEdited_(self, sender):
        px = self._parse_px(str(sender.stringValue()))
        if px is None:
            self._show_change(self.shown_change)       # put the old text back
            return
        self.panel.makeFirstResponder_(None)
        with self.cv:
            self.edit = px
            self.cv.notify()

    # ── Live resize ─────────────────────────────────────────────────────
    #
    # The slider only records the wanted amount. One worker thread applies
    # the LATEST amount, skipping any it was too slow to show, so dragging
    # never queues a backlog of Apple events.
    def slid_(self, sender):
        px = int(round(sender.doubleValue()))
        ev = NSApp().currentEvent()
        final = ev is not None and ev.type() == NSEventTypeLeftMouseUp
        self._update_readout(px)
        if not final and self.shown_change:
            self._show_change(None)          # the last change is now fixed
        with self.cv:
            # A release not yet handled stays a release.
            pending_final = self.wanted is not None and self.wanted[1]
            self.wanted = (px, final or pending_final)
            self.cv.notify()
        if final:
            sender.setDoubleValue_(0)             # back to the center
            self._update_readout(0)

    @objc.python_method
    def _worker(self):
        applied_steps = 0          # undo steps this drag has put on the stack
        applied_px = 0
        base_min = 0               # smaller side of the selection before the drag
        limit = None               # largest shrink that cannot erase the selection
        failed = False
        committed = None           # the last release, still open to refinement
        while True:
            with self.cv:
                while (self.wanted is None and self.edit is None
                       and not self.drop_committed):
                    self.cv.wait()
                edit, self.edit = self.edit, None
                drag, self.wanted = self.wanted, None
                if self.drop_committed:
                    self.drop_committed = False
                    committed, edit = None, None

            if edit is not None and committed is not None and drag is None:
                committed = self._refine(committed, edit)
                continue
            if drag is None:
                continue
            px, final = drag

            if limit is None and not failed:
                committed = None                   # a new drag fixes the last one
                ok, info = read_selection()
                if ok:
                    width, height, self.ppi, _b = info
                    base_min = min(width, height)
                    limit = max(0, int(base_min / 2) - 1)
                else:
                    failed = True
                    AppHelper.callAfter(self._set_status, info)

            if limit is not None and not failed:
                px = max(-limit, min(LIMIT, px))
                if px != applied_px:
                    ok, err = apply_steps(applied_steps, px)
                    if ok:
                        applied_steps, applied_px = len(chunks(px)), px
                    else:
                        # Unknown how far the undo got; leave the document alone.
                        failed = True
                        applied_steps = applied_px = 0
                        AppHelper.callAfter(self._set_status, err)

            if final:
                if not failed:
                    committed = None
                    if applied_px:
                        ok, info = read_selection()
                        if ok:
                            committed = {"steps": applied_steps, "px": applied_px,
                                         "bounds": info[3], "base_min": base_min}
                    AppHelper.callAfter(self._finished, applied_px)
                applied_steps = applied_px = 0
                limit, failed = None, False

    @objc.python_method
    def _refine(self, c, new_px):
        """Replace the last release's change with new_px, if nothing else moved."""
        ok, info = read_selection()
        if not ok or info[3] != c["bounds"]:
            AppHelper.callAfter(self._show_change, None)
            AppHelper.callAfter(self._set_status,
                                info if not ok else "The selection changed since.")
            return None
        limit = max(0, int(c["base_min"] / 2) - 1)
        new_px = max(-limit, min(MAX_REFINE, new_px))
        if new_px == c["px"]:
            AppHelper.callAfter(self._show_change, c["px"])
            return c
        ok, err = apply_steps(c["steps"], new_px)
        if not ok:
            AppHelper.callAfter(self._show_change, None)
            AppHelper.callAfter(self._set_status, err)
            return None
        AppHelper.callAfter(self._finished, new_px)
        if new_px == 0:
            return None
        ok, info = read_selection()
        if not ok:
            return None
        return {"steps": len(chunks(new_px)), "px": new_px,
                "bounds": info[3], "base_min": c["base_min"]}

    @objc.python_method
    def _set_status(self, text, keep_change=False):
        """Show a message. The Change field is hidden unless keep_change."""
        if not keep_change:
            self._show_change(None)
        self.status.setStringValue_(text)

    @objc.python_method
    def _finished(self, px):
        self.status.setStringValue_("")
        self._show_change(px if px else None)

    # ── App plumbing ────────────────────────────────────────────────────
    def placeChanged_(self, _sender):
        NSUserDefaults.standardUserDefaults().setObject_forKey_(
            str(self.place_popup.titleOfSelectedItem()), PLACE_KEY)

    def newLayer_(self, _sender):
        """Make the selection into a shape layer above or below the current one.

        One click, and no empty layer is left behind: Pixelmator's own
        `convert selection into shape` creates the shape layer (it lands on
        top), which is then moved next to the layer that was current and
        selected. Pixelmator indexes layers from 1 at the top, so "before"
        puts it above and "after" below.

        The new layer is the latest undo step, so a pending Change
        refinement would undo it instead -- the field is closed here.
        """
        with self.cv:
            self.drop_committed = True
            self.cv.notify()
        self.chg_field.setEnabled_(False)       # shown, but no longer refinable
        self._set_status("Making the layer…", keep_change=True)
        place = "before" if str(self.place_popup.titleOfSelectedItem()).startswith("Above") else "after"

        def work():
            path = target()
            if not path:
                msg = "Pixelmator Pro is not running."
            else:
                ok, out = osa(LAYER_SCRIPT % (path, place))
                if ok:
                    msg = "New layer added."
                elif "select" in out.lower() or "shape" in out.lower():
                    msg = "Needs an active selection."
                else:
                    msg = "No document is open."
            AppHelper.callAfter(self._set_status, msg, msg == "New layer added.")

        threading.Thread(target=work, daemon=True).start()

    def toggleHelp_(self, _sender):
        self.help_visible = not self.help_visible
        self._layout()

    def dismiss_(self, _sender):
        NSApp().terminate_(self)

    def applicationDidFinishLaunching_(self, _note):
        self.cv = threading.Condition()
        self.wanted = None
        self.edit = None
        self.drop_committed = False
        self.shown_change = None
        self.ppi = 72.0
        self._build_panel()
        threading.Thread(target=self._worker, daemon=True).start()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _flag):
        self.panel.orderFrontRegardless()
        return True

    def windowShouldClose_(self, _sender):
        NSApp().terminate_(self)
        return True


def main():
    app = NSApplication.sharedApplication()
    controller = Controller.alloc().init()
    app.setDelegate_(controller)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
