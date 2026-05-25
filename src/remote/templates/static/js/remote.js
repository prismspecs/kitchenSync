const requestedConfigs = new Set();
const lastSaveAt = new Map();
const draftConfigValues = new Map();
const openConfigPanels = new Set();
let latestState = null;

const REFRESH_ICON_SVG = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`;

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

async function uploadMedia(deviceId = null) {
    const inputId = deviceId ? `upload-input-${deviceId}` : 'mediaUploadInput';
    const statusId = deviceId ? `upload-status-${deviceId}` : 'uploadStatus';
    
    const input = document.getElementById(inputId);
    const status = document.getElementById(statusId);
    if (!input || !input.files.length) return;

    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    let url = '/api/media/upload';
    if (deviceId && deviceId !== 'remote-leader') {
        url += `?target_device_id=${encodeURIComponent(deviceId)}`;
    }

    status.textContent = 'Uploading...';
    try {
        const response = await fetch(url, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();
        if (result.status === 'ok') {
            status.textContent = deviceId ? 'Transferring...' : 'Uploaded: ' + result.filename;
            input.value = '';
            setTimeout(refresh, deviceId ? 2000 : 500);
        } else {
            status.textContent = 'Error: ' + (result.message || 'Upload failed');
        }
    } catch (err) {
        status.textContent = 'Error: ' + err.message;
    }
}

async function deleteMedia(deviceId, filename) {
    if (!confirm(`Delete ${filename} from ${deviceId}?`)) return;
    
    const response = await fetch(`/api/media?device_id=${encodeURIComponent(deviceId)}&filename=${encodeURIComponent(filename)}`, {
        method: 'DELETE'
    });
    
    if (response.ok) {
        setTimeout(refresh, 500);
    } else {
        const result = await response.json();
        alert('Delete failed: ' + (result.message || 'Unknown error'));
    }
}

async function syncMedia(deviceId, filename) {
    const response = await postJson('/api/media/sync', { device_id: deviceId, filename: filename });
    if (response && response.status === 'requested') {
        alert('Sync requested. This may take some time for large files.');
    }
}

async function requestMedia(deviceId) {
    await postJson('/api/media/request', { device_id: deviceId });
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

async function assignVideoToAllCollaborators() {
    const selector = document.getElementById('videoSelector');
    const selectedVideo = selector?.value;
    if (!selectedVideo || !latestState) {
        return;
    }

    const collaborators = (latestState.devices || []).filter((device) => device.role === 'collaborator');
    if (!collaborators.length) {
        return;
    }

    await Promise.all(collaborators.map(async (device) => {
        const draftValues = draftConfigValues.get(device.device_id) || {};
        draftConfigValues.set(device.device_id, { ...draftValues, video_file: selectedVideo });
        lastSaveAt.set(device.device_id, Date.now() / 1000);
        await postJson('/api/config/save', {
            device_id: device.device_id,
            role: 'collaborator',
            updates: { video_file: selectedVideo },
        });
    }));

    setTimeout(refresh, 500);
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

async function refreshDevice(deviceId) {
    await Promise.all([
        postJson('/api/media/request', { device_id: deviceId }),
        postJson('/api/config/request', { device_id: deviceId })
    ]);
}

function escapeHtml(value) {

    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function getStatusClass(device) {
    if (!device.online) {
        return 'status-offline';
    }

    const status = String(device.status || '').toLowerCase();
    if (status === 'ready') {
        return 'status-ready';
    }
    if (status === 'leading') {
        return 'status-leading';
    }
    if (status === 'syncing') {
        return 'status-syncing';
    }
    if (status === 'unknown') {
        return 'status-unknown';
    }
    return 'status-generic';
}

function renderTooltip(field) {
    if (!field.tooltip) {
        return '';
    }

    return `
        <span class="tooltip" tabindex="0" aria-label="Help for ${escapeHtml(field.label)}">
            <span class="tooltip-icon">?</span>
            <span class="tooltip-bubble">${escapeHtml(field.tooltip)}</span>
        </span>
    `;
}

function renderField(deviceId, field, value, videoOptions, scheduleOptions) {
    const fieldId = `${deviceId}-${field.key}`;
    const tooltip = renderTooltip(field);
    const safeValue = value ?? '';
    
    if (field.type === 'bool') {
        return `
            <div class="row bool-row">
                <label for="${fieldId}" class="field-label">${escapeHtml(field.label)}${tooltip}</label>
                <input id="${fieldId}" data-key="${field.key}" type="checkbox" ${safeValue ? 'checked' : ''}>
            </div>
        `;
    }

    if (field.type === 'choice') {
        const options = (field.options || []).map((opt) => `
            <option value="${escapeHtml(opt)}" ${opt === safeValue ? 'selected' : ''}>${escapeHtml(opt)}</option>
        `).join('');

        return `
            <div class="row">
                <label for="${fieldId}" class="field-label">${escapeHtml(field.label)}${tooltip}</label>
                <select id="${fieldId}" data-key="${field.key}">
                    ${options}
                </select>
            </div>
        `;
    }

    if (field.key === 'video_file' && videoOptions.length) {
        const options = videoOptions.map((video) => `
            <option value="${escapeHtml(video)}" ${video === safeValue ? 'selected' : ''}>${escapeHtml(video)}</option>
        `).join('');

        return `
            <div class="row">
                <label for="${fieldId}" class="field-label">${escapeHtml(field.label)}${tooltip}</label>
                <select id="${fieldId}" data-key="${field.key}">
                    ${options}
                </select>
            </div>
        `;
    }

    if (field.key === 'schedule_file' && scheduleOptions.length) {
        const allowCustom = safeValue && !scheduleOptions.includes(safeValue);
        const options = scheduleOptions.map((schedule) => `
            <option value="${escapeHtml(schedule)}" ${schedule === safeValue ? 'selected' : ''}>${escapeHtml(schedule)}</option>
        `).join('');

        return `
            <div class="row">
                <label for="${fieldId}" class="field-label">${escapeHtml(field.label)}${tooltip}</label>
                <select id="${fieldId}" data-key="${field.key}">
                    ${allowCustom ? `<option value="${escapeHtml(safeValue)}" selected>${escapeHtml(safeValue)}</option>` : ''}
                    ${options}
                </select>
            </div>
        `;
    }

    const type = field.type === 'int' || field.type === 'float' ? 'number' : 'text';
    const step = field.type === 'float' ? 'step="any"' : '';
    let list = '';
    if (field.key === 'video_file' && videoOptions.length) {
        list = 'list="videoSuggestions"';
    } else if (field.key === 'schedule_file' && scheduleOptions.length) {
        list = 'list="scheduleSuggestions"';
    }

    return `
        <div class="row">
            <label for="${fieldId}" class="field-label">${escapeHtml(field.label)}${tooltip}</label>
            <input id="${fieldId}" data-key="${field.key}" type="${type}" value="${escapeHtml(safeValue)}" ${step} ${list}>
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
        return '<div class="message ok">Saved. Restart required.</div>';
    }
    return '<div class="message ok">Saved.</div>';
}

