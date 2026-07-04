// State
let pairs = [];
let config = {};
let editingIndex = null;
let selectedIndices = new Set();
let isRunning = false;
let pollTimer = null;
let dragFromIndex = -1;

// ========== API Helper ==========
async function api(method, ...args) {
    try {
        return await pywebview.api[method](...args);
    } catch (e) {
        console.error(`API error: ${method}`, e);
        return null;
    }
}

async function apiGet(method) {
    try {
        return await pywebview.api[method]();
    } catch (e) {
        console.error(`API error: ${method}`, e);
        return null;
    }
}

// ========== Tab Switching ==========
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    });
});

// ========== Theme ==========
function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.getElementById('theme-' + theme).checked = true;
    api('set_theme', theme);
}

// ========== Game List (Run Tab) ==========
function renderGameList() {
    const container = document.getElementById('game-list');
    container.innerHTML = '';
    pairs.forEach((pair, i) => {
        const toolExe = pair.tool ? (pair.tool.executable || '').split(/[/\\]/).pop() : '';
        const cli = pair.tool ? (pair.tool.cli_args || '') : '';
        const desc = (toolExe + ' ' + cli).trim();
        const isSelected = selectedIndices.has(i);

        const item = document.createElement('div');
        item.className = 'game-item' + (isSelected ? ' selected' : '');
        item.dataset.index = i;
        item.draggable = true;
        item.innerHTML = `
            <span class="drag-handle">⋮</span>
            <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelect(${i}, this.checked)">
            <div class="info">
                <div class="name">${escHtml(pair.name)}</div>
                ${desc ? `<span class="desc">${escHtml(desc)}</span>` : ''}
            </div>
            <span class="status" id="status-${i}">等待</span>
        `;

        // Click to toggle selection
        item.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.classList.contains('drag-handle')) return;
            const cb = item.querySelector('input[type="checkbox"]');
            cb.checked = !cb.checked;
            toggleSelect(i, cb.checked);
        });

        // HTML5 Drag and Drop
        item.addEventListener('dragstart', (e) => {
            dragFromIndex = i;
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', String(i));
        });

        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            dragFromIndex = -1;
            container.querySelectorAll('.game-item').forEach(el => el.classList.remove('drag-over'));
            const indicator = container.querySelector('.drag-indicator');
            if (indicator) indicator.remove();
        });

        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            container.querySelectorAll('.drag-indicator').forEach(el => el.remove());
            const rect = item.getBoundingClientRect();
            const midY = rect.top + rect.height / 2;
            const indicator = document.createElement('div');
            indicator.className = 'drag-indicator';
            if (e.clientY < midY) {
                item.parentNode.insertBefore(indicator, item);
            } else {
                item.parentNode.insertBefore(indicator, item.nextSibling);
            }
        });

        item.addEventListener('dragleave', (e) => {
            if (!item.contains(e.relatedTarget)) {
                const indicator = item.querySelector('.drag-indicator');
                if (indicator) indicator.remove();
            }
        });

        item.addEventListener('drop', (e) => {
            e.preventDefault();
            const fromIndex = dragFromIndex;
            const indicators = container.querySelectorAll('.drag-indicator');
            let toIndex = i;
            if (indicators.length > 0) {
                const rect = item.getBoundingClientRect();
                const midY = rect.top + rect.height / 2;
                toIndex = e.clientY < midY ? i : i + 1;
            }
            indicators.forEach(el => el.remove());
            if (fromIndex >= 0 && fromIndex !== toIndex && fromIndex !== toIndex - 1) {
                reorderPairs(fromIndex, toIndex > fromIndex ? toIndex - 1 : toIndex);
            }
        });

        container.appendChild(item);
    });
    updateStatus();
}

function toggleSelect(index, checked) {
    if (checked) selectedIndices.add(index);
    else selectedIndices.delete(index);
    renderGameList();
}

function selectAll() {
    pairs.forEach((_, i) => selectedIndices.add(i));
    renderGameList();
}

function invertSelection() {
    const newSet = new Set();
    pairs.forEach((_, i) => {
        if (!selectedIndices.has(i)) newSet.add(i);
    });
    selectedIndices = newSet;
    renderGameList();
}

