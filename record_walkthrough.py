import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

def get_downloads_folder():
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Downloads"
    return Path(os.path.expanduser("~")) / "Downloads"

def log(step_num, message):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [STEP {step_num}] {message}", flush=True)

def record_walkthrough():
    downloads_folder = get_downloads_folder()
    downloads_folder.mkdir(parents=True, exist_ok=True)
    target_video_path = downloads_folder / "AegisFlow_Demo.webm"

    temp_video_dir = Path("c:/Users/Vraj/OneDrive/Desktop/hack/temp_recording")
    if temp_video_dir.exists():
        shutil.rmtree(temp_video_dir, ignore_errors=True)
    temp_video_dir.mkdir(parents=True, exist_ok=True)

    log(0, f"Target output: {target_video_path}")
    log(0, f"Temporary recording dir: {temp_video_dir}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--hide-scrollbars"
            ]
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(temp_video_dir),
            record_video_size={"width": 1920, "height": 1080},
            user_agent="AegisFlowDemoAgent/1.0"
        )

        page = context.new_page()

        try:
            # Reset any previous in-memory patches on the backend before starting
            try:
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:8000/api/reset-patches", method="POST")
                urllib.request.urlopen(req, timeout=5)
                log(0, "Backend in-memory patches reset for a clean baseline.")
            except Exception as e:
                log("WARN", f"Could not reset backend patches: {e}")

            # STEP 1: Navigate to https://aegisflow-ps01.web.app
            log(1, "Navigating to https://aegisflow-ps01.web.app ...")
            page.goto("https://aegisflow-ps01.web.app", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#btn-run-pipeline", timeout=15000)
            page.wait_for_selector("[id^='node-card-']", timeout=15000)
            log(1, "Page DOM loaded successfully.")

            # STEP 2: Wait 2-3 seconds on initial load — let header/LIVE STREAM badge and dashboard render fully
            log(2, "Pausing 3s for header, live stream badge, and dashboard to fully settle...")
            time.sleep(3.0)

            # STEP 3: Pause 2 seconds on the empty/idle pipeline state strip (all 5 nodes gray)
            log(3, "Pausing 2s on empty/idle pipeline state strip (all 5 nodes idle/gray)...")
            nodes = page.locator("[id^='node-card-']")
            node_count = nodes.count()
            log(3, f"Detected {node_count} pipeline nodes.")
            time.sleep(2.0)

            # STEP 4: Click the "Clean Baseline" scenario card
            log(4, "Selecting 'Clean Baseline' scenario card (#scenario-btn-none)...")
            clean_btn = page.locator("#scenario-btn-none")
            clean_btn.scroll_into_view_if_needed()
            clean_btn.click()
            time.sleep(1.5)

            # STEP 5: Click "Execute Pipeline"
            log(5, "Clicking 'Execute Pipeline' (#btn-run-pipeline)...")
            run_btn = page.locator("#btn-run-pipeline")
            run_btn.click()
            time.sleep(1.0)  # Allow React state to set isRunning=True

            # STEP 6: Wait for run to complete (poll for DONE/success state)
            log(6, "Waiting for Clean Baseline run to complete...")
            page.wait_for_selector("#btn-run-pipeline:not([disabled])", timeout=25000)
            # Verify node_load is successful
            page.wait_for_selector("#node-card-node_load .status-success", timeout=5000)
            log(6, "Clean Baseline execution finished successfully.")

            # STEP 7: Pause 2 seconds on completed green state
            log(7, "Pausing 2s on completed green baseline state...")
            time.sleep(2.0)

            # STEP 8: Click the "Schema Drift" scenario card
            log(8, "Selecting 'Schema Drift' scenario card (#scenario-btn-schema_drift)...")
            drift_btn = page.locator("#scenario-btn-schema_drift")
            drift_btn.scroll_into_view_if_needed()
            drift_btn.click()
            time.sleep(1.5)

            # STEP 9: Click "Execute Pipeline"
            log(9, "Clicking 'Execute Pipeline' (#btn-run-pipeline) to inject Schema Drift...")
            run_btn.click()
            time.sleep(1.0)  # Allow React state to set isRunning=True

            # STEP 10: Wait through full failure -> heal -> success cycle
            log(10, "Observing failure -> heal -> success cycle (Red -> Yellow -> Purple -> Green)...")
            start_drift_time = time.time()
            page.wait_for_selector("#btn-run-pipeline:not([disabled])", timeout=45000)
            elapsed = time.time() - start_drift_time
            log(10, f"Schema Drift self-healing cycle completed in {elapsed:.2f}s.")

            # STEP 11: Pause 2-3 seconds so patch diff viewer is clearly visible and readable
            log(11, "Smoothly scrolling to show synthesized patch diff viewer and pausing 3s...")
            page.evaluate("window.scrollBy({ top: 240, behavior: 'smooth' })")
            time.sleep(3.0)

            # STEP 12: Scroll down to show Event Log with diagnosis text visible. Pause 2 seconds.
            log(12, "Viewing Event Log and diagnosis text. Pausing 2.5s...")
            page.evaluate("window.scrollBy({ top: 160, behavior: 'smooth' })")
            time.sleep(2.5)

            # STEP 13: Click the "Corrupt Timestamps" scenario card
            log(13, "Scrolling up to scenario cards and selecting 'Corrupt Timestamps'...")
            page.evaluate("window.scrollTo({ top: 220, behavior: 'smooth' })")
            time.sleep(1.0)
            corrupt_btn = page.locator("#scenario-btn-corrupt_timestamp")
            corrupt_btn.scroll_into_view_if_needed()
            corrupt_btn.click()
            time.sleep(1.5)

            # STEP 14: Click "Execute Pipeline"
            log(14, "Clicking 'Execute Pipeline' (#btn-run-pipeline) for Corrupt Timestamps...")
            run_btn.scroll_into_view_if_needed()
            run_btn.click()
            time.sleep(1.0)  # Allow React state to set isRunning=True

            # STEP 15: Wait for completion, pause 2 seconds on result
            log(15, "Waiting for Corrupt Timestamps execution to complete...")
            start_corrupt_time = time.time()
            page.wait_for_selector("#btn-run-pipeline:not([disabled])", timeout=45000)
            elapsed_corrupt = time.time() - start_corrupt_time
            log(15, f"Corrupt Timestamps completed in {elapsed_corrupt:.2f}s. Pausing 2s on result...")
            time.sleep(2.0)

            # STEP 16: Scroll to Metrics Panel (Autonomous Recovery Rate, MTTR, Active Patches, Engineer Time Saved) and pause 3 seconds
            log(16, "Scrolling to Metrics Panel at the top and pausing 3s for live numbers...")
            page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
            time.sleep(3.0)

            # STEP 17: End recording on final metrics view, held for 2 seconds before stopping
            log(17, "Holding final metrics view for 2s before concluding recording...")
            time.sleep(2.0)

            log(17, "Walkthrough sequence completed successfully!")

        except Exception as e:
            log("FAIL", f"Walkthrough failed during execution: {e}")
            raise e
        finally:
            log("FINISH", "Closing browser context to finalize video encoding...")
            context.close()
            browser.close()

    # Find the recorded video file
    video_files = list(temp_video_dir.glob("*.webm"))
    if not video_files:
        raise RuntimeError("No video file found in recording directory!")

    source_video = video_files[0]
    log("SAVE", f"Found recorded video: {source_video} ({source_video.stat().st_size} bytes)")

    if target_video_path.exists():
        target_video_path.unlink()

    shutil.copy2(source_video, target_video_path)
    log("SAVE", f"Copied video to: {target_video_path}")

    # Clean up temp directory
    shutil.rmtree(temp_video_dir, ignore_errors=True)

    # Check file existence and get size
    if not target_video_path.exists():
        raise RuntimeError(f"Failed to save video to {target_video_path}")

    file_size_bytes = target_video_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)

    # Transcode to universal MP4 format (H.264 / YUV420p) for native Windows Media Player support
    target_mp4_path = downloads_folder / "AegisFlow_Demo.mp4"
    mp4_generated = False
    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        log("CONVERT", f"Transcoding to universal Windows-compatible MP4 (H.264)...")
        convert_res = subprocess.run(
            [
                ffmpeg_bin, "-y",
                "-i", str(target_video_path),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "22",
                str(target_mp4_path)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if convert_res.returncode == 0 and target_mp4_path.exists():
            mp4_generated = True
            log("CONVERT", f"Universal MP4 successfully generated: {target_mp4_path}")
    except Exception as e:
        log("WARN", f"Could not transcode to MP4: {e}")

    # Probe duration with ffmpeg if available
    duration_str = "Unknown"
    ffmpeg_exe = Path("C:/Users/Vraj/AppData/Local/ms-playwright/ffmpeg-1011/ffmpeg-win64.exe")
    if ffmpeg_exe.exists():
        try:
            result = subprocess.run(
                [str(ffmpeg_exe), "-i", str(target_video_path)],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )
            for line in result.stderr.splitlines():
                if "Duration:" in line:
                    duration_str = line.split("Duration:")[1].split(",")[0].strip()
                    break
        except Exception as e:
            log("WARN", f"Could not inspect duration with ffmpeg: {e}")

    print("\n=======================================================", flush=True)
    print(" AegisFlow Walkthrough Video Recording COMPLETE! ", flush=True)
    print("=======================================================", flush=True)
    if mp4_generated:
        mp4_size_mb = target_mp4_path.stat().st_size / (1024 * 1024)
        print(f"MP4 File (Universal): {target_mp4_path} ({mp4_size_mb:.2f} MB)", flush=True)
    print(f"WebM File:            {target_video_path} ({file_size_mb:.2f} MB)", flush=True)
    print(f"Duration:             {duration_str}", flush=True)
    print("=======================================================\n", flush=True)

if __name__ == "__main__":
    record_walkthrough()
