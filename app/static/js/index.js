const resultDiv = document.getElementById('result');
let currentOptimizedDockerfile = '';
let currentDockerignore = '';

// Debug layout: logs sizes of textarea/card/section on load to help diagnose width issues
document.addEventListener('DOMContentLoaded', () => {
    try {
        const el = document.getElementById('dockerfileText');
        const card = el ? el.closest('.card') : null;
        const section = el ? el.closest('.section') : null;
        console.log('layout-debug: body', document.body.getBoundingClientRect().width);
        if (section) console.log('layout-debug: section', section.getBoundingClientRect());
        if (card) console.log('layout-debug: card', card.getBoundingClientRect());
        if (el) console.log('layout-debug: textarea', el.getBoundingClientRect(), 'computed-width', window.getComputedStyle(el).width);

        // Wire up includeDockerignore checkbox to show/hide download button
        const chk = document.getElementById('includeDockerignore');
        const dlBtn = document.getElementById('download-dockerignore-btn');
        function updateDockerignoreBtn(e) {
            if (!dlBtn) return;
            const show = chk ? chk.checked : true;
            dlBtn.style.display = show ? '' : 'none';
            // If the user changed the checkbox and an optimized result is visible, re-run optimization
            if (e && document.getElementById('optimizeResult').style.display !== 'none') {
                // Debounce slightly to allow UI to settle
                setTimeout(() => {
                    const text = document.getElementById('dockerfileText').value.trim();
                    if (text && isValidDockerfile(text)) {
                        optimizeText();
                    }
                }, 50);
            }
        }
        if (chk) {
            chk.addEventListener('change', updateDockerignoreBtn);
        }
        // Initial state
        updateDockerignoreBtn();

        // If ?debug=layout is present in URL, show a small overlay with the same info
        if (window.location.search.includes('debug=layout')) {
            const info = [];
            if (section) info.push('section: ' + Math.round(section.getBoundingClientRect().width) + 'px');
            if (card) info.push('card: ' + Math.round(card.getBoundingClientRect().width) + 'px');
            if (el) info.push('textarea: ' + Math.round(el.getBoundingClientRect().width) + 'px');
            info.push('body: ' + Math.round(document.body.getBoundingClientRect().width) + 'px');
            const panel = document.createElement('div');
            panel.id = 'layout-debug-panel';
            panel.style.position = 'fixed';
            panel.style.right = '12px';
            panel.style.top = '12px';
            panel.style.zIndex = '9999';
            panel.style.background = 'rgba(0,0,0,0.75)';
            panel.style.color = '#fff';
            panel.style.padding = '8px 10px';
            panel.style.fontSize = '12px';
            panel.style.borderRadius = '4px';
            panel.style.fontFamily = 'monospace';
            panel.textContent = info.join(' | ');
            document.body.appendChild(panel);
        }
    } catch (e) {
        console.log('layout-debug error', e);
    }
});

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('fileTab').style.display = tab === 'file' ? 'block' : 'none';
    document.getElementById('textTab').style.display = tab === 'text' ? 'block' : 'none';
}

async function analyzeFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();
        displayResults(data);
    } catch (err) {
        alert('Error analyzing Dockerfile: ' + err.message);
    }
}




function isValidDockerfile(text) {
    const lines = text.split('\n').map(l => l.trim());
    // Must have at least one FROM instruction
    const hasFrom = lines.some(l => /^FROM\s/i.test(l));
    // Check if it looks like a Dockerfile: at least 2 non-empty, non-comment lines with valid instructions
    const hasValidInstructions = lines.filter(l => l && !l.startsWith('#') && !l.startsWith('//')).some(l =>
        /^(FROM|RUN|COPY|ADD|ENV|CMD|LABEL|EXPOSE|WORKDIR|ARG|USER|VOLUME|STOPSIGNAL|HEALTHCHECK|SHELL|MAINTAINER|ONBUILD)/i.test(l)
    );
    return hasFrom && hasValidInstructions && lines.filter(l => l && !l.startsWith('#')).length >= 2;
}

async function analyzeText() {
    const text = document.getElementById('dockerfileText').value.trim();
    if (!text) return alert('Please paste Dockerfile content first');

    if (!isValidDockerfile(text)) {
        return alert('⚠️ Invalid Dockerfile: the content does not appear to be a valid Dockerfile.\n\nA valid Dockerfile should:\n• Start with a FROM instruction\n• Contain valid Dockerfile instructions (FROM, RUN, COPY, ENV, CMD, etc.)\n• Have at least 2 non-empty lines');
    }

    try {
        const response = await fetch('/api/analyze/text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dockerfile_content: text }),
        });
        if (!response.ok) {
            const errText = await response.text();
            return alert('Ошибка сервера (' + response.status + '): ' + errText);
        }
        const data = await response.json();
        displayResults(data);
    } catch (err) {
        alert('Ошибка анализа: ' + err.message);
    }
}

