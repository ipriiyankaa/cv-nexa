let chartInstance = null;
let currentBatchData = [];
let currentSortOrder = 'asc';

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function switchTab(tabId, btnElement) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.add('hidden'));
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(tabId).classList.remove('hidden');
    btnElement.classList.add('active');
    if (tabId === 'history-tab') renderHistory();
}

document.getElementById('resume').addEventListener('change', function () {
    if (this.files[0]) {
        document.getElementById('singleFileName').innerText = "Selected: " + this.files[0].name;
    }
});

document.getElementById('batchResumes').addEventListener('change', function () {
    if (this.files.length > 0) {
        document.getElementById('batchFileCount').innerText = `${this.files.length} resumes selected for ranking`;
    }
});

document.getElementById('analyzerForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    const btn = document.getElementById('submitBtn');
    const resumeFile = document.getElementById('resume').files[0];
    const jd = document.getElementById('jd').value;
    if (!resumeFile) return alert("Please select a resume file.");

    btn.innerText = "Running Deep NLP Audit...";
    btn.disabled = true;

    const formData = new FormData();
    formData.append('resume', resumeFile);
    formData.append('job_description', jd);

    try {
        const res = await fetch('/analyze', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.error) return alert(data.error);

        document.getElementById('results').classList.remove('hidden');
        document.getElementById('score').innerText = data.match_score;

        const verdict = document.getElementById('scoreVerdict');
        if (data.match_score >= 75) verdict.innerText = "🔥 Strong ATS Match (Shortlist Ready)";
        else if (data.match_score >= 50) verdict.innerText = "⚡ Moderate Match (Needs Optimization)";
        else verdict.innerText = "⚠️ Low Match (High Skill Gap)";

        renderBadges('matchedList', data.matched_keywords);
        renderBadges('missingList', data.missing_keywords);
        document.getElementById('aiContent').innerText = data.ai_insights;
        renderChart(data.breakdown);
        saveToHistory(data.filename, data.match_score);
        document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        alert("Server connection error.");
    } finally {
        btn.innerText = "Run Deep ATS Scan ⚡";
        btn.disabled = false;
    }
});

document.getElementById('batchForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    const btn = document.getElementById('batchSubmitBtn');
    const files = document.getElementById('batchResumes').files;
    const jd = document.getElementById('batchJd').value;
    if (files.length === 0) return alert("Select at least one resume.");

    btn.innerText = `Scanning & Ranking ${files.length} Resumes...`;
    btn.disabled = true;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('resumes', files[i]);
    }
    formData.append('job_description', jd);

    try {
        const res = await fetch('/analyze-batch', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.error) return alert(data.error);

        currentBatchData = data.ranked_resumes;
        document.getElementById('batchResults').classList.remove('hidden');
        sortBatchData('asc');
    } catch (err) {
        alert("Batch analysis failed.");
    } finally {
        btn.innerText = "Analyze & Rank All Resumes 🚀";
        btn.disabled = false;
    }
});

function sortBatchData(order) {
    currentSortOrder = order;
    document.getElementById('sortAscBtn').classList.toggle('active', order === 'asc');
    document.getElementById('sortDescBtn').classList.toggle('active', order === 'desc');

    const sorted = [...currentBatchData].sort((a, b) =>
        order === 'asc' ? a.score - b.score : b.score - a.score
    );
    const tbody = document.getElementById('batchTableBody');
    tbody.innerHTML = sorted.map((item, idx) => `
        <tr>
            <td>#${idx + 1}</td>
            <td><strong>${escapeHtml(item.filename)}</strong></td>
            <td><span class="score-pill">${item.score}%</span></td>
            <td>${item.keyword_score}%</td>
            <td>${item.matched_count} matched / ${item.missing_count} missing</td>
            <td>${escapeHtml(item.top_skills.join(', ') || 'None')}</td>
        </tr>
    `).join('');
}

