const requestedConfigs = new Set();
const lastSaveAt = new Map();
const draftConfigValues = new Map();
const openConfigPanels = new Set(['remote-leader']);
const openMediaPanels = new Set(['remote-leader']);
const openInfoPanels = new Set();
let latestState = null;

const REFRESH_ICON_SVG = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`;

console.log('remote.js v16 loaded');
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

function clampValue(input, min, max) {
    let val = parseFloat(input.value);
    if (isNaN(val)) return;
    if (min !== '' && val < min) val = min;
    if (max !== '' && val > max) val = max;
    input.value = val;
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
    const isRemote = deviceId && deviceId !== 'remote-leader';
    if (isRemote) {
        url += `?target_device_id=${encodeURIComponent(deviceId)}`;
    }

    status.textContent = '0%';
    status.style.display = 'block';

    try {
        const xhr = new XMLHttpRequest();
        const result = await new Promise((resolve, reject) => {
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    status.textContent = `${Math.round((e.loaded / e.total) * 100)}%`;
                }
            });
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch { resolve({ status: 'ok' }); }
                } else {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch { reject(new Error(`Upload failed (${xhr.status})`)); }
                }
            });
            xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
            xhr.open('POST', url);
            xhr.send(formData);
        });

        if (result.status === 'ok') {
            if (isRemote) {
                status.textContent = 'Transferred';
            } else {
                status.textContent = 'Uploaded: ' + result.filename;
            }
            input.value = '';
            setTimeout(refresh, isRemote ? 3000 : 500);
        } else {
            status.textContent = 'Error: ' + (result.message || 'Upload failed');
        }
    } catch (err) {
        status.textContent = 'Error: ' + err.message;
    }
}

async function convertAndUpload(deviceId) {
    const inputId = `convert-input-${deviceId}`;
    const statusId = `convert-status-${deviceId}`;
    const convertProgressId = `convert-progress-${deviceId}`;
    const uploadProgressId = `upload-progress-${deviceId}`;

    const input = document.getElementById(inputId);
    const status = document.getElementById(statusId);
    const convertProgress = document.getElementById(convertProgressId);
    const uploadProgress = document.getElementById(uploadProgressId);
    if (!input || !input.files.length) return;

    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);

    const url = `/api/media/convert-and-upload?target_device_id=${encodeURIComponent(deviceId)}`;

    status.textContent = 'Uploading source file...';
    status.style.display = 'block';
    convertProgress.style.display = 'block';
    convertProgress.querySelector('.progress-fill').style.width = '0%';
    uploadProgress.style.display = 'none';

    try {
        const xhr = new XMLHttpRequest();
        const result = await new Promise((resolve, reject) => {
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    status.textContent = `Uploading source: ${Math.round((e.loaded / e.total) * 100)}%`;
                }
            });
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch { resolve({ status: 'ok' }); }
                } else {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch { reject(new Error(`Upload failed (${xhr.status})`)); }
                }
            });
            xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
            xhr.open('POST', url);
            xhr.send(formData);
        });

        if (result.status === 'started') {
            status.textContent = 'Conversion started...';
            pollConvertStatus(deviceId);
        } else {
            status.textContent = 'Error: ' + (result.message || 'Failed to start conversion');
        }
    } catch (err) {
        status.textContent = 'Error: ' + err.message;
    }
}

let convertPollTimers = {};

function pollConvertStatus(deviceId) {
    const statusId = `convert-status-${deviceId}`;
    const convertProgressId = `convert-progress-${deviceId}`;
    const uploadProgressId = `upload-progress-${deviceId}`;

    if (convertPollTimers[deviceId]) {
        clearInterval(convertPollTimers[deviceId]);
    }

    convertPollTimers[deviceId] = setInterval(async () => {
        try {
            const response = await fetch(`/api/media/convert-status?device_id=${encodeURIComponent(deviceId)}`);
            const data = await response.json();

            const status = document.getElementById(statusId);
            const convertProgress = document.getElementById(convertProgressId);
            const uploadProgress = document.getElementById(uploadProgressId);

            if (!status) {
                clearInterval(convertPollTimers[deviceId]);
                delete convertPollTimers[deviceId];
                return;
            }

            if (data.status === 'not_found') {
                status.textContent = 'Conversion job not found';
                clearInterval(convertPollTimers[deviceId]);
                delete convertPollTimers[deviceId];
                return;
            }

            if (data.status === 'converting') {
                convertProgress.style.display = 'block';
                convertProgress.querySelector('.progress-fill').style.width = data.convert_progress + '%';
                convertProgress.querySelector('.progress-label').textContent = `Converting (${data.convert_progress}%)`;
                status.textContent = `Converting to ${data.target_codec.toUpperCase()}...`;
                return;
            }

            if (data.status === 'uploading') {
                convertProgress.querySelector('.progress-fill').style.width = '100%';
                convertProgress.querySelector('.progress-label').textContent = 'Conversion complete';
                uploadProgress.style.display = 'block';
                uploadProgress.querySelector('.progress-fill').style.width = '50%';
                uploadProgress.querySelector('.progress-label').textContent = 'Transferring to device...';
                status.textContent = 'Uploading to device...';
                return;
            }

            if (data.status === 'complete') {
                convertProgress.querySelector('.progress-fill').style.width = '100%';
                convertProgress.querySelector('.progress-label').textContent = 'Conversion complete';
                uploadProgress.style.display = 'block';
                uploadProgress.querySelector('.progress-fill').style.width = '100%';
                uploadProgress.querySelector('.progress-label').textContent = 'Uploaded';
                status.textContent = `Complete: ${data.output_filename}`;
                status.className = 'message ok';
                clearInterval(convertPollTimers[deviceId]);
                delete convertPollTimers[deviceId];
                setTimeout(refresh, 2000);
                return;
            }

            if (data.status === 'error') {
                status.textContent = 'Error: ' + (data.error || 'Conversion failed');
                status.className = 'message error';
                clearInterval(convertPollTimers[deviceId]);
                delete convertPollTimers[deviceId];
                return;
            }
        } catch (err) {
            // Silently retry on network errors
        }
    }, 500);
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

async function loadVideo(deviceId, filename) {
    if (deviceId === 'remote-leader') {
        await changeVideo(filename);
        setTimeout(refresh, 500);
        return;
    }
    if (!confirm(`Load ${filename} on ${deviceId}? The device will restart playback.`)) return;
    const draftValues = draftConfigValues.get(deviceId) || {};
    draftConfigValues.set(deviceId, { ...draftValues, video_file: filename });
    lastSaveAt.set(deviceId, Date.now() / 1000);
    await postJson('/api/media/load', { device_id: deviceId, filename });
    // The device saves the config and restarts itself; re-pull its config
    // once it should be back so the panel reflects reality.
    setTimeout(() => requestConfig(deviceId), 4000);
    setTimeout(() => requestConfig(deviceId), 9000);
    setTimeout(refresh, 1000);
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

async function resetClusterSeeks() {
    await fetch('/api/seeks/reset', { method: 'POST' });
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
    let step = '';
    if (field.type === 'int') {
        step = field.step != null ? `step="${field.step}"` : 'step="1"';
    } else if (field.type === 'float') {
        step = field.step != null ? `step="${field.step}"` : 'step="any"';
    }
    const min = field.min != null ? `min="${field.min}"` : '';
    const max = field.max != null ? `max="${field.max}"` : '';
    const clamp = (field.min != null || field.max != null) ? `onchange="clampValue(this, ${field.min ?? ''}, ${field.max ?? ''})"` : '';
    let list = '';
    if (field.key === 'video_file' && videoOptions.length) {
        list = 'list="videoSuggestions"';
    } else if (field.key === 'schedule_file' && scheduleOptions.length) {
        list = 'list="scheduleSuggestions"';
    }

    return `
        <div class="row">
            <label for="${fieldId}" class="field-label">${escapeHtml(field.label)}${tooltip}</label>
            <input id="${fieldId}" data-key="${field.key}" type="${type}" value="${escapeHtml(safeValue)}" ${step} ${min} ${max} ${clamp} ${list}>
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
    const refreshIcon = `<button class="btn-icon btn-refresh-cell" title="Refresh Config" onclick="requestConfig('${device.device_id}')">${REFRESH_ICON_SVG}</button>`;

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
    const isOpen = openConfigPanels.has(device.device_id);

    const ADVANCED_KEYS = new Set([
        'tick_interval',
        'latency_factor',
        'max_drift',
        'min_drift',
        'kp',
        'max_samples',
        'min_rate',
        'max_rate',
        'enable_caching',
        'enable_latency_compensation',
        'enable_deviation_log',
        'video_offset',
        'midi_port',
        'video_width',
        'video_height',
        'position_poll_interval',
        'remote_sync_mode'
    ]);

    const standardFieldsHtml = [];
    const advancedFieldsHtml = [];

    config.fields.forEach((field) => {
        const rendered = renderField(device.device_id, field, values[field.key], videoOptions, scheduleOptions);
        if (ADVANCED_KEYS.has(field.key)) {
            advancedFieldsHtml.push(rendered);
        } else {
            standardFieldsHtml.push(rendered);
        }
    });

    let advancedSectionHtml = '';
    if (advancedFieldsHtml.length > 0) {
        advancedSectionHtml = `
            <div class="advanced-section">
                <div class="advanced-header">Advanced Settings</div>
                <div class="advanced-fields">
                    ${advancedFieldsHtml.join('')}
                </div>
            </div>
        `;
    }

    return `
        <div class="cell-container">
            ${refreshIcon}
            <details class="config-panel" data-device-id="${device.device_id}" ${isOpen ? 'open' : ''}>
                <summary>
                    <span>Configuration</span>
                    <span class="config-meta">${escapeHtml(config.config_path || '')}</span>
                </summary>
                <form onsubmit="saveConfig(event, '${device.device_id}', '${config.role}')">
                    ${standardFieldsHtml.join('')}
                    ${advancedSectionHtml}
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

const updatingDevices = new Set();
let initialLoadDone = false;
let currentPreviewVideo = null;

function renderMediaCell(device, leaderMedia) {
    const media = device.media || [];
    const isLeader = device.role === 'leader';
    const refreshIcon = `<button class="btn-icon btn-refresh-cell" title="Refresh Media" onclick="requestMedia('${device.device_id}')">${REFRESH_ICON_SVG}</button>`;

    if (!device.online && !isLeader) {
        return `
            <div class="cell-container">
                ${refreshIcon}
                <div class="message info">Device offline</div>
            </div>
        `;
    }

    // Auto-request media for every real device (the Pi leader included -
    // only the local web-UI node has its media injected directly).
    if (device.device_id !== 'remote-leader' && device.media == null && !requestedConfigs.has(device.device_id + '-media')) {
        requestedConfigs.add(device.device_id + '-media');
        requestMedia(device.device_id);
    }

    const mediaListHtml = media.map(m => {
        const sizeMb = (m.size / (1024 * 1024)).toFixed(1);
        const sourceLabel = m.location === 'usb' ? 'USB' : 'DISK';
        const sourceClass = m.location === 'usb' ? 'source-usb' : 'source-local';
        const infoId = 'info-' + device.device_id + '-' + m.name.replace(/[^a-zA-Z0-9]/g, '_');
        const isInfoOpen = openInfoPanels.has(infoId);
        return `
            <div class="media-item">
                <div class="media-item-info">
                    <span class="media-source ${sourceClass}">${sourceLabel}</span>
                    <span class="media-name" title="${escapeHtml(m.path)}">${escapeHtml(m.name)}</span>
                </div>
                <div class="media-item-actions">
                    <span class="media-meta">${sizeMb} MB</span>
                    <button class="btn-small btn-primary" title="Set as this device's video and restart playback" onclick="loadVideo('${device.device_id}', '${escapeHtml(m.name)}')">Load</button>
                    <button class="btn-small btn-info" onclick="toggleMediaInfo(event, '${infoId}')">Info</button>
                    <button class="btn-small btn-danger" onclick="deleteMedia('${device.device_id}', '${escapeHtml(m.name)}')">Delete</button>
                </div>
                <div id="${infoId}" class="media-item-details" style="display: ${isInfoOpen ? 'block' : 'none'};">
                    Format: <b>${escapeHtml(m.format || 'unknown')}</b> | Codec: <b>${escapeHtml(m.video_codec || 'unknown')}</b> ${m.is_optimized ? '<span class="optimized-badge" style="margin-left:4px;">Optimized</span>' : ''}<br>
                    Resolution: <b>${m.width || 0}x${m.height || 0}</b><br>
                    Duration: <b>${m.duration ? m.duration.toFixed(1) + 's' : 'unknown'}</b><br>
                    Audio: <b>${m.audio_tracks > 0 ? `${m.audio_codec || 'yes'} (${m.audio_tracks} track(s))` : 'none'}</b>
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
                <div id="upload-status-${device.device_id}" class="message info" style="display:none"></div>
            </div>
            <div class="sync-section">
                <h4>Convert &amp; Upload</h4>
                <div class="row btn-group">
                    <input type="file" id="convert-input-${device.device_id}" class="file-input-small">
                    <button class="btn-small btn-primary" onclick="convertAndUpload('${device.device_id}')">Convert &amp; Upload</button>
                </div>
                <div class="convert-progress" id="convert-progress-${device.device_id}" style="display:none">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width:0%"></div>
                    </div>
                    <span class="progress-label">Waiting...</span>
                </div>
                <div class="convert-progress" id="upload-progress-${device.device_id}" style="display:none">
                    <div class="progress-bar progress-upload">
                        <div class="progress-fill" style="width:0%"></div>
                    </div>
                    <span class="progress-label">Waiting...</span>
                </div>
                <div id="convert-status-${device.device_id}" class="message info" style="display:none"></div>
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

    const isMediaOpen = openMediaPanels.has(device.device_id);

    return `
        <div class="cell-container">
            ${refreshIcon}
            <details class="media-panel" data-device-id="${device.device_id}" ${isMediaOpen ? 'open' : ''}>
                <summary>
                    <h4>Available Videos</h4>
                </summary>
                <div class="media-list">
                    ${mediaListHtml || '<div class="message info">No videos found</div>'}
                </div>
                ${syncSection}
            </details>
        </div>
    `;
}

