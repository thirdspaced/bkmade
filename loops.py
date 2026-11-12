"""Render seamless looping clips for the Third Space 95 feed.
usage: python3 loops.py <scene> <outdir> [frames] [only_frame]
"""
import sys, math, os
import bpy, bmesh
from mathutils import Matrix, Vector, Euler

SCENE, OUT = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 72
ONLY = int(sys.argv[4]) if len(sys.argv) > 4 else None
TAU = math.tau
os.makedirs(OUT, exist_ok=True)

def lin(h, a=1.0):
    h = h.lstrip('#')
    return tuple((int(h[i:i+2], 16) / 255) ** 2.2 for i in (0, 2, 4)) + (a,)

PAL = dict(night='#07054a', dusk='#100a88', pink='#ea3f98', pinkd='#b3246f', cyan='#8acbfa', sodium='#f8d682',
           sand='#f3e3b4', sandhi='#fdf3d2', sandlo='#b89a52', ink='#06043a', paper='#fdf6e3', lilac='#cfd9f5', orange='#f2a444')

# ---------- scene setup ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = 12
sc.cycles.use_denoising = False
sc.cycles.max_bounces = 0
sc.cycles.use_adaptive_sampling = False
sc.cycles.filter_width = 1.0
sc.render.resolution_x, sc.render.resolution_y = 270, 480
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
coll = sc.collection

def world_solid(hexc):
    w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = lin(hexc)

def world_gradient(stops):
    """stops: list of (pos 0..1 along view-z mapped from -0.15..0.7, hex)"""
    w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
    nt = w.node_tree; n = nt.nodes; l = nt.links
    tc = n.new('ShaderNodeTexCoord'); sep = n.new('ShaderNodeSeparateXYZ'); mr = n.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = -0.15; mr.inputs['From Max'].default_value = 0.7
    cr = n.new('ShaderNodeValToRGB'); ramp = cr.color_ramp
    ramp.elements[0].position, ramp.elements[0].color = stops[0][0], lin(stops[0][1])
    ramp.elements[1].position, ramp.elements[1].color = stops[-1][0], lin(stops[-1][1])
    for p, c in stops[1:-1]:
        e = ramp.elements.new(p); e.color = lin(c)
    l.new(tc.outputs['Generated'], sep.inputs[0]); l.new(sep.outputs['Z'], mr.inputs['Value'])
    l.new(mr.outputs['Result'], cr.inputs['Fac']); l.new(cr.outputs['Color'], n['Background'].inputs['Color'])

def emit(name, a, b=None, strength=1.0, blend=0.35):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; n = nt.nodes; l = nt.links
    n.remove(n['Principled BSDF'])
    e = n.new('ShaderNodeEmission'); e.inputs['Strength'].default_value = strength
    l.new(e.outputs[0], n['Material Output'].inputs['Surface'])
    if b is None:
        e.inputs['Color'].default_value = lin(a)
    else:
        lw = n.new('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = blend
        mx = n.new('ShaderNodeMix'); mx.data_type = 'RGBA'
        mx.inputs[6].default_value = lin(a); mx.inputs[7].default_value = lin(b)
        l.new(lw.outputs['Facing'], mx.inputs['Factor']); l.new(mx.outputs[2], e.inputs['Color'])
    return m

def scanline_mat(name, hexc, hexb):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; n = nt.nodes; l = nt.links
    n.remove(n['Principled BSDF'])
    e = n.new('ShaderNodeEmission'); e.inputs['Strength'].default_value = 1.6
    wv = n.new('ShaderNodeTexWave'); wv.wave_type = 'BANDS'; wv.bands_direction = 'Z'
    wv.inputs['Scale'].default_value = 6.0; wv.inputs['Distortion'].default_value = 0.0
    tc = n.new('ShaderNodeTexCoord')
    mx = n.new('ShaderNodeMix'); mx.data_type = 'RGBA'
    mx.inputs[6].default_value = lin(hexb); mx.inputs[7].default_value = lin(hexc)
    l.new(tc.outputs['Object'], wv.inputs['Vector']); l.new(wv.outputs['Fac'], mx.inputs['Factor'])
    l.new(mx.outputs[2], e.inputs['Color']); l.new(e.outputs[0], n['Material Output'].inputs['Surface'])
    return m, wv

def build(name, parts, mats, bevel=0.0):
    """parts: list of (size(x,y,z), loc(x,y,z), material index)"""
    bm = bmesh.new()
    for size, loc, mi in parts:
        mat = Matrix.Translation(Vector(loc)) @ Matrix.Diagonal((*size, 1.0))
        r = bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
        for f in {f for v in r['verts'] for f in v.link_faces}:
            f.material_index = mi
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob)
    if bevel:
        bv = ob.modifiers.new('bv', 'BEVEL'); bv.width = bevel; bv.segments = 1; bv.limit_method = 'ANGLE'
    return ob

