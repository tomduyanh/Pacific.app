"""Render a faithful mockup of the Pacific floating overlay (Subsystem D).

No browser is available in this environment, so this reproduces the overlay's
exact design values from desktop/src/overlay/overlay.css with representative
data, including a faint AI-chat window behind it to show the drop target.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 2  # supersample for crisp text, downscaled at the end
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def f(size, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, size * S)


def rr(d, box, radius, **kw):
    d.rounded_rectangle([c * S for c in box], radius=radius * S, **kw)


def text(d, xy, s, font, fill, anchor=None):
    d.text((xy[0] * S, xy[1] * S), s, font=font, fill=fill, anchor=anchor)


W, H = 940, 660
img = Image.new("RGB", (W * S, H * S), (17, 18, 22))
d = ImageDraw.Draw(img, "RGBA")

# ── Desktop wallpaper: soft diagonal gradient ────────────────────────────────
for y in range(H * S):
    t = y / (H * S)
    d.line([(0, y), (W * S, y)], fill=(int(24 + 18 * t), int(26 + 14 * t), int(38 + 10 * t)))

# ── Faint AI-chat window behind (drop target) ────────────────────────────────
rr(d, (40, 70, 600, 600), 14, fill=(248, 249, 251, 235))
rr(d, (40, 70, 600, 116), 14, fill=(238, 240, 244, 255))
for i, c in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
    d.ellipse([(58 + i * 18) * S, 86 * S, (58 + i * 18 + 11) * S, 97 * S], fill=c)
text(d, (96, 86), "New chat — AI assistant", f(12, True), (90, 96, 110))
text(d, (60, 150), "How should I phrase the Q3 partnership outreach?", f(13), (40, 44, 52))
rr(d, (60, 188, 580, 250), 12, fill=(245, 213, 74, 36), outline=(231, 191, 46, 180), width=2)
text(d, (74, 205), "▼  drop context here", f(12, True), (160, 130, 30))
# input bar
rr(d, (60, 540, 580, 580), 12, fill=(255, 255, 255, 255), outline=(214, 218, 224, 255), width=2)
text(d, (74, 552), "Message…  (drag a sticky note in)", f(12), (150, 156, 166))

# ════════════════════════════════════════════════════════════════════════════
# OVERLAY PANEL (right edge, per main.js placement)
# ════════════════════════════════════════════════════════════════════════════
PX, PY, PW = 612, 28, 304
NOTE = (247, 212, 74)
NOTE_EDGE = (227, 191, 46)
DARKBG = (28, 28, 32, 235)

# ── Bar ──────────────────────────────────────────────────────────────────────
bar_h = 38
rr(d, (PX, PY, PX + PW, PY + bar_h), 10, fill=DARKBG)
cx = PX + 14
d.ellipse([cx * S, (PY + 15) * S, (cx + 9) * S, (PY + 24) * S], fill=NOTE)
# busy pulse ring
d.ellipse([(cx - 3) * S, (PY + 12) * S, (cx + 12) * S, (PY + 27) * S], outline=(247, 212, 74, 90), width=2 * S)
text(d, (cx + 16, PY + 11), "Pacific", f(13, True), (243, 244, 246))
# count badge
bx = cx + 74
rr(d, (bx, PY + 12, bx + 17, PY + 28), 8, fill=NOTE)
text(d, (bx + 8.5, PY + 19.5), "3", f(10, True), (31, 41, 55), anchor="mm")
# task chip
tx = bx + 24
rr(d, (tx, PY + 12, tx + 50, PY + 27), 8, fill=(247, 212, 74, 46), outline=(247, 212, 74, 90), width=1)
text(d, (tx + 25, PY + 19.5), "email", f(10, True), NOTE, anchor="mm")
# action buttons
for i, gly in enumerate(["⟳", "▦", "▾"]):
    ax = PX + PW - 14 - (3 - i) * 30
    rr(d, (ax, PY + 7, ax + 24, PY + 31), 6, fill=(255, 255, 255, 22))
    text(d, (ax + 12, PY + 19), gly, f(13), (229, 231, 235), anchor="mm")

y = PY + bar_h + 8

# ── Context-type chips (Subsystem B) ─────────────────────────────────────────
KIND_BORDER = {"meta": (59, 130, 246), "file": (249, 115, 22),
               "data": (34, 197, 94), "people": (168, 85, 247)}
chips = [
    ("Tone & writing-voice profile", "match how you usually write", "meta"),
    ("Recipient / collaborator history", "recall prior threads", "people"),
    ("Prior emails on this topic", "reuse phrasing and commitments", "file"),
]
for label, reason, kind in chips:
    ch_h = 32
    rr(d, (PX, y, PX + PW, y + ch_h), 8, fill=DARKBG)
    d.rectangle([PX * S, y * S, (PX + 3) * S, (y + ch_h) * S], fill=KIND_BORDER[kind])
    text(d, (PX + 11, y + 6), label, f(11, True), (243, 244, 246))
    text(d, (PX + 11, y + 18), reason, f(10), (140, 144, 152))
    y += ch_h + 6

y += 4

# ── Sticky notes ─────────────────────────────────────────────────────────────
KIND_BADGE = {
    "meta": ((219, 234, 254), (29, 78, 216)),
    "file": ((255, 237, 213), (194, 65, 12)),
    "data": ((220, 252, 231), (21, 128, 61)),
    "people": ((243, 232, 255), (126, 34, 206)),
}
notes = [
    ("email_templates.md", "file", "Reusable outreach + follow-up email templates", 0.612, -1.1),
    ("tone_voice_profile.md", "meta", "Your professional writing tone and voice", 0.547, 0.8),
    ("contact_jane_doe.md", "people", "Prior threads and role context for Jane Doe", 0.498, -0.5),
]


def draw_note(title, kind, desc, score, tilt):
    nw, nh = PW, 96
    pad = 24  # rotation padding
    layer = Image.new("RGBA", ((nw + pad) * S, (nh + pad) * S), (0, 0, 0, 0))
    nd = ImageDraw.Draw(layer, "RGBA")
    ox, oy = pad // 2, pad // 2

    def lrr(box, radius, **kw):
        nd.rounded_rectangle([(box[0] + ox) * S, (box[1] + oy) * S,
                              (box[2] + ox) * S, (box[3] + oy) * S], radius=radius * S, **kw)

    def ltext(xy, s, font, fill, anchor=None):
        nd.text(((xy[0] + ox) * S, (xy[1] + oy) * S), s, font=font, fill=fill, anchor=anchor)

    # body + bottom edge + shadow-ish gradient (approx with solid + edge)
    lrr((0, 0, nw, nh), 10, fill=NOTE)
    lrr((0, nh - 3, nw, nh), 10, fill=NOTE_EDGE)
    # peeled corner
    nd.polygon([((nw - 14 + ox) * S, (nh + oy) * S), ((nw + ox) * S, (nh + oy) * S),
                ((nw + ox) * S, (nh - 14 + oy) * S)], fill=(0, 0, 0, 28))
    # file handle
    lrr((nw - 52, 8, nw - 12, 24), 5, fill=(0, 0, 0, 18))
    ltext((nw - 48, 11), "⇲ file", f(10), (107, 91, 21))
    # kind badge
    bg, fg = KIND_BADGE[kind]
    bw = 30 + len(kind) * 6
    lrr((12, 12, 12 + bw, 27), 4, fill=bg)
    ltext((12 + bw / 2, 19.5), kind.upper(), f(9, True), fg, anchor="mm")
    # title
    ltext((12 + bw + 8, 12), title, f(13, True), (31, 41, 55))
    # desc
    ltext((12, 38), desc, f(11), (75, 85, 99))
    # foot: score dot + value
    nd.ellipse([(14 + ox) * S, (74 + oy) * S, (20 + ox) * S, (80 + oy) * S], fill=(107, 91, 21, 140))
    ltext((24, 71), f"{score:.3f}", f(10), (107, 91, 21))
    # action buttons (Copy/Dismiss use subtle tints pre-blended over the note)
    btns = [("Attach", (31, 41, 55), (255, 255, 255)),
            ("Copy", (226, 196, 86), (31, 41, 55)),
            ("Dismiss", (223, 192, 80), (31, 41, 55))]
    bxr = nw - 12
    for lbl, bgc, fgc in reversed(btns):
        bwid = 16 + len(lbl) * 7
        outline = None if lbl == "Attach" else (180, 152, 40)
        lrr((bxr - bwid, 70, bxr, 86), 6, fill=bgc, outline=outline, width=1)
        ltext((bxr - bwid / 2, 78), lbl, f(11, True), fgc, anchor="mm")
        bxr -= bwid + 5

    return layer.rotate(tilt, resample=Image.BICUBIC, expand=False), pad


for title, kind, desc, score, tilt in notes:
    layer, pad = draw_note(title, kind, desc, score, tilt)
    img.paste(layer, ((PX - pad // 2) * S, (y - pad // 2) * S), layer)
    y += 96 + 10

# ── Status line ──────────────────────────────────────────────────────────────
text(d, (PX + 4, y - 2), "Context: Gmail · Compose — Q3 partnership", f(10), (140, 144, 152))

# ── Toast ────────────────────────────────────────────────────────────────────
tw = 150
tcx = PX + PW / 2
rr(d, (tcx - tw / 2, H - 42, tcx + tw / 2, H - 22), 10, fill=(20, 20, 24, 245))
text(d, (tcx, H - 32), "Copied to clipboard ✓", f(11, True), (255, 255, 255), anchor="mm")

out = img.resize((W, H), Image.LANCZOS)
dest = "/home/user/Pacific/desktop/docs/overlay-preview.png"
import os
os.makedirs(os.path.dirname(dest), exist_ok=True)
out.save(dest)
print("saved", dest)