/**
 * Morph - A highly surgical vanilla DOM morphing engine.
 * Recursively diffs oldNode and newNode, updating attributes, text nodes,
 * and form input values without rebuilding DOM elements, thus preserving
 * active cursor/selection state, element identities, and interactive toggles.
 */
function morph(oldNode, newNode) {
    if (oldNode.nodeType !== newNode.nodeType || oldNode.nodeName !== newNode.nodeName) {
        oldNode.parentNode.replaceChild(newNode.cloneNode(true), oldNode);
        return;
    }

    if (oldNode.nodeType === Node.TEXT_NODE) {
        if (oldNode.nodeValue !== newNode.nodeValue) {
            oldNode.nodeValue = newNode.nodeValue;
        }
        return;
    }

    // Skip morphing the currently focused input/select element to prevent cursor jumping
    if (oldNode === document.activeElement) {
        return;
    }

    // Sync attributes
    for (let attr of Array.from(oldNode.attributes)) {
        if (!newNode.hasAttribute(attr.name)) {
            oldNode.removeAttribute(attr.name);
        }
    }
    for (let attr of Array.from(newNode.attributes)) {
        if (oldNode.getAttribute(attr.name) !== attr.value) {
            oldNode.setAttribute(attr.name, attr.value);
        }
    }

    // Sync form inputs safely
    if (oldNode.nodeName === 'INPUT' || oldNode.nodeName === 'SELECT' || oldNode.nodeName === 'TEXTAREA') {
        if (oldNode.value !== newNode.value) {
            oldNode.value = newNode.value;
        }
        if (oldNode.nodeName === 'INPUT' && oldNode.type === 'checkbox') {
            if (oldNode.checked !== newNode.checked) {
                oldNode.checked = newNode.checked;
            }
        }
        return;
    }

    // Sync child nodes recursively
    const oldChildren = Array.from(oldNode.childNodes);
    const newChildren = Array.from(newNode.childNodes);

    const maxLen = Math.max(oldChildren.length, newChildren.length);
    for (let i = 0; i < maxLen; i++) {
        const oldChild = oldChildren[i];
        const newChild = newChildren[i];

        if (!oldChild && newChild) {
            oldNode.appendChild(newChild.cloneNode(true));
        } else if (oldChild && !newChild) {
            oldNode.removeChild(oldChild);
        } else if (oldChild && newChild) {
            morph(oldChild, newChild);
        }
    }
}

