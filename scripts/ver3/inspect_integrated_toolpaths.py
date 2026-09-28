"""Read actual Orca extrusion paths, not STL validity or a slicer exit status."""

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import find_peaks
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
import trimesh

from slice_integrated_representatives import PARTS, placement, sha, write_json


NON_MODEL = {"Custom", "Brim", "Skirt", "Support", "Support interface", "Prime tower"}
COLORS = {
    "Outer wall": "#1557b0", "Inner wall": "#368ac8", "Overhang wall": "#852ac2",
    "Bridge": "#d2254c", "Support": "#efad44", "Support interface": "#dd741c",
    "Brim": "#409773", "Top surface": "#3b9c9b", "Internal solid infill": "#7bb9cc",
}
VIEWS = {
    "P_INPUT_PINION": [.84, 10.12, 11.08, 34.92],
    "P_COMPOUND_1": [.84, 20.2, 21, 31],
    "T_GUIDE_COUPON": [.2, 2.12, 6.6, 12.84],
    "T_JOURNAL_COUPON": [.2, 2.12, 4.04, 6.76],
    "T_DIAMETER_COUPON": [.2, 1, 2.6, 4.84],
}
GEAR_CHECKS = {
    "P_INPUT_PINION": [(10.12, 12), (11.08, 12)],
    "P_COMPOUND_1": [(20.2, 144), (21, 144), (31, 12)],
}


@dataclass
class Segment:
    start: tuple
    end: tuple
    width: float
    extrusion: float
    feature: str


@dataclass
class Layer:
    z: float = math.nan
    height: float = math.nan
    segments: list = field(default_factory=list)

    def model(self):
        return [s for s in self.segments if s.feature not in NON_MODEL]


def parse_gcode(path):
    with path.open() as stream:
        return parse_gcode_lines(stream)


def parse_gcode_lines(lines):
    layers = []
    position = np.zeros(3)
    relative_xyz = False
    relative_e = False
    extrusion_position = 0.
    feature = "Custom"
    width = math.nan
    nozzle_offset = None
    metadata = {}
    for line in lines:
        line = line.strip()
        if line == "; CHANGE_LAYER":
            layers.append(Layer())
        elif line.startswith("; Z_HEIGHT:"):
            layers[-1].z = float(line.split(":")[1])
        elif line.startswith("; LAYER_HEIGHT:"):
            layers[-1].height = float(line.split(":")[1])
        elif line.startswith("; LINE_WIDTH:"):
            width = float(line.split(":")[1])
        elif line.startswith("; FEATURE:"):
            feature = line.split(":", 1)[1].strip()
        elif line.startswith("; model printing time:"):
            metadata["timeEstimate"] = line[2:]
        elif line.startswith("; filament used ["):
            key, value = line[2:].split(" = ")
            metadata[key] = float(value)
        elif line.startswith("; total layer number:"):
            metadata["reportedLayerCount"] = int(line.split(":")[1])
        elif line.startswith("; extruder_offset = "):
            offsets = line.split(" = ", 1)[1].split(",")
            if len(offsets) != 1:
                raise ValueError("Only a single-tool representative is supported")
            nozzle_offset = np.array([float(value) for value in offsets[0].split("x")])
            if nozzle_offset.shape != (2,):
                raise ValueError("Invalid nozzle offset")
            metadata["gcodeXYToModelBedOffsetMm"] = nozzle_offset.tolist()
        if not line or line.startswith(";"):
            continue
        code = line.split(";", 1)[0]
        command = code.split()[0]
        values = {key: float(value) for key, value in re.findall(r"([XYZE])(-?(?:\d+\.?\d*|\.\d+))", code)}
        if command == "G90":
            relative_xyz = False
        elif command == "G91":
            relative_xyz = True
        elif command == "M82":
            relative_e = False
        elif command == "M83":
            relative_e = True
        elif command == "G20":
            raise ValueError("Inch-mode G-code is not supported by this millimetre inspection")
        elif command == "G92":
            extrusion_position = values.get("E", extrusion_position)
            for i, key in enumerate("XYZ"):
                if key in values:
                    position[i] = values[key]
        elif command in ("G0", "G1", "G2", "G3"):
            end = position.copy()
            for i, key in enumerate("XYZ"):
                if key in values:
                    end[i] = position[i] + values[key] if relative_xyz else values[key]
            amount = values.get("E", 0.) if relative_e else values.get("E", extrusion_position) - extrusion_position
            extrusion_position = extrusion_position + amount
            if layers and feature != "Custom" and amount > 0 and command in ("G2", "G3"):
                raise ValueError("Extruding arcs require an arc-aware inspector; disable arc fitting")
            if layers and feature != "Custom" and amount > 0 and np.linalg.norm(end[:2] - position[:2]) > 1e-8:
                layer = layers[-1]
                if not all(math.isfinite(v) and v > 0 for v in (width, layer.z, layer.height)):
                    raise ValueError("Missing actual extrusion width/layer metadata")
                if abs(end[2] - layer.z) > .001:
                    raise ValueError("Extrusion does not lie on its declared layer")
                if nozzle_offset is None:
                    raise ValueError("No declared nozzle offset for model-space comparison")
                layer.segments.append(Segment(tuple(position[:2] + nozzle_offset),
                                              tuple(end[:2] + nozzle_offset), width, amount, feature))
            position = end
    if not layers or any(not math.isfinite(layer.z) for layer in layers):
        raise ValueError("No complete actual layer data")
    if metadata.get("reportedLayerCount") != len(layers):
        raise ValueError("Layer count differs from the slicer header")
    return layers, metadata