async function reorderPairs(from, to) {
    const item = pairs.splice(from, 1)[0];
    pairs.splice(to, 0, item);
    const newSelected = new Set();
    selectedIndices.forEach(i => {
        if (i === from) newSelected.add(to);
        else if (from < to && i > from && i <= to) newSelected.add(i - 1);
        else if (from > to && i >= to && i < from) newSelected.add(i + 1);
        else newSelected.add(i);
    });
    selectedIndices = newSelected;
    await api('reorder_pairs', pairs.map(p => p.name));
    renderGameList();
}

function updateStatus() {
    const el = document.getElementById('status-text');
    el.textContent = `共 ${pairs.length} 组游戏`;
}

function setStatus(index, text, color) {
    const el = document.getElementById('status-' + index);
    if (el) {
        el.textContent = text;
        el.style.color = color || '';
    }
}

// ========== Log ==========
function appendLog(message, level) {
    const area = document.getElementById('log-area');
    const now = new Date();
    const time = now.toTimeString().slice(0, 8);
    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-${level || 'INFO'}">${escHtml(message)}</span>`;
    area.appendChild(line);
    area.scrollTop = area.scrollHeight;
}

function clearLog() {
    document.getElementById('log-area').innerHTML = '';
}

async function openLogDir() {
    await api('open_log_dir');
}

// ========== Config Tab ==========
function renderConfigList() {
    const container = document.getElementById('config-list');
    container.innerHTML = '';
    pairs.forEach((pair, i) => {
        const item = document.createElement('div');
        item.className = 'list-item' + (editingIndex === i ? ' active' : '');
        item.textContent = pair.name;
        item.onclick = () => selectConfig(i);
        container.appendChild(item);
    });
}

function selectConfig(index) {
    editingIndex = index;
    loadForm();
    renderConfigList();
}

function loadForm() {
    if (editingIndex === null || editingIndex >= pairs.length) return;
    const pair = pairs[editingIndex];
    const game = pair.game || {};
    const tool = pair.tool || {};
    const launcher = pair.launcher || {};

    document.getElementById('f-name').value = pair.name || '';
    document.getElementById('f-game-exe').value = game.executable || '';
    document.getElementById('f-game-auto').checked = game.auto_start || false;
    document.getElementById('f-tool-exe').value = tool.executable || '';
    document.getElementById('f-tool-dir').value = tool.working_dir || '';
    document.getElementById('f-tool-args').value = tool.cli_args || '';
    document.getElementById('f-tool-wait').checked = tool.wait_for_exit !== false;
    document.getElementById('f-tool-timeout').value = tool.timeout || 1800;
    document.getElementById('f-tool-process').value = tool.process_name || '';
    document.getElementById('f-launcher-exe').value = launcher.executable || '';
}

function saveFormToPair() {
    if (editingIndex === null || editingIndex >= pairs.length) return;
    const pair = pairs[editingIndex];
    pair.name = document.getElementById('f-name').value;
    pair.game = {
        executable: document.getElementById('f-game-exe').value,
        auto_start: document.getElementById('f-game-auto').checked,
    };
    pair.tool = {
        executable: document.getElementById('f-tool-exe').value,
        working_dir: document.getElementById('f-tool-dir').value,
        cli_args: document.getElementById('f-tool-args').value,
        wait_for_exit: document.getElementById('f-tool-wait').checked,
        timeout: parseInt(document.getElementById('f-tool-timeout').value) || 1800,
        process_name: document.getElementById('f-tool-process').value,
    };
    const launcherExe = document.getElementById('f-launcher-exe').value;
    if (launcherExe) {
        pair.launcher = { executable: launcherExe };
    }
}

function onNameChange() {
    if (editingIndex !== null && editingIndex < pairs.length) {
        pairs[editingIndex].name = document.getElementById('f-name').value;
        renderConfigList();
        renderGameList();
    }
}

async function addPair() {
    const newPair = { name: "新游戏", game: { executable: "" }, tool: { executable: "", working_dir: "", cli_args: "", wait_for_exit: true, timeout: 1800 } };
    pairs.push(newPair);
    editingIndex = pairs.length - 1;
    await api('add_pair', newPair);
    loadForm();
    renderConfigList();
    renderGameList();
}

async function deletePair() {
    if (editingIndex === null) return;
    if (!confirm(`删除 ${pairs[editingIndex].name}？`)) return;
    const name = pairs[editingIndex].name;
    pairs.splice(editingIndex, 1);
    editingIndex = null;
    await api('delete_pair', name);
    if (pairs.length > 0) {
        editingIndex = 0;
        loadForm();
    }
    renderConfigList();
    renderGameList();
}

