import cv2
import numpy as np
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".MP4", ".MOV", ".AVI"}


# ── Config ─────────────────────────────────────────────────────────────────────
@dataclass
class Config:
    # I/O
    input_folder:  str = "/home/asus/LifeLens/video/input"   # folder with videos
    output_folder: str = "/home/asus/LifeLens/video/output"  # one output per video

    # Frame sampling
    frame_skip: int   = 1       # 1 = every frame; raise to 2 for speed
    resize_w:   int   = 640
    resize_h:   int   = 360

    # Optical flow
    flow_levels:     int = 3
    flow_winsize:    int = 15
    flow_iterations: int = 3

    # Adaptive baseline (fast detector)
    baseline_frames:  int   = 45
    spike_multiplier: float = 2.5

    # Fast fall — state machine
    freefall_down_ratio: float = 0.55
    impact_drop_ratio:   float = 0.4
    blur_threshold:      float = 80.0
    spike_window:        int   = 6
    freefall_window:     int   = 8
    cooldown_seconds:    float = 2.0

    # Slow fall — trend detector
    slow_slope_window:        int   = 20
    slow_slope_threshold:     float = 0.04
    slow_down_ratio_mean_min: float = 0.52
    slow_stillness_mag:       float = 0.8
    slow_stillness_frames:    int   = 15
    slow_min_buildup_frames:  int   = 12


cfg = Config()


# ── Flow extractor ─────────────────────────────────────────────────────────────
class FlowExtractor:
    def __init__(self, cfg: Config):
        self.cfg       = cfg
        self.prev_gray = None

    def reset(self):
        """Call between videos to clear inter-frame state."""
        self.prev_gray = None

    def extract(self, gray: np.ndarray) -> dict:
        if self.prev_gray is None or self.prev_gray.shape != gray.shape:
            self.prev_gray = gray.copy()
            return self._null()

        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray, gray, None,
            pyr_scale=0.5,
            levels=self.cfg.flow_levels,
            winsize=self.cfg.flow_winsize,
            iterations=self.cfg.flow_iterations,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )
        self.prev_gray = gray.copy()

        fx, fy   = flow[..., 0], flow[..., 1]
        mag      = np.sqrt(fx**2 + fy**2)
        mean_mag = float(mag.mean())

        down_flow  = float(fy[fy > 0].mean())         if (fy > 0).any() else 0.0
        up_flow    = float(np.abs(fy[fy < 0]).mean()) if (fy < 0).any() else 0.0
        total_vert = down_flow + up_flow + 1e-6
        down_ratio = down_flow / total_vert

        h, w         = gray.shape
        y_idx, x_idx = np.mgrid[0:h, 0:w]
        rx           = x_idx - w // 2
        ry           = y_idx - h // 2
        rotation     = float(np.mean(fx * ry - fy * rx))
        uniformity   = 1.0 - float(mag.std() / (mean_mag + 1e-6))

        return {
            "magnitude":  mean_mag,
            "down_ratio": down_ratio,
            "rotation":   abs(rotation),
            "uniformity": max(0.0, uniformity),
            "raw_fy":     float(fy.mean()),
        }

    @staticmethod
    def _null() -> dict:
        return {"magnitude": 0.0, "down_ratio": 0.5,
                "rotation": 0.0, "uniformity": 0.5, "raw_fy": 0.0}


# ── Blur detector ──────────────────────────────────────────────────────────────
def laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


# ── Adaptive baseline ──────────────────────────────────────────────────────────
class AdaptiveBaseline:
    def __init__(self, window: int, multiplier: float):
        self.buf        = deque(maxlen=window)
        self.multiplier = multiplier

    def update(self, val: float) -> tuple:
        self.buf.append(val)
        if len(self.buf) < 10:
            return 0.0, 999.0, False
        mean   = float(np.mean(self.buf))
        std    = float(np.std(self.buf))
        thresh = mean + self.multiplier * std
        return mean, thresh, bool(val > thresh)


# ── Fast fall — state machine ──────────────────────────────────────────────────
class FastFallDetector:
    NORMAL   = "NORMAL"
    SPIKE    = "SPIKE"
    FREEFALL = "FREEFALL"
    IMPACT   = "IMPACT"
    COOLDOWN = "COOLDOWN"

    def __init__(self, cfg: Config, fps: float):
        self.cfg             = cfg
        self.fps             = max(fps, 15.0)
        self.state           = self.NORMAL
        self.phase_age       = 0
        self.peak_mag        = 0.0
        self.cooldown_frames = int(self.fps * cfg.cooldown_seconds)

    def update(self, flow: dict, is_spike: bool, blur: float) -> bool:
        self.phase_age += 1
        confirmed = False

        if self.state == self.NORMAL:
            if is_spike:
                self.state     = self.SPIKE
                self.phase_age = 0
                self.peak_mag  = flow["magnitude"]

        elif self.state == self.SPIKE:
            self.peak_mag = max(self.peak_mag, flow["magnitude"])
            if flow["down_ratio"] > self.cfg.freefall_down_ratio:
                self.state     = self.FREEFALL
                self.phase_age = 0
            elif self.phase_age > self.cfg.spike_window and not is_spike:
                self.state = self.NORMAL

        elif self.state == self.FREEFALL:
            self.peak_mag = max(self.peak_mag, flow["magnitude"])
            impact_drop   = flow["magnitude"] < self.peak_mag * self.cfg.impact_drop_ratio
            heavy_blur    = blur < self.cfg.blur_threshold
            if impact_drop or heavy_blur:
                self.state     = self.IMPACT
                self.phase_age = 0
                confirmed      = True
            elif self.phase_age > self.cfg.freefall_window:
                self.state = self.NORMAL

        elif self.state == self.IMPACT:
            self.state     = self.COOLDOWN
            self.phase_age = 0

        elif self.state == self.COOLDOWN:
            if self.phase_age > self.cooldown_frames:
                self.state = self.NORMAL

        return confirmed

    @property
    def display_state(self) -> str:
        return self.state


