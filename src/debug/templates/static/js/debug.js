/* KitchenSync Debug Overlay JavaScript */

// Auto-refresh configuration
const REFRESH_INTERVAL = 5000; // 5 seconds

// Auto-refresh function with improved reliability and error handling
function startAutoRefresh() {
    let refreshCount = 0;
    let errorCount = 0;
    const maxRefreshes = 1000; // Prevent infinite refreshes
    const maxErrors = 5; // Stop auto-refresh after too many errors

    function doRefresh() {
        try {
            refreshCount++;

            // Update refresh status
            const statusElement = document.getElementById('refresh-status');
            if (statusElement) {
                statusElement.textContent = `Active (${refreshCount})`;
            }

            // Log refresh attempt
            console.log(`Auto-refresh #${refreshCount}`);

            // Check if we've hit the max refresh limit
            if (refreshCount >= maxRefreshes) {
                console.warn('Max refreshes reached, stopping auto-refresh');
                clearInterval(window.kitchenSyncRefreshInterval);
                return;
            }

            // Check for too many errors
            if (errorCount >= maxErrors) {
                console.error('Too many refresh errors, stopping auto-refresh');
                clearInterval(window.kitchenSyncRefreshInterval);
                return;
            }

            // Perform the refresh with timeout protection
            setTimeout(() => {
                try {
                    window.location.reload(true); // Force reload from server
                } catch (reloadError) {
                    errorCount++;
                    console.error(`Reload error #${errorCount}: ${reloadError.message}`);
                }
            }, 100);

        } catch (error) {
            errorCount++;
            console.error(`Refresh error #${errorCount}: ${error.message}`);
        }
    }

    // Start the refresh interval
    const refreshInterval = setInterval(doRefresh, REFRESH_INTERVAL);

    // Store the interval ID for potential cleanup
    window.kitchenSyncRefreshInterval = refreshInterval;

    console.log('Auto-refresh started');
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

    // Disable auto-refresh to prevent conflicts with Python backend updates
    // The Python HTMLDebugManager handles updates every 5 seconds
    console.log('Auto-refresh disabled - using Python backend updates');

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
