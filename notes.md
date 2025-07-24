Generating videos with error messages....

ffmpeg -f lavfi -i color=c=black:s=1920x1080:r=15 -t 5 -filter_complex "\
noise=alls=80:allf=t+u,hue=h=t*150:s=3,eq=contrast=1.5:brightness=0.1:saturation=2,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='KitchenSync':fontcolor=white:fontsize=100:x=(w-text_w)/2:y=(h-text_h)/2" \
-c:v libx264 -crf 28 -preset veryfast kitchen_sync_noise.mp4

# restart app - improved version

# Kill any running KitchenSync processes
pkill -f kitchensync
pkill -f leader.py
pkill -f collaborator.py

# Kill VLC processes that might be hanging
pkill vlc

# Clean up any debug terminals and pygame windows
pkill -f "KitchenSync Debug"
pkill -f pygame

# Clean up any leftover debug pipes
rm -f /tmp/kitchensync_debug

# Wait a moment for cleanup
sleep 2

# Restart manually
cd /home/grayson/workbench/kitchenSync
python3 kitchensync.py