#!/usr/bin/env bash
set -euo pipefail

mkdir -p video/.render

render_segment() {
  local source="$1"
  local duration="$2"
  local frames="$3"
  local output="$4"

  ffmpeg -y -loglevel error -loop 1 -i "$source" -t "$duration" \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,zoompan=z='min(zoom+0.00008,1.025)':d=${frames}:s=1920x1080:fps=30" \
    -an -c:v libx264 -preset veryfast -crf 22 -pix_fmt yuv420p -r 30 "$output"
}

render_segment "frontend/public/relay-og.png" 22 660 \
  "video/.render/segment-01.mp4"
render_segment "outputs/relay-landing-preview.png" 28 840 \
  "video/.render/segment-02.mp4"
render_segment "outputs/relay-preview.png" 30 900 \
  "video/.render/segment-03.mp4"
render_segment "outputs/relay-landing-preview.png" 35 1050 \
  "video/.render/segment-04.mp4"
render_segment "outputs/relay-preview.png" 30 900 \
  "video/.render/segment-05.mp4"
render_segment "frontend/public/relay-og.png" 25 750 \
  "video/.render/segment-06.mp4"

ffmpeg -y -loglevel error -f concat -safe 0 -i video/concat.txt \
  -c copy video/.render/slides.mp4
ffmpeg -y -loglevel error -i video/.render/slides.mp4 -i video/narration.aiff \
  -c:v copy -c:a aac -b:a 160k -shortest -movflags +faststart \
  video/relay-demo.mp4

ffprobe -v error -show_entries format=duration,size \
  -of default=noprint_wrappers=1 video/relay-demo.mp4