function renderConfigCell(device, videoOptions, scheduleOptions) {
    const config = device.config;
    const refreshIcon = `<button class="btn-icon btn-refresh-cell" title="Refresh Config & Media" onclick="refreshDevice('${device.device_id}')">${REFRESH_ICON_SVG}</button>`;

    if (!config) {
        if (device.role === 'collaborator' && !requestedConfigs.has(device.device_id)) {
            requestConfig(device.device_id);
        }
        return `
            <div class="cell-container">
                ${refreshIcon}
                <button onclick="requestConfig('${device.device_id}')">Load config</button>
                <div class="message-area">${renderMessage(device.message)}</div>
            </div>
        `;
    }

    const baseValues = config.values || {};
    const draftValues = draftConfigValues.get(device.device_id) || {};
    const values = { ...baseValues, ...draftValues };
    const isOpen = openConfigPanels.has(device.device_id) || device.role === 'leader';
    const fields = config.fields.map((field) => renderField(device.device_id, field, values[field.key], videoOptions, scheduleOptions)).join('');

    return `
        <div class="cell-container">
            ${refreshIcon}
            <details class="config-panel" data-device-id="${device.device_id}" ${isOpen ? 'open' : ''}>
                <summary>
                    <span>Configuration</span>
                    <span class="config-meta">${escapeHtml(config.config_path || '')}</span>
                </summary>
                <form onsubmit="saveConfig(event, '${device.device_id}', '${config.role}')">
                    ${fields}
                    <div class="row actions-row">
                        <button type="submit">Save</button>
                        <button type="button" onclick="loadDefaults('${device.device_id}')">Defaults</button>
                    </div>
                    <div class="message-area">${renderMessage(device.message)}</div>
                </form>
            </details>
        </div>
    `;
}