/**
 * Surgical DOM Reconciliation
 * Morph the cell container content rather than writing innerHTML to preserve live details toggles
 * and prevent input disruption.
 */
function reconcileCell(container, newHtml, force = false) {
    if (!container) return;
    
    // 1. If nothing changed, do nothing
    const currentHtml = container.innerHTML;
    if (!force && currentHtml === newHtml) return;

    // 2. Parse newHtml string into a DOM node
    const parser = new DOMParser();
    const doc = parser.parseFromString(newHtml, 'text/html');
    const newDom = doc.body.firstElementChild;
    if (!newDom) return;

    // 3. Morph container's first child recursively
    const oldDom = container.firstElementChild;
    if (!oldDom) {
        container.innerHTML = newHtml;
    } else {
        morph(oldDom, newDom);
    }
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
        const latencyText = latency.avg_rtt_ms != null ? ` | Cluster RTT avg: ${latency.avg_rtt_ms}ms` : '';
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
            const statusTooltip = `
                <span class="tooltip" tabindex="0" aria-label="Status Explanation">
                    <span class="tooltip-icon" style="margin-left: 4px;">?</span>
                    <span class="tooltip-bubble" style="font-weight: normal; color: #000; background: #fff;">
                        <b>Yellow (Ready):</b> Device is online and idle (playback stopped).<br>
                        <b>Green (Syncing):</b> Device is actively playing and synchronizing with the Leader.<br>
                        <b>Blue (Leading):</b> This is the Leader node directing the cluster.<br>
                        <b>Red (Offline):</b> Device is disconnected or unreachable.
                    </span>
                </span>
            `;
            
            const newSummaryHtml = `
                <div class="cell-container">
                    <div class="device-summary-primary">${escapeHtml(device.label)}</div>
                    <div class="device-summary-line device-summary-status ${getStatusClass(device)}">
                        ${escapeHtml(statusText)}
                        ${statusTooltip}
                    </div>
                    <div class="device-summary-line device-summary-role">${escapeHtml(device.role)}</div>
                    ${device.video_driver ? `<div class="device-summary-line device-summary-driver">Driver: ${escapeHtml(device.video_driver)}</div>` : ''}
                    ${device.pi_model ? `<div class="device-summary-line device-summary-model">${escapeHtml(device.pi_model)}</div>` : ''}
                    <div class="device-summary-line device-summary-ip">${escapeHtml(device.ip)}</div>
                    <div class="device-summary-line device-summary-latency">${escapeHtml(latencyText)}</div>
                    ${device.sync_deviation != null ? `<div class="device-summary-line device-summary-deviation">Dev: ${device.sync_deviation > 0 ? '+' : ''}${device.sync_deviation.toFixed(3)}s</div>` : ''}
                    ${device.playback_rate != null ? `<div class="device-summary-line device-summary-rate">Rate: ${device.playback_rate.toFixed(4)}x</div>` : ''}
                    ${device.role === 'collaborator' ? `<div class="device-summary-line device-summary-seeks">Hard Seeks: ${device.hard_seeks || 0}</div>` : ''}
                    ${device.video_file ? `
                    <div class="device-summary-line device-summary-playing" style="margin-top: 4px; font-size: 11px; color: #555;">
                        Playing: <b>${escapeHtml(device.video_file)}</b> 
                        ${device.is_optimized ? '<span class="optimized-badge" style="margin-left:4px;">HEVC</span>' : '<span class="not-optimized-badge" style="margin-left:4px;">Non-HEVC</span>'}
                    </div>` : ''}
                    <div class="device-summary-actions">
                        <button class="btn-small view-logs-btn" data-device-id="${device.device_id}">View Logs</button>
                        ${device.device_id !== 'remote-leader' ? `<button class="btn-small update-device-btn" data-device-id="${device.device_id}">Update & Reboot</button>` : ''}
                    </div>
                </div>
            `;
            if (cells[0].innerHTML !== newSummaryHtml) {
                cells[0].innerHTML = newSummaryHtml;
            }

            // Re-apply updating state after innerHTML replacement
            if (updatingDevices.has(device.device_id)) {
                const btn = row.querySelector('.update-device-btn');
                if (btn) {
                    btn.disabled = true;
                    btn.textContent = 'Updating...';
                }
            }

            // 2. Update Config Cell (Surgical)
            const snapshotTime = device.config?.updated_at || 0;
            const saveTime = lastSaveAt.get(device.device_id) || 0;
            if (saveTime > 0) {
                const isPending = saveTime > snapshotTime && (Date.now() / 1000 - saveTime < 8);
                if (!isPending && snapshotTime >= saveTime) {
                    draftConfigValues.delete(device.device_id);
                    lastSaveAt.delete(device.device_id);
                }
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

            // Update Media Toggle State
            const mediaPanel = cells[2].querySelector('.media-panel');
            if (mediaPanel && !mediaPanel.dataset.bound) {
                mediaPanel.addEventListener('toggle', () => {
                    if (mediaPanel.open) openMediaPanels.add(device.device_id);
                    else openMediaPanels.delete(device.device_id);
                });
                mediaPanel.dataset.bound = "true";
            }
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
    // Devices restart after applying a config update; re-pull their config
    // once they're back up so the panel shows what was actually persisted.
    if (deviceId !== 'remote-leader') {
        setTimeout(() => requestConfig(deviceId), 4000);
        setTimeout(() => requestConfig(deviceId), 9000);
    }
}

async function loadDefaults(deviceId) {
    if (!confirm('Reset this device to defaults?')) {
        return;
    }
    draftConfigValues.delete(deviceId);
    await postJson('/api/config/reset', { device_id: deviceId });
    setTimeout(refresh, 500);
}

function isEditingForm() {
    const ae = document.activeElement;
    if (!ae || !ae.closest) return false;
    return !!ae.closest('.config-panel form');
}

async function refresh() {
    // Don't re-render anything while the user is editing a config field -
    // the periodic refresh was clobbering in-progress edits.
    if (isEditingForm()) return;
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

    const rows = document.getElementById('deviceRows');
    if (rows) {
        rows.addEventListener('click', (e) => {
            const viewBtn = e.target.closest('.view-logs-btn');
            if (viewBtn) {
                viewDeviceLogs(viewBtn.dataset.deviceId);
                return;
            }
            const updateBtn = e.target.closest('.update-device-btn');
            if (updateBtn) {
                const deviceId = updateBtn.dataset.deviceId;
                if (!updatingDevices.has(deviceId)) {
                    updateDevice(deviceId, updateBtn);
                }
            }
        });
    }
});

