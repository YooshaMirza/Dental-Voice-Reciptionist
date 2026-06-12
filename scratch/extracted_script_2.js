
    // Navigation Routing Tabs
    const menuItems = document.querySelectorAll('.menu-item');
    const views = document.querySelectorAll('.tab-view');
    const tabTitleMain = document.getElementById('tab-title-main');

    menuItems.forEach(item => {
        item.addEventListener('click', () => {
            menuItems.forEach(el => el.classList.remove('active'));
            views.forEach(el => el.classList.remove('active'));
            
            item.classList.add('active');
            const target = item.getAttribute('data-target');
            
            if (target === 'dashboard') {
                document.getElementById('view-dashboard').classList.add('active');
                tabTitleMain.textContent = 'Recent Call Interactions';
            } else if (target === 'patients') {
                document.getElementById('view-patients').classList.add('active');
                tabTitleMain.textContent = 'Registered Clinic Patients';
} else if (target === 'appointments') {
                document.getElementById('view-appointments').classList.add('active');
                tabTitleMain.textContent = 'Scheduled Patient Slots';
            } else if (target === 'dialer') {
                document.getElementById('view-dialer').classList.add('active');
                tabTitleMain.textContent = 'Web Dialer Integration Simulator';
            } else if (target === 'guide') {
                document.getElementById('view-guide').classList.add('active');
                tabTitleMain.textContent = 'DCAI Houston Voice Bot | System Guide';
            } else if (target === 'kb') {
                document.getElementById('view-kb').classList.add('active');
                tabTitleMain.textContent = 'Knowledge Base Manager';
                loadKbRules();
            } else if (target === 'prompts') {
                document.getElementById('view-prompts').classList.add('active');
                tabTitleMain.textContent = 'System Prompts Manager';
                loadSystemPrompts();
            }
        });
    });

    // ── Knowledge Base Management Logic ──────────────────────────────────────
    let kbRules = [];
    let kbFilter = 'all';

    const kbModalOverlay = document.getElementById('kb-modal-overlay');
    const kbRuleForm = document.getElementById('kb-rule-form');
    const btnAddKbRule = document.getElementById('btn-add-kb-rule');
    const kbModalClose = document.getElementById('kb-modal-close');
    const btnCancelKbModal = document.getElementById('btn-cancel-kb-modal');
    const kbSearchInput = document.getElementById('kb-search-input');
    const kbCategorySelect = document.getElementById('kb-category');
    const pricingFields = document.getElementById('pricing-specific-fields');

    // Load KB Rules from API
    async function loadKbRules() {
        const container = document.getElementById('kb-rules-container');
        if (!container) return;
        container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: var(--text-muted); padding: 3rem;">Loading Knowledge Base rules...</div>';
        
        try {
            const resp = await fetch('/api/voice-agent/api/kb/');
            const result = await resp.json();
            if (result.success) {
                kbRules = result.data;
                renderKbRules();
            } else {
                container.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: var(--danger); padding: 3rem;">Failed to load rules: ${result.error}</div>`;
            }
        } catch (err) {
            container.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: var(--danger); padding: 3rem;">Error: ${err.message}</div>`;
        }
    }

    // Render KB cards with filtering/search
    window.renderKbRules = function() {
        const container = document.getElementById('kb-rules-container');
        if (!container) return;
        const query = kbSearchInput ? kbSearchInput.value.toLowerCase() : '';
        
        const filtered = kbRules.filter(rule => {
            const catMatch = (kbFilter === 'all' || rule.category === kbFilter);
            const searchMatch = !query || 
                (rule.question && rule.question.toLowerCase().includes(query)) ||
                (rule.answer && rule.answer.toLowerCase().includes(query)) ||
                (rule.keywords && rule.keywords.some(k => k.toLowerCase().includes(query))) ||
                (rule.procedure_name && rule.procedure_name.toLowerCase().includes(query));
            return catMatch && searchMatch;
        });

        if (filtered.length === 0) {
            container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: var(--text-muted); padding: 3rem;">No matching Knowledge Base rules found.</div>';
            return;
        }

        container.innerHTML = filtered.map(rule => {
            const keywordsHtml = rule.keywords && rule.keywords.length > 0 
                ? `<div class="kb-card-keywords">${rule.keywords.map(k => `<span class="kb-keyword-pill">${k}</span>`).join('')}</div>`
                : '';
                
            let pricingInfo = '';
            if (rule.category === 'pricing' && rule.starting_price) {
                pricingInfo = `<div style="font-size:0.75rem; color:var(--accent-purple); font-weight:700; margin-bottom:0.25rem;">Price: $${rule.starting_price}</div>`;
            }

            return `
                <div class="kb-card" data-id="${rule._id}">
                    <div class="kb-card-header">
                        <span class="kb-category-badge badge-cat-${rule.category}">${rule.category}</span>
                        <div class="kb-card-actions">
                            <button class="btn-icon-action" onclick="editKbRule('${rule._id}')" title="Edit Rule">
                                <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" fill="none" stroke="currentColor" stroke-width="2"/></svg>
                            </button>
                            <button class="btn-icon-action delete" onclick="deleteKbRule('${rule._id}')" title="Delete Rule">
                                <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6" fill="none" stroke="currentColor" stroke-width="2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" fill="none" stroke="currentColor" stroke-width="2"/><line x1="10" y1="11" x2="10" y2="17" fill="none" stroke="currentColor" stroke-width="2"/><line x1="14" y1="11" x2="14" y2="17" fill="none" stroke="currentColor" stroke-width="2"/></svg>
                            </button>
                        </div>
                    </div>
                    <div class="kb-card-question">${rule.question}</div>
                    ${pricingInfo}
                    <div class="kb-card-answer">${rule.answer}</div>
                    ${keywordsHtml}
                </div>
            `;
        }).join('');
    };

    // Filter by category pills
    document.querySelectorAll('[data-kb-filter]').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('[data-kb-filter]').forEach(el => el.classList.remove('active'));
            pill.classList.add('active');
            kbFilter = pill.getAttribute('data-kb-filter');
            renderKbRules();
        });
    });

    if (kbSearchInput) {
        kbSearchInput.addEventListener('input', renderKbRules);
    }

    // Modal Control
    window.togglePricingFields = function(category) {
        if (!pricingFields) return;
        if (category === 'pricing') {
            pricingFields.style.display = 'flex';
        } else {
            pricingFields.style.display = 'none';
        }
    };

    window.openKbModal = function(rule = null) {
        if (!kbModalOverlay) return;
        kbModalOverlay.classList.add('open');
        if (rule) {
            document.getElementById('kb-modal-title').textContent = 'Edit KB Rule';
            document.getElementById('kb-rule-id').value = rule._id;
            document.getElementById('kb-category').value = rule.category;
            document.getElementById('kb-question').value = rule.question;
            document.getElementById('kb-answer').value = rule.answer;
            document.getElementById('kb-keywords').value = rule.keywords ? rule.keywords.join(', ') : '';
            
            togglePricingFields(rule.category);
            if (rule.category === 'pricing') {
                document.getElementById('kb-proc-name').value = rule.procedure_name || '';
                document.getElementById('kb-start-price').value = rule.starting_price || '';
                document.getElementById('kb-proc-notes').value = rule.notes || '';
            }
        } else {
            document.getElementById('kb-modal-title').textContent = 'Add KB Rule';
            if (kbRuleForm) kbRuleForm.reset();
            document.getElementById('kb-rule-id').value = '';
            togglePricingFields('general');
        }
    };

    window.closeKbModal = function() {
        if (kbModalOverlay) kbModalOverlay.classList.remove('open');
    };

    if (btnAddKbRule) btnAddKbRule.addEventListener('click', () => openKbModal());
    if (kbModalClose) kbModalClose.addEventListener('click', closeKbModal);
    if (btnCancelKbModal) btnCancelKbModal.addEventListener('click', closeKbModal);

    // Add / Edit Form Submit
    window.handleKbFormSubmit = async function(event) {
        event.preventDefault();
        
        const id = document.getElementById('kb-rule-id').value;
        const category = document.getElementById('kb-category').value;
        const question = document.getElementById('kb-question').value.trim();
        const answer = document.getElementById('kb-answer').value.trim();
        const keywords = document.getElementById('kb-keywords').value.trim();
        
        const payload = {
            category,
            question,
            answer,
            keywords
        };
        
        if (id) payload.id = id;
        
        if (category === 'pricing') {
            payload.procedure_name = document.getElementById('kb-proc-name').value.trim();
            payload.starting_price = document.getElementById('kb-start-price').value.trim();
            payload.notes = document.getElementById('kb-proc-notes').value.trim();
        }

        try {
            const resp = await fetch('/api/voice-agent/api/kb/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(payload)
            });
            const data = await resp.json();
            if (data.success) {
                closeKbModal();
                loadKbRules();  // reload rules
            } else {
                alert('Failed to save KB rule: ' + data.error);
            }
        } catch (err) {
            console.error(err);
            alert('Error saving KB rule.');
        }
    };

    // Edit Rule
    window.editKbRule = function(id) {
        const rule = kbRules.find(r => r._id === id);
        if (rule) openKbModal(rule);
    };

    // Delete Rule
    window.deleteKbRule = async function(id) {
        if (!confirm('Are you sure you want to delete this Knowledge Base rule?')) return;
        
        try {
            const resp = await fetch(`/api/voice-agent/api/kb/${id}/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await resp.json();
            if (data.success) {
                loadKbRules();
            } else {
                alert('Failed to delete rule: ' + data.error);
            }
        } catch (err) {
            console.error(err);
            alert('Error deleting KB rule.');
        }
    };

    // ── System Prompts Management Logic ─────────────────────────────────────
    const promptInboundText = document.getElementById('prompt-inbound-text');
    const promptOutboundText = document.getElementById('prompt-outbound-text');

    async function loadSystemPrompts() {
        if (promptInboundText) promptInboundText.placeholder = "Loading system prompt from MongoDB...";
        if (promptOutboundText) promptOutboundText.placeholder = "Loading system prompt from MongoDB...";
        
        try {
            const resp = await fetch('/api/voice-agent/api/prompts/');
            const result = await resp.json();
            if (result.success) {
                if (promptInboundText) promptInboundText.value = result.prompts.inbound;
                if (promptOutboundText) promptOutboundText.value = result.prompts.outbound;
            } else {
                alert('Failed to load system prompts: ' + result.error);
            }
        } catch (err) {
            console.error(err);
            alert('Error loading prompts.');
        }
    }

    window.savePrompt = async function(type) {
        const textVal = type === 'inbound' ? promptInboundText.value : promptOutboundText.value;
        
        if (!confirm(`Are you sure you want to save modifications to the ${type.toUpperCase()} prompt?`)) return;
        
        try {
            const resp = await fetch('/api/voice-agent/api/prompts/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    prompt_type: type,
                    prompt_text: textVal
                })
            });
            const data = await resp.json();
            if (data.success) {
                alert(`Success: ${type.capitalize()} prompt updated successfully!`);
            } else {
                alert('Failed to save prompt: ' + data.error);
            }
        } catch (err) {
            console.error(err);
            alert('Error saving system prompt.');
        }
    };
    
    // Capitalize Helper
    String.prototype.capitalize = function() {
        return this.charAt(0).toUpperCase() + this.slice(1);
    }

    // Campaign Filter Tabs
    const filterTabs = document.querySelectorAll('.filter-tab');
    const callRows = document.querySelectorAll('.call-row-item');

    filterTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            filterTabs.forEach(el => el.classList.remove('active'));
            tab.classList.add('active');
            
            const filter = tab.getAttribute('data-filter');
            
            callRows.forEach(row => {
                const dir = row.getAttribute('data-direction');
                if (filter === 'all') {
                    row.style.display = 'table-row';
                } else if (filter === 'inbound' && dir === 'inbound') {
                    row.style.display = 'table-row';
                } else if (filter === 'outbound' && dir === 'outbound') {
                    row.style.display = 'table-row';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    });

    // Custom Transcript Toggle
    const toggleBtn = document.getElementById('toggle-transcript-btn');
    const bubblesContainer = document.getElementById('modal-transcript-bubbles');
    toggleBtn.addEventListener('click', () => {
        const isCollapsed = bubblesContainer.classList.toggle('collapsed');
        toggleBtn.classList.toggle('collapsed');
        toggleBtn.querySelector('span').textContent = isCollapsed ? 'Show transcript' : 'Hide transcript';
    });

    // Custom Audio Player State
    const hiddenPlayer = document.getElementById('hidden-player');
    const customPlayBtn = document.getElementById('custom-play-btn');
    const customTimeline = document.getElementById('custom-timeline');
    const customProgress = document.getElementById('custom-progress');
    const customTimeLabel = document.getElementById('custom-time-label');

    customPlayBtn.addEventListener('click', () => {
        if (!hiddenPlayer.src) return;
        if (hiddenPlayer.paused) {
            hiddenPlayer.play();
            customPlayBtn.innerHTML = '<svg viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>';
        } else {
            hiddenPlayer.pause();
            customPlayBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>';
        }
    });

    hiddenPlayer.addEventListener('timeupdate', () => {
        if (!hiddenPlayer.duration) return;
        const progressPercentage = (hiddenPlayer.currentTime / hiddenPlayer.duration) * 100;
        customProgress.style.width = `${progressPercentage}%`;
        
        const curMin = Math.floor(hiddenPlayer.currentTime / 60);
        const curSec = Math.floor(hiddenPlayer.currentTime % 60).toString().padStart(2, '0');
        const totMin = Math.floor(hiddenPlayer.duration / 60);
        const totSec = Math.floor(hiddenPlayer.duration % 60).toString().padStart(2, '0');
        
        customTimeLabel.textContent = `${curMin}:${curSec} / ${totMin}:${totSec}`;
    });

    customTimeline.addEventListener('click', (e) => {
        if (!hiddenPlayer.duration) return;
        const rect = customTimeline.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const clickPercentage = clickX / rect.width;
        hiddenPlayer.currentTime = clickPercentage * hiddenPlayer.duration;
    });

    // Transcript String Parser
    function parseTranscriptToTurns(text, turns) {
        if (turns && turns.length > 0) return turns;
        if (!text) return [];
        
        const lines = text.split('\n');
        const parsed = [];
        for (let line of lines) {
            line = line.trim();
            if (!line) continue;
            
            if (line.startsWith('Agent:')) {
                parsed.push({speaker: 'agent', text: line.replace('Agent:', '').trim()});
            } else if (line.startsWith('Alice:')) {
                parsed.push({speaker: 'agent', text: line.replace('Alice:', '').trim()});
            } else if (line.startsWith('Dentina:')) {
                parsed.push({speaker: 'agent', text: line.replace('Dentina:', '').trim()});
            } else if (line.startsWith('Candidate:')) {
                parsed.push({speaker: 'candidate', text: line.replace('Candidate:', '').trim()});
            } else if (line.startsWith('Patient:')) {
                parsed.push({speaker: 'candidate', text: line.replace('Patient:', '').trim()});
            } else if (line.startsWith('Human:')) {
                parsed.push({speaker: 'candidate', text: line.replace('Human:', '').trim()});
            } else if (line.includes(':')) {
                const idx = line.indexOf(':');
                const speaker = line.slice(0, idx).trim().toLowerCase();
                const content = line.slice(idx + 1).trim();
                if (speaker.includes('agent') || speaker.includes('alice') || speaker.includes('dentina') || speaker.includes('ai')) {
                    parsed.push({speaker: 'agent', text: content});
                } else {
                    parsed.push({speaker: 'candidate', text: content});
                }
            } else {
                parsed.push({speaker: 'candidate', text: line});
            }
        }
        return parsed;
    }

    // Modal Details Fetcher
    const overlay = document.getElementById('call-details-overlay');
    const modalPatientName = document.getElementById('modal-patient-name');
    const modalPatientPhone = document.getElementById('modal-patient-phone');
    const modalPatientStatus = document.getElementById('modal-patient-status');
    const modalAttemptLabel = document.getElementById('modal-attempt-label');
    const modalAttemptTime = document.getElementById('modal-attempt-time');
    const modalDirectionBadge = document.getElementById('modal-direction-badge');
    const statSentiment = document.getElementById('stat-sentiment');
    const statInteracted = document.getElementById('stat-interacted');
    const statScheduled = document.getElementById('stat-scheduled');
    const statNewPatient = document.getElementById('stat-newpatient');
    const modalAiInsight = document.getElementById('modal-ai-insight');
    const customOpenTab = document.getElementById('custom-open-tab');

    async function openCallModal(callSid) {
        bubblesContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 1rem;">Loading transcription turns...</div>';
        overlay.classList.add('open');
        
        // Reset player UI
        hiddenPlayer.pause();
        hiddenPlayer.src = '';
        customPlayBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>';
        customProgress.style.width = '0%';
        customTimeLabel.textContent = '0:00 / 0:00';
        
        try {
            const resp = await fetch(`/api/voice-agent/api/calls/${callSid}/`);
            const data = await resp.json();
            
            if (data.success) {
                const call = data.call;
                
                // Prefill details
                modalPatientName.textContent = call.phone_number;
                modalPatientPhone.textContent = `📞 ${call.phone_number}`;
                modalPatientStatus.textContent = call.call_status.toUpperCase();
                modalAttemptLabel.textContent = `Attempt 1 of 1`;
                
                if (call.call_date) {
                    modalAttemptTime.textContent = new Date(call.call_date).toLocaleString();
                } else {
                    modalAttemptTime.textContent = 'Recent Call';
                }
                
                // Direction badge
                modalDirectionBadge.textContent = call.direction.toUpperCase();
                modalDirectionBadge.className = `badge ${call.direction === 'inbound' ? 'badge-inbound' : 'badge-outbound'}`;
                
                // Grid stats
                statSentiment.textContent = call.sentiment.toUpperCase();
                statSentiment.className = `grid-stat-val ${call.sentiment === 'positive' ? '' : (call.sentiment === 'negative' ? 'danger' : 'neutral')}`;
                
                // Deduce interacted/scheduled
                const interacted = call.call_duration > 5 ? 'Yes' : 'No';
                statInteracted.textContent = interacted;
                
                const apptMatch = call.conversation_summary.toLowerCase().includes('book') || call.conversation_summary.toLowerCase().includes('schedul');
                const scheduled = apptMatch ? 'Yes' : 'No';
                statScheduled.textContent = scheduled;
                
                statNewPatient.textContent = call.direction === 'inbound' ? 'Yes' : 'No';
                
                // AI Insight text
                modalAiInsight.textContent = call.conversation_summary || 'No AI insight summary available for this call attempt.';
                
                // Set audio player source
                if (call.call_recording_url) {
                    hiddenPlayer.src = call.call_recording_url;
                    customOpenTab.href = call.call_recording_url;
                    customOpenTab.style.display = 'flex';
                } else {
                    customOpenTab.style.display = 'none';
                }

                // Render turns
                const turns = parseTranscriptToTurns(call.transcript, call.turns);
                bubblesContainer.innerHTML = '';
                
                if (turns.length > 0) {
                    turns.forEach(turn => {
                        const isAgent = turn.speaker === 'agent';
                        const bubble = document.createElement('div');
                        bubble.className = `bubble-turn ${isAgent ? 'bubble-agent' : 'bubble-customer'}`;
                        bubble.innerHTML = `
                            <div class="bubble-speaker ${isAgent ? 'bubble-speaker-agent' : 'bubble-speaker-customer'}">
                                ${isAgent ? 'AGENT' : 'CUSTOMER'}
                            </div>
                            <div>${turn.text}</div>
                        `;
                        bubblesContainer.appendChild(bubble);
                    });
                } else {
                    bubblesContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); font-size: 0.7rem; padding: 1rem;">No speech turns transcribed.</div>';
                }
            } else {
                bubblesContainer.innerHTML = `<div style="color: var(--danger); text-align: center; padding: 1rem;">Failed: ${data.error}</div>`;
            }
        } catch (err) {
            bubblesContainer.innerHTML = `<div style="color: var(--danger); text-align: center; padding: 1rem;">Error rendering: ${err.message}</div>`;
        }
    }

    function closeCallModal() {
        overlay.classList.remove('open');
        hiddenPlayer.pause();
    }

    // Twilio Web Dialer Logic (Simulator)
    let device = null;
    let activeCall = null;
    let initialized = false;

    const simStartBtn = document.getElementById('sim-start-btn');
    const simStopBtn = document.getElementById('sim-stop-btn');
    const simConsole = document.getElementById('sim-console');
    const simStatusText = document.getElementById('sim-status-text');
    const simStatusBox = document.getElementById('sim-status-box');

    function logSim(msg) {
        const time = new Date().toLocaleTimeString();
        simConsole.innerHTML = `<div><span style="color:var(--primary);">[${time}]</span> ${msg}</div>` + simConsole.innerHTML;
    }

    async function initDevice() {
        if (initialized) return true;
        logSim("Init Twilio WebRTC Device...");
        return new Promise((resolve) => {
            fetch('/api/voice-agent/twilio/token/')
                .then(r => r.json())
                .then(data => {
                    if (!data.success || !data.token) {
                        logSim("❌ Config Error: " + (data.error || "Missing Twilio voice SDK token. Check credentials."));
                        resetSimUI();
                        resolve(false);
                        return;
                    }
                    device = new Twilio.Device(data.token, { codecPreferences: ['opus', 'pcmu'] });
                    
                    device.on('registered', () => {
                        logSim("Device registered successfully.");
                        initialized = true;
                        resolve(true);
                    });

                    device.on('error', (err) => {
                        logSim("Device Error: " + err.message + " (Code: " + err.code + ")");
                        initialized = false;
                        resetSimUI();
                        resolve(false);
                    });
                    
                    device.register();
                })
                .catch(err => {
                    logSim("Device Init Error: " + err.message);
                    resolve(false);
                });
        });
    }

    simStartBtn.addEventListener('click', async () => {
        const phone = document.getElementById('sim-phone-id').value.trim();
        if (!phone) {
            alert("Simulated Phone is required.");
            return;
        }

        const success = await initDevice();
        if (!success) return;

        simStatusText.textContent = "Initiating...";
        simStatusBox.className = "dialer-status calling";
        simStartBtn.disabled = true;
        logSim("Connecting dialer to Alice...");

        try {
            activeCall = await device.connect({
                from: phone,
                direction: 'inbound',
                name: 'Test Patient'
            });

            simStartBtn.style.display = 'none';
            simStopBtn.style.display = 'block';
            simStatusText.textContent = "Connecting...";
            logSim("Outgoing connection request created.");

            activeCall.on('accept', () => {
                logSim("Call established with Voicebot.");
                simStatusText.textContent = "Call Active (Inbound)";
                simStatusBox.className = "dialer-status calling";
            });

            activeCall.on('disconnect', () => {
                logSim("Call finished.");
                resetSimUI();
            });

            activeCall.on('error', (err) => {
                logSim("Call Error: " + err.message);
                resetSimUI();
            });
        } catch (err) {
            logSim("Error: " + err.message);
            resetSimUI();
        }
    });

    simStopBtn.addEventListener('click', () => {
        if (activeCall) activeCall.disconnect();
    });

    function resetSimUI() {
        simStartBtn.style.display = 'block';
        simStartBtn.disabled = false;
        simStopBtn.style.display = 'none';
        simStatusText.textContent = "Ready to Simulator";
        simStatusBox.className = "dialer-status ready";
    }

    // Outbound Call Trigger
    const outboundTriggerBtn = document.getElementById('outbound-trigger-btn');
    outboundTriggerBtn.addEventListener('click', async () => {
        const phone = document.getElementById('outbound-phone-val').value.trim();
        const name = document.getElementById('outbound-name-val').value.trim();
        const apptType = document.getElementById('outbound-appt-val').value;

        if (!phone) {
            alert("Phone number is required.");
            return;
        }

        outboundTriggerBtn.disabled = true;
        logSim(`Triggering outbound patient call to ${phone}...`);

        try {
            const resp = await fetch('/api/voice-agent/twilio/make-call/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: phone,
                    customerName: name || 'Patient',
                    appointment_type: apptType
                })
            });
            const data = await resp.json();
            if (data.success) {
                logSim(`✅ Outbound Call placed! SID: ${data.call_sid}`);
            } else {
                logSim(`❌ Failed outbound: ${data.error}`);
            }
        } catch (err) {
            logSim(`Error: ${err.message}`);
        } finally {
            outboundTriggerBtn.disabled = false;
        }
    });

    // Slide-out Drawer Control
    const drawerOverlay = document.getElementById('about-drawer-overlay');
    const systemDrawer = document.getElementById('about-system-drawer');
    const drawerTrigger = document.getElementById('about-drawer-trigger');
    const drawerClose = document.getElementById('about-drawer-close');

    function openDrawer() {
        drawerOverlay.classList.add('open');
        systemDrawer.classList.add('open');
    }

    function closeDrawer() {
        drawerOverlay.classList.remove('open');
        systemDrawer.classList.remove('open');
    }

    if (drawerTrigger) drawerTrigger.addEventListener('click', openDrawer);
    if (drawerClose) drawerClose.addEventListener('click', closeDrawer);
    if (drawerOverlay) drawerOverlay.addEventListener('click', closeDrawer);

    // Manual Booking Sync Actions
    window.updateBooking = async function(patientId, status) {
        if (!confirm(`Are you sure you want to mark this booking as ${status}?`)) return;
        
        try {
            const resp = await fetch('/api/voice-agent/api/booking/update/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ patient_id: patientId, status: status })
            });
            const data = await resp.json();
            if (data.success) {
                // Update badge text and colors
                const statusSpan = document.getElementById('status-' + patientId);
                if (statusSpan) {
                    statusSpan.textContent = status;
                    statusSpan.className = `badge ${status === 'confirmed' ? 'badge-completed' : 'badge-failed'}`;
                }
                
                // Hide actions container
                const actionsTd = document.getElementById('actions-' + patientId);
                if (actionsTd) {
                    actionsTd.innerHTML = '';
                }
            } else {
                alert('Error updating booking status: ' + data.error);
            }
        } catch(e) {
            console.error(e);
            alert('Booking update request failed.');
        }
    };
    
    // Cookie Helper for CSRF
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