let initialLoadDone = false;
let currentPreviewVideo = null;

function renderMediaCell(device, leaderMedia) {
    const media = device.media || [];
    const isLeader = device.role === 'leader';
    const refreshIcon = `<button class="btn-icon btn-refresh-cell" title="Refresh Config & Media" onclick="refreshDevice('${device.device_id}')">${REFRESH_ICON_SVG}</button>`;

    if (!device.online && !isLeader) {
        return `
            <div class="cell-container">
                ${refreshIcon}
                <div class="message info">Device offline</div>
            </div>
        `;
    }

    if (!isLeader && !device.media && !requestedConfigs.has(device.device_id + '-media')) {
        requestedConfigs.add(device.device_id + '-media');
        requestMedia(device.device_id);
    }

    const mediaListHtml = media.map(m => {
        const sizeMb = (m.size / (1024 * 1024)).toFixed(1);
        const sourceLabel = m.location === 'usb' ? 'USB' : 'DISK';
        const sourceClass = m.location === 'usb' ? 'source-usb' : 'source-local';
        return `
            <div class="media-item">
                <div class="media-item-info">
                    <span class="media-source ${sourceClass}">${sourceLabel}</span>
                    <span class="media-name" title="${escapeHtml(m.path)}">${escapeHtml(m.name)}</span>
                </div>
                <div class="media-item-actions">
                    <span class="media-meta">${sizeMb} MB</span>
                    <button class="btn-small btn-danger" onclick="deleteMedia('${device.device_id}', '${escapeHtml(m.name)}')">Delete</button>
                </div>
            </div>
        `;
    }).join('');

    let syncSection = '';
    
    if (!isLeader) {
        const deviceFileNames = media.map(m => m.name);
        const missingFiles = (leaderMedia || []).filter(m => !deviceFileNames.includes(m.name));
        
        const uploadSection = `
            <div class="sync-section">
                <h4>Upload to device</h4>
                <div class="row btn-group">
                    <input type="file" id="upload-input-${device.device_id}" class="file-input-small">
                    <button class="btn-small" onclick="uploadMedia('${device.device_id}')">Upload</button>
                </div>
                <div id="upload-status-${device.device_id}" class="message info"></div>
            </div>
        `;

        if (missingFiles.length > 0) {
            const options = missingFiles.map(m => `
                <option value="${escapeHtml(m.name)}">${escapeHtml(m.name)} (${(m.size / (1024 * 1024)).toFixed(1)} MB)</option>
            `).join('');
            
            syncSection = `
                <div class="sync-section">
                    <h4>Download video from Leader</h4>
                    <div class="row btn-group">
                        <select id="sync-select-${device.device_id}" class="select-small">${options}</select>
                        <button class="btn-small" onclick="syncMedia('${device.device_id}', document.getElementById('sync-select-${device.device_id}').value)">Pull</button>
                    </div>
                </div>
                ${uploadSection}
            `;
        } else {
            syncSection = `
                ${uploadSection}
            `;
        }
    }

    return `
        <div class="cell-container">
            ${refreshIcon}
            <div class="media-panel">
                <h4>Available Videos</h4>
                <div class="media-list">
                    ${mediaListHtml || '<div class="message info">No videos found</div>'}
                </div>
                ${syncSection}
            </div>
        </div>
    `;
}

/**
 * Surgical DOM Reconciliation
 * Replaces the content of a container ONLY if it has changed, 
 * and ALWAYS preserves focus/selection in inputs/forms.
 */