# ── Slow fall — trend detector ─────────────────────────────────────────────────
class SlowFallDetector:
    def __init__(self, cfg: Config, fps: float):
        self.cfg      = cfg
        self.fps      = max(fps, 15.0)
        self.mag_buf  = deque(maxlen=60)
        self.down_buf = deque(maxlen=60)

        self.rising_since    = None
        self.stillness_count = 0
        self.cooldown        = 0
        self.cooldown_frames = int(self.fps * 2.0)

    def update(self, flow: dict, blur: float, frame_idx: int) -> bool:
        self.mag_buf.append(flow["magnitude"])
        self.down_buf.append(flow["down_ratio"])

        if self.cooldown > 0:
            self.cooldown -= 1
            return False

        if len(self.mag_buf) < self.cfg.slow_slope_window:
            return False

        recent    = list(self.mag_buf)[-self.cfg.slow_slope_window:]
        x         = np.arange(len(recent), dtype=float)
        slope     = float(np.polyfit(x, recent, 1)[0])
        mean_down = float(np.mean(list(self.down_buf)[-self.cfg.slow_slope_window:]))

        if flow["magnitude"] < self.cfg.slow_stillness_mag:
            self.stillness_count += 1
        else:
            self.stillness_count = 0

        rising = (slope > self.cfg.slow_slope_threshold and
                  mean_down > self.cfg.slow_down_ratio_mean_min)

        if rising:
            if self.rising_since is None:
                self.rising_since = frame_idx
            return False
        else:
            if (self.rising_since is not None and
                    frame_idx - self.rising_since >= self.cfg.slow_min_buildup_frames and
                    self.stillness_count >= self.cfg.slow_stillness_frames):
                self.rising_since    = None
                self.stillness_count = 0
                self.cooldown        = self.cooldown_frames
                return True
            self.rising_since = None
            return False