async function saveConfig() {
    saveFormToPair();
    await api('save_config', JSON.stringify(pairs));
    alert('配置已保存');
}

async function browseFile(targetId) {
    const path = await api('browse_file');
    if (path) document.getElementById(targetId).value = path;
}

async function browseDir(targetId) {
    const path = await api('browse_dir');
    if (path) document.getElementById(targetId).value = path;
}

// ========== Settings ==========
async function saveSettings() {
    const settings = {
        theme: document.querySelector('input[name="theme"]:checked').value,
        auto_start: document.getElementById('s-auto-start').checked,
        auto_execute: document.getElementById('s-auto-execute').checked,
        log_level: document.getElementById('s-log-level').value,
    };
    await api('save_settings', JSON.stringify(settings));
    alert('设置已保存');
}

function loadSettings(appConfig) {
    const app = appConfig.app || {};
    const theme = app.theme || 'dark';
    document.getElementById('theme-' + theme).checked = true;
    setTheme(theme);
    document.getElementById('s-auto-start').checked = app.auto_start || false;
    document.getElementById('s-auto-execute').checked = app.auto_execute || false;
    document.getElementById('s-log-level').value = app.log_level || 'INFO';
}

// ========== Execution ==========
async function startExecution() {
    // Iterate pairs in display order, skip unselected — guarantees UI order
    const selected = [];
    pairs.forEach((pair, i) => {
        if (selectedIndices.has(i)) selected.push({name: pair.name, uiIdx: i});
    });
    if (selected.length === 0) {
        alert('请至少选择一个游戏');
        return;
    }
    isRunning = true;
    document.getElementById('btn-start').disabled = true;
    document.getElementById('btn-stop').disabled = false;
    document.getElementById('status-text').textContent = '运行中...';
    document.getElementById('status-text').style.color = 'var(--accent)';

    selected.forEach(s => setStatus(s.uiIdx, '等待', ''));
    clearLog();
    appendLog(`开始执行 ${selected.length} 组游戏`, 'INFO');

    startPolling();
    api('start', JSON.stringify(selected));
}

async function stopExecution() {
    isRunning = false;
    document.getElementById('btn-start').disabled = false;
    document.getElementById('btn-stop').disabled = true;
    document.getElementById('status-text').textContent = '已停止';
    document.getElementById('status-text').style.color = 'var(--yellow)';
    stopPolling();
    appendLog('用户停止执行', 'WARNING');
    // Reset all game statuses
    pairs.forEach((_, i) => setStatus(i, '已停止', 'var(--yellow)'));
    api('stop');
}

function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollStatus, 500);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

async function pollStatus() {
    if (!isRunning) return;
    const result = await apiGet('poll');
    if (!result) return;

    if (result.logs) {
        result.logs.forEach(([msg, level]) => appendLog(msg, level));
    }
    if (result.statuses) {
        result.statuses.forEach(([idx, text, color]) => setStatus(idx, text, color));
    }
    if (result.done) {
        isRunning = false;
        document.getElementById('btn-start').disabled = false;
        document.getElementById('btn-stop').disabled = true;
        document.getElementById('status-text').textContent = result.message || '执行完成';
        document.getElementById('status-text').style.color = result.error ? 'var(--red)' : 'var(--green)';
        stopPolling();
    }
}

// ========== Utility ==========
function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// ========== Init ==========
function initFromData(data) {
    if (!data) return;
    config = data.config || {};
    pairs = data.pairs || [];
    loadSettings(config);
    selectedIndices = new Set(pairs.map((_, i) => i));
    renderGameList();
    renderConfigList();
}

function tryInit() {
    if (window.__INIT_DATA__) {
        initFromData(window.__INIT_DATA__);
        delete window.__INIT_DATA__;
        return true;
    }
    if (window.pywebview && window.pywebview.api) {
        apiGet('init').then(data => { if (data) initFromData(data); });
        return true;
    }
    return false;
}

if (!tryInit()) {
    window.addEventListener('pywebviewready', tryInit);
    let attempts = 0;
    const poller = setInterval(() => {
        attempts++;
        if (tryInit() || attempts > 100) {
            clearInterval(poller);
        }
    }, 200);
}
