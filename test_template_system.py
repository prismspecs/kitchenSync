#!/usr/bin/env python3
"""
Test script for the new template system
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from debug.template_engine import DebugTemplateManager


def test_template_system():
    """Test the template system with sample data"""
    print("Testing KitchenSync Debug Template System...")
    
    # Initialize template manager
    template_dir = Path("src/debug/templates")
    template_manager = DebugTemplateManager(str(template_dir))
    
    # Sample system info
    system_info = {
        'service_status': 'Active (running)',
        'service_status_class': 'good',
        'service_pid': '12345',
        'service_uptime': '2:15:30',
        'vlc_status': 'Running (embedded in PID: 12345)',
        'vlc_status_class': 'good',
        'video_file': 'test_video.mp4',
        'video_current_time': 45.7,
        'video_total_time': 180.0,
        'video_position': 0.254,
        'video_state': 'playing',
        'video_loop_count': 2,
        'midi_loop_count': 1,
        'looping_enabled': True,
        'midi_recent': [
            {'type': 'note_on', 'time': 40.5, 'note': 60, 'channel': 1, 'velocity': 127},
            {'type': 'note_off', 'time': 41.0, 'note': 60, 'channel': 1},
        ],
        'midi_upcoming': [
            {'type': 'note_on', 'time': 50.0, 'note': 64, 'channel': 1, 'velocity': 100},
            {'type': 'control_change', 'time': 55.0, 'control': 7, 'value': 127, 'channel': 1},
        ],
        'recent_logs': 'System started successfully\\nVideo playback initialized\\nMIDI scheduler active',
        'vlc_logs': 'VLC initialized\\nVideo loaded: test_video.mp4\\nPlayback started',
    }
    
    # Test rendering
    try:
        html_file = template_manager.render_debug_overlay("test-pi", system_info)
        
        if html_file and os.path.exists(html_file):
            print(f"✅ Template system test successful!")
            print(f"📄 Generated HTML file: {html_file}")
            
            # Check if static files were copied
            html_dir = Path(html_file).parent
            css_file = html_dir / "static" / "css" / "debug.css"
            js_file = html_dir / "static" / "js" / "debug.js"
            
            if css_file.exists():
                print(f"✅ CSS file copied: {css_file}")
            else:
                print(f"❌ CSS file missing: {css_file}")
                
            if js_file.exists():
                print(f"✅ JS file copied: {js_file}")
            else:
                print(f"❌ JS file missing: {js_file}")
            
            # Show file size
            file_size = os.path.getsize(html_file)
            print(f"📊 Generated HTML size: {file_size} bytes")
            
            # Show first few lines of generated HTML
            print("\\n📝 Generated HTML preview:")
            with open(html_file, 'r') as f:
                lines = f.readlines()[:10]
                for i, line in enumerate(lines, 1):
                    print(f"  {i:2d}: {line.rstrip()}")
            
            print(f"\\n🌐 To view in browser, open: file://{html_file}")
            return True
            
        else:
            print(f"❌ Template rendering failed - no output file")
            return False
            
    except Exception as e:
        print(f"❌ Template system test failed: {e}")
        return False


if __name__ == "__main__":
    success = test_template_system()
    sys.exit(0 if success else 1)