def poly_extrude(name, pts, depth, mats, outline=None):
    bm = bmesh.new()
    def add(points, z0, d, mi, scale=1.0, cx=0, cy=0):
        vs = [bm.verts.new(((x - cx) * scale + cx, z0, (y - cy) * scale + cy)) for x, y in points]
        f = bm.faces.new(vs); f.material_index = mi
        r = bmesh.ops.extrude_face_region(bm, geom=[f])
        nv = [g for g in r['geom'] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=nv, vec=(0, d, 0))
        for g in r['geom']:
            if isinstance(g, bmesh.types.BMFace): g.material_index = mi
        for e in nv:
            for ff in e.link_faces: ff.material_index = mi
    add(pts, 0, depth, 0)
    if outline:
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        add(pts, depth * 0.6, depth * 0.9, 1, outline, cx, cy)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob)
    return ob

def wire_grid(name, size, cuts, thick, mat, loc=(0, 0, 0), rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=cuts, y_segments=cuts, size=size / 2)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob)
    ob.location = loc; ob.rotation_euler = rot
    wm = ob.modifiers.new('w', 'WIREFRAME'); wm.thickness = thick; wm.use_replace = True
    return ob

def camera(loc, look=None, rot=None, lens=50, ortho=None):
    cd = bpy.data.cameras.new('C'); cd.lens = lens; cd.clip_end = 300
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    co = bpy.data.objects.new('C', cd); coll.objects.link(co); sc.camera = co
    co.location = loc
    if look is not None:
        d = Vector(look) - Vector(loc)
        co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    elif rot is not None:
        co.rotation_euler = rot
    return co

def copies(src, n):
    out = [src]
    for _ in range(n - 1):
        c = src.copy(); coll.objects.link(c); out.append(c)
    return out

# ---------- icon builders ----------
def window_icon(name='win', s=1.0):
    mats = [emit('wbody', PAL['sandhi'], PAL['sandlo'], 1.0, .4), emit('wtitle', PAL['sodium'], PAL['pinkd'], 1.4, .45),
            emit('wscreen', PAL['dusk'], PAL['cyan'], 1.0, .25), emit('wbtn', PAL['sandhi'], PAL['ink'], 1.0, .5)]
    W, H = 1.7 * s, 1.25 * s
    parts = [((W, .12 * s, H), (0, 0, 0), 0),
             ((W * .94, .14 * s, .2 * s), (0, -.02 * s, H / 2 - .16 * s), 1),
             ((W * .9, .13 * s, H * .66), (0, -.01 * s, -.08 * s), 2)]
    for i in range(3):
        parts.append(((.13 * s, .16 * s, .12 * s), (W / 2 - .14 * s - i * .16 * s, -.04 * s, H / 2 - .16 * s), 3))
    return build(name, parts, mats, bevel=.015 * s)

