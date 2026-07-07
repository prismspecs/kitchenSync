#!/usr/bin/env python3
"""Generate a definitive sync test video with numbered seconds for kSync.

Creates a video with 1-second intervals, labeled with large numbers, cycling
background colors, and a sweeping position bar for visual sync inspection
across multiple displays.

Output is HEVC (H.265) optimized for Raspberry Pi 5 hardware decoding.

Usage:
    python3 tools/generate_sync_video.py -o media/sync_test_definitive.mp4 -d 30
"""

import argparse
import os
import subprocess
import tempfile

COLORS = [
    (0xFF, 0x00, 0x00),  # Red
    (0x00, 0xFF, 0x00),  # Lime
    (0x00, 0x00, 0xFF),  # Blue
    (0xFF, 0xFF, 0x00),  # Yellow
    (0xFF, 0x00, 0xFF),  # Magenta
    (0x00, 0xFF, 0xFF),  # Cyan
    (0xFF, 0xFF, 0xFF),  # White
    (0xFF, 0x88, 0x00),  # Orange
    (0xFF, 0x69, 0xB4),  # Hot Pink
    (0x88, 0x00, 0xFF),  # Purple
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a definitive sync test video for kSync"
    )
    parser.add_argument(
        "-o", "--output", default="sync_test_definitive.mp4",
        help="Output file path (default: sync_test_definitive.mp4)"
    )
    parser.add_argument(
        "-d", "--duration", type=int, default=30,
        help="Duration in seconds (default: 30)"
    )
    parser.add_argument(
        "-f", "--fps", type=int, default=30,
        help="Frame rate (default: 30)"
    )
    parser.add_argument(
        "-W", "--width", type=int, default=1920,
        help="Video width (default: 1920)"
    )
    parser.add_argument(
        "-H", "--height", type=int, default=1080,
        help="Video height (default: 1080)"
    )
    parser.add_argument(
        "--codec", default="libx265",
        help="Video encoder (default: libx265)"
    )
    parser.add_argument(
        "--preset", default="medium",
        help="Encoder preset (default: medium)"
    )
    parser.add_argument(
        "--pix-fmt", default="yuv420p",
        help="Pixel format (default: yuv420p)"
    )
    parser.add_argument(
        "--keep-temp", action="store_true",
        help="Keep temporary segment files"
    )
    return parser.parse_args()


def build_drawtext_filters(i, width, height):
    font_size = max(48, width // 10)
    sub_size = max(16, width // 20)
    bar_w = max(20, width // 40)
    bar_h = max(8, height // 72)

    return (
        f"drawtext=text='{i}':"
        f"fontsize={font_size}:fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"box=1:boxcolor=black@0.4:boxborderw={max(10, font_size//10)},"
        f"drawtext=text='{i}s':"
        f"fontsize={sub_size}:fontcolor=white:"
        f"x=w-text_w-40:y=h-text_h-40:"
        f"box=1:boxcolor=black@0.3:boxborderw={max(5, sub_size//10)},"
        f"drawtext=text='%{{n}}':"
        f"fontsize={max(10, sub_size//2)}:fontcolor=white@0.6:"
        f"x=40:y=40:"
        f"box=1:boxcolor=black@0.2:boxborderw=4,"
        f"drawbox='(t-trunc(t))*w':{bar_h + 10}:{bar_w}:{bar_h}:color=white@0.85"
    )


def generate_segment(i, args, tmpdir):
    r, g, b = COLORS[i % len(COLORS)]
    seg_file = os.path.join(tmpdir, f"seg_{i:03d}.ts")
    color_hex = f"#%02x%02x%02x" % (r, g, b)

    filter_str = build_drawtext_filters(i, args.width, args.height)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        f"color=c={color_hex}:s={args.width}x{args.height}:d=1:r={args.fps}",
        "-vf", filter_str,
        "-c:v", args.codec,
        "-preset", args.preset,
    ]

    if args.codec == "libx265":
        cmd += ["-x265-params", "keyint=30:no-scenecut=1"]

    cmd += ["-pix_fmt", args.pix_fmt, seg_file]

    subprocess.run(cmd, check=True, capture_output=True)
    return seg_file


def main():
    args = parse_args()

    tmpdir = tempfile.mkdtemp(prefix="ksync_sync_")
    segments = []

    total = args.duration
    print(f"Generating {total}s sync test video...", flush=True)

    for i in range(total):
        seg = generate_segment(i, args, tmpdir)
        segments.append(seg)

        if (i + 1) % 10 == 0 or i == total - 1:
            print(f"  {i+1}/{total} seconds", flush=True)

    concat_file = os.path.join(tmpdir, "concat.txt")
    with open(concat_file, "w") as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")

    print("Concatenating...", flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        "-fflags", "+genpts",
        args.output,
    ], check=True)

    if not args.keep_temp:
        for seg in segments:
            os.unlink(seg)
        os.unlink(concat_file)
        os.rmdir(tmpdir)

    size_mb = os.path.getsize(args.output) / (1024 * 1024)
    print(f"\nDone: {args.output}")
    print(f"  Resolution: {args.width}x{args.height}")
    print(f"  Duration:   {args.duration}s @ {args.fps}fps")
    print(f"  Codec:      {args.codec}")
    print(f"  Size:       {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