function reconcileCell(container, newHtml, force = false) {
    if (!container) return;
    
    // 1. If nothing changed, do nothing
    const currentHtml = container.innerHTML;
    if (!force && currentHtml === newHtml) return;

    // 2. If the user is currently interacting with something in this cell, 
    // we must be very careful not to wipe their state.
    const activeElement = document.activeElement;
    const hasFocus = container.contains(activeElement);
    
    if (hasFocus) {
        // If it's a form element, we skip the broad innerHTML update to preserve focus/typing.
        // We only update non-input parts of the cell if possible.
        // For now, if focused, we only update the 'message-area' if it exists.
        const messageArea = container.querySelector('.message-area');
        if (messageArea) {
            const temp = document.createElement('div');
            temp.innerHTML = newHtml;
            const newMessageArea = temp.querySelector('.message-area');
            if (newMessageArea && messageArea.innerHTML !== newMessageArea.innerHTML) {
                messageArea.innerHTML = newMessageArea.innerHTML;
            }
        }
        
        // Also update the 'media-list' if it's a media cell and the user isn't focused there
        const mediaList = container.querySelector('.media-list');
        const mediaInput = container.querySelector('.file-input-small');
        const isMediaFocused = mediaList?.contains(activeElement) || mediaInput === activeElement;
        
        if (!isMediaFocused) {
            const temp = document.createElement('div');
            temp.innerHTML = newHtml;
            const newMediaList = temp.querySelector('.media-list');
            if (newMediaList && mediaList && mediaList.innerHTML !== newMediaList.innerHTML) {
                mediaList.innerHTML = newMediaList.innerHTML;
            }
        }
        
        return;
    }

    // 3. No focus, safe to replace
    container.innerHTML = newHtml;
}