def floppy_icon(name, label_hex, s=1.0):
    mats = [emit('fbody' + name, '#1c14b0', '#06043a', 1.0, .4), emit('fshut' + name, PAL['lilac'], '#7f8fc4', 1.0, .4),
            emit('flab' + name, label_hex, PAL['ink'], 1.3, .5), emit('fline' + name, PAL['paper'])]
    parts = [((3 * s, .14 * s, 3 * s), (0, 0, 0), 0),
             ((1.5 * s, .16 * s, 1.05 * s), (0, -.01 * s, 1.0 * s), 1),
             ((.42 * s, .18 * s, .7 * s), (.32 * s, -.02 * s, 1.0 * s), 0),
             ((2.2 * s, .16 * s, 1.3 * s), (0, -.01 * s, -.75 * s), 2),
             ((1.8 * s, .18 * s, .07 * s), (0, -.02 * s, -.55 * s), 3),
             ((1.4 * s, .18 * s, .07 * s), (-.2 * s, -.02 * s, -.85 * s), 3),
             ((.2 * s, .17 * s, .2 * s), (1.28 * s, -.01 * s, -1.28 * s), 1)]
    return build(name, parts, mats, bevel=.02 * s)

def cursor_icon(name, tint):
    pts = [(0, 0), (0, -17), (4, -13), (7, -20), (10, -19), (7, -12), (12, -12)]
    pts = [(x / 18, y / 18 + .55) for x, y in pts]
    pts.reverse()
    mats = [emit('cface' + name, tint, PAL['paper'], 1.3, .3), emit('cline' + name, PAL['ink'])]
    return poly_extrude(name, pts, .12, mats, outline=1.18)

def crt_icon(name, screen_mat):
    mats = [emit('crtb' + name, PAL['sandhi'], PAL['sandlo'], 1.0, .45), screen_mat, emit('crtd' + name, '#06043a')]
    parts = [((1.5, 1.1, 1.25), (0, 0, 0), 0), ((1.1, .7, .95), (0, .75, -.02), 0),
             ((1.18, .06, .9), (0, -.56, .06), 1), ((1.3, .02, .08), (0, -.56, -.5), 2),
             ((.6, .5, .12), (0, .1, -.68), 0), ((1.0, .8, .08), (0, .1, -.76), 0)]
    return build(name, parts, mats, bevel=.03)

# ---------- scenes ----------
states = []

if SCENE == 'trails':
    world_solid(PAL['night'])
    wire_grid('grid', 26, 26, .035, emit('g', PAL['pinkd'], strength=1.2), loc=(0, 12, 0), rot=(math.pi / 2, 0, 0))
    sun = bpy.data.meshes.new('sun'); bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=2.6)
    bm.to_mesh(sun); bm.free(); sun.materials.append(emit('sun', PAL['orange'], strength=1.3))
    so = bpy.data.objects.new('sun', sun); coll.objects.link(so); so.location = (0, 11, 3.2); so.rotation_euler = (math.pi / 2, 0, 0)
    camera((0, -14, 0), look=(0, 0, 0), lens=50)
    src = window_icon('win', 1.0)
    T, D = 42, 1.15 / N
    objs = copies(src, T)
    def st(u):
        for k, o in enumerate(objs):
            v = u - k * D
            a = TAU * v
            o.location = (1.55 * math.sin(a), k * .11, 3.1 * math.sin(2 * a))
            o.rotation_euler = (.25 * math.cos(a), .45 * math.sin(a), .3 * math.sin(2 * a))
    states.append(st)

elif SCENE == 'floppy':
    world_solid('#07054a')
    camera((0, -20, 0), rot=(math.pi / 2, 0, 0), ortho=9.2)
    labels = [PAL['pink'], PAL['cyan'], PAL['sodium']]
    objs = [(k, floppy_icon('fl%d' % (k + 20), labels[k % 3])) for k in range(-14, 42)]
    S0, s, th = 1.6, .86, math.radians(11)
    def st(u):
        U = 3 * u
        for k, o in objs:
            p = k - U
            sc_ = S0 * s ** p
            o.scale = (sc_, .3, sc_)
            o.rotation_euler = (0, th * p, 0)
            o.location = (0, -p * .07, 0)
            o.hide_render = sc_ > 16 or sc_ < .004
    states.append(st)

