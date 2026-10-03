# PixProRefsel 1.4.1

Shrinks or grows the active selection in Pixelmator Pro with a slider, and
shows the change live as you drag.

Requires macOS 13 or later on Apple silicon, and Pixelmator Pro. Both the 3.x
build and the Creator Studio build work; the app drives whichever one is in
front.

## Using it

PixProRefsel is a small floating panel that stays above Pixelmator Pro and
never takes focus from it, so you can leave it up while you work.

1. Make a selection in Pixelmator Pro.
2. Drag the slider. Left shrinks the selection, right grows it, and the
   selection follows as you drag.
3. Let go. The size is fixed and the slider returns to the center, ready for
   the next nudge. Nudges add up.
4. To refine the amount you just applied, type a new number in the **Change**
   field and press Return, for example 0.9 to 1. The change is replaced, not
   added to. The field stays available until you drag again or change the
   selection some other way.

**New Layer** turns the selection into a shape on its own layer, in one click
and with no empty layer left behind. The menu beside it puts the new layer
above or below the current one (your choice is remembered), and the new layer
becomes the current layer. The Change field stays on screen showing the amount,
but can no longer be edited, since the layer is now the latest step.

The **Units** menu chooses how the amount is shown: pixels, centimeters or
inches. Centimeters and inches use the document's resolution, and your choice
is remembered. The slider covers 200 pixels each way, and a shrink stops short
of erasing the selection.

Each drag is one step in Pixelmator's undo history, so Undo reverses it.
**Hide Help** and **Help** show and hide the help text; **Dismiss**, or closing
the window, quits the app.

## Emulating a shape stroke

Pixelmator Pro shapes have a stroke, but a selection does not. PixProRefsel can
stand in for one: select a layer's outline, grow the selection by the stroke
width, click **New Layer** with *Below current layer*, and fill the new shape.
The shape sits behind the original as an outline you can recolor, resize or
restyle on its own, even around text or a pixel layer.

## Notes

- A selection has to be active, and a document open, or the panel says so.
- The first time you use it, macOS asks to let PixProRefsel control Pixelmator
  Pro. Allow it.

## Problems or suggestions

Please open an issue at
https://github.com/spurious-cox/pixprorefsel/issues
