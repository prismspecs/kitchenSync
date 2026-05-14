const requestedConfigs = new Set();

async function postJson(path, payload) {
    const response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
    });
    if (response.status === 204) {
        return null;
    }
    return response.json();
}

async function playCluster() {
    await fetch('/api/play', { method: 'POST' });
    document.getElementById('preview').play().catch(() => {});
}

async function stopCluster() {
    await fetch('/api/stop', { method: 'POST' });
    const preview = document.getElementById('preview');
    preview.pause();
    preview.currentTime = 0;
}

async function changeVideo(filename) {
    await fetch('/api/video?file=' + encodeURIComponent(filename), { method: 'POST' });
    const preview = document.getElementById('preview');
    preview.src = '/video_file?t=' + Date.now();
    preview.load();
}

async function seekCluster(seconds) {
    await postJson('/api/seek', { value: seconds });
}

async function requestConfig(deviceId) {
    requestedConfigs.add(deviceId);
    await postJson('/api/config/request', { device_id: deviceId });
}

function renderField(deviceId, field, value, videoOptions) {
    const fieldId = `${deviceId}-${field.key}`;
    const tooltip = field.tooltip ? `<span class="tooltip-icon" data-tooltip="${field.tooltip}">?</span>` : '';
    
    if (field.type === 'bool') {
        return `
            <div class="row">
                <label for="${fieldId}">${field.label}${tooltip}</label>
                <input id="${fieldId}" data-key="${field.key}" type="checkbox" ${value ? 'checked' : ''}>
            </div>
        `;
    }

    const type = field.type === 'int' || field.type === 'float' ? 'number' : 'text';
    const step = field.type === 'float' ? 'step="any"' : '';
    const list = field.key === 'video_file' && videoOptions.length ? 'list="videoSuggestions"' : '';
    return `
        <div class="row">
            <label for="${fieldId}">${field.label}${tooltip}</label>
            <input id="${fieldId}" data-key="${field.key}" type="${type}" value="${value ?? ''}" ${step} ${list}>
        </div>
    `;
}

function renderMessage(message) {
    if (!message) {
        return '';
    }
    if (message.error) {
        return `<div class="message error">${message.error}</div>`;
    }
    if (message.requires_restart) {
        return '<div class="message ok">Saved. Restart may be required for video or MIDI changes.</div>';
    }
    return '<div class="message ok">Saved.</div>';
}

function renderConfigCell(device, videoOptions) {
    const config = device.config;
    if (!config) {
        if (device.role === 'collaborator' && !requestedConfigs.has(device.device_id)) {
            requestConfig(device.device_id);
        }
        return `
            <button onclick="requestConfig('${device.device_id}')">Load config</button>
            ${renderMessage(device.message)}
        `;
    }

    const fields = config.fields.map((field) => renderField(device.device_id, field, config.values?.[field.key], videoOptions)).join('');
    return `
        <form onsubmit="saveConfig(event, '${device.device_id}', '${config.role}')">
            ${fields}
            <div class="row">
                <button type="submit">Save</button>
                ${device.role === 'collaborator' ? `<button type="button" onclick="requestConfig('${device.device_id}')">Refresh</button>` : ''}
            </div>
            ${renderMessage(device.message)}
        </form>
    `;
}

function renderState(state) {
    const selector = document.getElementById('videoSelector');
    if (selector && document.activeElement !== selector) {
        selector.innerHTML = (state.available_videos || []).map((video) => `
            <option value="${video}" ${video === state.current_video ? 'selected' : ''}>${video}</option>
        `).join('');
        selector.onchange = () => changeVideo(selector.value);
    }

    const suggestions = document.getElementById('videoSuggestions');
    if (suggestions) {
        suggestions.innerHTML = (state.available_videos || []).map((video) => `
            <option value="${video}"></option>
        `).join('');
    }

    const clusterStatus = document.getElementById('clusterStatus');
    if (clusterStatus) {
        clusterStatus.textContent =
            `Status: ${state.status} | Time: ${state.video_pos.toFixed(2)}s | Duration: ${state.duration.toFixed(2)}s | Video: ${state.current_video}`;
    }

    const rows = document.getElementById('deviceRows');
    if (rows) {
        // We update the table cell by cell to avoid clobbering focused inputs
        state.devices.forEach((device) => {
            let row = document.getElementById(`row-${device.device_id}`);
            if (!row) {
                // Create row if it doesn't exist
                row = document.createElement('tr');
                row.id = `row-${device.device_id}`;
                row.innerHTML = '<td></td><td></td><td></td><td></td><td class="config-cell"></td>';
                rows.appendChild(row);
            }

            const cells = row.cells;
            cells[0].textContent = device.label;
            cells[1].textContent = device.role;
            cells[2].textContent = device.ip;
            cells[3].textContent = device.status;

            const configCell = cells[4];
            // Only update the config cell if no input inside it has focus
            const hasFocus = configCell.contains(document.activeElement);
            if (!hasFocus) {
                configCell.innerHTML = renderConfigCell(device, state.available_videos || []);
            }
        });

        // Remove rows for devices that are no longer in the state
        const activeIds = new Set(state.devices.map(d => `row-${d.device_id}`));
        Array.from(rows.children).forEach(row => {
            if (!activeIds.has(row.id)) {
                rows.removeChild(row);
            }
        });
    }
}

async function saveConfig(event, deviceId, role) {
    event.preventDefault();
    const form = event.currentTarget;
    const updates = {};
    form.querySelectorAll('[data-key]').forEach((input) => {
        if (input.type === 'checkbox') {
            updates[input.dataset.key] = input.checked;
        } else if (input.type === 'number') {
            updates[input.dataset.key] = input.value === '' ? '' : Number(input.value);
        } else {
            updates[input.dataset.key] = input.value;
        }
    });
    await postJson('/api/config/save', { device_id: deviceId, role, updates });
    await refresh();
}

async function refresh() {
    try {
        const response = await fetch('/api/state');
        const state = await response.json();
        renderState(state);
    } catch (err) {
        console.error("Refresh failed", err);
    }
}

refresh();
setInterval(refresh, 2000); // Relaxed refresh rate slightly

// Initialize seek event listener for preview video
document.addEventListener('DOMContentLoaded', () => {
    const preview = document.getElementById('preview');
    if (preview) {
        preview.addEventListener('seeked', () => {
            // Only seek cluster if we are the master (playing)
            seekCluster(preview.currentTime);
        });
    }
});
