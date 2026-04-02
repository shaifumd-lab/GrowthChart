"""
Chart point auto-detection using OpenCV.

Detects colored data points (dots, circles, marks) plotted on growth chart images.
Works with the chart-digitizer.js calibration system.
"""

from typing import List, Dict, Optional, Tuple
from pathlib import Path

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from PIL import Image
except ImportError:
    Image = None


class ChartPointDetector:
    """Detect colored data points on a growth chart image."""

    # Common colors used to plot growth data on paper charts
    # Each entry: (name, HSV low, HSV high)
    COLOR_RANGES = [
        # Blue markers (pens, stamps)
        ("blue", np.array([100, 50, 50]), np.array([130, 255, 255])),
        # Red markers
        ("red_low", np.array([0, 70, 50]), np.array([10, 255, 255])),
        ("red_high", np.array([170, 70, 50]), np.array([180, 255, 255])),
        # Black markers (dark, low saturation)
        ("black", np.array([0, 0, 0]), np.array([180, 80, 80])),
        # Green markers
        ("green", np.array([35, 50, 50]), np.array([85, 255, 255])),
        # Purple markers
        ("purple", np.array([130, 50, 50]), np.array([165, 255, 255])),
    ]

    # Min/max contour area for a data point (in pixels)
    MIN_POINT_AREA = 15
    MAX_POINT_AREA = 2000

    # Min circularity (1.0 = perfect circle, lower = more lenient)
    MIN_CIRCULARITY = 0.3

    def detect(self, image_path: str,
               cal_x1_px: float, cal_x1_val: float,
               cal_x2_px: float, cal_x2_val: float,
               cal_y1_py: float, cal_y1_val: float,
               cal_y2_py: float, cal_y2_val: float) -> Dict:
        """
        Detect data points on a chart image.

        Args:
            image_path: Path to chart image
            cal_*: Calibration points (pixel coords + real values)

        Returns:
            {success, points: [{px, py, color}], message}
        """
        if not HAS_CV2:
            return {"success": False, "error": "OpenCV not available"}

        path = Path(image_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {image_path}"}

        img = cv2.imread(str(path))
        if img is None:
            return {"success": False, "error": "Could not load image"}

        # Convert to HSV for color detection
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Define the chart area from calibration bounds
        # Use calibration points to estimate the chart region
        x_min_px = min(cal_x1_px, cal_x2_px)
        x_max_px = max(cal_x1_px, cal_x2_px)
        y_min_px = min(cal_y1_py, cal_y2_py)
        y_max_px = max(cal_y1_py, cal_y2_py)

        # Expand region slightly (10% padding)
        pad_x = (x_max_px - x_min_px) * 0.1
        pad_y = (y_max_px - y_min_px) * 0.1
        roi_x1 = max(0, int(x_min_px - pad_x))
        roi_x2 = min(img.shape[1], int(x_max_px + pad_x))
        roi_y1 = max(0, int(y_min_px - pad_y))
        roi_y2 = min(img.shape[0], int(y_max_px + pad_y))

        all_points = []

        for name, hsv_low, hsv_high in self.COLOR_RANGES:
            # Create color mask
            mask = cv2.inRange(hsv, hsv_low, hsv_high)

            # Restrict to chart region
            roi_mask = np.zeros_like(mask)
            roi_mask[roi_y1:roi_y2, roi_x1:roi_x2] = mask[roi_y1:roi_y2, roi_x1:roi_x2]

            # Morphological operations to clean up
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_CLOSE, kernel)
            roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_OPEN, kernel)

            # Find contours
            contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < self.MIN_POINT_AREA or area > self.MAX_POINT_AREA:
                    continue

                # Check circularity
                perimeter = cv2.arcLength(cnt, True)
                if perimeter == 0:
                    continue
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                if circularity < self.MIN_CIRCULARITY:
                    continue

                # Get centroid
                M = cv2.moments(cnt)
                if M["m00"] == 0:
                    continue
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]

                all_points.append({
                    "px": round(cx, 1),
                    "py": round(cy, 1),
                    "color": name,
                    "area": round(area, 1),
                    "circularity": round(circularity, 2),
                })

        # Deduplicate: merge points within 10px of each other
        merged = self._merge_nearby(all_points, threshold=10)

        # Sort by X position (left to right = earliest to latest age)
        merged.sort(key=lambda p: p["px"])

        return {
            "success": True,
            "points": merged,
            "message": f"Detected {len(merged)} potential data points",
            "chart_region": {
                "x1": roi_x1, "y1": roi_y1,
                "x2": roi_x2, "y2": roi_y2,
            },
        }

    def _merge_nearby(self, points: List[Dict], threshold: float = 10) -> List[Dict]:
        """Merge points that are within threshold pixels of each other."""
        if not points:
            return []

        merged = []
        used = set()

        for i, p1 in enumerate(points):
            if i in used:
                continue
            cluster = [p1]
            for j, p2 in enumerate(points):
                if j <= i or j in used:
                    continue
                dist = ((p1["px"] - p2["px"])**2 + (p1["py"] - p2["py"])**2)**0.5
                if dist < threshold:
                    cluster.append(p2)
                    used.add(j)
            used.add(i)

            # Average the cluster
            avg_px = sum(p["px"] for p in cluster) / len(cluster)
            avg_py = sum(p["py"] for p in cluster) / len(cluster)
            merged.append({
                "px": round(avg_px, 1),
                "py": round(avg_py, 1),
                "color": cluster[0]["color"],
            })

        return merged
