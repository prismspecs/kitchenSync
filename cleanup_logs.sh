#!/bin/bash
# KitchenSync Log Cleanup Script
# Archives current logs and starts fresh, keeping last 1000 lines of history

echo "🧹 KitchenSync Log Cleanup Starting..."

# Function to archive logs with rotation (max 1000 lines per archive)
archive_log() {
    local current_log="$1"
    local archive_log="$2"
    local max_lines=1000
    
    if [[ -f "$current_log" ]]; then
        local current_size=$(du -h "$current_log" | cut -f1)
        echo "📁 Archiving $current_log ($current_size) -> $archive_log"
        
        # If archive exists, combine current + archive, keep only last 1000 lines
        if [[ -f "$archive_log" ]]; then
            # Append current log to archive, then keep only last 1000 lines
            cat "$current_log" >> "$archive_log"
            tail -n "$max_lines" "$archive_log" > "${archive_log}.tmp"
            mv "${archive_log}.tmp" "$archive_log"
        else
            # First time: just move current to archive (but limit to 1000 lines)
            tail -n "$max_lines" "$current_log" > "$archive_log"
        fi
        
        # Remove current log to start fresh
        rm "$current_log"
        local archived_lines=$(wc -l < "$archive_log" 2>/dev/null || echo "0")
        echo "✅ Archived $archived_lines lines to $archive_log"
    else
        echo "⚠️  $current_log not found, skipping"
    fi
}

echo ""
echo "📊 Current log file sizes:"
ls -lah /tmp/kitchensync*.log 2>/dev/null || echo "No current log files found"

echo ""
echo "🔄 Archiving logs..."

# Archive each log type (system, VLC, debug, stderr/stdout)
archive_log "/tmp/kitchensync_system.log" "/tmp/kitchensync_system_archive.log"
archive_log "/tmp/kitchensync_vlc.log" "/tmp/kitchensync_vlc_archive.log"
archive_log "/tmp/kitchensync_leader_debug.txt" "/tmp/kitchensync_debug_archive.log"
archive_log "/tmp/kitchensync_vlc_stderr.log" "/tmp/kitchensync_vlc_stderr_archive.log"
archive_log "/tmp/kitchensync_vlc_stdout.log" "/tmp/kitchensync_vlc_stdout_archive.log"

echo ""
echo "📚 Archive file status:"
ls -lah /tmp/kitchensync*_archive.log 2>/dev/null || echo "No archive files found"

echo ""
echo "✨ Log cleanup complete! Fresh logs will be created on next run."
echo ""
echo "💡 To view archived logs:"
echo "   System:  tail -50 /tmp/kitchensync_system_archive.log"
echo "   VLC:     tail -50 /tmp/kitchensync_vlc_archive.log"
echo "   Debug:   tail -50 /tmp/kitchensync_debug_archive.log"