def bore_specs(part):
    if part == "P_INPUT_PINION":
        return [(0, 0, 2.6)]
    if part == "P_COMPOUND_1":
        return [(0, 0, 2.56)]
    if part == "T_GUIDE_COUPON":
        return [(4 + 12 * i, 4, d / 2) for i, d in enumerate((4.15, 4.25, 4.35))]
    if part == "T_JOURNAL_COUPON":
        return [(6 + 12 * i, 5, 2.56) for i in range(3)]
    if part == "T_DIAMETER_COUPON":
        return ([(8 + 12 * i, 8, d / 2) for i, d in enumerate((4, 4.1, 4.2, 4.3))]
                + [(60 + 12 * i, 8, d / 2) for i, d in enumerate((8, 8.1, 8.2))]
                + [(10 + 20 * i, 27, d / 2) for i, d in enumerate((14, 14.2, 14.4, 16, 16.2))])
    raise ValueError("Not a selected representative: " + part)


def point_clearance(segments, point):
    if not segments:
        return None
    starts = np.array([s.start for s in segments])
    ends = np.array([s.end for s in segments])
    delta = ends - starts
    t = np.clip(np.sum((point - starts) * delta, axis=1) / np.sum(delta * delta, axis=1), 0, 1)
    distances = np.linalg.norm(starts + t[:, None] * delta - point, axis=1)
    return float(np.min(distances - np.array([s.width for s in segments]) / 2))


def swept_material(segments):
    return unary_union([LineString([s.start, s.end]).buffer(s.width / 2, quad_segs=4) for s in segments])


def largest_polygon(shape):
    if shape.geom_type == "Polygon":
        return shape
    polygons = [g for g in shape.geoms if g.geom_type == "Polygon"]
    if not polygons:
        raise ValueError("No deposited polygon")
    return max(polygons, key=lambda p: p.area)


def mesh_section(mesh, z, transform):
    section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        raise ValueError(f"Missing STL section at {z}")
    outlines = []
    for loop in section.discrete:
        points = (np.c_[loop, np.ones(len(loop))] @ transform.T)[:, :2]
        if not np.allclose(points[0], points[-1], atol=1e-5):
            raise ValueError("Open section in the frozen mesh")
        polygon = Polygon(points)
        if not polygon.is_valid:
            raise ValueError("Invalid section polygon")
        outlines.append(polygon)
    return sorted(outlines, key=lambda p: p.area, reverse=True)


def radial_profile(polygon, center, count):
    points = np.asarray(polygon.exterior.coords)[:-1] - center
    angles = np.arctan2(points[:, 1], points[:, 0])
    radii = np.linalg.norm(points, axis=1)
    order = np.argsort(angles)
    angles, radii = angles[order], radii[order]
    unique, inverse = np.unique(angles, return_inverse=True)
    maximum = np.zeros(len(unique))
    np.maximum.at(maximum, inverse, radii)
    grid = np.linspace(-math.pi, math.pi, count, endpoint=False)
    values = np.interp(grid, np.r_[unique - 2 * math.pi, unique, unique + 2 * math.pi],
                       np.tile(maximum, 3))
    return grid, values