# ── Single video processor ─────────────────────────────────────────────────────
class VideoProcessor:
    def __init__(self, cfg: Config):
        self.cfg  = cfg
        self.flow = FlowExtractor(cfg)

    def _open_video(self, video_path: str) -> tuple:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"Cannot open: {video_path}")

        fps   = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or total <= 0:
            logger.warning(f"  Metadata missing — scanning {Path(video_path).name}...")
            count = 0
            while cap.read()[0]:
                count += 1
            cap.release()
            cap   = cv2.VideoCapture(video_path)
            fps   = 30.0
            total = count

        return cap, fps, total

    def _timestamp(self, frame_idx: int, fps: float) -> str:
        secs = frame_idx / fps
        return f"{int(secs // 60):02d}:{int(secs % 60):02d}"

    def _annotate(self, frame, flow, blur, state, mean,
                  thresh, confirmed, fall_type, video_stem) -> np.ndarray:
        out  = frame.copy()
        h, w = out.shape[:2]

        state_colors = {
            "NORMAL":   (100, 200, 100),
            "SPIKE":    (0,   200, 255),
            "FREEFALL": (0,   140, 255),
            "IMPACT":   (0,   0,   255),
            "COOLDOWN": (180, 180, 180),
        }
        col = state_colors.get(state, (255, 255, 255))

        cv2.rectangle(out, (0, 0), (w, 22), (20, 20, 20), -1)
        cv2.putText(
            out,
            f"{video_stem}  |  {state}  mag:{flow['magnitude']:.2f}"
            f"  thr:{thresh:.2f}  down:{flow['down_ratio']:.2f}  blur:{blur:.0f}",
            (6, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1,
        )

        if confirmed:
            label   = "SLOW FALL DETECTED" if fall_type == "slow" else "FALL DETECTED"
            overlay = out.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 180), -1)
            cv2.addWeighted(overlay, 0.2, out, 0.8, 0, out)
            cv2.putText(out, label, (w // 2 - 150, h // 2),
                        cv2.FONT_HERSHEY_DUPLEX, 1.4, (0, 0, 255), 3)

        return out

    def process(self, video_path: str, output_path: str) -> list:
        name = Path(video_path).name
        logger.info(f"\n{'─'*55}")
        logger.info(f"  Processing: {name}")

        # Reset flow state between videos — critical to avoid bleed
        self.flow.reset()

        cap, fps, total = self._open_video(video_path)
        logger.info(f"  {total} frames @ {fps:.1f} fps ({total/fps:.1f}s)")

        fast_det = FastFallDetector(self.cfg, fps)
        slow_det = SlowFallDetector(self.cfg, fps)
        baseline = AdaptiveBaseline(self.cfg.baseline_frames, self.cfg.spike_multiplier)

        out_w, out_h = self.cfg.resize_w, self.cfg.resize_h
        writer = cv2.VideoWriter(
            output_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            max(fps / self.cfg.frame_skip, 1.0),
            (out_w, out_h),
        )

        events:      list = []
        mag_history: list = []
        idx = 0
        t0  = time.time()

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if idx % self.cfg.frame_skip != 0:
                idx += 1
                continue

            frame = cv2.resize(frame, (out_w, out_h))
            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            flow_data           = self.flow.extract(gray)
            blur                = laplacian_variance(gray)
            mean, thresh, spike = baseline.update(flow_data["magnitude"])

            fast_confirmed = fast_det.update(flow_data, spike, blur)
            slow_confirmed = slow_det.update(flow_data, blur, idx)

            confirmed = fast_confirmed or slow_confirmed
            fall_type = ("fast" if fast_confirmed else "slow") if confirmed else None

            mag_history.append(flow_data["magnitude"])
            ts = self._timestamp(idx, fps)

            if confirmed:
                event = {
                    "video":     name,
                    "frame":     idx,
                    "timestamp": ts,
                    "type":      fall_type,
                    "magnitude": round(flow_data["magnitude"], 3),
                    "blur":      round(blur, 1),
                }
                events.append(event)
                logger.warning(
                    f"  🚨 {'SLOW' if slow_confirmed else 'FAST'} FALL @ {ts} "
                    f"(frame {idx})  mag={flow_data['magnitude']:.3f}"
                )

            annotated = self._annotate(
                frame, flow_data, blur,
                fast_det.display_state,
                mean, thresh, confirmed, fall_type,
                Path(video_path).stem,
            )
            writer.write(annotated)
            idx += 1

        cap.release()
        writer.release()

        elapsed = time.time() - t0
        logger.info(f"  Done in {elapsed:.1f}s — {len(events)} fall(s) detected")
        if mag_history:
            logger.info(
                f"  Flow — mean:{np.mean(mag_history):.3f}"
                f"  max:{np.max(mag_history):.3f}"
                f"  std:{np.std(mag_history):.3f}"
            )

        return events


# ── Folder runner ──────────────────────────────────────────────────────────────
class FolderFallDetector:
    def __init__(self, cfg: Config):
        self.cfg       = cfg
        self.processor = VideoProcessor(cfg)

    def _find_videos(self) -> list:
        folder = Path(self.cfg.input_folder)
        if not folder.exists():
            raise FileNotFoundError(f"Input folder not found: {folder}")

        videos = sorted([
            p for p in folder.iterdir()
            if p.is_file() and p.suffix in SUPPORTED_EXTENSIONS
        ])

        if not videos:
            raise FileNotFoundError(
                f"No supported videos found in {folder}\n"
                f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        return videos

    def run(self) -> dict:
        videos  = self._find_videos()
        out_dir = Path(self.cfg.output_folder)
        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"\nFound {len(videos)} video(s) in {self.cfg.input_folder}")
        for i, v in enumerate(videos, 1):
            logger.info(f"  {i}. {v.name}")

        all_events: dict = {}
        total_t0 = time.time()

        for video_path in videos:
            output_path = out_dir / f"{video_path.stem}_annotated.mp4"
            try:
                events = self.processor.process(str(video_path), str(output_path))
                all_events[video_path.name] = events
            except Exception as e:
                logger.error(f"  Failed to process {video_path.name}: {e}")
                all_events[video_path.name] = []

        self._final_summary(all_events, time.time() - total_t0)
        return all_events

    def _final_summary(self, all_events: dict, elapsed: float):
        total_falls = sum(len(v) for v in all_events.values())

        logger.info(f"\n{'='*55}")
        logger.info(f"  COMPLETE — {len(all_events)} video(s) processed in {elapsed:.1f}s")
        logger.info(f"  Total fall events: {total_falls}")
        logger.info(f"{'─'*55}")

        for video_name, events in all_events.items():
            status = f"{len(events)} fall(s)" if events else "no falls detected"
            logger.info(f"  {video_name}: {status}")
            for e in events:
                logger.info(
                    f"    [{e['type'].upper()}] {e['timestamp']}"
                    f"  frame={e['frame']}  mag={e['magnitude']}"
                )

        logger.info(f"\n  Annotated videos saved to: {cfg.output_folder}")
        logger.info(f"{'='*55}")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    detector = FolderFallDetector(cfg)
    results  = detector.run()