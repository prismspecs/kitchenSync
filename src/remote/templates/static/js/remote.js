const requestedConfigs = new Set();
const lastSaveAt = new Map();

async function postJson(path, payload) {
    const response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
    });
    if (response.status === 204) return null;
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
    if (filename === currentPreviewVideo) return;
    await fetch('/api/video?file=' + encodeURIComponent(filename), { method: 'POST' });
    currentPreviewVideo = filename;
    const preview = document.getElementById('preview');
    if (preview) {
        preview.src = '/video_file?t=' + Date.now();
        preview.load();
    }
}

async function seekCluster(seconds) {
    await postJson('/api/seek', { value: seconds });
}

async function requestConfig(deviceId) {
    requestedConfigs.add(deviceId);
    await postJson('/api/config/request', { device_id: deviceId });
}

function renderField(deviceId, field, value, videoOptions, scheduleOptions) {
    const fieldId = `${deviceId}-${field.key}`;
    const tooltip = field.tooltip ? `<span class="tooltip-icon" title="${field.tooltip}">?</span>` : '';
    
    if (field.type === 'bool') {
        return `
            <div class="row">
                <label for="${fieldId}">${field.label}${tooltip}</label>
                <input id="${fieldId}" data-key="${field.key}" type="checkbox" ${value ? 'checked' : ''}>
            </div>
        `;
    }

    const type = (field.type === 'int' || field.type === 'float') ? 'number' : 'text';
    const step = field.type === 'float' ? 'step="any"' : '';
    let list = '';
    if (field.key === 'video_file' && videoOptions.length) list = 'list="videoSuggestions"';
    else if (field.key === 'schedule_file' && scheduleOptions.length) list = 'list="scheduleSuggestions"';

    return `
        <div class="row">
            <label for="${fieldId}">${field.label}${tooltip}</label>
            <input id="${fieldId}" data-key="${field.key}" type="${type}" value="${value ?? ''}" ${step} ${list}>
        </div>
    `;
}

function renderMessage(message) {
    if (!message) return '';
    const cls = message.error ? 'error' : 'ok';
    const text = message.error || (message.requires_restart ? 'Saved. Restart required.' : 'Saved.');
    return `<div class="message ${cls}">${text}</div>`;
}

function renderConfigArea(device, videoOptions, scheduleOptions) {
    const config = device.config;
    if (!config) {
        if (device.role === 'collaborator' && !requestedConfigs.has(device.device_id)) {
            requestConfig(device.device_id);
        }
        return `<button onclick="requestConfig('${device.device_id}')">Load Configuration</button>`;
    }

    const fields = config.fields.map(f => renderField(device.device_id, f, config.values?.[f.key], videoOptions, scheduleOptions)).join('');
    return `
        <form class="config-form" onsubmit="saveConfig(event, '${device.device_id}', '${config.role}')">
            ${fields}
            <div class="row">
                <button type="submit" class="primary">Save</button>
                <button type="button" onclick="loadDefaults('${device.device_id}')">Defaults</button>
                <button type="button" onclick="requestConfig('${device.device_id}')">Refresh</button>
            </div>
            <div class="message-area">${renderMessage(device.message)}</div>
        </form>
    `;
}

let initialLoadDone = false;
let currentPreviewVideo = null;