function exportBatchCSV() {
    if (!currentBatchData.length) return;
    const sorted = [...currentBatchData].sort((a, b) =>
        currentSortOrder === 'asc' ? a.score - b.score : b.score - a.score
    );
    let csv = "Rank,Filename,Overall_ATS_Score,Keyword_Match_Score,Matched_Count,Missing_Count,Top_Skills\n";
    sorted.forEach((row, i) => {
        const safeName = row.filename.replace(/"/g, '""');
        const safeSkills = row.top_skills.join('; ').replace(/"/g, '""');
        csv += `${i + 1},"${safeName}",${row.score}%,${row.keyword_score}%,${row.matched_count},${row.missing_count},"${safeSkills}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ranked_resumes_${currentSortOrder}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

async function rewriteBullet() {
    const input = document.getElementById('bulletInput').value;
    const btn = document.getElementById('rewriteBtn');
    if (!input.trim()) return alert("Enter a bullet point first.");

    btn.innerText = "Optimizing...";
    btn.disabled = true;

    try {
        const res = await fetch('/rewrite-bullet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bullet: input })
        });
        const data = await res.json();
        if (data.error) return alert(data.error);

        document.getElementById('rewrittenOutput').classList.remove('hidden');
        document.getElementById('rewrittenText').innerText = data.rewritten;
    } catch (e) {
        alert("Failed to rewrite.");
    } finally {
        btn.innerText = "Rewrite with STAR Method ✨";
        btn.disabled = false;
    }
}

 
function saveToHistory(filename, score) {
    const history = JSON.parse(localStorage.getItem('ats_history') || '[]');
    history.unshift({ filename, score, date: new Date().toLocaleString() });
    localStorage.setItem('ats_history', JSON.stringify(history.slice(0, 15)));
}

function renderHistory() {
    const history = JSON.parse(localStorage.getItem('ats_history') || '[]');
    const container = document.getElementById('historyContainer');
    if (!history.length) {
        container.innerHTML = '<p style="color:#64748b; font-size:13px;">No scans recorded yet. Run an analysis to save logs here.</p>';
        return;
    }
    container.innerHTML = history.map(item => `
        <div class="history-item">
            <div>
                <strong>📄 ${escapeHtml(item.filename)}</strong>
                <p style="font-size:11px; color:#94a3b8; margin-top:3px;">Scanned on: ${escapeHtml(item.date)}</p>
            </div>
            <span class="score-pill">${item.score}% ATS Score</span>
        </div>
    `).join('');
}

function clearHistory() {
    localStorage.removeItem('ats_history');
    renderHistory();
}

function copyText(elementId, btn) {
    const text = document.getElementById(elementId).innerText;
    navigator.clipboard.writeText(text);
    const old = btn.innerText;
    btn.innerText = "✅ Copied!";
    setTimeout(() => { btn.innerText = old; }, 2000);
}

function renderBadges(id, list) {
    const el = document.getElementById(id);
    el.innerHTML = list.length
        ? list.map(k => `<span class="badge">${escapeHtml(k)}</span>`).join(' ')
        : '<em>None</em>';
}

function renderChart(breakdown) {
    const ctx = document.getElementById('scoreChart').getContext('2d');
    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['Keywords & Phrases', 'Formatting', 'Action Verbs', 'Impact Metrics'],
            datasets: [{
                data: [
                    breakdown.keyword_score,
                    breakdown.formatting_score,
                    breakdown.action_verbs_score,
                    breakdown.metrics_score
                ],
                backgroundColor: 'rgba(99, 102, 241, 0.25)',
                borderColor: '#6366f1',
                pointBackgroundColor: '#a855f7'
            }]
        },
        options: {
            scales: {
                r: {
                    angleLines: { color: 'rgba(255,255,255,0.1)' },
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    pointLabels: { color: '#94a3b8' },
                    ticks: { display: false, beginAtZero: true, max: 100 }
                }
            },
            plugins: { legend: { display: false } }
        }
    });
}
