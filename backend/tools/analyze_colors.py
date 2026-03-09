"""
Diagnostic tool to analyze hi-vis colors in an image ROI
Usage: python analyze_colors.py <image_path> [x1 y1 x2 y2]
"""
import cv2
import numpy as np
import sys
from pathlib import Path

def analyze_hivis_colors(image_path, bbox=None):
    """Analyze hi-vis color presence in an image or ROI"""

    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Error: Cannot load image {image_path}")
        return

    print(f"Image size: {img.shape[1]}x{img.shape[0]}")

    # If bbox provided, extract ROI
    if bbox:
        x1, y1, x2, y2 = bbox
        roi = img[y1:y2, x1:x2]
        print(f"ROI: ({x1},{y1}) to ({x2},{y2}) = {x2-x1}x{y2-y1} pixels")
    else:
        roi = img
        print("Analyzing full image")

    if roi.size == 0:
        print("Error: ROI is empty")
        return

    # Convert to HSV
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Hi-vis ranges (current settings)
    hi_vis_ranges = [
        ("Red", (0, 70, 50), (10, 255, 255)),
        ("Red-wrap", (170, 70, 50), (180, 255, 255)),
        ("Orange", (0, 80, 80), (25, 255, 255)),
        ("Yellow", (25, 80, 120), (45, 255, 255)),
        ("Green", (45, 60, 80), (95, 255, 255)),
    ]

    # Relaxed ranges for distant persons (new implementation)
    relaxed_ranges = [
        ("Red-relaxed", (0, 50, 40), (10, 255, 255)),      # Red - lower S,V for distant
        ("Red-wrap-relax", (170, 50, 40), (180, 255, 255)), # Red-wrap for distant
        ("Orange-relaxed", (0, 50, 50), (25, 255, 255)),   # Lower S,V for distant
        ("Yellow-relaxed", (25, 50, 80), (50, 255, 255)),  # Extended range
        ("Green-relaxed", (40, 40, 60), (100, 255, 255)),  # Extended range
    ]

    # Extended ranges (even more permissive for dark/shadowed areas)
    extended_ranges = [
        ("Orange-dark", (0, 30, 30), (25, 255, 255)),      # Very dark orange/red
        ("Red-deep", (0, 40, 40), (10, 255, 255)),         # Deep red
        ("Red-wrap", (170, 40, 40), (180, 255, 255)),      # Red wraps around in HSV
    ]

    total_pixels = roi.shape[0] * roi.shape[1]
    print(f"\nTotal pixels in ROI: {total_pixels}")
    print("\n=== Current Hi-Vis Ranges (threshold 8%) ===")

    total_hivis = 0
    for name, lower, upper in hi_vis_ranges:
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        count = cv2.countNonZero(mask)
        pct = count / total_pixels * 100
        total_hivis += count
        print(f"  {name}: {count} pixels ({pct:.1f}%) - H:{lower[0]}-{upper[0]} S:{lower[1]}-{upper[1]} V:{lower[2]}-{upper[2]}")

    total_pct = total_hivis / total_pixels * 100
    print(f"\n  TOTAL hi-vis: {total_hivis} pixels ({total_pct:.1f}%)")
    if total_pct >= 8:
        print("  [PASS] Would pass 8% threshold")
    else:
        print("  [FAIL] Would NOT pass 8% threshold")

    print("\n=== Relaxed Ranges (for distant persons) ===")
    total_relaxed = 0
    for name, lower, upper in relaxed_ranges:
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        count = cv2.countNonZero(mask)
        pct = count / total_pixels * 100
        total_relaxed += count
        print(f"  {name}: {count} pixels ({pct:.1f}%)")
    print(f"  TOTAL relaxed: {total_relaxed} pixels ({total_relaxed/total_pixels*100:.1f}%)")

    print("\n=== Extended Ranges (very dark/shadowed) ===")
    for name, lower, upper in extended_ranges:
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        count = cv2.countNonZero(mask)
        pct = count / total_pixels * 100
        print(f"  {name}: {count} pixels ({pct:.1f}%)")

    # Analyze lateral strips (for open vests)
    print("\n=== Lateral Strip Analysis (25% each side) ===")
    roi_h, roi_w = roi.shape[:2]
    strip_width = max(1, roi_w // 4)
    left_strip = roi[:, :strip_width]
    right_strip = roi[:, -strip_width:]

    for strip_name, strip in [("Left", left_strip), ("Right", right_strip)]:
        if strip.size == 0:
            continue
        strip_hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        strip_pixels = strip.shape[0] * strip.shape[1]
        strip_hivis = 0
        for name, lower, upper in hi_vis_ranges:
            mask = cv2.inRange(strip_hsv, np.array(lower), np.array(upper))
            strip_hivis += cv2.countNonZero(mask)
        strip_pct = strip_hivis / strip_pixels * 100
        print(f"  {strip_name} strip: {strip_hivis}/{strip_pixels} pixels ({strip_pct:.1f}%)")

    # Show dominant colors in ROI
    print("\n=== Dominant HSV Values in ROI ===")
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()

    print(f"  H (Hue):        min={h_vals.min()}, max={h_vals.max()}, mean={h_vals.mean():.1f}, median={np.median(h_vals):.1f}")
    print(f"  S (Saturation): min={s_vals.min()}, max={s_vals.max()}, mean={s_vals.mean():.1f}, median={np.median(s_vals):.1f}")
    print(f"  V (Value):      min={v_vals.min()}, max={v_vals.max()}, mean={v_vals.mean():.1f}, median={np.median(v_vals):.1f}")

    # Find pixels that SHOULD be orange but aren't matching
    # Orange hue range but low saturation/value
    print("\n=== Potential Orange Pixels Not Matching ===")
    orange_hue_mask = (hsv[:,:,0] <= 25)  # Orange hue range
    low_sat_mask = (hsv[:,:,1] < 80)      # Below saturation threshold
    low_val_mask = (hsv[:,:,2] < 80)      # Below value threshold

    potential_orange_low_sat = np.count_nonzero(orange_hue_mask & low_sat_mask)
    potential_orange_low_val = np.count_nonzero(orange_hue_mask & low_val_mask)
    print(f"  Pixels with orange hue (H<=25) but S<80: {potential_orange_low_sat} ({potential_orange_low_sat/total_pixels*100:.1f}%)")
    print(f"  Pixels with orange hue (H<=25) but V<80: {potential_orange_low_val} ({potential_orange_low_val/total_pixels*100:.1f}%)")

    # Save debug visualization
    output_dir = Path(image_path).parent / "debug"
    output_dir.mkdir(exist_ok=True)

    # Create visualization
    vis = roi.copy()
    combined_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for name, lower, upper in hi_vis_ranges:
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        combined_mask = cv2.bitwise_or(combined_mask, mask)

    # Overlay mask in green
    overlay = vis.copy()
    overlay[combined_mask > 0] = [0, 255, 0]
    vis = cv2.addWeighted(vis, 0.7, overlay, 0.3, 0)

    debug_path = output_dir / f"color_debug_{Path(image_path).stem}.jpg"
    cv2.imwrite(str(debug_path), vis)
    print(f"\n[OK] Debug visualization saved to: {debug_path}")

    # Also save ROI
    roi_path = output_dir / f"roi_{Path(image_path).stem}.jpg"
    cv2.imwrite(str(roi_path), roi)
    print(f"[OK] ROI saved to: {roi_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_colors.py <image_path> [x1 y1 x2 y2]")
        print("Example: python analyze_colors.py alert.jpg 500 50 560 120")
        sys.exit(1)

    image_path = sys.argv[1]
    bbox = None

    if len(sys.argv) >= 6:
        bbox = [int(sys.argv[i]) for i in range(2, 6)]

    analyze_hivis_colors(image_path, bbox)