let activeLogDeviceId = null;

async function viewDeviceLogs(deviceId) {
    activeLogDeviceId = deviceId;
    const modal = document.getElementById('logModal');
    const title = document.getElementById('logModalTitle');
    const body = document.getElementById('logModalBody');
    
    if (modal && title && body) {
        title.textContent = `Logs for ${deviceId}`;
        body.textContent = 'Loading logs...';
        modal.style.display = 'block';
        
        try {
            const response = await fetch(`/api/logs?device_id=${encodeURIComponent(deviceId)}`);
            if (response.ok) {
                const data = await response.json();
                body.textContent = data.logs || 'No logs returned.';
                body.scrollTop = body.scrollHeight;
            } else {
                const data = await response.json();
                body.textContent = `Error loading logs: ${data.message || 'Unknown error'}`;
            }
        } catch (err) {
            body.textContent = `Error: ${err.message}`;
        }
    }
}

function updateDevice(deviceId, btn) {
    console.log('updateDevice called for', deviceId);
    updatingDevices.add(deviceId);
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Updating...';
    }
    postJson('/api/device/update', { device_id: deviceId }).then(() => {
        console.log('updateDevice: POST succeeded for', deviceId);
        setTimeout(() => {
            updatingDevices.delete(deviceId);
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Update & Reboot';
            }
        }, 10000);
    }).catch((err) => {
        console.error('updateDevice: POST failed for', deviceId, err);
        updatingDevices.delete(deviceId);
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Update & Reboot';
        }
    });
}