def gear_check(mesh, transform, layer, teeth):
    center = (transform @ np.array([0, 0, 0, 1]))[:2]
    nominal = mesh_section(mesh, layer.z - layer.height / 2, transform)[0]
    segments = layer.model()
    deposit = swept_material(segments)
    connected = largest_polygon(deposit)
    n = teeth * 80
    angles, expected = radial_profile(nominal, center, n)
    _, actual = radial_profile(connected, center, n)
    def peaks(values):
        locations, _ = find_peaks(np.tile(values, 3), distance=48, prominence=.5)
        return locations[(locations >= n) & (locations < 2 * n)] - n
    nominal_peaks, actual_peaks = peaks(expected), peaks(actual)
    if len(nominal_peaks) != teeth:
        raise ValueError("The nominal-section tooth-count control failed")
    tip_widths = []
    root_r = float(expected.min())
    for segment in segments:
        midpoint = (np.array(segment.start) + segment.end) / 2
        if np.linalg.norm(midpoint - center) > float(expected.max()) - .7:
            tip_widths.append(segment.width)
    if not tip_widths:
        raise ValueError("No deposited tooth-tip paths")
    tips = [center + (actual[i] - .04) * np.array([math.cos(angles[i]), math.sin(angles[i])])
            for i in actual_peaks]
    return {
        "zMm": layer.z, "layerHeightMm": layer.height,
        "expectedTeeth": teeth, "nominalSectionTeeth": len(nominal_peaks),
        "depositedEnvelopeTeeth": len(actual_peaks),
        "allDetectedTipsOnOneRootConnectedComponent": all(connected.buffer(.005).covers(Point(p)) for p in tips),
        "nominalRootRadiusMm": root_r,
        "maximumTipRadialSetbackMm": float(np.max(expected[nominal_peaks] - actual[nominal_peaks])),
        "tipPathWidthRangeMm": [min(tip_widths), max(tip_widths)],
        "depositedConnectedComponentCount": 1 if deposit.geom_type == "Polygon" else len(deposit.geoms),
        "method": "Actual positive-extrusion segments swept by annotated width; largest connected exterior, circular radial lobe count with 0.5mm prominence and 80 angular samples/tooth.",
    }


def nearest_model_layer(layers, z):
    return min((layer for layer in layers if layer.model()), key=lambda layer: abs(layer.z - z))


def panel(part, layer, outlines, bounds=None, size=(720, 610)):
    image = Image.new("RGB", size, "white")
    plot = Image.new("RGB", (size[0] - 32, size[1] - 130), "white")
    draw = ImageDraw.Draw(plot)
    points = np.array([p for s in layer.segments for p in (s.start, s.end)])
    if bounds is None:
        lower, upper = points.min(axis=0) - 1, points.max(axis=0) + 1
    else:
        lower, upper = np.array(bounds[:2]), np.array(bounds[2:])
    scale = min((plot.width - 10) / (upper[0] - lower[0]), (plot.height - 10) / (upper[1] - lower[1]))
    center = (lower + upper) / 2
    def pixel(p):
        return ((p[0] - center[0]) * scale + plot.width / 2,
                -(p[1] - center[1]) * scale + plot.height / 2)
    for shape in outlines:
        draw.line([pixel(p) for p in shape.exterior.coords], fill="#555555", width=1)
    for segment in sorted(layer.segments, key=lambda s: s.feature not in NON_MODEL):
        a, b = pixel(segment.start), pixel(segment.end)
        w = max(1, round(segment.width * scale))
        color = COLORS.get(segment.feature, "#6ca2aa")
        draw.line([a, b], fill=color, width=w)
        for x, y in (a, b):
            r = w / 2
            draw.ellipse((x-r, y-r, x+r, y+r), fill=color)
    image.paste(plot, (16, 65))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=19)
    draw.text((16, 10), f"{part} / Z {layer.z:g} mm", fill="#142c44", font=font)
    draw.text((16, 37), "Actual G-code bead widths; not a print photograph", fill="#465767", font=font)
    draw.text((16, size[1] - 47), f"XY window {upper[0]-lower[0]:.2f} x {upper[1]-lower[1]:.2f} mm",
              fill="#465767", font=font)
    draw.text((16, size[1] - 24), "Blue: walls  Purple: overhang  Orange: support  Red: bridge",
              fill="#465767", font=ImageFont.load_default(size=14))
    return image


