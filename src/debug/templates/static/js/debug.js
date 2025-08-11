/* KitchenSync Debug Overlay JavaScript */

// Auto-refresh configuration
const REFRESH_INTERVAL = 5000; // 5 seconds

// Auto-refresh function
function startAutoRefresh() {
    setInterval(function() {
        location.reload();
    }, REFRESH_INTERVAL);
}

// Update timestamp on page load
function updateTimestamp() {
    const timestampElement = document.getElementById('last-refresh');
    if (timestampElement) {
        timestampElement.textContent = new Date().toLocaleString();
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Update timestamp
    updateTimestamp();
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Add manual refresh button handler
    const refreshButton = document.querySelector('.refresh-button');
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            location.reload();
        });
    }
    
    console.log('KitchenSync Debug Overlay initialized');
});

// Utility functions for future enhancements
const DebugOverlay = {
    
    // Format time in MM:SS format
    formatTime: function(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    },
    
    // Format MIDI note names
    formatMidiNote: function(noteNumber) {
        const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        const octave = Math.floor(noteNumber / 12) - 1;
        const noteName = noteNames[noteNumber % 12];
        return `${noteName}${octave}`;
    },
    
    // Update status indicator
    updateStatus: function(elementId, status, className) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = status;
            element.className = className;
        }
    },
    
    // Log debug information to console
    log: function(message, level = 'info') {
        const timestamp = new Date().toISOString();
        console[level](`[${timestamp}] KitchenSync Debug: ${message}`);
    }
};

// Export for potential future module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DebugOverlay;
}
