"""Procedural energy-orb renderer for NEXUS (no Qt, numpy only).

The orb is drawn as a *light buffer*: every particle, filament, ring and spark
adds light to a floating-point image, the image is blurred at several scales to
make bloom, and the result is tone-mapped through an orange / gold / white-hot
colour ramp.  Additive light plus bloom is what gives the glowing, layered,
transparent look of a hologram, which ordinary vector drawing cannot match.

Nothing here is pre-rendered.  All geometry is generated once from a fixed seed
and animated every frame from time, the NEXUS state, and a real audio level.

Usage:
    engine = OrbEngine("balanced")
    engine.set_state("thinking")
    engine.set_level(0.4)          # real microphone / Piper amplitude, 0..1
    engine.step(dt)                # advance the animation
    frame = engine.render()        # uint8 array (size, size, 4), BGRA order
"""

import math

import numpy as np

try:  # scipy is in requirements.txt; the numpy fallback is used without it
    from scipy.ndimage import uniform_filter1d as _uniform_filter1d
except Exception:  # pragma: no cover - exercised only without scipy
    _uniform_filter1d = None


TAU = math.tau

# Render size and amount of detail for each quality level.
QUALITY = {
    "low": dict(res=384, fps=24, dust=2400, frags=420, band=200, spokes=18,
                bolts=16, motes=24, sparks=36, cloud=700, bokeh=8),
    "balanced": dict(res=512, fps=30, dust=4200, frags=760, band=340,
                     spokes=28, bolts=22, motes=40, sparks=60, cloud=1100,
                     bokeh=11),
    "high": dict(res=704, fps=30, dust=7000, frags=1200, band=520, spokes=40,
                 bolts=30, motes=56, sparks=90, cloud=1700, bokeh=14),
    "companion": dict(res=200, fps=20, dust=900, frags=150, band=90, spokes=8,
                      bolts=7, motes=10, sparks=14, cloud=320, bokeh=3),
}

# Target animation parameters for every NEXUS state.
#   energy   overall brightness and activity
#   spin     speed of the whole sphere
#   ringspin speed of the orbital rings
#   core     brightness of the centre
#   flow     speed of travelling particles
#   crackle  how often the lightning filaments re-form
#   inward   0 = particles drift outward, 1 = they stream into the core
#   warn     0..1 shift of the colour ramp toward red (error state)
STATE_PARAMS = {
    "idle": dict(energy=0.30, spin=1.0, ringspin=1.0, core=0.55, flow=0.35,
                 crackle=0.7, inward=0.0, warn=0.0),
    "listening": dict(energy=0.55, spin=1.25, ringspin=1.3, core=0.75,
                      flow=0.7, crackle=1.6, inward=0.5, warn=0.0),
    "thinking": dict(energy=0.88, spin=1.7, ringspin=2.7, core=1.15,
                     flow=1.2, crackle=4.5, inward=0.3, warn=0.0),
    "speaking": dict(energy=0.62, spin=1.3, ringspin=1.5, core=0.9,
                     flow=0.9, crackle=2.2, inward=0.0, warn=0.0),
    "researching": dict(energy=0.78, spin=1.5, ringspin=2.1, core=0.95,
                        flow=1.7, crackle=2.6, inward=1.0, warn=0.0),
    "error": dict(energy=0.34, spin=0.45, ringspin=0.6, core=0.5, flow=0.2,
                  crackle=1.0, inward=0.0, warn=0.75),
}

VALID_STATES = tuple(STATE_PARAMS)
PARAM_NAMES = tuple(STATE_PARAMS["idle"])

# Colour ramps: tone-mapped brightness (0..1) -> RGB.
_RAMP_NORMAL = (
    (0.00, 0, 0, 0), (0.05, 20, 6, 1), (0.16, 74, 22, 2),
    (0.34, 182, 76, 6), (0.56, 252, 140, 24), (0.76, 255, 196, 86),
    (0.91, 255, 234, 160), (1.00, 255, 250, 226),
)
_RAMP_WARN = (
    (0.00, 0, 0, 0), (0.05, 22, 5, 1), (0.16, 80, 16, 3),
    (0.34, 190, 50, 8), (0.56, 250, 104, 18), (0.76, 255, 166, 70),
    (0.91, 255, 214, 148), (1.00, 255, 244, 218),
)

LUT_SIZE = 1024


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------

def _normalise(vectors):
    """Scale rows to unit length; zero rows stay zero."""
    vectors = np.asarray(vectors, dtype=np.float64)
    length = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(length, 1e-12)