def inspect(run_folder, public_folder):
    public_folder.mkdir(parents=True, exist_ok=True)
    run = json.loads((run_folder / "run.json").read_text())
    results = []
    for record in run["parts"]:
        part = record["partId"]
        folder = run_folder / part
        gcode = folder / "plate_1.gcode"
        if record["exitCode"] != 0 or sha(gcode) != record["gcodeSha256"]:
            raise ValueError("Slicer run or toolpath identity differs")
        transform = np.array(placement(folder / (part + ".3mf"))["sourceStlToBedTransformRowMajor4x4"])
        mesh = trimesh.load_mesh(folder / (part + ".stl"))
        layers, estimates = parse_gcode(gcode)
        with zipfile.ZipFile(folder / (part + ".3mf")) as archive:
            plate = json.loads(archive.read("Metadata/plate_1.json"))
        first = layers[0].segments
        first_lower = np.min([np.minimum(s.start, s.end) - s.width / 2 for s in first], axis=0)
        first_upper = np.max([np.maximum(s.start, s.end) + s.width / 2 for s in first], axis=0)
        bbox_error = float(np.max(np.abs(np.r_[first_lower, first_upper] - plate["bbox_all"])))
        if bbox_error > .05:
            raise ValueError("Model-bed coordinate mapping disagrees with Orca's own first-layer bounding box")
        model_layers = [layer for layer in layers if layer.model()]
        all_segments = [s for layer in layers for s in layer.segments]
        support_segments = [s for s in all_segments if s.feature in ("Support", "Support interface")]
        features = Counter(s.feature for s in all_segments)
        bores = []
        for x, y, radius in bore_specs(part):
            center = (transform @ np.array([x, y, 0, 1]))[:2]
            clearances = [point_clearance(layer.model(), center) for layer in model_layers]
            intrusions = []
            for layer in layers:
                supports = [s for s in layer.segments if s.feature in ("Support", "Support interface")]
                clearance = point_clearance(supports, center)
                if clearance is not None and clearance < radius:
                    intrusions.append({"zMm": layer.z, "heightMm": layer.height,
                                       "clearRadiusMm": clearance})
            bores.append({
                "sourceCenterXYMm": [x, y], "nominalInscribedRadiusMm": radius,
                "checkedModelLayerCount": len(clearances),
                "minimumModelToolpathClearRadiusMm": min(clearances),
                "minimumSupportToolpathClearRadiusMm": point_clearance(support_segments, center),
                "supportIntrusionLayers": intrusions,
                "modelNeverClosesBoreCenter": min(clearances) > 0,
                "dimensionOrFitCertified": False,
            })
        lower = np.min([np.minimum(s.start, s.end) - s.width / 2 for s in all_segments], axis=0)
        upper = np.max([np.maximum(s.start, s.end) + s.width / 2 for s in all_segments], axis=0)
        gear_samples=GEAR_CHECKS.get(part,[])
        if record.get("gearTeeth"):
            teeth=record["gearTeeth"]
            gear_samples=[(z,teeth[0] if index<2 else teeth[-1])
                          for index,(z,_) in enumerate(gear_samples)]
        elif "/C/" in record["stl"] and gear_samples:
            raise ValueError("C gear counts must come from the pinned assembly")
        gears = [gear_check(mesh, transform, nearest_model_layer(layers, z), teeth)
                 for z, teeth in gear_samples]
        images = []
        montage = Image.new("RGB", (1440, 1220), "white")
        for index, z in enumerate(VIEWS[part]):
            layer = nearest_model_layer(layers, z)
            if index == 0 and part in GEAR_CHECKS:
                underside = 10 if part == "P_INPUT_PINION" else 20
                layer = max((l for l in layers if l.z < underside
                             and any(s.feature == "Support interface" for s in l.segments)),
                            key=lambda l: l.z)
            outlines = mesh_section(mesh, layer.z - layer.height / 2, transform)
            montage.paste(panel(part, layer, outlines), ((index % 2) * 720, (index // 2) * 610))
        image_path = public_folder / (part + "_layers.png")
        montage.save(image_path, optimize=True)
        images.append({"path": image_path.name, "sha256": sha(image_path)})
        if gears:
            first_layer = layers[0]
            center = (transform @ np.array([0, 0, 0, 1]))[:2]
            crop = [*(center - 8), *(center + 8)]
            image_path = public_folder / (part + "_support_bore.png")
            panel(part, first_layer, mesh_section(mesh, first_layer.z-first_layer.height/2, transform),
                  crop, (1000, 900)).save(image_path, optimize=True)
            images.append({"path": image_path.name, "sha256": sha(image_path)})
            z, _ = GEAR_CHECKS[part][-1 if part == "P_INPUT_PINION" else 1]
            layer = nearest_model_layer(layers, z)
            outlines = mesh_section(mesh, layer.z - layer.height / 2, transform)
            shape = outlines[0]
            minx, miny, maxx, maxy = shape.bounds
            center = (transform @ np.array([0, 0, 0, 1]))[:2]
            point = np.array([maxx, center[1]])
            radius = 4 if part == "P_INPUT_PINION" else 7
            crop = [*(point - radius), *(point + radius)]
            image_path = public_folder / (part + "_tooth_detail.png")
            panel(part, layer, outlines, crop, (1000, 900)).save(image_path, optimize=True)
            images.append({"path": image_path.name, "sha256": sha(image_path)})
        result = {
            **record, "estimates": estimates, "modelLayerCount": len(model_layers),
            "firstLayerBoundingBoxAgreementWithOrcaMm": bbox_error,
            "allLayerCountIncludingSeparateSupportLayers": len(layers),
            "featureSegmentCounts": dict(features), "bores": bores, "gearLayers": gears,
            "supportInterfaceLayerHeightsMm": [layer.z for layer in layers
                                             if any(s.feature=="Support interface" for s in layer.segments)],
            "bridgeLayerHeightsMm": [layer.z for layer in layers
                                    if any(s.feature=="Bridge" for s in layer.segments)],
            "depositionBoundsXYMm": [lower.tolist(), upper.tolist()],
            "minimumBedEdgeMarginIncludingSupportAndBrimMm": float(min(*lower, *(256 - upper))),
            "layerImages": images,
            "layerInspectionStatus": "EXTRUSION_CHECKS_COMPUTED",
        }
        results.append(result)
        print(part, "model layers", len(model_layers), "bores", len(bores),
              "teeth", [g["depositedEnvelopeTeeth"] for g in gears], flush=True)
    write_json(public_folder / "toolpath_checks.json", {
        "reviewedArtifactCommit": run["reviewedArtifactCommit"], "orcaVersion": "2.4.2",
        "inputArtifactCommit":run.get("inputArtifactCommit",run["reviewedArtifactCommit"]),
        "designId":run.get("designId","A"),
        "sourceScriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "coordinateConvention": "Model-bed XY equals emitted G-code XY plus the declared single-nozzle offset; source STL placement comes from the saved 3MF. First-layer bounds are checked against Orca's own plate metadata.",
        "coordinateSource": "https://github.com/OrcaSlicer/OrcaSlicer/blob/v2.4.2/src/libslic3r/GCode.cpp#L8123-L8134",
        "scope": "Selected actual toolpaths only; center-open checks do not certify bore diameter, support removal, material strength or any physical walking.",
        "modelAndSupportSeparated": True, "machineStartupAndPurgeExcludedFromBedAndBoreChecks": True,
        "physicalPrintingPerformed": False, "parts": results,
    })
    provenance={**run,"recordScope":"Executed slicer inputs and outputs; final visual review is recorded separately in slicing_status.json.",
                "parts":[{k:v for k,v in row.items() if k!="layerInspectionStatus"} for row in run["parts"]]}
    write_json(public_folder / "profile_provenance.json", provenance)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-folder", type=Path, required=True)
    parser.add_argument("--public-folder", type=Path, required=True)
    args = parser.parse_args()
    inspect(args.run_folder, args.public_folder)
