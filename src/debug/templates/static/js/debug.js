/* KitchenSync Debug Overlay JavaScript */

// Auto-refresh configuration
const REFRESH_INTERVAL = 5000; // 5 seconds

// Auto-refresh function with improved reliability
function startAutoRefresh() {
    let refreshCount = 0;
    const maxRefreshes = 1000; // Prevent infinite refreshes

    function doRefresh() {
        try {
            refreshCount++;

            // Update refresh status
            const statusElement = document.getElementById('refresh-status');
            if (statusElement) {
                statusElement.textContent = `Active (${refreshCount})`;
            }

            // Log refresh attempt
            DebugOverlay.log(`Auto-refresh #${refreshCount}`, 'debug');

            // Check if we've hit the max refresh limit
            if (refreshCount >= maxRefreshes) {
                DebugOverlay.log('Max refreshes reached, stopping auto-refresh', 'warn');
                return;
            }

            // Perform the refresh
            window.location.reload(true); // Force reload from server

        } catch (error) {
            DebugOverlay.log(`Refresh error: ${error.message}`, 'error');
        }
    }

    // Start the refresh interval
    const refreshInterval = setInterval(doRefresh, REFRESH_INTERVAL);

    // Store the interval ID for potential cleanup
    window.kitchenSyncRefreshInterval = refreshInterval;

    DebugOverlay.log('Auto-refresh started', 'info');
}

// Update timestamp on page load
function updateTimestamp() {
    const timestampElement = document.getElementById('last-refresh');
    if (timestampElement) {
        timestampElement.textContent = new Date().toLocaleString();
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    // Update timestamp
    updateTimestamp();

    // Start auto-refresh
    startAutoRefresh();

    // Add manual refresh button handler
    const refreshButton = document.querySelector('.refresh-button');
    if (refreshButton) {
        refreshButton.addEventListener('click', function () {
            location.reload();
        });
    }

    console.log('KitchenSync Debug Overlay initialized');
});

// Utility functions for future enhancements
const DebugOverlay = {

    // Format time in MM:SS format
    formatTime: function (seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    },

    // Format MIDI note names
    formatMidiNote: function (noteNumber) {
        const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        const octave = Math.floor(noteNumber / 12) - 1;
        const noteName = noteNames[noteNumber % 12];
        return `${noteName}${octave}`;
    },

    // Update status indicator
    updateStatus: function (elementId, status, className) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = status;
            element.className = className;
        }
    },

    // Log debug information to console
    log: function (message, level = 'info') {
        const timestamp = new Date().toISOString();
        console[level](`[${timestamp}] KitchenSync Debug: ${message}`);
    }
};

// Export for potential future module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DebugOverlay;
}