function renderState(state) {
    latestState = state;
    
    // Update Top-level Video Selector
    const selector = document.getElementById('videoSelector');
    if (selector && document.activeElement !== selector) {
        const newSelectorHtml = (state.available_videos || []).map((video) => `
            <option value="${video}" ${video === state.current_video ? 'selected' : ''}>${video}</option>
        `).join('');
        if (selector.innerHTML !== newSelectorHtml) {
            selector.innerHTML = newSelectorHtml;
            selector.onchange = () => changeVideo(selector.value);
        }
    }

    if (state.current_video && state.current_video !== currentPreviewVideo) {
        const preview = document.getElementById('preview');
        if (preview) {
            const buster = initialLoadDone ? '?t=' + Date.now() : '';
            preview.src = '/video_file' + buster;
            preview.load();
        }
        currentPreviewVideo = state.current_video;
        initialLoadDone = true;
    }

    // Update Suggestions
    const suggestions = document.getElementById('videoSuggestions');
    if (suggestions) {
        const newSugg = (state.available_videos || []).map(v => `<option value="${v}"></option>`).join('');
        if (suggestions.innerHTML !== newSugg) suggestions.innerHTML = newSugg;
    }

    const scheduleSuggestions = document.getElementById('scheduleSuggestions');
    if (scheduleSuggestions) {
        const newSugg = (state.available_schedules || []).map(s => `<option value="${s}"></option>`).join('');
        if (scheduleSuggestions.innerHTML !== newSugg) scheduleSuggestions.innerHTML = newSugg;
    }

    // Update Status Header
    const clusterStatus = document.getElementById('clusterStatus');
    if (clusterStatus) {
        const latency = state.latency || {};
        const latencyText = latency.enabled
            ? ` | RTT: ${latency.avg_rtt_ms ?? 'n/a'}ms | Compensation: ${latency.compensation_ms ?? 0}ms`
            : ' | RTT compensation: off';
        const newStatusText = `Status: ${state.status} | Time: ${state.video_pos.toFixed(2)}s | Video: ${state.current_video}${latencyText}`;
        if (clusterStatus.textContent !== newStatusText) {
            clusterStatus.textContent = newStatusText;
        }
    }

    // Sync Preview Video
    const preview = document.getElementById('preview');
    if (preview && state.status === 'Leading' && !preview.paused && !preview.seeking) {
        const dev = preview.currentTime - state.video_pos;
        if (Math.abs(dev) > 0.25) {
            preview.currentTime = state.video_pos;
        }
    }

    // Update Device Table
    const rows = document.getElementById('deviceRows');
    if (rows) {
        state.devices.forEach((device) => {
            let row = document.getElementById(`row-${device.device_id}`);
            if (!row) {
                row = document.createElement('tr');
                row.id = `row-${device.device_id}`;
                row.innerHTML = '<td class="device-summary-cell"></td><td class="config-cell"></td><td class="media-cell"></td>';
                rows.appendChild(row);
            }

            const cells = row.cells;
            
            // 1. Update Summary Cell
            const latencyLabel = device.role === 'leader' ? 'Cluster RTT avg' : 'Ping';
            const latencyText = device.latency_ms != null ? `${latencyLabel}: ${device.latency_ms} ms` : `${latencyLabel}: n/a`;
            const statusText = `${device.status} (${device.online ? 'Online' : 'Offline'})`;
            const refreshIcon = `<button class="btn-icon btn-refresh-cell" title="Refresh Config & Media" onclick="refreshDevice('${device.device_id}')">${REFRESH_ICON_SVG}</button>`;
            
            const newSummaryHtml = `
                <div class="cell-container">
                    ${refreshIcon}
                    <div class="device-summary-primary">${escapeHtml(device.label)}</div>
                    <div class="device-summary-line device-summary-status ${getStatusClass(device)}">${escapeHtml(statusText)}</div>
                    <div class="device-summary-line device-summary-role">${escapeHtml(device.role)}</div>
                    <div class="device-summary-line device-summary-ip">${escapeHtml(device.ip)}</div>
                    <div class="device-summary-line device-summary-latency">${escapeHtml(latencyText)}</div>
                </div>
            `;
            if (cells[0].innerHTML !== newSummaryHtml) {
                cells[0].innerHTML = newSummaryHtml;
            }

            // 2. Update Config Cell (Surgical)
            const snapshotTime = device.config?.updated_at || 0;
            const saveTime = lastSaveAt.get(device.device_id) || 0;
            const isPending = saveTime > snapshotTime && (Date.now() / 1000 - saveTime < 8);
            if (!isPending && snapshotTime >= saveTime) {
                draftConfigValues.delete(device.device_id);
            }

            const newConfigHtml = renderConfigCell(device, state.available_videos || [], state.available_schedules || []);
            reconcileCell(cells[1], newConfigHtml);

            // Re-attach listeners to new inputs if they were just rendered
            cells[1].querySelectorAll('[data-key]').forEach((input) => {
                if (!input.dataset.bound) {
                    const updateDraft = () => storeDraftValues(device.device_id, cells[1]);
                    input.addEventListener('input', updateDraft);
                    input.addEventListener('change', updateDraft);
                    input.dataset.bound = "true";
                }
            });
            
            // Update Toggle State
            const panel = cells[1].querySelector('.config-panel');
            if (panel && !panel.dataset.bound) {
                panel.addEventListener('toggle', () => {
                    if (panel.open) openConfigPanels.add(device.device_id);
                    else openConfigPanels.delete(device.device_id);
                });
                panel.dataset.bound = "true";
            }

            // 3. Update Media Cell (Surgical)
            const newMediaHtml = renderMediaCell(device, state.leader_media);
            reconcileCell(cells[2], newMediaHtml);
        });

        // Prune dead rows
        const activeIds = new Set(state.devices.map(d => `row-${d.device_id}`));
        Array.from(rows.children).forEach(row => {
            if (!activeIds.has(row.id)) rows.removeChild(row);
        });
    }
}

function storeDraftValues(deviceId, container) {
    const values = {};
    container.querySelectorAll('[data-key]').forEach((input) => {
        if (input.type === 'checkbox') {
            values[input.dataset.key] = input.checked;
        } else if (input.type === 'number') {
            values[input.dataset.key] = input.value === '' ? '' : Number(input.value);
        } else {
            values[input.dataset.key] = input.value;
        }
    });
    draftConfigValues.set(deviceId, values);
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
    draftConfigValues.set(deviceId, updates);

    const messageArea = form.querySelector('.message-area');
    if (messageArea) {
        messageArea.innerHTML = '<div class="message info">Saving...</div>';
    }

    lastSaveAt.set(deviceId, Date.now() / 1000);
    await postJson('/api/config/save', { device_id: deviceId, role, updates });
    setTimeout(refresh, 500);
}

async function loadDefaults(deviceId) {
    if (!confirm('Reset this device to defaults?')) {
        return;
    }
    draftConfigValues.delete(deviceId);
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