function closeLogModal() {
    const modal = document.getElementById('logModal');
    if (modal) {
        modal.style.display = 'none';
    }
    activeLogDeviceId = null;
}

async function refreshLogs() {
    if (activeLogDeviceId) {
        await viewDeviceLogs(activeLogDeviceId);
    }
}

window.addEventListener('click', (event) => {
    const modal = document.getElementById('logModal');
    if (event.target === modal) {
        closeLogModal();
    }
});

window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeLogModal();
    }
});

function copyLogs() {
    const body = document.getElementById('logModalBody');
    const copyBtn = document.getElementById('copyLogsBtn');
    if (body) {
        navigator.clipboard.writeText(body.textContent)
            .then(() => {
                if (copyBtn) {
                    const originalText = copyBtn.textContent;
                    copyBtn.textContent = 'Copied!';
                    setTimeout(() => {
                        copyBtn.textContent = originalText;
                    }, 2000);
                }
            })
            .catch(err => {
                alert('Failed to copy logs: ' + err);
            });
    }
}

function toggleMediaInfo(event, infoId) {
    event.preventDefault();
    const el = document.getElementById(infoId);
    if (el) {
        const isHidden = el.style.display === 'none';
        el.style.display = isHidden ? 'block' : 'none';
        if (isHidden) {
            openInfoPanels.add(infoId);
        } else {
            openInfoPanels.delete(infoId);
        }
    }
}