async function optimizeText() {
    const text = document.getElementById('dockerfileText').value.trim();
    if (!text) return alert('Please paste Dockerfile content first');

    if (!isValidDockerfile(text)) {
        return alert('⚠️ Invalid Dockerfile: the content does not appear to be a valid Dockerfile.\n\nA valid Dockerfile should:\n• Start with a FROM instruction\n• Contain valid Dockerfile instructions (FROM, RUN, COPY, ENV, CMD, etc.)\n• Have at least 2 non-empty lines');
    }

    const optimizeResultDiv = document.getElementById('optimizeResult');
    optimizeResultDiv.style.display = 'block';
    document.getElementById('optimize-meta').innerHTML = '<span class="loading">Generating optimized Dockerfile...</span>';

    try {
        const includeDockerignore = (() => {
            const el = document.getElementById('includeDockerignore');
            return el ? el.checked : true;
        })();
        const response = await fetch('/api/optimize/text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dockerfile_content: text, include_dockerignore: includeDockerignore }),
        });
        if (!response.ok) {
            const errText = await response.text();
            return alert('Ошибка сервера (' + response.status + '): ' + errText);
        }
        const data = await response.json();
        displayOptimizeResults(data);
    } catch (err) {
        alert('Ошибка оптимизации: ' + err.message);
    }
}

function displayResults(data) {
    resultDiv.style.display = 'block';

    const meta = document.getElementById('meta');
    meta.innerHTML = `
        <span>Base: ${data.base_image || '—'}</span>
        <span>Tag: ${data.base_tag || '—'}</span>
        <span>RUN: ${data.run_count}</span>
        <span>COPY: ${data.copy_count}</span>
        <span>ADD: ${data.add_count}</span>
    `;

    const issuesDiv = document.getElementById('issues');
    if (data.issues.length === 0) {
        issuesDiv.innerHTML = '<p class="status-line" style="color:#22c55e;"><svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg><span>No issues found! Your Dockerfile looks good.</span></p>';
    } else {
        issuesDiv.innerHTML = data.issues.map(issue => `
            <div class="issue ${issue.level}">
                <div class="level">${issue.level}${issue.line ? ' — Line ' + issue.line : ''}</div>
                <div>${issue.message}</div>
            </div>
        `).join('');
    }

    // Multi-stage build suggestion
    const msDiv = document.getElementById('ms-suggestion');
    if (data.multi_stage_suggestion) {
        msDiv.innerHTML = `
            <div class="ms-title"><svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 18h6M10 22h4M12 2a6 6 0 0 0-4 10v2h8v-2a6 6 0 0 0-4-10z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg><span>Multi-stage build suggestion (~${data.multi_stage_savings_pct}% smaller)</span></div>
            <div class="ms-changes">
                ${data.multi_stage_changes.map(c => `<span class="ms-change">• ${escapeHtml(c)}</span>`).join('')}
            </div>
            <div class="ms-dockerfile">
                <pre><code class="language-dockerfile">${escapeHtml(data.multi_stage_suggestion)}</code></pre>
            </div>
        `;
        // highlight ms suggestion
        try { const msCode = msDiv.querySelector('.ms-dockerfile pre code'); if (window.hljs && msCode) hljs.highlightElement(msCode); } catch(e){}
    } else {
        msDiv.innerHTML = '';
    }

    document.getElementById('optimizeResult').style.display = 'none';
}

function renderHighlightedCode(element, text) {
    if (!element) return;

    // highlight.js marks processed nodes and skips them on subsequent calls.
    // Clear that state before replacing/re-highlighting the text.
    element.removeAttribute('data-highlighted');
    element.classList.remove('hljs');
    element.textContent = text || '';

    if (window.hljs && typeof window.hljs.highlightElement === 'function') {
        try {
            window.hljs.highlightElement(element);
        } catch (error) {
            console.warn('Could not highlight Dockerfile code block', error);
        }
    }
}

