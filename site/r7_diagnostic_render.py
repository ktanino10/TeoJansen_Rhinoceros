"""Render three clearly labelled diagnostic phases; no complete walking animation."""

import json
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r7_blender import OUTPUT, MEDIA, open_verified_native, fit_camera, render_image


def main(design="A"):
    bpy, handoff, models = open_verified_native()
    from mathutils import Matrix, Vector
    report = json.loads((MEDIA/f"diagnostic_{design}.json").read_text())
    if report["artifactCommit"] != handoff["candidateCommit"] or report["geometrySha256"] != models[design]["guide"]["model"]["sha256"]:
        raise ValueError("Diagnostic and native model sources differ")
    original = bpy.data.scenes[f"R7_{design}_HERO"]
    source_objects = {o["instance_id"]: o for o in original.objects if "instance_id" in o}
    all_bounds = []
    for frame in report["frames"]:
        for name, rows in frame["instanceWorld4x4Mm"].items():
            matrix = Matrix(rows)
            matrix.translation *= 0.001
            all_bounds.extend(matrix @ Vector(p) for p in source_objects[name].bound_box)

    def flat_material(name, rgb, strength=1):
        existing = bpy.data.materials.get(name)
        if existing:
            return existing
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        material.node_tree.nodes.clear()
        shader = material.node_tree.nodes.new("ShaderNodeEmission")
        shader.inputs["Color"].default_value = (*rgb, 1)
        shader.inputs["Strength"].default_value = strength
        output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
        material.node_tree.links.new(shader.outputs[0], output.inputs["Surface"])
        return material

    white = flat_material("DIAGNOSTIC_TEXT", (0.8, 0.86, 0.91))
    amber = flat_material("DIAGNOSTIC_WARNING", (1.0, 0.62, 0.20))
    green = flat_material("DIAGNOSTIC_CALC_POINT", (0.12, 0.8, 0.42))
    blue = flat_material("DIAGNOSTIC_DISPLAY_POINT", (0.15, 0.55, 1.0))
    grid_material = flat_material("DIAGNOSTIC_GRID", (0.10, 0.19, 0.22), 0.6)

    def text(scene, body, x, y, size, material):
        curve = bpy.data.curves.new("DIAG_LABEL", "FONT")
        curve.body = body
        curve.size = size / 1280 * scene.camera.data.ortho_scale
        curve.materials.append(material)
        obj = bpy.data.objects.new(body[:38], curve)
        scene.collection.objects.link(obj)
        obj.parent = scene.camera
        width = scene.camera.data.ortho_scale
        obj.location = ((x/1280-0.5)*width, (0.5-y/720)*width*720/1280, -0.012)
        obj["diagnostic_annotation_only"] = True

    def line(scene, name, coords, material, width=0.0003):
        curve = bpy.data.curves.new(name, "CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = width
        curve.resolution_u = 1
        spline = curve.splines.new("POLY")
        spline.points.add(len(coords)-1)
        for point, xyz in zip(spline.points, coords):
            point.co = (*xyz, 1)
        curve.materials.append(material)
        obj = bpy.data.objects.new(name, curve)
        scene.collection.objects.link(obj)
        obj["diagnostic_annotation_only"] = True

    def marker(scene, coords, material, size):
        x, y, z = [v*0.001 for v in coords]
        line(scene, "CALCULATED_POINT", [(x-size, y, z), (x+size, y, z)], material, 0.00065)
        line(scene, "CALCULATED_POINT", [(x, y-size, z), (x, y+size, z)], material, 0.00065)
        line(scene, "CALCULATED_POINT", [(x, y, z-size), (x, y, z+size)], material, 0.00065)

    for frame in report["frames"]:
        name = f"R7_{design}_DIAGNOSTIC_{int(frame['crankDeg']):03}"
        existing = bpy.data.scenes.get(name)
        if existing:
            bpy.data.scenes.remove(existing)
        scene = bpy.data.scenes.new(name)
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = 32
        scene.render.resolution_x, scene.render.resolution_y = 1280, 720
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.world = original.world
        scene.view_settings.view_transform = "AgX"
        scene.unit_settings.system = "METRIC"
        camera = original.camera.copy()
        camera.data = original.camera.data.copy()
        camera.animation_data_clear()
        scene.collection.objects.link(camera)
        scene.camera = camera
        for obj in original.objects:
            if obj.type == "LIGHT":
                duplicate = obj.copy()
                duplicate.data = obj.data.copy()
                scene.collection.objects.link(duplicate)
        for name, rows in frame["instanceWorld4x4Mm"].items():
            source = source_objects[name]
            obj = bpy.data.objects.new(f"DIAGNOSTIC:{int(frame['crankDeg'])}:{name}", source.data)
            scene.collection.objects.link(obj)
            matrix = Matrix(rows)
            matrix.translation *= 0.001
            obj.matrix_world = matrix
            obj.color = (0.85, 0.05, 0.015, 1) if name in frame["belowReferencePlaneParts"] else source.color
            obj["instance_id"] = name
            obj["part_id"] = source["part_id"]
            obj["source_commit"] = handoff["candidateCommit"]
            obj["diagnostic_not_independent_solver_pose"] = True
        for x in range(-160, 181, 20):
            line(scene, "FIXED_MODEL_GRID", [(x/1000, -0.24, 0), (x/1000, 0.17, 0)], grid_material, 0.00018)
        for y in range(-240, 171, 20):
            line(scene, "FIXED_MODEL_GRID", [(-0.16, y/1000, 0), (0.18, y/1000, 0)], grid_material, 0.00018)
        for foot in frame["feet"]:
            marker(scene, foot["calculatedContactPlanePointMm"], green, 0.003)
            marker(scene, foot["rigidDisplayCenterWorldMm"], blue, 0.002)
        bpy.context.window.scene = scene
        scene.view_layers[0].update()
        fit_camera(scene, all_bounds)
        text(scene, "R7 / THREE-PHASE DIAGNOSTIC / NOT COMPLETE CAD WALKING", 40, 34, 17, amber)
        text(scene, f"{design} / CRANK {frame['crankDeg']:g} DEG / SAVED Y {frame['sourceIntegratedPlanarComponents'][1]:+.3f} mm", 40, 76, 26, white)
        text(scene, "Rigid CAD uses a polar display frame. Green: source contact-plane points. Blue: rigid-frame centers.", 40, 110, 14, white)
        text(scene, "PASSIVE ROCKER DISPLAY", 920, 180, 15, amber)
        for index, foot in enumerate(frame["feet"]):
            angle = foot["geometryDisplayRockerAngleRad"]
            label = f"F{index}: " + (f"geometry-only {angle*180/3.141592653589793:+.3f} deg" if angle is not None else "UNRESOLVED / omitted")
            text(scene, label, 920, 209+index*24, 13, white)
        text(scene, f"Max center-map difference: {frame['maximumFootCenterRepresentationDifferenceMm']:.6f} mm", 40, 582, 16, amber)
        text(scene, f"Actual shown CAD min Z: {frame['minimumRenderedVertexZMm']:+.6f} mm; NO floor correction or mesh stretching.", 40, 608, 14, white)
        text(scene, f"{len(frame['omittedInstances'])} parts omitted: unsolved airborne rockers and coil-wire deformation. Source rocker angles remain NULL.", 40, 637, 14, amber)
        text(scene, "Source small-angle states are not an exact rigid-body dynamics solution. Geometry-derived loaded angles are display rules only.", 40, 668, 13, white)
        text(scene, f"Source {handoff['candidateCommit'][:7]} / assumed input120RPM / no interpolation / physical walking UNKNOWN", 40, 697, 13, white)
        if frame["belowReferencePlaneParts"]:
            text(scene, "RED: REFERENCE-PLANE OVERLAP, NOT CORRECTED", 40, 142, 17, amber)
        scene["diagnostic_source_frame"] = json.dumps(frame)
        scene["source_commit"] = handoff["candidateCommit"]
        scene["not_complete_walking"] = True
        path = MEDIA/f"diagnostic_{design}_{int(frame['crankDeg']):03}.png"
        render_image(bpy, scene, path)
    text_block = bpy.data.texts.get(f"R7_{design}_DIAGNOSTIC.json") or bpy.data.texts.new(f"R7_{design}_DIAGNOSTIC.json")
    text_block.clear()
    text_block.write(json.dumps(report))
    bpy.context.window.scene = bpy.data.scenes["R7_COMPARE"]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)
    print("Three diagnostic phases rendered; complete walking remains unresolved.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", choices=list("ABC"), default="A")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else None)
    main(args.design)
