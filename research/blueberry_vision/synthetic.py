"""Deterministic synthetic RGB assets with final-visibility reference annotations.

The renderer's reference comes from a final instance ownership raster, never from
the number of fruit shapes requested. No real image, biological label or weight
measurement is represented by these assets.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import PIL
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from research.blueberry_vision.assets import load_asset
from research.blueberry_vision.contracts import canonical_record_hash
from research.blueberry_vision.r2_common import (
    CLASS_LABEL,
    JSONDict,
    canonical_hash,
    dataset_split_hash,
    file_hash,
    seal,
    write_json_new,
)

GENERATOR_VERSION = "synthetic-blueberry-renderer/2.0.0"
LABEL_VERSION = "synthetic-visible-fruit/2.0.0"
ANNOTATION_VERSION = "synthetic-render-reference/2.0.0"
MIN_VISIBLE_FRACTION = 0.15
MIN_VISIBLE_PIXELS = 12
SPLITS = ("train", "validation", "test", "out_of_domain")
SCENE_TYPES = (
    "sparse",
    "dense",
    "touching",
    "partial_occlusion",
    "high_occlusion",
    "leaf_branch_background",
    "shadow",
    "glare",
    "mixed_sizes",
    "color_appearance",
    "edge_crop",
    "empty",
    "distractors",
    "pressure",
)
MAX_IMAGES_PER_SPLIT = 128


def _scene_seed(seed: int, split: str, index: int) -> int:
    digest = hashlib.sha256(f"{GENERATOR_VERSION}|{seed}|{split}|{index}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _background(
    width: int, height: int, rng: np.random.Generator, ood: bool
) -> tuple[NDArray[np.uint8], JSONDict]:
    yy, xx = np.mgrid[:height, :width]
    base = np.array([55.0, 69.0, 39.0] if not ood else [80.0, 62.0, 42.0])
    variation = 8 * np.sin(xx / 29) + 4 * np.cos(yy / 17)
    values = base[None, None, :] + variation[:, :, None]
    values += rng.normal(0, 3.2, (height, width, 3))
    image = Image.fromarray(np.clip(values, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    leaves: list[list[int]] = []
    branches: list[list[int]] = []
    for _ in range(7):
        x = int(rng.integers(-20, width))
        y = int(rng.integers(-15, height))
        leaves.append([x, y, x + 65, y + 24])
        draw.ellipse((x, y, x + 65, y + 24), fill=(35, int(rng.integers(77, 104)), 29))
        draw.line((x + 4, y + 12, x + 59, y + 12), fill=(50, 110, 33), width=1)
    for _ in range(3):
        x = int(rng.integers(0, width))
        branch = [x, 0, x + int(rng.integers(-70, 70)), height]
        branches.append(branch)
        draw.line(branch, fill=(96, 71, 43), width=3)
    return np.array(image, dtype=np.uint8), {
        "leaf_ellipses_xyxy": leaves,
        "branch_segments_xyxy": branches,
    }


def _fruit_layout(
    scene: str, width: int, height: int, rng: np.random.Generator
) -> list[tuple[float, float, float, str]]:
    """Positions vary independently by split; they are not detector answers."""
    if scene == "empty":
        return []
    if scene == "pressure":
        offset_x, offset_y = rng.uniform(18, 23, 2)
        return [
            (
                float(offset_x + column * 25 + rng.uniform(-1.5, 1.5)),
                float(offset_y + row * 23 + rng.uniform(-1.5, 1.5)),
                float(rng.uniform(7, 9)),
                "blue",
            )
            for row in range(10)
            for column in range(12)
        ]
    if scene == "edge_crop":
        return [
            (
                float(rng.uniform(0.25, 3)),
                float(rng.uniform(25, 60)),
                float(rng.uniform(16, 22)),
                "blue",
            ),
            (
                float(width - rng.uniform(0.25, 3)),
                float(rng.uniform(55, 85)),
                float(rng.uniform(16, 22)),
                "blue",
            ),
            (
                float(rng.uniform(60, 90)),
                float(rng.uniform(0.25, 3)),
                float(rng.uniform(16, 22)),
                "blue",
            ),
            (
                float(rng.uniform(150, 200)),
                float(height - rng.uniform(0.25, 3)),
                float(rng.uniform(16, 22)),
                "blue",
            ),
            (
                float(rng.uniform(68, 80)),
                float(rng.uniform(85, 95)),
                float(rng.uniform(16, 20)),
                "blue",
            ),
            (
                float(rng.uniform(135, 149)),
                float(rng.uniform(95, 105)),
                float(rng.uniform(16, 20)),
                "blue",
            ),
            (
                float(rng.uniform(53, 67)),
                float(rng.uniform(149, 161)),
                float(rng.uniform(14, 18)),
                "blue",
            ),
            (
                float(rng.uniform(201, 213)),
                float(rng.uniform(144, 156)),
                float(rng.uniform(16, 20)),
                "blue",
            ),
        ]
    if scene == "distractors":
        return [
            (
                float(35 + column * 54 + rng.uniform(-5, 5)),
                float(40 + row * 55 + rng.uniform(-5, 5)),
                float(rng.uniform(11, 16)),
                "blue",
            )
            for row in range(3)
            for column in range(2)
        ]
    counts = {
        "sparse": 6,
        "dense": 28,
        "touching": 8,
        "partial_occlusion": 20,
        "high_occlusion": 22,
        "leaf_branch_background": 12,
        "shadow": 12,
        "glare": 12,
        "mixed_sizes": 16,
        "color_appearance": 15,
    }
    count = counts[scene]
    columns = (
        7
        if scene == "dense"
        else 5
        if scene in {"partial_occlusion", "high_occlusion", "color_appearance"}
        else 4
        if count >= 8
        else 3
    )
    rows = math.ceil(count / columns)
    step_x = (
        29.0
        if scene == "dense"
        else 43.0
        if scene == "touching"
        else (width - 55.0) / max(columns - 1, 1)
    )
    step_y = 34.0 if scene == "dense" else (height - 60.0) / max(rows - 1, 1)
    layout: list[tuple[float, float, float, str]] = []
    touching_radius = float(rng.uniform(20, 23))
    touching_origin = rng.uniform([42, 53], [56, 65])
    for index in range(count):
        x = 28 + (index % columns) * step_x + float(rng.uniform(-3, 3))
        y = 28 + (index // columns) * step_y + float(rng.uniform(-3, 3))
        radius = float(rng.uniform(14, 19))
        if scene == "dense":
            radius = float(rng.uniform(17, 23))
        elif scene == "touching":
            radius = touching_radius * float(rng.uniform(0.94, 1.06))
            x = float(touching_origin[0] + (index % 4) * touching_radius * 1.85)
            y = float(touching_origin[1] + (index // 4) * touching_radius * 1.85)
        elif scene == "mixed_sizes":
            radius = float(rng.uniform(5, 9) if index % 2 == 0 else rng.uniform(17, 23))
        if scene == "high_occlusion":
            # Top row is reserved for two guaranteed hidden/ignored references.
            y = 80 + (index // columns) * 24 + float(rng.uniform(-2, 2))
        appearance = (
            ("blue", "green_candidate", "pink_candidate")[index % 3]
            if scene == "color_appearance"
            else "blue"
        )
        layout.append((x, y, radius, appearance))
    if scene == "high_occlusion":
        layout.extend([(34.0, 35.0, 15.0, "blue"), (85.0, 35.0, 15.0, "blue")])
    return layout


def _draw_fruit(
    canvas: NDArray[np.uint8],
    ownership: NDArray[np.int32],
    rng: np.random.Generator,
    fruit: tuple[float, float, float, str],
    number: int,
    ood: bool,
) -> JSONDict:
    x, y, radius, appearance = fruit
    height, width = ownership.shape
    radius_y = radius * (float(rng.uniform(0.78, 1.12)) if ood else float(rng.uniform(0.93, 1.05)))
    x1, y1 = max(0, math.floor(x - radius)), max(0, math.floor(y - radius_y))
    x2, y2 = min(width, math.ceil(x + radius)), min(height, math.ceil(y + radius_y))
    yy, xx = np.mgrid[y1:y2, x1:x2]
    dx, dy = (xx + 0.5 - x) / radius, (yy + 0.5 - y) / radius_y
    norm = dx * dx + dy * dy
    silhouette = norm <= 1.0
    palettes = {
        "blue": [52.0, 77.0, 151.0],
        "green_candidate": [74.0, 132.0, 73.0],
        "pink_candidate": [157.0, 77.0, 118.0],
    }
    base = np.array(palettes[appearance])
    base += rng.uniform(-8, 8, 3)
    if ood:
        base += np.array([19.0, -14.0, -16.0])
    shade = 0.78 + 0.20 * (1 - norm) - 0.12 * dx - 0.10 * dy
    body = base[None, None, :] * shade[:, :, None]
    bloom = np.exp(-((dx + 0.25) ** 2 + (dy + 0.22) ** 2) / 0.17)
    body += bloom[:, :, None] * np.array([28.0, 24.0, 18.0])
    body += rng.normal(0, 2.0, body.shape)
    # Small specular mark and dark calyx provide texture beyond plain circles.
    highlight = ((dx + 0.34) ** 2 + (dy + 0.35) ** 2) < 0.035
    body[highlight] += np.array([48.0, 48.0, 40.0])
    calyx = ((dx - 0.13) ** 2 + (dy - 0.22) ** 2) < 0.037
    body[calyx] *= 0.53
    pixels = np.clip(body, 0, 255).astype(np.uint8)
    canvas_region = canvas[y1:y2, x1:x2]
    owner_region = ownership[y1:y2, x1:x2]
    canvas_region[silhouette] = pixels[silhouette]
    owner_region[silhouette] = number
    return {
        "object_index": number,
        "geometry": {"center_xy": [x, y], "radius_xy": [radius, radius_y]},
        "unoccluded_pixels": int(np.count_nonzero(silhouette)),
        "candidate_appearance": appearance,
        "edge_cropped": x - radius < 0
        or y - radius_y < 0
        or x + radius > width
        or y + radius_y > height,
    }


def _occlude(canvas: NDArray[np.uint8], ownership: NDArray[np.int32], scene: str) -> None:
    height, width = ownership.shape
    layer = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(layer)
    if scene == "partial_occlusion":
        draw.polygon([(0, 64), (140, 95), (163, 115), (0, 88)], fill=255)
        draw.ellipse((147, 113, 264, 151), fill=255)
    elif scene == "high_occlusion":
        draw.rectangle((13, 13, 55, 57), fill=255)
        # Leaves only the final x=99 sliver (<12 pixels) of fruit centered at 85.
        draw.rectangle((64, 15, 98, 55), fill=255)
        draw.polygon([(0, 100), (width, 123), (width, 143), (0, 120)], fill=255)
        draw.ellipse((121, 143, 278, 176), fill=255)
    occlusion = np.asarray(layer) > 0
    canvas[occlusion] = (40, 99, 31)
    ownership[occlusion] = 0


def _tight_box(mask: NDArray[np.bool_]) -> list[float]:
    ys, xs = np.nonzero(mask)
    return [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]


def _render_scene(
    scene: str, seed: int, ood: bool, image_id: str
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], JSONDict]:
    width, height = (320, 256) if scene == "pressure" else (256, 192)
    rng = np.random.default_rng(seed)
    canvas, background_geometry = _background(width, height, rng, ood)
    ownership = np.zeros((height, width), dtype=np.int32)
    layout = _fruit_layout(scene, width, height, rng)
    rendered = [
        _draw_fruit(canvas, ownership, rng, fruit, index + 1, ood)
        for index, fruit in enumerate(layout)
    ]
    _occlude(canvas, ownership, scene)
    distractor_geometry: JSONDict = {}
    if scene == "distractors":
        image = Image.fromarray(canvas)
        draw = ImageDraw.Draw(image)
        shift_x, shift_y = map(int, rng.integers(-7, 8, 2))
        box_radius = int(rng.integers(12, 17))
        polygon_a = [
            (155 + shift_x, 25 + shift_y),
            (197 + shift_x, 29 + shift_y),
            (205 + shift_x, 49 + shift_y),
            (158 + shift_x, 51 + shift_y),
        ]
        circle = (
            177 + shift_x - box_radius,
            97 + shift_y - box_radius,
            177 + shift_x + box_radius,
            97 + shift_y + box_radius,
        )
        polygon_b = [
            (162 + shift_x, 143 + shift_y),
            (183 + shift_x, 124 + shift_y),
            (204 + shift_x, 148 + shift_y),
            (182 + shift_x, 164 + shift_y),
        ]
        draw.polygon(polygon_a, fill=(48, 73, 147))
        draw.ellipse(circle, fill=(44, 69, 139))
        draw.polygon(polygon_b, fill=(53, 82, 155))
        canvas = np.array(image, dtype=np.uint8)
        distractor_geometry = {
            "polygon_a": polygon_a,
            "ellipse_xyxy": circle,
            "polygon_b": polygon_b,
        }
    illumination = float(rng.uniform(0.86, 1.10))
    lighting = "normal"
    values = canvas.astype(np.float64) * illumination
    if scene == "shadow":
        lighting = "shadow"
        xx = np.arange(width)
        attenuation = np.where(xx < width * 0.58, 0.43, 0.73)
        values *= attenuation[None, :, None]
    elif scene == "glare":
        lighting = "glare"
        yy, xx = np.mgrid[:height, :width]
        light = 105 * np.exp(-((xx - width * 0.40) ** 2 + (yy - height * 0.42) ** 2) / 1400)
        values = values * 1.16 + light[:, :, None]
    canvas = np.clip(values, 0, 255).astype(np.uint8)
    objects: list[JSONDict] = []
    ignores: list[list[float]] = []
    pixel_targets = np.zeros((height, width), dtype=np.uint8)
    visibility: list[JSONDict] = []
    for item in rendered:
        number = item["object_index"]
        mask = ownership == number
        visible = int(np.count_nonzero(mask))
        total = item["unoccluded_pixels"]
        fraction = visible / total if total else 0.0
        object_id = f"{image_id}:fruit:{number:04d}"
        if visible == 0:
            status = "hidden"
        elif fraction < MIN_VISIBLE_FRACTION or visible < MIN_VISIBLE_PIXELS:
            status = "ignored"
            ignores.append(_tight_box(mask))
            pixel_targets[mask] = 128
        else:
            status = "included"
            objects.append(
                {"object_id": object_id, "class_label": CLASS_LABEL, "bbox_xyxy": _tight_box(mask)}
            )
            pixel_targets[mask] = 255
        visibility.append(
            {
                "object_id": object_id,
                "unoccluded_pixels": total,
                "visible_pixels": visible,
                "visible_fraction": fraction,
                "reference_status": status,
                "candidate_appearance": item["candidate_appearance"],
                "edge_cropped": item["edge_cropped"],
            }
        )
    metadata: JSONDict = {
        "scene_type": scene,
        "density": "pressure"
        if scene == "pressure"
        else "dense"
        if scene in {"dense", "touching", "partial_occlusion", "high_occlusion"}
        else "sparse",
        "occlusion": "high"
        if scene == "high_occlusion"
        else "partial"
        if scene in {"dense", "touching", "partial_occlusion"}
        else "none",
        "lighting": lighting,
        "size": "small" if scene == "pressure" else "mixed" if scene == "mixed_sizes" else "large",
        "domain": "ood" if ood else "regular",
        "empty": len(objects) == 0,
        "illumination_multiplier": illumination,
        "camera_device": "synthetic-software-renderer; no physical calibration",
        "candidate_color_is_biological_maturity": False,
        "edge_cropped_objects": sum(item["edge_cropped"] for item in rendered),
        "rendered_object_visibility": visibility,
        "template_geometry_parameters": {
            "fruit_shapes": [item["geometry"] for item in rendered],
            "distractors": distractor_geometry,
            "background": background_geometry,
        },
        "visible_reference_rule": {
            "fraction_minimum": MIN_VISIBLE_FRACTION,
            "pixels_minimum": MIN_VISIBLE_PIXELS,
            "fraction_denominator": "in_frame_unoccluded_silhouette_pixels",
            "box_convention": "tight_visible_pixels_xyxy_half_open",
            "fully_hidden_in_reference": False,
            "low_visibility_region_is_ignored": True,
        },
    }
    metadata["template_geometry_hash"] = canonical_hash(metadata["template_geometry_parameters"])
    return (
        canvas,
        pixel_targets,
        {
            "objects": objects,
            "ignore_regions": ignores,
            "visible_count": len(objects),
            "drawn_object_count": len(rendered),
            "hidden_object_count": sum(item["reference_status"] == "hidden" for item in visibility),
            "ignored_object_count": len(ignores),
            "scene_metadata": metadata,
        },
    )


def _save_png(path: Path, pixels: NDArray[np.uint8]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # No timestamps, EXIF or host-specific metadata enter the encoded bytes.
    Image.fromarray(pixels).save(path, format="PNG", optimize=False, compress_level=9)


def generate_dataset(
    output_dir: Path, seed: int = 20261013, images_per_split: int = 14
) -> JSONDict:
    """Generate actual public synthetic assets; reject replacing existing runs."""
    if type(images_per_split) is not int or not 1 <= images_per_split <= MAX_IMAGES_PER_SPLIT:
        raise ValueError("IMAGES_PER_SPLIT_LIMIT")
    if type(seed) is not int:
        raise ValueError("INTEGER_SEED_REQUIRED")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output_dir.mkdir(parents=True, exist_ok=True)
    images: list[JSONDict] = []
    for split_index, split in enumerate(SPLITS):
        for index in range(images_per_split):
            scene = SCENE_TYPES[index % len(SCENE_TYPES)]
            scene_seed = _scene_seed(seed, split, index)
            image_id = f"synthetic-r2-{seed}-{split}-{index:04d}"
            image_ref = f"images/{split}/{image_id}.png"
            mask_ref = f"masks/{split}/{image_id}.png"
            pixels, mask, annotation = _render_scene(
                scene, scene_seed, split == "out_of_domain", image_id
            )
            _save_png(output_dir / image_ref, pixels)
            _save_png(output_dir / mask_ref, mask)
            asset = load_asset(output_dir, image_ref)
            record: JSONDict = {
                "image_id": image_id,
                "original_asset_ref": image_ref,
                "asset_sha256": asset.metadata["asset_sha256"],
                "image_width": asset.metadata["image_width"],
                "image_height": asset.metadata["image_height"],
                "observed_at": f"2000-01-0{split_index + 1}T00:00:00Z",
                "asset_available_at": f"2000-01-0{split_index + 1}T00:00:01Z",
                "available_at": f"2000-01-0{split_index + 1}T00:00:02Z",
                "capture_session_id": f"synthetic-session:{seed}:{split}:{index}",
                "sampling_unit_id": f"synthetic-unit:{seed}:{split}:{index}",
                "base_identity": {
                    "status": "unresolved",
                    "base_id": None,
                    "authority_ref": None,
                    "unresolved_reason": "synthetic assets have no business identity",
                },
                "source_authority": {
                    "authority_id": "task-authorized-synthetic-renderer",
                    "source_ref": GENERATOR_VERSION,
                    "permission_status": "synthetic_only",
                    "evidence_ref": "task:BLUEBERRY_VISION_R2_OFFLINE_DETECTION_COUNTING_PIPELINE",
                    "allowed_uses": [
                        "metadata_validation",
                        "train",
                        "validation",
                        "test",
                        "out_of_domain",
                    ],
                    "granted_at": None,
                    "expires_at": None,
                },
                "SYNTHETIC": True,
                "split": split,
                "generation_seed": scene_seed,
                "template_group_id": f"synthetic-template:{seed}:{split}:{index}",
                "near_duplicate_group_id": f"synthetic-duplicate-group:{seed}:{split}:{index}",
                "preprocessing_version": asset.metadata["preprocessing_version"],
                "preprocessing_hash": asset.metadata["preprocessing_hash"],
                "label_definition_version": LABEL_VERSION,
                "annotation_version": ANNOTATION_VERSION,
                "annotation_quality_status": "synthetic_reference",
                "gt_status": "complete",
                **annotation,
                "training_mask_ref": mask_ref,
                "training_mask_sha256": file_hash(output_dir / mask_ref),
            }
            record["record_hash"] = canonical_record_hash(record)
            images.append(record)
    config: JSONDict = {
        "seed": seed,
        "images_per_split": images_per_split,
        "scenes": list(SCENE_TYPES),
        "splits": list(SPLITS),
        "standard_dimensions": [256, 192],
        "pressure_dimensions": [320, 256],
        "minimum_visible_fraction": MIN_VISIBLE_FRACTION,
        "minimum_visible_pixels": MIN_VISIBLE_PIXELS,
        "png_encoding": {"optimize": False, "compress_level": 9, "metadata": "none"},
        "dependency_versions": {"Pillow": PIL.__version__, "numpy": np.__version__},
        "references_are_real_business_labels": False,
    }
    manifest = seal(
        {
            "schema_version": "blueberry-vision-dataset/2.0.0",
            "SYNTHETIC": True,
            "image_files_present": True,
            "generator_version": GENERATOR_VERSION,
            "generation_config": config,
            "label_definition_version": LABEL_VERSION,
            "annotation_version": ANNOTATION_VERSION,
            "images": images,
            "split_hash": dataset_split_hash(images),
        },
        "manifest_hash",
    )
    write_json_new(output_dir / "dataset_manifest.json", manifest)
    return manifest