function renderState(state) {
    // 1. Video Selector
    const selector = document.getElementById('videoSelector');
    if (selector && document.activeElement !== selector) {
        selector.innerHTML = (state.available_videos || []).map(v => `
            <option value="${v}" ${v === state.current_video ? 'selected' : ''}>${v}</option>
        `).join('');
        selector.onchange = () => changeVideo(selector.value);

        if (state.current_video && state.current_video !== currentPreviewVideo) {
            const preview = document.getElementById('preview');
            if (preview) {
                preview.src = '/video_file' + (initialLoadDone ? '?t=' + Date.now() : '');
                preview.load();
            }
            currentPreviewVideo = state.current_video;
            initialLoadDone = true;
        }
    }

    // 2. Status Bar
    const clusterStatus = document.getElementById('clusterStatus');
    if (clusterStatus) {
        clusterStatus.innerHTML = `
            <strong>STATUS:</strong> ${state.status} | 
            <strong>TIME:</strong> ${state.video_pos.toFixed(2)}s | 
            <strong>VIDEO:</strong> ${state.current_video}
        `;
    }

    // 3. Sync Preview Video
    const preview = document.getElementById('preview');
    if (preview && state.status === 'Leading' && !preview.paused && !preview.seeking) {
        const dev = preview.currentTime - state.video_pos;
        if (Math.abs(dev) > 0.25) {
            preview.currentTime = state.video_pos;
        }
    }

    // 4. Device Cards
    const list = document.getElementById('deviceList');
    if (!list) return;

    state.devices.forEach(device => {
        let card = document.getElementById(`card-${device.device_id}`);
        if (!card) {
            card = document.createElement('div');
            card.id = `card-${device.device_id}`;
            card.className = `device-card ${device.online ? 'online' : 'offline'}`;
            list.appendChild(card);
        }

        card.className = `device-card ${device.online ? 'online' : 'offline'}`;
        
        // Only update inner content if no input has focus and no save is pending
        const hasFocus = card.contains(document.activeElement);
        const snapshotTime = device.config?.updated_at || 0;
        const saveTime = lastSaveAt.get(device.device_id) || 0;
        const isPending = saveTime > snapshotTime && (Date.now() / 1000 - saveTime < 8);

        if (!hasFocus && !isPending) {
            card.innerHTML = `
                <div class="device-header">
                    <div class="device-info">
                        <h3>${device.label}</h3>
                        <div class="device-meta">${device.role} | ${device.ip}</div>
                    </div>
                    <span class="status-badge ${device.status.toLowerCase()}">${device.status}</span>
                </div>
                <div class="config-area">
                    ${renderConfigArea(device, state.available_videos, state.available_schedules)}
                </div>
            `;
        } else {
            // Update message area only
            const messageArea = card.querySelector('.message-area');
            if (messageArea) {
                if (isPending) {
                    messageArea.innerHTML = '<div class="message info">Saving...</div>';
                } else {
                    messageArea.innerHTML = renderMessage(device.message);
                }
            }
        }
    });

    // Cleanup stale cards
    const activeIds = new Set(state.devices.map(d => `card-${d.device_id}`));
    Array.from(list.children).forEach(c => {
        if (c.id.startsWith('card-') && !activeIds.has(c.id)) list.removeChild(c);
    });
}

async function saveConfig(event, deviceId, role) {
    event.preventDefault();
    const form = event.currentTarget;
    const updates = {};
    form.querySelectorAll('[data-key]').forEach(input => {
        if (input.type === 'checkbox') updates[input.dataset.key] = input.checked;
        else if (input.type === 'number') updates[input.dataset.key] = input.value === '' ? '' : Number(input.value);
        else updates[input.dataset.key] = input.value;
    });

    lastSaveAt.set(deviceId, Date.now() / 1000);
    const messageArea = form.querySelector('.message-area');
    if (messageArea) messageArea.innerHTML = '<div class="message info">Saving...</div>';

    await postJson('/api/config/save', { device_id: deviceId, role, updates });
    setTimeout(refresh, 500); // Quick refresh to confirm
}

async function loadDefaults(deviceId) {
    if (!confirm('Reset to defaults?')) return;
    await postJson('/api/config/reset', { device_id: deviceId });
    setTimeout(refresh, 500);
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
setInterval(refresh, 1500);

document.addEventListener('DOMContentLoaded', () => {
    const preview = document.getElementById('preview');
    if (preview) {
        preview.addEventListener('seeked', () => {
            seekCluster(preview.currentTime);
        });
    }
});
