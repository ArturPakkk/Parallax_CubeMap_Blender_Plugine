# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable shader nodes: analytic room intersection and alpha sprite layers.

Room coordinates: X = UV right, Y = UV up, Z = into the window.
The input is a 3x3 cross atlas, NOT a latitude/longitude panorama.
"""
import bpy
from .translations import tr, CONTEXT

GROUP_NAME = "PX Interior • Cross Atlas"
VERSION = 3

# Fixed preset: no user controls or group inputs.
PRESET = {
    "Room Width": 1.0, "Room Height": 1.0, "Room Depth": 1.1,
    "Exposure": 2.2, "Glass Reflection": 0.25, "Glass Roughness": 0.08,
    "Furniture 1 Depth": 0.45, "Furniture 2 Depth": 0.85,
    "Furniture 3 Depth": 0.22,
    "Furniture 1": 1.0, "Furniture 2": 1.0, "Furniture 3": 1.0,
    "Curtains": 1.0, "Interior Tint": (1, 1, 1),
}
MATERIAL_NAME = "Debug_Parallax"


class Graph:
    def __init__(self, tree):
        self.tree = tree
        self.frame = None
        self.count = 0

    def section(self, title, x):
        f = self.tree.nodes.new("NodeFrame")
        f.label = title
        f.name = title
        f.location = (x, 0)
        self.frame = f
        self.count = 0

    def node(self, kind, label=""):
        n = self.tree.nodes.new(kind)
        if label:
            n.label = label
        n.parent = self.frame
        n.location = ((self.count // 9) * 210, -(self.count % 9) * 155)
        n.width = 185
        self.count += 1
        return n

    def put(self, value, target):
        if isinstance(value, bpy.types.NodeSocket):
            self.tree.links.new(value, target)
        else:
            target.default_value = value

    def math(self, op, a, b=None, label=""):
        n = self.node("ShaderNodeMath", label)
        n.operation = op
        self.put(a, n.inputs[0])
        if b is not None:
            self.put(b, n.inputs[1])
        return n.outputs[0]

    def vec(self, op, a, b=None):
        n = self.node("ShaderNodeVectorMath")
        n.operation = op
        self.put(a, n.inputs[0])
        if b is not None:
            self.put(b, n.inputs[3] if op == "SCALE" else n.inputs[1])
        return n.outputs["Value" if op in {"DOT_PRODUCT", "DISTANCE", "LENGTH"} else "Vector"]

    def xyz(self, x, y, z=0.0):
        n = self.node("ShaderNodeCombineXYZ")
        for value, socket in zip((x, y, z), n.inputs):
            self.put(value, socket)
        return n.outputs[0]

    def split(self, vector):
        n = self.node("ShaderNodeSeparateXYZ")
        self.put(vector, n.inputs[0])
        return tuple(n.outputs)

    def mix(self, fac, a, b):
        n = self.node("ShaderNodeMixRGB")
        n.blend_type = "MIX"
        for v, s in zip((fac, a, b), n.inputs):
            self.put(v, s)
        return n.outputs[0]

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def minimum(self, a, b):
        return self.math("MINIMUM", a, b)

    def maximum(self, a, b):
        return self.math("MAXIMUM", a, b)

    def divide(self, a, b):
        return self.math("DIVIDE", a, b)

    def clamp01(self, x):
        return self.minimum(self.maximum(x, 0.0), 1.0)

    def sample(self, image, u, v, col, row, label):
        # Inset half a texel into the tile to prevent neighbouring tiles bleeding.
        # The 2048px input does not divide by 3: use fractional tile boundaries.
        eps_u = 1.5 / max(image.size[0], 3)
        eps_v = 1.5 / max(image.size[1], 3)
        u = self.minimum(self.maximum(u, eps_u), 1.0 - eps_u)
        v = self.minimum(self.maximum(v, eps_v), 1.0 - eps_v)
        uv = self.xyz(self.divide(self.add(u, col), 3.0),
                      self.divide(self.add(v, row), 3.0))
        n = self.node("ShaderNodeTexImage", label)
        n.image = image
        n.interpolation = "Linear"
        n.extension = "EXTEND"
        self.put(uv, n.inputs["Vector"])
        return n.outputs["Color"], n.outputs["Alpha"]

    def inside(self, x):
        return self.mul(self.math("GREATER_THAN", x, 0.0),
                        self.math("LESS_THAN", x, 1.0))


def make_group(image, debug=False):
    tree = bpy.data.node_groups.new(GROUP_NAME, "ShaderNodeTree")
    tree["px_version"] = VERSION
    tree["px_atlas"] = image.name
    tree["px_role"] = "DEBUG" if debug else "ROOM"
    tree.interface.new_socket(name="Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    tree.interface.new_socket(name="Interior Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    g = Graph(tree)
    g.section("01 • Window UV and camera ray", 0)
    p = PRESET
    tex = g.node("ShaderNodeTexCoord", "Original active-render UV - no remapping")
    u, v, _ = g.split(tex.outputs["UV"])
    # Use coordinates verbatim. There is no fract(), island normalization,
    # auto unwrap, bounding-box fitting or clamping of the source UV.
    valid = g.mul(g.sub(1.0, g.math("LESS_THAN", u, -0.000001)),
                  g.sub(1.0, g.math("GREATER_THAN", u, 1.000001)))
    valid = g.mul(valid, g.sub(1.0, g.math("LESS_THAN", v, -0.000001)))
    valid = g.mul(valid, g.sub(1.0, g.math("GREATER_THAN", v, 1.000001)))
    geometry = g.node("ShaderNodeNewGeometry")
    normal = geometry.outputs["Normal"]

    def uv_axis(color, label):
        # Blender's native tangent-space conversion includes bitangent sign.
        # Cross(N,T) alone is incorrect on mirrored UVs. These two nodes follow
        # UV edits live, with no cached mesh attributes or dependency handlers.
        node = g.node("ShaderNodeNormalMap", label)
        node.space = "TANGENT"
        node.uv_map = ""
        node.inputs["Strength"].default_value = 1.0
        node.inputs["Color"].default_value = color
        return g.vec("NORMALIZE", node.outputs["Normal"])

    t = uv_axis((1.0, 0.5, 0.5, 1.0), "Signed UV U axis")
    b = uv_axis((0.5, 1.0, 0.5, 1.0), "Signed UV V axis")
    incoming = geometry.outputs["Incoming"]
    dx = g.divide(g.mul(g.vec("DOT_PRODUCT", incoming, t), -1.0), p["Room Width"])
    dy = g.divide(g.mul(g.vec("DOT_PRODUCT", incoming, b), -1.0), p["Room Height"])
    dz = g.divide(g.maximum(g.math("ABSOLUTE", g.vec("DOT_PRODUCT", incoming, normal)), 0.00001),
                  p["Room Depth"])

    g.section("02 • Ray intersection with five room surfaces", 2300)
    def exit_time(pos, direction):
        positive = g.math("GREATER_THAN", direction, 0.0)
        # lerp(pos, 1-pos, positive)
        distance = g.add(pos, g.mul(positive, g.sub(1.0, g.mul(pos, 2.0))))
        return g.divide(distance, g.maximum(g.math("ABSOLUTE", direction), 0.000001))
    tx, ty, tz = exit_time(u, dx), exit_time(v, dy), g.divide(1.0, dz)
    hit_time = g.minimum(g.minimum(tx, ty), tz)
    hx = g.add(u, g.mul(dx, hit_time))
    hy = g.add(v, g.mul(dy, hit_time))
    hz = g.mul(dz, hit_time)
    # Deterministic ties: back first, then horizontal, then vertical.
    xwin = g.mul(g.math("LESS_THAN", tx, tz), g.sub(1.0, g.math("GREATER_THAN", tx, ty)))
    ywin = g.mul(g.math("LESS_THAN", ty, tz), g.math("LESS_THAN", ty, tx))
    xpositive = g.math("GREATER_THAN", dx, 0.0)
    ypositive = g.math("GREATER_THAN", dy, 0.0)
    # Cross unfold: left=(z,y), right=(1-z,y),
    # ceiling=(x,1-z), floor=(x,z), back=(x,y).
    su = g.add(hz, g.mul(xpositive, g.sub(1.0, g.mul(hz, 2.0))))
    sv = g.add(hz, g.mul(ypositive, g.sub(1.0, g.mul(hz, 2.0))))
    tile_u = g.add(hx, g.mul(xwin, g.sub(su, hx)))
    tile_v = g.add(hy, g.mul(ywin, g.sub(sv, hy)))
    col = g.add(1.0, g.mul(xwin, g.sub(g.mul(xpositive, 2.0), 1.0)))
    row = g.add(1.0, g.mul(ywin, g.sub(g.mul(ypositive, 2.0), 1.0)))
    room, _ = g.sample(image, tile_u, tile_v, col, row, "Walls / ceiling / floor")

    if debug:
        # The supplied debug atlas has alpha=1 everywhere, including black
        # corner tiles. It contains five labelled walls, no furniture layers.
        # Sample only the cross and keep its diagnostic colors unlit.
        color = g.vec("SCALE", room, valid)
        g.section("03 • Debug colors", 5500)
        emission = g.node("ShaderNodeEmission", "Unlit debug atlas")
        g.put(color, emission.inputs["Color"])
        output = g.node("NodeGroupOutput")
        g.put(emission.outputs[0], output.inputs["Shader"])
        g.put(color, output.inputs["Interior Color"])
        return tree

    sprites = []
    for i, (col, row) in enumerate(((0, 2), (2, 2), (2, 0)), 1):
        g.section("0%d • Furniture layer %d" % (i + 2, i), 5200 + (i - 1) * 1200)
        depth = p["Furniture %d Depth" % i]
        time = g.divide(depth, dz)
        x, y = g.add(u, g.mul(dx, time)), g.add(v, g.mul(dy, time))
        color, alpha = g.sample(image, x, y, col, row, "Furniture %d" % i)
        visible = g.mul(g.inside(x), g.inside(y))
        visible = g.mul(visible, g.math("LESS_THAN", depth, g.add(hz, 0.00001)))
        alpha = g.mul(g.mul(g.clamp01(alpha), visible), p["Furniture %d" % i])
        sprites.append((depth, color, alpha))

    g.section("06 • Depth-sorted alpha composition", 8800)
    # Compute transmittance of all nearer layers. Correct for any depth order,
    # including identical depths (lower numbered layer wins ties).
    room_weight = 1.0
    for _, _, alpha in sprites:
        room_weight = g.mul(room_weight, g.sub(1.0, alpha))
    color = g.vec("SCALE", room, room_weight)
    for i, (depth, rgb, alpha) in enumerate(sprites):
        weight = alpha
        for j, (other_depth, _, other_alpha) in enumerate(sprites):
            if i == j:
                continue
            nearer = (g.sub(1.0, g.math("GREATER_THAN", other_depth, depth))
                      if j < i else g.math("LESS_THAN", other_depth, depth))
            weight = g.mul(weight, g.sub(1.0, g.mul(nearer, other_alpha)))
        color = g.vec("ADD", color, g.vec("SCALE", rgb, weight))
    curtain, alpha = g.sample(image, u, v, 0, 0, "Front layer / curtains")
    color = g.mix(g.mul(g.clamp01(alpha), p["Curtains"]), color, curtain)

    g.section("07 • Exposure and reflective window surface", 11100)
    color = g.vec("MULTIPLY", color, p["Interior Tint"])
    color = g.vec("SCALE", color, valid)
    emitted = g.node("ShaderNodeEmission", "Baked room lighting")
    g.put(color, emitted.inputs["Color"])
    g.put(g.math("POWER", 2.0, p["Exposure"]), emitted.inputs["Strength"])
    glossy = g.node("ShaderNodeBsdfGlossy", "Glass reflection")
    glossy.inputs["Color"].default_value = (1, 1, 1, 1)
    g.put(p["Glass Roughness"], glossy.inputs["Roughness"])
    fresnel = g.node("ShaderNodeFresnel")
    fresnel.inputs["IOR"].default_value = 1.45
    mix = g.node("ShaderNodeMixShader")
    g.put(g.mul(fresnel.outputs["Fac"], p["Glass Reflection"]), mix.inputs[0])
    g.put(emitted.outputs[0], mix.inputs[1])
    g.put(glossy.outputs[0], mix.inputs[2])
    out = g.node("NodeGroupOutput")
    g.put(mix.outputs[0], out.inputs["Shader"])
    g.put(color, out.inputs["Interior Color"])
    return tree


def material_node(material, role="ROOM"):
    if not material or not material.use_nodes:
        return None
    return next((n for n in material.node_tree.nodes
                 if n.type == "GROUP" and n.node_tree
                 and n.node_tree.get("px_version") == VERSION
                 and n.node_tree.get("px_role") == role), None)


SWITCH_NAME = "PX Room Debug Switch"
OWNER = "arturpakkk.parallax_cubemap"
LEGACY_OWNER = "artinspector.px_cubemap_windows"


def switch_node(material):
    if not material or not material.use_nodes:
        return None
    node = material.node_tree.nodes.get(SWITCH_NAME)
    return node if node and node.bl_idname == "ShaderNodeMixShader" else None


def is_managed(material):
    if not material or material.get("px_owner") not in {OWNER, LEGACY_OWNER} or material.get("px_cubemap_windows") != VERSION:
        return False
    room, debug = material_node(material, "ROOM"), material_node(material, "DEBUG")
    switch = switch_node(material)
    if not room or not debug or not switch or switch.inputs[0].is_linked:
        return False
    for socket, source in ((switch.inputs[1], room), (switch.inputs[2], debug)):
        if len(socket.links) != 1 or socket.links[0].from_socket != source.outputs["Shader"]:
            return False
    return any(n.type == "OUTPUT_MATERIAL" and n.is_active_output
               and len(n.inputs["Surface"].links) == 1
               and n.inputs["Surface"].links[0].from_node == switch
               for n in material.node_tree.nodes)


def debug_enabled(material):
    switch = switch_node(material)
    return bool(switch and switch.inputs[0].default_value >= 0.5)


def create_material(image, name=MATERIAL_NAME, debug_image=None):
    # Never let Blender silently allocate Debug_Parallax.001.
    if bpy.data.materials.get(name):
        raise ValueError(tr("Material name is already in use: ") + name)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material["px_cubemap_windows"] = VERSION
    material["px_owner"] = OWNER
    material.diffuse_color = (0.12, 0.19, 0.23, 1.0)
    nodes = material.node_tree.nodes
    nodes.clear()
    created_groups = []
    try:
        room = nodes.new("ShaderNodeGroup")
        room.node_tree = make_group(image)
        created_groups.append(room.node_tree)
        room.name = "PX Room"
        room.label = "Room"
        room.location = (0, 100)
        room.width = 220
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (650, 0)
        if debug_image is None:  # Small diagnostic fixtures used by render tests.
            material.node_tree.links.new(room.outputs["Shader"], output.inputs["Surface"])
        else:
            debug = nodes.new("ShaderNodeGroup")
            debug.node_tree = make_group(debug_image, debug=True)
            created_groups.append(debug.node_tree)
            debug.name = "PX Debug"
            debug.label = "Debug"
            debug.location = (0, -160)
            debug.width = 220
            switch = nodes.new("ShaderNodeMixShader")
            switch.name = SWITCH_NAME
            switch.label = "Room / Debug"
            switch.location = (350, 20)
            switch.inputs[0].default_value = 0.0
            material.node_tree.links.new(room.outputs["Shader"], switch.inputs[1])
            material.node_tree.links.new(debug.outputs["Shader"], switch.inputs[2])
            material.node_tree.links.new(switch.outputs[0], output.inputs["Surface"])
        material.asset_mark()
        material.asset_data.description = "Direct UV parallax room with a debug atlas switch"
        material.use_fake_user = True
        return material
    except Exception:
        bpy.data.materials.remove(material)
        for group in created_groups:
            if group.users == 0:
                bpy.data.node_groups.remove(group)
        raise
