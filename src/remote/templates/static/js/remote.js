const requestedConfigs = new Set();
const lastSaveAt = new Map();
const draftConfigValues = new Map();
const openConfigPanels = new Set();

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

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
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
    if (!config) {
        if (device.role === 'collaborator' && !requestedConfigs.has(device.device_id)) {
            requestConfig(device.device_id);
        }
        return `
            <button onclick="requestConfig('${device.device_id}')">Load config</button>
            <div class="message-area">${renderMessage(device.message)}</div>
        `;
    }

    const baseValues = config.values || {};
    const draftValues = draftConfigValues.get(device.device_id) || {};
    const values = { ...baseValues, ...draftValues };
    const isOpen = openConfigPanels.has(device.device_id) || device.role === 'leader';
    const fields = config.fields.map((field) => renderField(device.device_id, field, values[field.key], videoOptions, scheduleOptions)).join('');

    return `
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
                    ${device.role === 'collaborator' ? `<button type="button" onclick="requestConfig('${device.device_id}')">Refresh</button>` : ''}
                </div>
                <div class="message-area">${renderMessage(device.message)}</div>
            </form>
        </details>
    `;
}
let initialLoadDone = false;
let currentPreviewVideo = null;

function renderState(state) {
    const selector = document.getElementById('videoSelector');
    if (selector && document.activeElement !== selector) {
        selector.innerHTML = (state.available_videos || []).map((video) => `
            <option value="${video}" ${video === state.current_video ? 'selected' : ''}>${video}</option>
        `).join('');
        selector.onchange = () => changeVideo(selector.value);

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
    }


    const suggestions = document.getElementById('videoSuggestions');
    if (suggestions) {
        suggestions.innerHTML = (state.available_videos || []).map((video) => `
            <option value="${video}"></option>
        `).join('');
    }

    const scheduleSuggestions = document.getElementById('scheduleSuggestions');
    if (scheduleSuggestions) {
        scheduleSuggestions.innerHTML = (state.available_schedules || []).map((schedule) => `
            <option value="${schedule}"></option>
        `).join('');
    }

    const clusterStatus = document.getElementById('clusterStatus');
    if (clusterStatus) {
        const latency = state.latency || {};
        const latencyText = latency.enabled
            ? ` | RTT: ${latency.avg_rtt_ms ?? 'n/a'}ms | Compensation: ${latency.compensation_ms ?? 0}ms`
            : ' | RTT compensation: off';
        clusterStatus.textContent =
            `Status: ${state.status} | Time: ${state.video_pos.toFixed(2)}s | Video: ${state.current_video}${latencyText}`;
    }

    // Sync Preview Video
    const preview = document.getElementById('preview');
    if (preview && state.status === 'Leading' && !preview.paused && !preview.seeking) {
        const dev = preview.currentTime - state.video_pos;
        if (Math.abs(dev) > 0.25) {
            preview.currentTime = state.video_pos;
        }
    }

    const rows = document.getElementById('deviceRows');
    if (rows) {
        state.devices.forEach((device) => {
            let row = document.getElementById(`row-${device.device_id}`);
            if (!row) {
                row = document.createElement('tr');
                row.id = `row-${device.device_id}`;
                row.innerHTML = '<td></td><td></td><td></td><td></td><td class="config-cell"></td>';
                rows.appendChild(row);
            }

            const cells = row.cells;
            cells[0].textContent = device.label;
            cells[1].textContent = device.role;
            cells[2].textContent = device.latency_ms != null
                ? `${device.ip} | RTT ${device.latency_ms}ms`
                : device.ip;
            cells[3].textContent = `${device.status} (${device.online ? 'Online' : 'Offline'})`;

            const configCell = cells[4];
            
            const snapshotTime = device.config?.updated_at || 0;
            const saveTime = lastSaveAt.get(device.device_id) || 0;
            const isPending = saveTime > snapshotTime && (Date.now() / 1000 - saveTime < 8);
            if (!isPending && snapshotTime >= saveTime) {
                draftConfigValues.delete(device.device_id);
            }

            const hasFocus = configCell.contains(document.activeElement);
            if (!hasFocus && !isPending) {
                configCell.innerHTML = renderConfigCell(device, state.available_videos || [], state.available_schedules || []);
                const panel = configCell.querySelector('.config-panel');
                if (panel) {
                    panel.addEventListener('toggle', () => {
                        const panelDeviceId = panel.dataset.deviceId;
                        if (panel.open) {
                            openConfigPanels.add(panelDeviceId);
                        } else {
                            openConfigPanels.delete(panelDeviceId);
                        }
                    });
                }

                configCell.querySelectorAll('[data-key]').forEach((input) => {
                    const updateDraft = () => storeDraftValues(device.device_id, configCell);
                    input.addEventListener('input', updateDraft);
                    input.addEventListener('change', updateDraft);
                });
            } else {
                const messageArea = configCell.querySelector('.message-area');
                if (messageArea) {
                    if (isPending) {
                        messageArea.innerHTML = '<div class="message info">Saving...</div>';
                    } else {
                        messageArea.innerHTML = renderMessage(device.message);
                    }
                }
            }
        });

        const activeIds = new Set(state.devices.map(d => `row-${d.device_id}`));
        Array.from(rows.children).forEach(row => {
            if (!activeIds.has(row.id)) {
                rows.removeChild(row);
            }
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