def rotation_matrix(yaw, pitch, roll):
    """3x3 rotation, applied to row vectors as points @ matrix.T."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]])
    rz = np.array([[cr, -sr, 0.0], [sr, cr, 0.0], [0.0, 0.0, 1.0]])
    return rz @ rx @ ry


def tangent_basis(normals):
    """Two unit vectors perpendicular to each row of `normals` (and to each other)."""
    normals = _normalise(normals)
    helper = np.where(
        np.abs(normals[:, 1:2]) < 0.9,
        np.array([[0.0, 1.0, 0.0]]),
        np.array([[1.0, 0.0, 0.0]]),
    )
    first = _normalise(np.cross(helper, normals))
    second = np.cross(normals, first)
    return first, second


def box_blur(image, radius, passes=2):
    """Separable box blur; two passes approximate a gaussian."""
    if radius <= 0:
        return image
    out = image
    size = 2 * radius + 1
    for _ in range(passes):
        for axis in (0, 1):
            if _uniform_filter1d is not None:
                out = _uniform_filter1d(
                    out, size, axis=axis, mode="constant", cval=0.0)
            else:
                out = _blur_axis(out, radius, axis)
    return out


def _blur_axis(image, radius, axis):
    """Numpy-only box blur along one axis (zero padded)."""
    size = 2 * radius + 1
    length = image.shape[axis]
    pad = [(0, 0), (0, 0)]
    pad[axis] = (radius, radius)
    padded = np.pad(image, pad)
    cumulative = np.cumsum(padded, axis=axis, dtype=np.float64)
    zero_shape = list(cumulative.shape)
    zero_shape[axis] = 1
    cumulative = np.concatenate(
        [np.zeros(zero_shape, dtype=np.float64), cumulative], axis=axis)
    upper = np.take(cumulative, np.arange(size, size + length), axis=axis)
    lower = np.take(cumulative, np.arange(0, length), axis=axis)
    return ((upper - lower) / size).astype(np.float32)


def blur3(image):
    """Cheap separable [1 2 1] / 4 blur (zero edges) using array slices."""
    wide = image * 0.5
    wide[:, 1:] += image[:, :-1] * 0.25
    wide[:, :-1] += image[:, 1:] * 0.25
    tall = wide * 0.5
    tall[1:] += wide[:-1] * 0.25
    tall[:-1] += wide[1:] * 0.25
    return tall


def downsample(image, factor=2):
    """Halve the size by averaging 2 x 2 blocks (size must be even)."""
    return (image[0::2, 0::2] + image[1::2, 0::2]
            + image[0::2, 1::2] + image[1::2, 1::2]) * 0.25


def upsample(image, factor=2, smooth=True):
    """Double the size by repeating pixels, then smooth the blockiness away."""
    big = np.repeat(np.repeat(image, 2, axis=0), 2, axis=1)
    if smooth:
        big = blur3(big)
    return big


def splat(x, y, weight, width, height):
    """Bilinearly add point lights into a (height, width) float32 image."""
    if x.size == 0:
        return np.zeros((height, width), dtype=np.float32)
    ix = np.floor(x).astype(np.int64)
    iy = np.floor(y).astype(np.int64)
    ok = (ix >= 0) & (ix < width - 1) & (iy >= 0) & (iy < height - 1)
    if not ok.all():
        ix, iy, x, y, weight = ix[ok], iy[ok], x[ok], y[ok], weight[ok]
    fx = x - ix
    fy = y - iy
    base = iy * width + ix
    indices = np.concatenate((base, base + 1, base + width, base + width + 1))
    weights = np.concatenate((
        weight * (1.0 - fx) * (1.0 - fy),
        weight * fx * (1.0 - fy),
        weight * (1.0 - fx) * fy,
        weight * fx * fy,
    ))
    flat = np.bincount(indices, weights=weights, minlength=width * height)
    return flat.astype(np.float32).reshape(height, width)


def build_lut(warn=0.0):
    """Colour ramp lookup table, (LUT_SIZE, 4) uint8 in BGRA order."""
    positions = np.linspace(0.0, 1.0, LUT_SIZE)
    channels = []
    for channel in (1, 2, 3):
        normal = np.interp(positions, [s[0] for s in _RAMP_NORMAL],
                           [s[channel] for s in _RAMP_NORMAL])
        alarm = np.interp(positions, [s[0] for s in _RAMP_WARN],
                          [s[channel] for s in _RAMP_WARN])
        channels.append(normal * (1.0 - warn) + alarm * warn)
    red, green, blue = channels
    lut = np.empty((LUT_SIZE, 4), dtype=np.uint8)
    lut[:, 0] = np.clip(blue, 0, 255)
    lut[:, 1] = np.clip(green, 0, 255)
    lut[:, 2] = np.clip(red, 0, 255)
    lut[:, 3] = 255
    return lut


def smooth_towards(current, target, dt, rate):
    """Frame-rate independent exponential approach."""
    return current + (target - current) * (1.0 - math.exp(-max(0.0, dt) * rate))


# ----------------------------------------------------------------------
# The engine
# ----------------------------------------------------------------------

class OrbEngine:
    """Generates and renders the NEXUS energy orb."""

    SHELL_RADIUS_FRACTION = 0.60     # shell radius as a share of half the image

    def __init__(self, quality="balanced", seed=27011, transparent=False):
        """`transparent=True` writes premultiplied alpha (for see-through windows)."""
        if quality not in QUALITY:
            quality = "balanced"
        self.quality = quality
        self.transparent = bool(transparent)
        self.cfg = dict(QUALITY[quality])
        self.res = int(self.cfg["res"])
        self.fps = int(self.cfg["fps"])
        # Block sizes used for bloom need the size divisible by 4.
        self.res -= self.res % 4
        self.centre = self.res / 2.0
        self.base_radius = self.res * 0.5 * self.SHELL_RADIUS_FRACTION
        self.radius = self.base_radius
        # About one sample per pixel along every line.
        self.spacing = 0.9
        self.rng = np.random.default_rng(seed)
        self.live_rng = np.random.default_rng(seed + 1)

        self.t = 0.0
        self.state = "idle"
        self.params = dict(STATE_PARAMS["idle"])
        self.level_target = 0.0
        self.level = 0.0
        self.pulse = 0.0
        self.yaw = 0.0
        self.waves = []                 # [(birth_time, strength)]
        self._last_wave = -10.0
        self._level_prev = 0.0
        self._bolt_clock = 0.0
        self._lut_warn = -1.0
        self._lut = build_lut(0.0)

        self._build_dust()
        self._build_fragments()
        self._build_bands()
        self._build_rings()
        self._build_spokes()
        self._build_bolts()
        self._build_core()
        self._build_particles()

        size = self.res
        self._out = np.zeros((size, size, 4), dtype=np.uint8)
        self._out[..., 3] = 255
        self._noise = self.rng.random(size * size).astype(np.float32)
        qs = size // 4
        yy, xx = np.mgrid[0:qs, 0:qs].astype(np.float32)
        self._quarter_d2 = (xx - qs / 2.0) ** 2 + (yy - qs / 2.0) ** 2

    # ------------------------------------------------------------------
    # Geometry construction
    # ------------------------------------------------------------------

    def _unit_vectors(self, count):
        return _normalise(self.rng.normal(size=(count, 3)))

    def _clumped(self, count, clumped_share=0.5):
        """Unit vectors, part uniform and part gathered into irregular patches."""
        if not hasattr(self, "_clump_centres"):
            self._clump_centres = self._unit_vectors(16)
            self._clump_sigma = self.rng.uniform(0.16, 0.46, 16)
        clumped = int(count * clumped_share)
        uniform = self._unit_vectors(count - clumped)
        which = self.rng.integers(0, len(self._clump_centres), clumped)
        spread = self.rng.normal(size=(clumped, 3)) * self._clump_sigma[which, None]
        patches = _normalise(self._clump_centres[which] + spread)
        return np.concatenate((uniform, patches))

    def _samples_for(self, length_units):
        """How many samples a line of this length needs for ~1px spacing."""
        return max(2, int(length_units * self.base_radius / self.spacing) + 1)

    def _build_dust(self):
        """The thin, irregular shell of golden sparks."""
        count = self.cfg["dust"]
        directions = self._clumped(count, 0.45)
        radius = 1.0 + self.rng.normal(0.0, 0.011, count)
        stray = self.rng.random(count) < 0.035
        radius[stray] = self.rng.uniform(1.04, 1.5, stray.sum())
        self.dust_pos = directions * radius[:, None]
        brightness = self.rng.lognormal(-0.35, 0.65, count)
        hot = self.rng.random(count) < 0.06
        brightness[hot] *= 3.2
        self.dust_w = brightness.astype(np.float32) * 0.55
        self.dust_phase = self.rng.uniform(0, TAU, count)
        self.dust_rate = self.rng.uniform(0.6, 2.6, count)

    def _build_fragments(self):
        """Short circuit-board strokes lying on the shell, many with right-angle bends."""
        count = self.cfg["frags"]
        centres = self._clumped(count, 0.55)
        east, north = tangent_basis(centres)
        aligned = self.rng.random(count) < 0.62
        quarter = self.rng.integers(0, 2, count) * (math.pi / 2)
        angle = np.where(aligned, quarter + self.rng.normal(0, 0.05, count),
                         self.rng.uniform(0, math.pi, count))
        length = np.clip(self.rng.lognormal(math.log(0.05), 0.62, count),
                         0.012, 0.22)
        bend = self.rng.random(count) < 0.38
        blink_phase = self.rng.uniform(0, TAU, count)
        blink_rate = self.rng.uniform(0.4, 3.0, count)
        strength = self.rng.lognormal(-0.1, 0.45, count)

        points, weights, phases, rates = [], [], [], []
        for index in range(count):
            direction = math.cos(angle[index]) * east[index] \
                + math.sin(angle[index]) * north[index]
            side = _normalise(np.cross(centres[index], direction)[None, :])[0]
            span = length[index]
            segments = [(-span / 2, span / 2, direction, 0.0, 0.0)]
            if bend[index]:
                segments.append((0.0, span * 0.45, side, span / 2, 0.0))
            for start, stop, vec, forward, _unused in segments:
                steps = self._samples_for(stop - start)
                along = np.linspace(start, stop, steps)
                if forward:
                    base = centres[index] + direction * forward
                else:
                    base = centres[index]
                path = _normalise(base[None, :] + vec[None, :] * along[:, None])
                path *= 1.0 + self.rng.normal(0.0, 0.004)
                points.append(path)
                weights.append(np.full(steps, strength[index] * 0.62))
                phases.append(np.full(steps, blink_phase[index]))
                rates.append(np.full(steps, blink_rate[index]))
        self.frag_pos = np.concatenate(points)
        self.frag_w = np.concatenate(weights).astype(np.float32)
        self.frag_phase = np.concatenate(phases)
        self.frag_rate = np.concatenate(rates)

    def _build_bands(self):
        """Streams of dust that circle the sphere along tilted bands."""
        bands = 6
        per_band = max(40, self.cfg["band"])
        axes = self._unit_vectors(bands)
        first, second = tangent_basis(axes)
        polar = self.rng.uniform(0.35, 1.25, bands)
        speeds = self.rng.choice((-1.0, 1.0), bands) * self.rng.uniform(0.15, 0.5, bands)
        band_id = np.repeat(np.arange(bands), per_band)
        total = bands * per_band
        psi = self.rng.uniform(0, TAU, total)
        # Gaps break each band into several streams.
        gap_centres = self.rng.uniform(0, TAU, (bands, 3))
        keep = np.ones(total, dtype=bool)
        for band in range(bands):
            mask = band_id == band
            for centre in gap_centres[band]:
                width = self.rng.uniform(0.25, 0.7)
                difference = np.abs((psi[mask] - centre + math.pi) % TAU - math.pi)
                keep[np.where(mask)[0][difference < width]] = False
        self.band_axis = axes[band_id[keep]]
        self.band_u = first[band_id[keep]]
        self.band_v = second[band_id[keep]]
        self.band_polar = polar[band_id[keep]] + self.rng.normal(0, 0.022, keep.sum())
        self.band_psi = psi[keep]
        self.band_speed = speeds[band_id[keep]]
        self.band_radius = 1.0 + self.rng.normal(0, 0.014, keep.sum())
        self.band_w = (self.rng.lognormal(-0.2, 0.5, keep.sum()) * 0.7).astype(np.float32)

    def _build_rings(self):
        """Orbital ellipses at different tilts, with ticks, dashes and moving bright arcs."""
        # (scale, flatten, thickness, brightness, inner)
        specs = [
            (1.40, 0.62, 1, 0.95, False), (1.27, 0.88, 3, 0.85, False),
            (1.16, 0.74, 1, 1.05, False), (1.08, 0.93, 1, 0.80, False),
            (1.33, 0.52, 1, 0.70, False),
            (0.31, 0.80, 1, 1.00, True), (0.24, 0.62, 1, 1.15, True),
            (0.19, 0.93, 1, 1.30, True),
        ]
        ring_count = len(specs)
        self.ring_normal = self._unit_vectors(ring_count)
        self.ring_u, self.ring_v = tangent_basis(self.ring_normal)
        self.ring_speed = self.rng.choice((-1.0, 1.0), ring_count) \
            * self.rng.uniform(0.10, 0.34, ring_count)
        self.ring_spec = specs

        ids, thetas, scales, flattens, base, dash_n, dash_s, duty = \
            [], [], [], [], [], [], [], []
        bump_a, bump_b, bump_sa, bump_sb = [], [], [], []
        for ring, (scale, flatten, thickness, brightness, inner) in enumerate(specs):
            circumference = TAU * scale * (1 + flatten) / 2
            steps = self._samples_for(circumference)
            theta = np.linspace(0, TAU, steps, endpoint=False)
            offsets = (0.0,) if thickness == 1 else (-0.014, 0.0, 0.014)
            for offset in offsets:
                ids.append(np.full(steps, ring))
                thetas.append(theta)
                scales.append(np.full(steps, scale + offset))
                flattens.append(np.full(steps, flatten))
                base.append(np.full(steps, brightness * (0.55 if offset else 1.0)))
                dash_n.append(np.full(steps, self.rng.integers(5, 15)))
                dash_s.append(np.full(steps, self.rng.uniform(0.05, 0.25)
                                      * self.rng.choice((-1, 1))))
                duty.append(np.full(steps, self.rng.uniform(0.45, 0.8)))
                bump_a.append(np.full(steps, self.rng.uniform(0, TAU)))
                bump_b.append(np.full(steps, self.rng.uniform(0, TAU)))
                bump_sa.append(np.full(steps, self.rng.uniform(0.4, 1.1)
                                       * self.rng.choice((-1, 1))))
                bump_sb.append(np.full(steps, self.rng.uniform(0.3, 0.9)
                                       * self.rng.choice((-1, 1))))
        self.rs_ring = np.concatenate(ids)
        self.rs_theta = np.concatenate(thetas)
        self.rs_scale = np.concatenate(scales)
        self.rs_flat = np.concatenate(flattens)
        self.rs_base = np.concatenate(base)
        self.rs_dash_n = np.concatenate(dash_n)
        self.rs_dash_s = np.concatenate(dash_s)
        self.rs_duty = np.concatenate(duty)
        self.rs_bump_a = np.concatenate(bump_a)
        self.rs_bump_b = np.concatenate(bump_b)
        self.rs_bump_sa = np.concatenate(bump_sa)
        self.rs_bump_sb = np.concatenate(bump_sb)

        # Tick marks on the larger rings, short strokes pointing outward.
        tick_rings = [0, 2, 3, 4]
        tick_ring, tick_theta, tick_off = [], [], []
        for ring in tick_rings:
            count = 90 if ring in (0, 2) else 60
            for index in range(count):
                long_tick = index % 5 == 0
                for step in range(3 if long_tick else 2):
                    tick_ring.append(ring)
                    tick_theta.append(TAU * index / count)
                    tick_off.append(0.012 + 0.011 * step if long_tick else 0.010 + 0.007 * step)
        self.tick_ring = np.array(tick_ring)
        self.tick_theta = np.array(tick_theta)
        self.tick_off = np.array(tick_off)

        # Chunky blocks riding on two rings (like the data tiles in the references).
        blocks = 26
        self.block_ring = self.rng.choice([0, 1, 2, 4], blocks)
        self.block_theta = self.rng.uniform(0, TAU, blocks)
        self.block_len = self.rng.uniform(0.03, 0.11, blocks)
        self.block_speed = self.rng.choice((-1, 1), blocks) * self.rng.uniform(0.05, 0.22, blocks)

    def _build_spokes(self):
        """Long straight filaments crossing the interior like the spokes of a wheel."""
        count = self.cfg["spokes"]
        start = self._unit_vectors(count)
        to_core = self.rng.random(count) < 0.45
        end = np.empty_like(start)
        end[to_core] = self._unit_vectors(to_core.sum()) \
            * self.rng.uniform(0.10, 0.30, to_core.sum())[:, None]
        end[~to_core] = self._unit_vectors((~to_core).sum()) \
            * self.rng.uniform(1.0, 1.2, (~to_core).sum())[:, None]
        self.spoke_start, self.spoke_end = start, end
        self.spoke_speed = self.rng.uniform(0.25, 0.7, count)
        self.spoke_offset = self.rng.uniform(0, 1.5, count)
        self.spoke_base = self.rng.uniform(0.22, 0.6, count)
        ids, along = [], []
        for index in range(count):
            steps = self._samples_for(np.linalg.norm(end[index] - start[index]))
            ids.append(np.full(steps, index))
            along.append(np.linspace(0.0, 1.0, steps))
        self.sp_id = np.concatenate(ids)
        self.sp_s = np.concatenate(along)

    def _make_bolts(self, count, depth=4):
        """Jagged lightning paths built by midpoint displacement: (count, nodes, 3)."""
        rng = self.live_rng if hasattr(self, "live_rng") else self.rng
        start = self._unit_vectors(count)
        far = rng.random(count) < 0.55
        end = np.where(
            far[:, None],
            _normalise(start + rng.normal(size=(count, 3)) * 0.95),
            _normalise(rng.normal(size=(count, 3))) * rng.uniform(0.05, 0.8, (count, 1)),
        )
        nodes = np.stack((start, end), axis=1)
        amplitude = 0.42
        for _ in range(depth):
            mids = (nodes[:, :-1] + nodes[:, 1:]) / 2.0
            seg = np.linalg.norm(nodes[:, 1:] - nodes[:, :-1], axis=2, keepdims=True)
            mids = mids + rng.normal(size=mids.shape) * seg * amplitude
            merged = np.empty((count, nodes.shape[1] * 2 - 1, 3))
            merged[:, 0::2] = nodes
            merged[:, 1::2] = mids
            nodes = merged
            amplitude *= 0.72
        # Keep every filament inside (or just outside) the shell.
        reach = np.linalg.norm(nodes, axis=2, keepdims=True)
        return nodes * np.minimum(1.0, 1.06 / np.maximum(reach, 1e-9))

    def _build_bolts(self):
        count = self.cfg["bolts"]
        self.bolt_nodes = self._make_bolts(count)
        self.bolt_phase = self.rng.uniform(0, TAU, count)
        self.bolt_rate = self.rng.uniform(1.0, 5.0, count)
        self.bolt_base = self.rng.uniform(0.45, 1.1, count)
        # Samples per bolt segment: enough for ~1px spacing at typical segment length.
        self.bolt_reps = max(2, int(0.07 * self.base_radius / self.spacing))
        self.bolt_frac = np.tile(
            np.linspace(0, 1, self.bolt_reps, endpoint=False), self.bolt_nodes.shape[1] - 1)
        self.bolt_seg = np.repeat(np.arange(self.bolt_nodes.shape[1] - 1), self.bolt_reps)

    def _build_core(self):
        """White-hot centre: a hollow reactor ring, spiral arms and an irregular dust cloud."""
        steps = self._samples_for(TAU * 0.16)
        theta = np.linspace(0, TAU, steps, endpoint=False)
        self.core_ring = np.stack((np.cos(theta), np.sin(theta), np.zeros_like(theta)), axis=1)
        self.core_ring_theta = theta

        arms, per_arm = 4, 150
        arm_id = np.repeat(np.arange(arms), per_arm)
        turn = np.tile(np.linspace(0.0, 1.0, per_arm), arms)
        base_angle = TAU * arm_id / arms + turn * 3.6 * math.pi
        radius = 0.13 + turn * 0.20 + self.rng.normal(0, 0.008, arms * per_arm)
        self.arm_pos = np.stack((radius * np.cos(base_angle), radius * np.sin(base_angle),
                                 self.rng.normal(0, 0.012, arms * per_arm)), axis=1)
        self.arm_w = ((1.0 - turn * 0.7) * self.rng.lognormal(0, 0.4, arms * per_arm)
                      ).astype(np.float32)

        cloud = self.cfg["cloud"]
        centres = self._unit_vectors(7) * self.rng.uniform(0.05, 0.36, (7, 1))
        which = self.rng.integers(0, 7, cloud)
        self.cloud_pos = centres[which] + self.rng.normal(size=(cloud, 3)) * \
            self.rng.uniform(0.06, 0.2, (cloud, 1))
        self.cloud_w = (self.rng.lognormal(-0.8, 0.6, cloud) * 0.5).astype(np.float32)
        self.cloud_phase = self.rng.uniform(0, TAU, cloud)

    def _build_particles(self):
        """Travelling lights, sparks and soft out-of-focus dots."""
        motes = self.cfg["motes"]
        self.mote_ring = self.rng.integers(0, 5, motes)
        self.mote_theta = self.rng.uniform(0, TAU, motes)
        self.mote_speed = self.rng.choice((-1, 1), motes) * self.rng.uniform(0.4, 1.3, motes)
        self.mote_spoke = self.rng.integers(0, len(self.spoke_start), motes)
        self.mote_offset = self.rng.uniform(0, 1, motes)
        self.mote_on_spoke = self.rng.random(motes) < 0.45
        self.trail = 7

        sparks = self.cfg["sparks"]
        self.spark_dir = self._unit_vectors(sparks)
        side, _ = tangent_basis(self.spark_dir)
        self.spark_side = side
        self.spark_rate = self.rng.uniform(0.55, 1.5, sparks)
        self.spark_offset = self.rng.uniform(0, 1, sparks)
        self.spark_rank = self.rng.permutation(sparks) / max(1, sparks - 1)

        bokeh = self.cfg["bokeh"]
        self.bokeh_pos = self._unit_vectors(bokeh) * self.rng.uniform(0.4, 1.35, (bokeh, 1))
        self.bokeh_w = self.rng.uniform(0.35, 0.9, bokeh)
        self.bokeh_phase = self.rng.uniform(0, TAU, bokeh)

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------

    def set_state(self, state):
        state = str(state or "idle").lower()
        self.state = state if state in STATE_PARAMS else "idle"

    def set_level(self, level):
        """Real audio level, 0..1 (microphone while listening, Piper while speaking)."""
        try:
            level = float(level)
        except (TypeError, ValueError):
            level = 0.0
        self.level_target = min(1.0, max(0.0, level))

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def step(self, dt):
        """Advance the animation by dt seconds."""
        dt = min(0.1, max(0.0, float(dt)))
        self.t += dt

        target = STATE_PARAMS[self.state]
        for name in PARAM_NAMES:
            self.params[name] = smooth_towards(
                self.params[name], target[name], dt, 3.0)

        rate = 28.0 if self.level_target > self.level else 7.0
        self.level = smooth_towards(self.level, self.level_target, dt, rate)

        # A new shock-wave leaves the core each time the audio level jumps.
        rise = self.level_target - self._level_prev
        self._level_prev = self.level_target
        if (rise > 0.12 and self.level_target > 0.25
                and self.t - self._last_wave > 0.14):
            self.waves.append((self.t, min(1.0, self.level_target)))
            self._last_wave = self.t
        self.waves = [w for w in self.waves if self.t - w[0] < 0.9][-4:]

        self.yaw += dt * 0.13 * self.params["spin"]

        # Lightning filaments re-form at random, faster when NEXUS is busy.
        self._bolt_clock += dt * self.params["crackle"] * 3.0
        while self._bolt_clock >= 1.0:
            self._bolt_clock -= 1.0
            index = int(self.live_rng.integers(0, len(self.bolt_nodes)))
            self.bolt_nodes[index] = self._make_bolts(1)[0]

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self):
        """Draw the current frame. Returns the persistent (res, res, 4) BGRA buffer."""
        p = self.params
        t = self.t
        energy = p["energy"] + 0.55 * self.level
        gain = 0.72 + 0.55 * energy
        breath = 1.0 + 0.022 * math.sin(TAU * 0.21 * t) + 0.07 * self.level
        self.radius = self.base_radius * breath

        pitch = 0.40 + 0.06 * math.sin(0.21 * t)
        roll = 0.10 * math.sin(0.13 * t)
        shell_rot = rotation_matrix(self.yaw, pitch, roll)
        inner_rot = rotation_matrix(-self.yaw * 1.6 + 0.8, pitch * 0.6 - 0.2, roll * 2)
        spoke_rot = rotation_matrix(self.yaw * 0.55 + 2.0, pitch + 0.3, -roll)

        self._xs, self._ys, self._ws = [], [], []

        self._emit_dust(shell_rot, gain)
        self._emit_fragments(shell_rot, gain)
        self._emit_bands(shell_rot, gain)
        self._emit_rings(shell_rot, gain)
        self._emit_spokes(spoke_rot, gain)
        self._emit_bolts(spoke_rot, gain)
        self._emit_core(inner_rot, gain)
        self._emit_motes(shell_rot, spoke_rot, gain)
        self._emit_sparks(shell_rot, gain)
        self._emit_waves(gain)

        size = self.res
        acc = splat(np.concatenate(self._xs), np.concatenate(self._ys),
                    np.concatenate(self._ws), size, size)

        bokeh = self._bokeh_layer(shell_rot)
        glow = self._bloom(acc, bokeh, p["core"] + 0.8 * self.level)

        total = acc * 0.85 + glow
        value = 1.0 - np.exp(-total * 1.05)
        warn = p["warn"]
        if abs(warn - self._lut_warn) > 0.01:
            self._lut = build_lut(warn)
            self._lut_warn = warn
        index = (value * (LUT_SIZE - 1) + self._noise.reshape(size, size)).astype(np.int32)
        np.take(self._lut, index.reshape(-1), axis=0,
                out=self._out.reshape(-1, 4), mode="clip")
        if self.transparent:
            # Premultiplied alpha: the brightest channel decides opacity.
            np.max(self._out[..., :3], axis=2, out=self._out[..., 3])
        return self._out

    @property
    def frame(self):
        """The persistent BGRA frame buffer that render() fills."""
        return self._out

    # -- projection --------------------------------------------------------

    def _add(self, points, rotation, weight, limb=None):
        """Rotate, project and queue lights (depth dims the far side).

        `limb=(floor, power)` makes points seen edge-on brighter than points
        seen face-on, which keeps the middle of the sphere see-through.
        """
        rotated = points @ rotation.T
        z = rotated[:, 2]
        scale = self.radius / (1.0 - 0.12 * z)
        x = self.centre + rotated[:, 0] * scale
        y = self.centre - rotated[:, 1] * scale
        depth = 0.40 + 0.60 * np.clip((z + 1.0) * 0.5, 0.0, 1.0)
        if limb is not None:
            floor, power = limb
            edge = np.clip(1.0 - z * z, 0.0, 1.0) ** power
            depth = depth * (floor + (1.0 - floor) * edge)
        self._xs.append(x)
        self._ys.append(y)
        self._ws.append(weight * depth)

    # -- layers --------------------------------------------------------------

    def _emit_dust(self, rot, gain):
        twinkle = 0.7 + 0.3 * np.sin(self.t * self.dust_rate + self.dust_phase)
        self._add(self.dust_pos, rot, self.dust_w * twinkle * gain, limb=(0.16, 1.3))

    def _emit_fragments(self, rot, gain):
        blink = np.sin(self.t * self.frag_rate + self.frag_phase)
        level = 0.5 + 0.5 * np.clip(blink * 1.6, -1.0, 1.0)
        self._add(self.frag_pos, rot, self.frag_w * (0.35 + 0.9 * level) * gain, limb=(0.22, 1.1))

    def _emit_bands(self, rot, gain):
        psi = self.band_psi + self.band_speed * self.t * (0.6 + self.params["flow"])
        ring = np.cos(psi)[:, None] * self.band_u + np.sin(psi)[:, None] * self.band_v
        points = (np.cos(self.band_polar)[:, None] * self.band_axis
                  + np.sin(self.band_polar)[:, None] * ring) * self.band_radius[:, None]
        self._add(points, rot, self.band_w * 1.5 * gain, limb=(0.55, 1.0))

    def _ring_basis(self):
        """Rings turn about their own normals, each at its own speed."""
        angle = self.ring_speed * self.t * self.params["ringspin"]
        cos_a, sin_a = np.cos(angle)[:, None], np.sin(angle)[:, None]
        u = cos_a * self.ring_u + sin_a * self.ring_v
        v = -sin_a * self.ring_u + cos_a * self.ring_v
        return u, v

    def _emit_rings(self, rot, gain):
        u, v = self._ring_basis()
        ids = self.rs_ring
        theta = self.rs_theta
        points = (self.rs_scale * np.cos(theta))[:, None] * u[ids] \
            + (self.rs_scale * self.rs_flat * np.sin(theta))[:, None] * v[ids]
        t = self.t
        gate = ((theta / TAU * self.rs_dash_n + t * self.rs_dash_s) % 1.0) < self.rs_duty
        arc_a = self._ang_bump(theta - (self.rs_bump_a + self.rs_bump_sa * t * self.params["ringspin"]), 0.42)
        arc_b = self._ang_bump(theta - (self.rs_bump_b + self.rs_bump_sb * t * self.params["ringspin"]), 0.28)
        weight = self.rs_base * (0.12 + 0.62 * gate) * (0.60 + 2.3 * arc_a + 1.6 * arc_b)
        self._add(points, rot, (weight * (0.8 + 0.5 * self.level) * gain * self.spacing).astype(np.float32))

        # Tick marks on the bigger rings.
        ring = self.tick_ring
        theta = self.tick_theta
        scale = self.rs_scale_for(ring) + self.tick_off
        flat = self.rs_flat_for(ring)
        ticks = (scale * np.cos(theta))[:, None] * u[ring] \
            + (scale * flat * np.sin(theta))[:, None] * v[ring]
        self._add(ticks, rot, np.full(len(ticks), 0.34 * gain, dtype=np.float32))

        # Bright data blocks sliding along the rings.
        steps = 5
        along = np.linspace(-0.5, 0.5, steps)
        theta = (self.block_theta + self.block_speed * t * self.params["ringspin"])[:, None] \
            + along[None, :] * self.block_len[:, None]
        ring = np.repeat(self.block_ring[:, None], steps, axis=1)
        scale = self.rs_scale_for(ring.ravel())
        flat = self.rs_flat_for(ring.ravel())
        theta = theta.ravel()
        blocks = (scale * np.cos(theta))[:, None] * u[ring.ravel()] \
            + (scale * flat * np.sin(theta))[:, None] * v[ring.ravel()]
        self._add(blocks, rot, np.full(len(blocks), 1.6 * gain, dtype=np.float32))

    def rs_scale_for(self, ring_ids):
        return np.array([s[0] for s in self.ring_spec])[ring_ids]

    def rs_flat_for(self, ring_ids):
        return np.array([s[1] for s in self.ring_spec])[ring_ids]

    @staticmethod
    def _ang_bump(angle, width):
        wrapped = (angle + math.pi) % TAU - math.pi
        return np.exp(-(wrapped / width) ** 2)

    def _flow_phase(self, speed, offset):
        """Position of a travelling pulse along a 0..1 line."""
        flow = 0.25 + self.params["flow"]
        return (self.t * speed * flow + offset) % 1.5 - 0.25

    def _emit_spokes(self, rot, gain):
        ids, s = self.sp_id, self.sp_s
        start, end = self.spoke_start[ids], self.spoke_end[ids]
        inward = self.params["inward"]
        points = start + (end - start) * s[:, None]
        position = self._flow_phase(self.spoke_speed[ids], self.spoke_offset[ids])
        pulse = np.exp(-((s - position) / 0.10) ** 2)
        weight = self.spoke_base[ids] * (0.30 + 1.5 * pulse * (0.6 + 0.8 * inward)) \
            * gain * self.spacing * 0.8
        self._add(points, rot, weight.astype(np.float32))

    def _emit_bolts(self, rot, gain):
        nodes = self.bolt_nodes
        count, node_count, _ = nodes.shape
        seg = self.bolt_seg
        frac = self.bolt_frac[None, :, None]
        a = nodes[:, seg]
        b = nodes[:, seg + 1]
        points = (a + (b - a) * frac).reshape(-1, 3)
        flicker = 0.45 + 0.55 * np.sin(self.t * self.bolt_rate + self.bolt_phase) ** 2
        weight = np.repeat((self.bolt_base * flicker)[:, None], len(seg), axis=1).reshape(-1)
        weight = weight * (0.5 + 0.6 * self.params["energy"] + 0.8 * self.level) \
            * gain * self.spacing * 0.9
        self._add(points, rot, weight.astype(np.float32))

    def _emit_core(self, rot, gain):
        p = self.params
        core = p["core"] + 1.1 * self.level
        t = self.t

        # Hollow reactor ring, tilted and slowly turning.
        ring_rot = rotation_matrix(t * 0.5 * p["ringspin"], 1.0 + 0.2 * math.sin(t * 0.4), 0.3)
        thick = [(0.150, 2.0), (0.160, 1.3), (0.140, 1.3), (0.170, 0.7), (0.130, 0.7)]
        for radius, strength in thick:
            self._add(self.core_ring * radius,
                      rot @ ring_rot,
                      np.full(len(self.core_ring), strength * (0.7 + 0.8 * core) * gain * self.spacing,
                              dtype=np.float32))

        # Spiral arms swirl around the core.
        swirl = rotation_matrix(0.0, 0.0, -t * (0.6 + 0.9 * p["ringspin"]))
        tilt = rotation_matrix(0.0, 0.9, 0.0)
        self._add(self.arm_pos @ swirl.T, rot @ tilt,
                  self.arm_w * (0.5 + 0.7 * core) * gain)
        self._add(self.arm_pos @ swirl.T * 0.8, rot @ rotation_matrix(0.9, -0.5, 0.0),
                  self.arm_w * 0.7 * (0.5 + 0.7 * core) * gain)

        # Irregular inner dust cloud, drifting the other way.
        shimmer = 0.6 + 0.4 * np.sin(t * 1.3 + self.cloud_phase)
        self._add(self.cloud_pos, rot, self.cloud_w * shimmer * (0.6 + 0.8 * energy_scale(p)) * gain)

        # The white-hot centre point itself.
        centre = np.array([[0.0, 0.0, 0.0], [0.012, 0.008, 0.01], [-0.01, 0.006, -0.01]])
        self._add(centre, rot, np.full(3, 9.0 * (0.5 + core), dtype=np.float32))

    def _emit_motes(self, shell_rot, spoke_rot, gain):
        """Bright particles with short trails, riding the rings and the spokes inward."""
        flow = 0.25 + self.params["flow"]
        u, v = self._ring_basis()
        trail = np.arange(self.trail)
        fade = (1.0 - trail / self.trail) ** 1.6

        theta = (self.mote_theta + self.mote_speed * self.t * flow)[:, None] \
            - trail[None, :] * 0.022 * np.sign(self.mote_speed)[:, None]
        ring = np.repeat(self.mote_ring[:, None], self.trail, axis=1)
        scale = self.rs_scale_for(ring.ravel())
        flat = self.rs_flat_for(ring.ravel())
        theta = theta.ravel()
        points = (scale * np.cos(theta))[:, None] * u[ring.ravel()] \
            + (scale * flat * np.sin(theta))[:, None] * v[ring.ravel()]
        weight = np.tile(fade, len(self.mote_ring)) * 2.6 * gain
        mask = ~np.repeat(self.mote_on_spoke, self.trail)
        self._add(points[mask], shell_rot, weight[mask].astype(np.float32))

        # Spoke riders: travel along a spoke toward the core when researching.
        sel = self.mote_on_spoke
        if sel.any():
            spoke = self.mote_spoke[sel]
            position = (self.t * 0.35 * flow + self.mote_offset[sel]) % 1.0
            # Toward the core while researching, away from it otherwise.
            direction = 1.0 if self.params["inward"] > 0.5 else -1.0
            if direction < 0:
                position = 1.0 - position
            offsets = position[:, None] - direction * trail[None, :] * 0.018
            offsets = np.clip(offsets, 0.0, 1.0)
            start = self.spoke_start[spoke][:, None, :]
            end = self.spoke_end[spoke][:, None, :]
            points = (start + (end - start) * offsets[:, :, None]).reshape(-1, 3)
            weight = np.tile(fade, sel.sum()) * 2.4 * gain
            self._add(points, spoke_rot, weight.astype(np.float32))

    def _emit_sparks(self, rot, gain):
        """Sparks thrown off the surface; more of them when the orb is excited."""
        active = np.clip(0.18 + 0.55 * self.params["energy"] + 1.1 * self.level, 0.0, 1.0)
        live = self.spark_rank < active
        if not live.any():
            return
        direction = self.spark_dir[live]
        side = self.spark_side[live]
        rate = self.spark_rate[live]
        offset = self.spark_offset[live]
        trail = np.arange(5)
        life = ((self.t * rate + offset)[:, None] - trail[None, :] * 0.035) % 1.0
        points = direction[:, None, :] * (1.0 + 0.42 * life[:, :, None]) \
            + side[:, None, :] * (0.16 * life[:, :, None] ** 2)
        weight = (1.0 - life) ** 1.3 * (1.0 - trail[None, :] / 6.0) * 2.4 * gain
        self._add(points.reshape(-1, 3), rot, weight.reshape(-1).astype(np.float32))

    def _emit_waves(self, gain):
        """Rings of light that leave the core with each burst of speech or sound."""
        for born, strength in self.waves:
            age = (self.t - born) / 0.9
            radius = 0.18 + 1.25 * age
            steps = self._samples_for(TAU * radius)
            theta = np.linspace(0, TAU, steps, endpoint=False)
            ring = np.stack((radius * np.cos(theta), radius * np.sin(theta),
                             np.zeros_like(theta)), axis=1)
            weight = np.full(steps, strength * (1.0 - age) ** 1.5 * 1.4 * gain * self.spacing,
                             dtype=np.float32)
            self._add(ring, np.eye(3), weight)

    # -- bloom -------------------------------------------------------------------

    def _bokeh_layer(self, rot):
        """A few large soft out-of-focus lights, drawn at quarter resolution."""
        size = self.res // 4
        rotated = self.bokeh_pos @ rot.T
        scale = self.radius / (1.0 - 0.12 * rotated[:, 2]) / 4.0
        x = size / 2.0 + rotated[:, 0] * scale
        y = size / 2.0 - rotated[:, 1] * scale
        weight = self.bokeh_w * (0.55 + 0.45 * np.sin(self.t * 0.6 + self.bokeh_phase))
        layer = splat(x, y, weight * 16.0, size, size)
        return box_blur(layer, 2, passes=2)

    def _bloom(self, acc, bokeh, core):
        """Soft halo at three scales plus the core's glow, as one full-size image."""
        size = self.res
        tight = blur3(blur3(acc))

        half = downsample(acc, 2)
        medium = box_blur(half, 3, passes=2)

        quarter = downsample(half, 2)
        wide = box_blur(quarter, 5, passes=2)
        spread = (self.radius * 0.34 / 4.0) ** 2
        blob = np.exp(-self._quarter_d2 / (2.0 * spread)).astype(np.float32)
        wide = wide * 1.25 + blob * (1.1 * core) + bokeh * 1.0

        low = medium * 1.1 + upsample(wide, 2)
        return tight * 1.15 + upsample(low, 2) * 0.95


def energy_scale(params):
    """Brightness helper for the inner cloud."""
    return params["energy"]