elif SCENE == 'cursors':
    world_gradient([(0, PAL['orange']), (.18, PAL['pink']), (.5, PAL['dusk']), (1, '#07054a')])
    floor = wire_grid('floor', 40, 40, .04, emit('fg', PAL['cyan'], strength=1.4), loc=(0, 0, 0))
    base = bpy.data.meshes.new('fb'); bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=20)
    bm.to_mesh(base); bm.free(); base.materials.append(emit('fbase', '#0a0766'))
    fb = bpy.data.objects.new('fb', base); coll.objects.link(fb); fb.location = (0, 0, -.02)
    camera((0, -11.5, 3.0), look=(0, 0, 1.6), lens=38)
    tints = [PAL['paper'], PAL['pink'], PAL['cyan'], PAL['sodium']]
    groups = []
    for i, t in enumerate(tints):
        src = cursor_icon('cur%d' % i, t)
        groups.append(copies(src, 26))
    cell = 1.0
    def st(u):
        floor.location = (0, -cell * ((u * 3) % 1), 0)
        for i, g in enumerate(groups):
            ph = i / 4
            for k, o in enumerate(g):
                v = u + ph - k * (.85 / N)
                o.location = (2.0 * math.sin(TAU * v), -1.6 + i * 1.1 - k * .02, .1 + 2.9 * abs(math.sin(3 * math.pi * v)))
                o.rotation_euler = (0, .55 * math.sin(TAU * v), .35 * math.sin(TAU * v))
                o.scale = (.72, .72, .72)
    states.append(st)

elif SCENE == 'crt':
    world_gradient([(0, PAL['sodium']), (.12, PAL['orange']), (.3, PAL['pinkd']), (.6, PAL['dusk']), (1, '#07054a')])
    floor = wire_grid('floor', 40, 30, .04, emit('fg', PAL['pink'], strength=1.3), loc=(0, 0, -.82))
    base = bpy.data.meshes.new('fb'); bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=20)
    bm.to_mesh(base); bm.free(); base.materials.append(emit('fbase', '#0a0766'))
    fb = bpy.data.objects.new('fb', base); coll.objects.link(fb); fb.location = (0, 0, -.84)
    camera((0, -12.0, 7.4), look=(0, 0, .7), lens=33)
    smA, wvA = scanline_mat('scrA', PAL['cyan'], '#100a88')
    smB, wvB = scanline_mat('scrB', PAL['pink'], '#100a88')
    ring = []
    R = 4.2
    for i in range(12):
        o = crt_icon('crt%d' % i, smA if i % 2 == 0 else smB)
        ring.append(o)
    fsrc = floppy_icon('cfl', PAL['sodium'], .55)
    ftr = copies(fsrc, 18)
    def st(u):
        base_a = (TAU / 6) * u
        for i, o in enumerate(ring):
            a = base_a + i * TAU / 12
            o.location = (R * math.sin(a), R * math.cos(a), 0)
            o.rotation_euler = (0, 0, -a + math.pi)
        for wv in (wvA, wvB):
            wv.inputs['Phase Offset'].default_value = -TAU * 4 * u
        for k, o in enumerate(ftr):
            v = u - k * (.9 / N)
            o.location = (.9 * math.sin(TAU * v), .9 * math.cos(TAU * v) * .5, 2.0 + .45 * math.sin(2 * TAU * v))
            o.rotation_euler = (math.radians(-20), 0, TAU * v)
    states.append(st)
else:
    raise SystemExit('unknown scene')

frames = [ONLY] if ONLY is not None else range(N)
for f in frames:
    u = f / N
    for st in states: st(u)
    sc.render.filepath = os.path.join(OUT, '%s_%03d.png' % (SCENE, f))
    bpy.ops.render.render(write_still=True)
print('done', SCENE)