function displayOptimizeResults(data) {
    const meta = document.getElementById('optimize-meta');
    const originalSize = formatSize(data.original_size);
    const optimizedSize = formatSize(data.estimated_size);
    const savings = Math.max(0, Math.round((1 - data.estimated_size / data.original_size) * 100));

    // Store dockerignore (may be empty when not included)
    currentDockerignore = data.dockerignore || '';
    // Update download button visibility based on checkbox and presence
    const dlBtn = document.getElementById('download-dockerignore-btn');
    const chk = document.getElementById('includeDockerignore');
    if (dlBtn) {
        const show = (chk ? chk.checked : true) && !!currentDockerignore;
        dlBtn.style.display = show ? '' : 'none';
    }

    meta.innerHTML = `
        <span class="size-badge original">Original: ${originalSize}</span>
        <span class="size-badge optimized">Estimated: ${optimizedSize}</span>
        <span class="size-badge" style="background:#dbeafe;color:#2563eb;">~${savings}% smaller</span>
    `;

    const origEl = document.getElementById('original-code');
    renderHighlightedCode(origEl, data.original_dockerfile);
    // Keep the displayed/downloaded Dockerfile in sync with the checkbox even if an
    // older backend response returns dockerignore separately from optimized_dockerfile.
    const includeChk = document.getElementById('includeDockerignore');
    const includeDockerignore = includeChk ? includeChk.checked : true;
    const dockerignoreMarker = '# === Recommended .dockerignore ===';
    let optimizedText = data.optimized_dockerfile || '';
    if (!includeDockerignore) {
        if (optimizedText.includes(dockerignoreMarker)) {
            optimizedText = optimizedText.split(dockerignoreMarker)[0].trimEnd();
        }
    } else if (currentDockerignore && !optimizedText.includes(dockerignoreMarker)) {
        optimizedText = `${optimizedText.trimEnd()}\n\n${dockerignoreMarker}\n${currentDockerignore}`;
    }
    // Normalize newlines: collapse multiple consecutive blank lines into a single blank line
    optimizedText = optimizedText.replace(/\r\n/g, "\n");
    optimizedText = optimizedText.replace(/\n\s*\n(\s*\n)*/g, "\n\n");
    // Trim extra leading/trailing blank lines
    optimizedText = optimizedText.replace(/^\s+\n/, '');
    optimizedText = optimizedText.replace(/\n\s+$/g, '\n');

    const optEl = document.getElementById('optimized-code');
    renderHighlightedCode(optEl, optimizedText);
    currentOptimizedDockerfile = optimizedText;

    const changesDiv = document.getElementById('changes-list');
    if (data.changes.length === 0) {
        changesDiv.innerHTML = '<p class="status-line" style="color:#22c55e;"><svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg><span>No changes needed — your Dockerfile is already optimized!</span></p>';
    } else {
        changesDiv.innerHTML = '<p style="margin-bottom:0.5rem;font-weight:600;">Applied optimizations:</p>' +
            '<ul class="changes-list">' +
            data.changes.map(c => `<li>${c}</li>`).join('') +
            '</ul>';
    }
}

function formatSize(bytes) {
    if (bytes >= 1024) return Math.round(bytes / 1024) + 'KB';
    return bytes + 'B';
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;').replace(/"/g, '&quot;');
}

function showToast(msg) {
    try {
        const t = document.createElement('div');
        t.className = 'toast-message';
        t.textContent = msg;
        t.style.position = 'fixed';
        t.style.right = '12px';
        t.style.bottom = '80px';
        t.style.background = 'rgba(0,0,0,0.8)';
        t.style.color = '#fff';
        t.style.padding = '8px 12px';
        t.style.borderRadius = '6px';
        t.style.zIndex = 99999;
        document.body.appendChild(t);
        setTimeout(() => { t.style.transition = 'opacity 0.4s'; t.style.opacity = '0'; setTimeout(()=>t.remove(),400); }, 1400);
    } catch(e){ console.log(e); }
}

function copyTextToClipboard(text) {
    if (!navigator.clipboard) {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); showToast('Copied'); } catch(e){ alert('Copy failed'); }
        ta.remove();
        return;
    }
    navigator.clipboard.writeText(text).then(()=> showToast('Copied to clipboard')).catch(()=> alert('Copy failed'));
}

function copyOriginal(){
    const el = document.getElementById('original-code');
    if (el) copyTextToClipboard(el.textContent || el.innerText || '');
}
function copyOptimized(){
    const el = document.getElementById('optimized-code');
    if (el) copyTextToClipboard(el.textContent || el.innerText || '');
}

function downloadDockerfile() {
    const blob = new Blob([currentOptimizedDockerfile], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = 'Dockerfile.optimized';
    document.body.appendChild(a);
    a.click();
    // Revoke and remove after a short delay to avoid incomplete/partial downloads (.crdownload)
    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 250);
}

async function downloadDockerignore() {
    // If we have dockerignore from optimization, use it
    if (currentDockerignore) {
        const blob = new Blob([currentDockerignore], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = '.dockerignore';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 250);
        return;
    }
    // Otherwise fetch from API
    const resp = await fetch('/api/dockerignore');
    if (!resp.ok) return alert('Failed to download .dockerignore');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = '.dockerignore';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 250);
}

function loadTemplate(event) {
    try {
        const btn = event.currentTarget || event.target;
        const url = btn && btn.dataset && btn.dataset.template;
        if (!url) return;
        fetch(url).then(resp => {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.text();
        }).then(txt => {
            const ta = document.getElementById('dockerfileText');
            if (ta) {
                ta.value = txt;
                ta.focus();
                showToast('Template loaded');
            }
        }).catch(err => {
            console.error('loadTemplate error', err);
            alert('Failed to load template: ' + err.message);
        });
    } catch (e) {
        console.error(e);
        alert('Failed to load template');
    }
}

